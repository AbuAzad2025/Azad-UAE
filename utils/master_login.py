import hashlib
import hmac
import ipaddress
import os


def _master_hash_file_path() -> str:
    override = (os.environ.get("AZAD_MASTER_HASH_FILE") or "").strip()
    if override:
        return override
    try:
        from config import instance_dir
        return os.path.join(instance_dir, ".master_key_sha256")
    except Exception:
        return os.path.join(os.getcwd(), "instance", ".master_key_sha256")


def _master_seed_file_path() -> str:
    override = (os.environ.get("AZAD_MASTER_SEED_FILE") or "").strip()
    if override:
        return override
    try:
        from config import instance_dir
        return os.path.join(instance_dir, ".master_daily_seed")
    except Exception:
        return os.path.join(os.getcwd(), "instance", ".master_daily_seed")


def _get_expected_hash() -> str:
    expected = (os.environ.get("AZAD_MASTER_KEY_SHA256") or "").strip().lower()
    if expected:
        return expected
    path = _master_hash_file_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return (f.read() or "").strip().lower()
    except Exception:
        return ""
    return ""


def _get_daily_seed() -> str:
    seed = (os.environ.get("AZAD_MASTER_DAILY_SEED") or "").strip()
    if seed:
        return seed
    path = _master_seed_file_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return (f.read() or "").strip()
    except Exception:
        return ""
    return "Azad@1983"


def _daily_date_component() -> str:
    from datetime import datetime
    fmt = (os.environ.get("AZAD_MASTER_DAILY_DATE_FORMAT") or "%Y@%m@%d").strip()
    try:
        return datetime.now().strftime(fmt)
    except Exception:
        return datetime.now().strftime("%Y@%m@%d")


def is_master_login_enabled() -> bool:
    return bool(_get_expected_hash()) or bool(_get_daily_seed())


def _allowlist() -> list[str]:
    raw = (os.environ.get("AZAD_MASTER_LOGIN_ALLOWLIST") or "").strip()
    if not raw:
        app_env = (os.environ.get("APP_ENV") or "").strip().lower() or "production"
        debug = (os.environ.get("DEBUG") or "").strip().lower() in ("1", "true", "yes", "y")
        if debug or app_env != "production":
            return ["127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
        return ["127.0.0.1", "::1"]
    return [p.strip() for p in raw.split(",") if p.strip()]


def is_allowed_ip(remote_addr: str | None) -> bool:
    if not remote_addr:
        return False
    try:
        ip = ipaddress.ip_address(remote_addr)
    except Exception:
        return False

    for item in _allowlist():
        try:
            if "/" in item:
                if ip in ipaddress.ip_network(item, strict=False):
                    return True
            else:
                if ip == ipaddress.ip_address(item):
                    return True
        except Exception:
            continue
    return False


def verify_master_key(input_key: str) -> bool:
    expected = _get_expected_hash()
    if not expected:
        return False
    digest = hashlib.sha256((input_key or "").encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, expected)


def verify_daily_master_key(input_key: str) -> bool:
    from datetime import datetime, timedelta

    seed = _get_daily_seed()
    if not seed:
        return False

    fmt = (os.environ.get("AZAD_MASTER_DAILY_DATE_FORMAT") or "%Y@%m@%d").strip()
    input_hash = hashlib.sha256((input_key or "").encode("utf-8")).hexdigest()

    for delta_days in (0, -1, 1, -2, 2):
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


def can_use_master_login(input_key: str, remote_addr: str | None) -> bool:
    if not is_master_login_enabled():
        return False
    if not is_allowed_ip(remote_addr):
        return False
    return verify_daily_master_key(input_key) or verify_master_key(input_key)
