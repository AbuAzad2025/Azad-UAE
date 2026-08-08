"""Structured JSON telemetry logger — observability only.

One JSON object per event, written as JSONL to ``instance/telemetry.jsonl``
(instance dir resolved the same way as ``utils/telemetry.py``: project root's
``instance/`` folder, but its own filename — never the anti-piracy sink).

Design contract:
  * Context travels via ``contextvars`` (NOT ``flask.g``) so events emitted
    from background threads or CLI code still carry tenant/user/request data.
    The app factory's ``before_request`` hook bridges request values into the
    contextvars via :func:`bind_context`.
  * Zero console noise in tests: when ``app.testing`` is set or pytest is
    running, only a ``NullHandler`` is attached. The module logger never
    propagates to the root logger, and starts with a NullHandler even before
    :func:`init_telemetry` runs.
  * Unified error stream: every event is also bridged into the DB-backed
    ErrorAuditLog via LoggingCore (owner page /owner/error-audit-logs) unless
    the caller passes ``_bridge=False`` — see the bridge section below for
    the safety contract. Under pytest the bridge is opt-in only.
  * Never mutates business logic, never swallows business exceptions, never
    changes control flow — it only emits.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

TELEMETRY_LOGGER_NAME = "azad.telemetry"
TELEMETRY_FILENAME = "telemetry.jsonl"

CATEGORY_SOFTWARE_EXCEPTION = "SOFTWARE_EXCEPTION"
CATEGORY_CRITICAL_FINANCIAL = "CRITICAL_FINANCIAL"
CATEGORY_SECURITY_ALERT = "SECURITY_ALERT"
CATEGORY_HARDWARE_WARN = "HARDWARE_WARN"

_BASEDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_INSTANCE_DIR = os.path.join(_BASEDIR, "instance")

_CONTEXT_FIELDS = (
    "tenant_id",
    "user_id",
    "request_id",
    "ip",
    "endpoint",
    "method",
    "duration_ms",
    "request_start",
)

_ctx: dict[str, contextvars.ContextVar] = {
    field: contextvars.ContextVar(f"telemetry_{field}", default=None) for field in _CONTEXT_FIELDS
}

_levels = logging.getLevelNamesMapping() if hasattr(logging, "getLevelNamesMapping") else {}


def _telemetry_sink_path() -> str:
    os.makedirs(_INSTANCE_DIR, exist_ok=True)
    return os.path.join(_INSTANCE_DIR, TELEMETRY_FILENAME)


class _TelemetryEventFormatter(logging.Formatter):
    """One JSON object per telemetry event, merging bound context + extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "telemetry_event", None) or {}
        explicit = payload.get("explicit") or {}
        extras = payload.get("extras") or {}

        duration_ms = explicit.get("duration_ms")
        if duration_ms is None:
            duration_ms = _ctx["duration_ms"].get()
        if duration_ms is None:
            start = _ctx["request_start"].get()
            if start is not None:
                import time

                duration_ms = round((time.monotonic() - float(start)) * 1000, 2)

        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "category": payload.get("category"),
            "message": record.getMessage(),
            "tenant_id": _resolve(explicit, "tenant_id"),
            "user_id": _resolve(explicit, "user_id"),
            "request_id": _resolve(explicit, "request_id"),
            "ip": _resolve(explicit, "ip"),
            "endpoint": _resolve(explicit, "endpoint"),
            "method": _resolve(explicit, "method"),
            "duration_ms": duration_ms,
        }
        for key, value in extras.items():
            if key not in entry:
                entry[key] = value
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "traceback": self.formatException(record.exc_info),
            }
        return json.dumps(entry, ensure_ascii=False, default=str)


def _resolve(explicit: dict, field: str):
    value = explicit.get(field)
    if value is not None:
        return value
    return _ctx[field].get()


def bind_context(**fields) -> None:
    """Bind request/thread values into the telemetry contextvars."""
    for field, value in fields.items():
        var = _ctx.get(field)
        if var is not None:
            var.set(value)


def clear_context() -> None:
    """Reset every telemetry contextvar (request teardown / test isolation)."""
    for var in _ctx.values():
        var.set(None)


def _get_logger() -> logging.Logger:
    log = logging.getLogger(TELEMETRY_LOGGER_NAME)
    log.propagate = False
    return log


# Silence-by-default: even before init_telemetry runs, emits go nowhere.
_get_logger().addHandler(logging.NullHandler())


# ── Unified DB error-log bridge ──────────────────────────────────
# Every telemetry event ALSO persists into the DB-backed ErrorAuditLog via
# LoggingCore, so anomalies (frontend JS crashes, unbalanced GL, cross-tenant
# attempts, hardware agent failures) surface on the owner page
# /owner/error-audit-logs under their own categories, with fingerprint dedup.
#
# Safety contract (verified against services/logging_core.py):
#   * LoggingCore._persist_error writes through its own raw
#     ``db.engine.connect()`` + ``conn.commit()`` and NEVER touches
#     ``db.session`` — so bridging mid-transaction is safe: the error row
#     survives a business rollback, and the bridge can never flush or commit
#     pending business data.
#   * The bridge never raises into business flow (try/except) and never
#     recurses (``_in_bridge`` guard).
#   * Under pytest the bridge stays OFF unless a test opts in explicitly via
#     :func:`enable_error_log_bridge` — mirroring the NullHandler testing
#     guard, so suite runs never write error-log rows by accident.

_in_bridge: contextvars.ContextVar = contextvars.ContextVar("telemetry_in_bridge", default=False)
_bridge_opt_in: contextvars.ContextVar = contextvars.ContextVar("telemetry_bridge_opt_in", default=False)

# Default DB level per anomaly category. An explicitly passed level (threaded
# through ``_bridge_level`` by the helpers) always wins over this table.
_BRIDGE_LEVEL_BY_CATEGORY = {
    CATEGORY_CRITICAL_FINANCIAL: "CRITICAL",
    CATEGORY_SECURITY_ALERT: "ERROR",
    CATEGORY_HARDWARE_WARN: "WARNING",
}


@contextlib.contextmanager
def enable_error_log_bridge():
    """Opt the current context into the DB error-log bridge (test-only switch).

    Production bridges by default; under pytest the bridge is silent unless
    the emitting section is wrapped in this context manager.
    """
    token = _bridge_opt_in.set(True)
    try:
        yield
    finally:
        _bridge_opt_in.reset(token)


def _bridge_allowed() -> bool:
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return _bridge_opt_in.get()


def _bridge_to_error_log(category, message, *, event_level, bridge_level, exception, explicit, extras):
    """Forward one telemetry event into LoggingCore.log_error. Never raises.

    Mapping: category passes through as-is (owner page shows the telemetry
    categories distinctly); level falls back to the category table when the
    emitter did not pass an explicit level; ``source``/``stack``/``url`` come
    from extras (frontend events arrive with ``source="frontend"``); context
    ids resolve explicit-first so emitters running outside requests — or for
    another tenant — still win over whatever the request context would say.
    """
    if _in_bridge.get() or not _bridge_allowed():
        return
    token = _in_bridge.set(True)
    try:
        from services.logging_core import LoggingCore

        payload = dict(extras)
        source = str(payload.pop("source", None) or "backend")
        stack = payload.pop("stack", None)
        url = payload.pop("url", None)

        def _resolve_id(field):
            value = explicit.get(field)
            return value if value is not None else _ctx[field].get()

        LoggingCore.log_error(
            message,
            category=category,
            level=bridge_level or _BRIDGE_LEVEL_BY_CATEGORY.get(category) or event_level,
            source=source,
            exception=exception,
            stack_trace=stack,
            url=url,
            method=_resolve_id("method"),
            ip_address=_resolve_id("ip"),
            tenant_id=_resolve_id("tenant_id"),
            user_id=_resolve_id("user_id"),
            request_id=_resolve_id("request_id"),
            extra={
                "telemetry_category": category,
                "tenant_id": _resolve_id("tenant_id"),
                "user_id": _resolve_id("user_id"),
                "request_id": _resolve_id("request_id"),
                "endpoint": _resolve_id("endpoint"),
                **payload,
            },
        )
    except Exception:
        # Observability must never break control flow — not even its own bridge.
        logging.getLogger(__name__).debug("Telemetry bridge to error log failed", exc_info=True)
    finally:
        _in_bridge.reset(token)


def init_telemetry(app) -> logging.Logger:
    """Attach the JSONL sink (+ stdout in development) to the telemetry logger.

    In tests (app.testing or under pytest) only a NullHandler is attached so
    the suite stays console-quiet. Safe to call repeatedly — handlers are
    rebuilt each time.
    """
    log = _get_logger()
    log.handlers.clear()
    log.setLevel(logging.INFO)

    testing = bool(getattr(app, "testing", False)) or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if testing:
        log.addHandler(logging.NullHandler())
        return log

    formatter = _TelemetryEventFormatter()
    file_handler = RotatingFileHandler(
        _telemetry_sink_path(),
        maxBytes=int(app.config.get("LOG_MAX_BYTES", 10 * 1024 * 1024)),
        backupCount=int(app.config.get("LOG_BACKUP_COUNT", 5)),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)

    if os.environ.get("FLASK_ENV", "") == "development":
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        log.addHandler(stdout_handler)

    app.logger.info("[OK] Telemetry JSONL sink configured (%s)", TELEMETRY_FILENAME)
    return log


def log_event(
    category: str,
    message: str,
    *,
    level: str | int = "INFO",
    tenant_id=None,
    user_id=None,
    _bridge: bool = True,
    _bridge_level: str | None = None,
    **extras,
) -> None:
    """Emit one structured telemetry event. Never raises into business flow.

    ``tenant_id``/``user_id`` are explicit-first: pass them at the call site;
    unset values fall back to the bound context (directive invariant: every
    event carries tenant_id, ``None`` only when genuinely unknown).

    ``_bridge=False`` skips the DB error-log forward — used where the caller
    already persists the same event through LoggingCore itself (e.g. the 500
    handlers) so exactly one error_audit_logs row exists per real event.
    """
    level_no = _levels.get(level.upper(), logging.INFO) if isinstance(level, str) else int(level)
    explicit = {"tenant_id": tenant_id, "user_id": user_id}
    for field in _CONTEXT_FIELDS:
        if field in extras:
            explicit[field] = extras.pop(field)
    payload = {"category": category, "explicit": explicit, "extras": extras}
    try:
        _get_logger().log(level_no, message, extra={"telemetry_event": payload})
    except Exception:
        # Observability must never break control flow.
        logging.getLogger(__name__).debug("Telemetry log call failed", exc_info=True)
    if _bridge:
        event_level = level if isinstance(level, str) else logging.getLevelName(level_no)
        _bridge_to_error_log(
            category,
            message,
            event_level=event_level,
            bridge_level=_bridge_level,
            exception=None,
            explicit=explicit,
            extras=extras,
        )


def log_exception(
    message: str,
    exception: BaseException | None = None,
    *,
    level: str = "ERROR",
    tenant_id=None,
    _bridge: bool = True,
    **extras,
) -> None:
    """Emit a SOFTWARE_EXCEPTION event with stack info."""
    level_no = _levels.get(level.upper(), logging.ERROR) if isinstance(level, str) else int(level)
    explicit = {"tenant_id": tenant_id}
    payload = {"category": CATEGORY_SOFTWARE_EXCEPTION, "explicit": explicit, "extras": extras}
    exc_info = (type(exception), exception, exception.__traceback__) if exception is not None else True
    try:
        _get_logger().log(level_no, message, exc_info=exc_info, extra={"telemetry_event": payload})
    except Exception:
        logging.getLogger(__name__).debug("Exception telemetry log call failed", exc_info=True)
    if _bridge:
        _bridge_to_error_log(
            CATEGORY_SOFTWARE_EXCEPTION,
            message,
            event_level=level,
            bridge_level=level,
            exception=exception,
            explicit=explicit,
            extras=extras,
        )


def log_financial(message: str, *, level: str | None = None, tenant_id=None, **extras) -> None:
    """Emit a CRITICAL_FINANCIAL anomaly (unbalanced GL, negative stock...)."""
    log_event(
        CATEGORY_CRITICAL_FINANCIAL,
        message,
        level=level or "CRITICAL",
        tenant_id=tenant_id,
        _bridge_level=level,
        **extras,
    )


def log_security(message: str, *, level: str | None = None, tenant_id=None, **extras) -> None:
    """Emit a SECURITY_ALERT anomaly (override denial, cross-tenant attempt...)."""
    log_event(
        CATEGORY_SECURITY_ALERT,
        message,
        level=level or "WARNING",
        tenant_id=tenant_id,
        _bridge_level=level,
        **extras,
    )


def log_hardware(message: str, *, level: str | None = None, tenant_id=None, **extras) -> None:
    """Emit a HARDWARE_WARN anomaly (printer/drawer/scale agent failures)."""
    log_event(
        CATEGORY_HARDWARE_WARN,
        message,
        level=level or "WARNING",
        tenant_id=tenant_id,
        _bridge_level=level,
        **extras,
    )
