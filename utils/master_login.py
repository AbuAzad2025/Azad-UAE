"""
Break-glass master login for platform owner accounts.

The ONLY master-key mechanism is the daily key:

    login key  =  {seed}@{YYYY}@{MM}@{DD}

where {seed} is AZAD_MASTER_DAILY_SEED (env) or the first-run generated
seed persisted to instance/.master_daily_seed, and {YYYY}@{MM}@{DD} is the
current day (AZAD_MASTER_DAILY_DATE_FORMAT, default "%Y@%m@%d").

The key rotates every day automatically; there is intentionally NO static
hash fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# In-memory rate-limit tracker: {ip: [(timestamp, count)]}
_attempt_tracker: dict[str, list] = {}


def _master_seed_file_path() -> str:
    override = (os.environ.get("AZAD_MASTER_SEED_FILE") or "").strip()
    if override:
        return override
    try:
        from config import instance_dir

        return os.path.join(instance_dir, ".master_daily_seed")
    except Exception:
        return os.path.join(os.getcwd(), "instance", ".master_daily_seed")


def _ensure_master_daily_seed() -> str:
    """Return the daily master-key seed, generating + persisting it on first run.

    First-run behaviour: if no seed is configured via env/file, generate a
    strong random seed and persist it to ``instance/.master_daily_seed``.
    The break-glass daily key is then always ``{seed}@{YYYY}@{MM}@{DD}``,
    computed at request time — it rotates every day without any manual input.
    """
    seed = (os.environ.get("AZAD_MASTER_DAILY_SEED") or "").strip()
    if seed:
        return seed

    path = _master_seed_file_path()
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                stored = (f.read() or "").strip()
                if stored:
                    return stored
    except OSError:
        pass

    import secrets as _secrets

    generated = _secrets.token_hex(16)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(generated)
        logger.info("Generated daily master seed at %s", path)
    except OSError as exc:
        logger.warning("Could not persist master daily seed to %s: %s", path, exc)
    return generated


def _master_login_disabled() -> bool:
    return (os.environ.get("AZAD_MASTER_LOGIN_DISABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _is_production() -> bool:
    app_env = (os.environ.get("APP_ENV") or "production").strip().lower()
    debug = (os.environ.get("DEBUG") or "").strip().lower() in ("1", "true", "yes", "y")
    return app_env == "production" and not debug


def _seed_source() -> tuple[str, str]:
    """Return (seed, source) where source is env|file|generated|missing|disabled.

    First-run in NON-production: if no env seed and no persisted seed file
    exists, a strong random seed is generated and persisted automatically so
    the daily master key is always buildable for local/dev/test tenants.

    Production REQUIRES an explicit seed (env AZAD_MASTER_DAILY_SEED or a
    pre-seeded file) — it deliberately never auto-generates, so the platform
    owner controls the seed before any tenant starts.
    """
    if _master_login_disabled():
        return "", "disabled"

    seed = (os.environ.get("AZAD_MASTER_DAILY_SEED") or "").strip()
    if seed:
        return seed, "env"

    path = _master_seed_file_path()
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                stored = (f.read() or "").strip()
                if stored:
                    return stored, "file"
    except OSError:
        logger.warning("Could not read master daily seed file: %s", path)

    if _is_production():
        return "", "missing"

    generated = _ensure_master_daily_seed()
    if generated:
        return generated, "generated"

    return "", "missing"


def _get_daily_seed() -> str:
    seed, _source = _seed_source()
    return seed


def _daily_date_format() -> str:
    return (os.environ.get("AZAD_MASTER_DAILY_DATE_FORMAT") or "%Y@%m@%d").strip()


def is_master_login_enabled() -> bool:
    """Master login active only when a daily seed is configured.

    Daily-seed only: there is intentionally NO static-hash fallback. The break-glass
    key is always ``{AZAD_MASTER_DAILY_SEED}@{YYYY}@{MM}@{DD}`` and rotates daily.
    """
    if _master_login_disabled():
        return False
    seed, source = _seed_source()
    return bool(seed) and (source in ("env", "file"))


def _allowlist() -> list[str]:
    raw = (os.environ.get("AZAD_MASTER_LOGIN_ALLOWLIST") or "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    if not _is_production():
        return ["127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    return ["127.0.0.1", "::1"]


def is_allowed_ip(remote_addr: str | None) -> bool:
    if not remote_addr:
        return False
    try:
        ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False

    for item in _allowlist():
        try:
            if "/" in item:
                if ip in ipaddress.ip_network(item, strict=False):
                    return True
            elif ip == ipaddress.ip_address(item):
                return True
        except ValueError:
            logger.warning("Ignoring invalid master-login IP allowlist entry: %r", item)
            continue
    return False


def _check_rate_limit(remote_addr: str | None, max_attempts: int = 3, window_hours: int = 1) -> bool:
    """Return True if attempt is allowed, False if rate-limited."""
    if not remote_addr:
        return False
    now = datetime.now()
    cutoff = now - timedelta(hours=window_hours)
    history = _attempt_tracker.get(remote_addr, [])
    # prune old entries
    history = [t for t in history if t > cutoff]
    _attempt_tracker[remote_addr] = history
    return len(history) < max_attempts


def _record_attempt(remote_addr: str | None) -> None:
    if not remote_addr:
        return
    now = datetime.now()
    _attempt_tracker.setdefault(remote_addr, []).append(now)


def _get_max_attempts_from_config() -> int:
    try:
        from config import Config

        return getattr(Config, "MASTER_LOGIN_MAX_ATTEMPTS", 3)
    except Exception:
        return 3


def verify_daily_master_key(input_key: str) -> bool:
    seed = _get_daily_seed()
    if not seed:
        return False

    fmt = _daily_date_format()
    input_hash = hashlib.sha256((input_key or "").encode("utf-8")).hexdigest()

    for delta_days in (0, -1, 1):
        day = datetime.now() + timedelta(days=delta_days)
        try:
            date_part = day.strftime(fmt)
        except Exception:
            date_part = day.strftime("%Y@%m@%d")
        expected_clear = f"{seed}@{date_part}"
        expected_hash = hashlib.sha256(expected_clear.encode("utf-8")).hexdigest()
        if hmac.compare_digest(input_hash, expected_hash):
            return True
    return False


def build_today_master_cleartext(for_date: datetime | None = None) -> str:
    """Today's break-glass password string (for owner tooling / offline scripts)."""
    seed, source = _seed_source()
    if not seed:
        if _is_production() and source == "missing":
            raise RuntimeError("AZAD_MASTER_DAILY_SEED is required in production when master login is enabled.")
        raise RuntimeError("Master daily seed is not configured.")
    day = for_date or datetime.now()
    fmt = _daily_date_format()
    try:
        date_part = day.strftime(fmt)
    except Exception:
        date_part = day.strftime("%Y@%m@%d")
    return f"{seed}@{date_part}"


def master_login_status() -> dict:
    """Non-secret status for owner diagnostics."""
    seed, seed_source = _seed_source()
    return {
        "enabled": is_master_login_enabled(),
        "disabled_explicitly": _master_login_disabled(),
        "seed_source": seed_source,
        "seed_configured": bool(seed),
        "allowlist": _allowlist(),
        "date_format": _daily_date_format(),
        "production": _is_production(),
    }


def _log_security_alert(remote_addr: str | None, username: str, method: str) -> None:
    try:
        from extensions import db
        from models.security_alert import SecurityAlert

        alert = SecurityAlert(
            alert_type="master_login",
            severity="critical",
            title="Master login used",
            description=f"Master login succeeded via {method} from {remote_addr}",
            ip_address=remote_addr,
            username=username,
        )
        db.session.add(alert)
        db.session.flush()
    except Exception as exc:
        logger.warning("Failed to write SecurityAlert for master login: %s", exc)


def _log_audit_log(remote_addr: str | None, username: str, method: str) -> None:
    try:
        from services.logging_core import LoggingCore

        LoggingCore.log_audit(
            action="master_login_success",
            table_name="auth",
            record_id=None,
            changes={
                "ip": remote_addr,
                "username": username,
                "method": method,
            },
        )
    except Exception as exc:
        logger.warning("Failed to write AuditLog for master login: %s", exc)


def try_master_login(input_key: str, remote_addr: str | None, username: str = "") -> tuple[bool, dict]:
    """
    Attempt master login. Returns (success, audit_metadata).
    Never include secrets in metadata.
    """
    meta: dict = {
        "success": False,
        "method": None,
        "seed_source": _seed_source()[1],
        "reason": None,
    }

    if not is_master_login_enabled():
        meta["reason"] = "disabled"
        return False, meta

    if not is_allowed_ip(remote_addr):
        meta["reason"] = "ip_denied"
        logger.warning(
            "Master login blocked: IP not allowlisted (%s) user=%s",
            remote_addr,
            username,
        )
        _record_attempt(remote_addr)
        return False, meta

    max_attempts = _get_max_attempts_from_config()
    if not _check_rate_limit(remote_addr, max_attempts=max_attempts):
        meta["reason"] = "rate_limited"
        logger.warning(
            "Master login blocked: rate limit exceeded (%s) user=%s",
            remote_addr,
            username,
        )
        return False, meta

    if verify_daily_master_key(input_key):
        meta["success"] = True
        meta["method"] = "daily"
        _log_security_alert(remote_addr, username, "daily")
        _log_audit_log(remote_addr, username, "daily")
        return True, meta

    _record_attempt(remote_addr)
    meta["reason"] = "invalid"
    logger.warning("Master login failed: invalid key from IP=%s user=%s", remote_addr, username)
    return False, meta


def can_use_master_login(input_key: str, remote_addr: str | None) -> bool:
    ok, _meta = try_master_login(input_key, remote_addr)
    return ok
