"""
LoggingCore — Unified Logging, Monitoring & Audit System.

Consolidates:
  - File-based rotating logs (from enhanced_logging.py, monitoring.py, logging_setup.py)
  - Database error audit with dedup (from error_audit_service.py, error_audit_log.py)
  - Business audit logging (from audit_service.py, helpers.create_audit_log)
  - Security logging (from enhanced_logging.SecurityLogger, advanced_audit.py)
  - Performance monitoring (from monitoring.py, performance_tracker.py)
  - Health checks (from monitoring.py, monitoring_service.py)
  - Auto-cleanup for old records

Usage:
    from services.logging_core import LoggingCore
    LoggingCore.setup(app)
    LoggingCore.log_error(category="BACKEND", level="ERROR", message="...", exception=exc)
    LoggingCore.log_frontend_error(message="...", ...)
    LoggingCore.log_audit(action="create", table_name="sale", record_id=123, changes={...})
    LoggingCore.log_security(event_type="failed_login", message="...", ...)
    LoggingCore.health_check()
    LoggingCore.auto_cleanup()
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler
from typing import Any
from urllib.parse import urlparse

from flask import g, has_request_context, request, current_app
from utils.db_safety import atomic_transaction

try:
    from colorama import init as colorama_init, Fore, Style

    colorama_init(autoreset=True)
except ImportError:
    colorama_init = None

    class _Fore:
        BLUE = CYAN = GREEN = YELLOW = RED = MAGENTA = WHITE = ""

    class _Style:
        BRIGHT = RESET_ALL = ""

    Fore, Style = _Fore(), _Style()

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────
_MAX_MESSAGE_LEN = 4000
_MAX_TRACE_LEN = 4000
_MAX_URL_LEN = 500
_MAX_UA_LEN = 255
_DEDUP_WINDOW_MINUTES = 10
_LOGS_DIR = "logs"
_ERROR_RETAIN_DAYS = 90
_AUDIT_RETAIN_DAYS = 180
_LOGIN_RETAIN_DAYS = 90
_PERF_THRESHOLD_WARN_MS = 1000
_PERF_THRESHOLD_INFO_MS = 500
_SLOW_QUERY_THRESHOLD_S = 0.1

_SECRET_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "password_confirmation",
        "current_password",
        "new_password",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "api_secret",
        "secret",
        "secret_key",
        "csrf_token",
        "auth_token",
        "session_token",
        "credit_card",
        "cvv",
        "cvc",
        "card_number",
        "bank_account",
        "iban",
        "passport",
        "national_id",
        "emirates_id",
        "identity",
        "id_number",
        "mobile",
        "phone_number",
        "landline",
        "whatsapp",
        "tax_number",
        "vat_number",
        "cr_number",
        "license_number",
        "bank_name",
        "bank_branch",
        "swift_code",
        "routing_number",
    }
)

# ── Rate monitoring ─────────────────────────────────────────────
_ERROR_RATE_WINDOW_MINUTES = 5
_ERROR_RATE_ALERT_THRESHOLD = 20
_DEDUP_ESCALATION_THRESHOLD = 25
_DISK_WARN_PERCENT = 85
_DB_RETRY_MAX_SECONDS = 8.0

_AUDIT_ACTION_DISPLAY = {
    "create": {"ar": "إضافة", "en": "Create"},
    "update": {"ar": "تعديل", "en": "Update"},
    "delete": {"ar": "حذف", "en": "Delete"},
    "login": {"ar": "تسجيل دخول", "en": "Login"},
    "logout": {"ar": "تسجيل خروج", "en": "Logout"},
    "view": {"ar": "عرض", "en": "View"},
    "export": {"ar": "تصدير", "en": "Export"},
    "print": {"ar": "طباعة", "en": "Print"},
}

_CATEGORIES = frozenset(
    {
        "BACKEND",
        "DATABASE",
        "FRONTEND",
        "SYSTEM_INIT",
        "API",
        "SECURITY",
        "RATE_LIMIT",
    }
)

_FRONTEND_ALLOWED_TYPES = frozenset(
    {
        "runtime",
        "promise",
        "resource",
        "fetch",
        "fetch_slow",
        "ajax",
        "api",
        "api_slow",
        "concurrency",
        "longtask",
        "layout",
        "theme",
    }
)

# ── Helpers ──────────────────────────────────────────────────────


def _ensure_utf8_stream(stream):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
            return stream
        except Exception:
            pass
    if hasattr(stream, "buffer"):
        try:
            return io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass
    return stream


def _get_request_id() -> str:
    if has_request_context():
        rid = getattr(g, "request_id", None)
        if rid:
            return str(rid)
        rid = str(uuid.uuid4())
        g.request_id = rid
        return rid
    return str(uuid.uuid4())


def _sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in data.items():
        k_lower = str(key).lower()
        if any(sk in k_lower for sk in _SECRET_KEYS):
            clean[key] = "***REDACTED***"
            continue
        try:
            tname = type(value).__name__
        except Exception:
            tname = ""
        if tname == "Undefined":
            clean[key] = None
            continue
        if isinstance(value, dict):
            clean[key] = _sanitize_dict(value)
            continue
        if isinstance(value, list):
            clean[key] = [
                (
                    _sanitize_dict(v)
                    if isinstance(v, dict)
                    else (None if type(v).__name__ == "Undefined" else v)
                )
                for v in value
            ]
            continue
        clean[key] = value
    return clean


def _get_request_context() -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "url": None,
        "method": None,
        "ip": None,
        "ua": None,
        "user_id": None,
        "tenant_id": None,
    }
    if has_request_context() and request:
        ctx["url"] = request.url[:_MAX_URL_LEN]
        ctx["method"] = request.method
        ctx["ua"] = request.headers.get("User-Agent", "")[:_MAX_UA_LEN]
        ctx["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr) or ""
        try:
            from flask_login import current_user

            if getattr(current_user, "is_authenticated", False):
                ctx["user_id"] = int(current_user.get_id())
                ctx["tenant_id"] = getattr(current_user, "tenant_id", None)
        except Exception:
            pass
    return ctx


def _make_fingerprint(
    category: str, exc_type: str, source: str, endpoint: str, message: str = ""
) -> str:
    message_key = " ".join((message or "").split())[:160]
    raw = f"{category}::{exc_type}::{source}::{endpoint}::{message_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ── Formatters & Filters ─────────────────────────────────────────


class _RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = (
            getattr(g, "request_id", "-") if has_request_context() else "-"
        )
        return True


class _SafeLogRecordFilter(logging.Filter):
    DEFAULTS = {"user": "-", "ip": "-", "tenant": "-", "request_id": "-"}

    def filter(self, record):
        for field, default in self.DEFAULTS.items():
            if not hasattr(record, field):
                setattr(record, field, default)
        return True


class _ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": Fore.CYAN + Style.BRIGHT,
        "INFO": Fore.WHITE + Style.BRIGHT,
        "WARNING": Fore.YELLOW + Style.BRIGHT,
        "ERROR": Fore.RED + Style.BRIGHT,
        "CRITICAL": Fore.MAGENTA + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        use_colors = os.environ.get("FLASK_ENV", "development") == "development"
        color = self.COLORS.get(record.levelname, "") if use_colors else ""
        reset = Style.RESET_ALL if use_colors else ""
        req_id = getattr(record, "request_id", "-")
        ts = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        msg = f"[{ts}] {color}{record.levelname:8s}{reset} [{req_id}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        try:
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            msg = msg.encode(encoding, errors="replace").decode(
                encoding, errors="replace"
            )
        except Exception:
            msg = msg.encode("ascii", errors="replace").decode("ascii")
        return msg


class _JsonFormatter(logging.Formatter):
    """JSON-structured formatter for log-aggregator pipelines (ELK, Datadog, etc.).

    Activated via LOG_FORMAT=json in app config.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
            "tenant": getattr(record, "tenant", "-"),
            "user": getattr(record, "user", "-"),
            "ip": getattr(record, "ip", "-"),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "traceback": self.formatException(record.exc_info),
            }
        return json.dumps(entry, ensure_ascii=False, default=str)


# ── Rate monitor — shared mutable state ─────────────────────────
class _RateMonitor:
    """Thread-safe counter buckets for error-rate monitoring."""

    def __init__(self) -> None:
        self._lock = __import__("threading").Lock()
        self._buckets: dict[str, list[tuple[float, int]]] = {}

    def record(self, category: str):
        now = time.time()
        with self._lock:
            bucket = self._buckets.setdefault(category, [])
            bucket.append((now, 1))
            self._prune(bucket, now)

    def count(self, category: str, window_seconds: int = 300) -> int:
        now = time.time()
        with self._lock:
            bucket = self._buckets.get(category, [])
            self._prune(bucket, now)
            return sum(c for ts, c in bucket)

    @staticmethod
    def _prune(bucket: list, now: float, window: int = 300):
        cutoff = now - window
        while bucket and bucket[0][0] < cutoff:
            bucket.pop(0)

    def spike(
        self,
        category: str,
        threshold: int = _ERROR_RATE_ALERT_THRESHOLD,
        window: int = 300,
    ) -> bool:
        return self.count(category, window) >= threshold


# ══════════════════════════════════════════════════════════════════
#  LoggingCore — the unified service
# ══════════════════════════════════════════════════════════════════


class LoggingCore:
    """Single entry point for all logging, monitoring and audit operations."""

    # ── Instance state ────────────────────────────────────────────
    _handlers: dict[str, logging.Handler] = {}
    _initialized = False
    _alert_callbacks: list = []
    _rate_monitor = _RateMonitor()
    _json_mode = False

    # ──────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def setup(cls, app) -> None:
        """Configure all loggers once at application startup.

        Replaces:
          - utils/logging_setup.py → setup_logging()
          - utils/enhanced_logging.py → setup_enhanced_logging()
          - utils/monitoring.py → setup_advanced_logging()
        """
        if cls._initialized:
            app.logger.warning("LoggingCore.setup() called more than once — skipping")
            return

        cls._ensure_logs_dir()
        cls._setup_console_logging(app)
        cls._setup_file_handlers(app)

        cls._json_mode = app.config.get("LOG_FORMAT", "").lower() == "json"
        if cls._json_mode:
            cls._setup_json_logging(app)

        cls._register_request_hooks(app)
        cls._register_teardown(app)
        cls._capture_warnings(app)
        cls._run_self_diagnostics(app)

        cls._initialized = True
        app.logger.info("=" * 60)
        app.logger.info("[OK] LoggingCore initialized successfully")
        app.logger.info("=" * 60)
        app.logger.info("[OK] Warnings capture active")
        if cls._alert_callbacks:
            app.logger.info(
                "[OK] %d alert callback(s) registered", len(cls._alert_callbacks)
            )
        app.logger.info("=" * 60)

    @classmethod
    def _ensure_logs_dir(cls):
        if not os.path.exists(_LOGS_DIR):
            os.makedirs(_LOGS_DIR)

    @classmethod
    def _setup_console_logging(cls, app):
        """Console handler with colors and request_id filter."""
        utf8_stdout = _ensure_utf8_stream(sys.stdout)
        utf8_stderr = _ensure_utf8_stream(sys.stderr)

        level_name = app.config.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

        stdout_handler = logging.StreamHandler(utf8_stdout)
        stdout_handler.setLevel(level)
        stdout_handler.addFilter(_RequestIdFilter())
        stdout_handler.setFormatter(_ColorFormatter())

        stderr_handler = logging.StreamHandler(utf8_stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.addFilter(_RequestIdFilter())
        stderr_handler.setFormatter(_ColorFormatter())

        for log in (app.logger, logging.getLogger()):
            log.handlers.clear()
            log.setLevel(level)
            log.addHandler(stdout_handler)
            log.addHandler(stderr_handler)
            log.propagate = False

        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        werkzeug_log = logging.getLogger("werkzeug")
        werkzeug_log.setLevel(logging.INFO)
        werkzeug_log.handlers.clear()
        werkzeug_log.propagate = True

    @classmethod
    def _setup_file_handlers(cls, app) -> None:
        """Rotating file handlers for app, errors, security logs."""
        app.config.get("LOG_LEVEL", "INFO").upper()
        max_bytes = app.config.get("LOG_MAX_BYTES", 10 * 1024 * 1024)
        backup_count = app.config.get("LOG_BACKUP_COUNT", 5)

        configs: list[dict[str, Any]] = [
            {
                "name": "app",
                "file": os.path.join(_LOGS_DIR, "app.log"),
                "level": logging.INFO,
                "fmt": "[%(asctime)s] %(levelname)s in %(module)s:%(lineno)d - %(message)s",
                "max_bytes": max_bytes,
                "backup": backup_count + 5,
            },
            {
                "name": "error",
                "file": os.path.join(_LOGS_DIR, "errors.log"),
                "level": logging.ERROR,
                "fmt": "[%(asctime)s] %(levelname)s in %(module)s:%(lineno)d\n"
                "Message: %(message)s\nPath: %(pathname)s\n%(exc_info)s\n",
                "max_bytes": max_bytes,
                "backup": backup_count,
            },
            {
                "name": "security",
                "file": os.path.join(_LOGS_DIR, "security.log"),
                "level": logging.WARNING,
                "fmt": "[%(asctime)s] SECURITY - %(levelname)s\n"
                "User: %(user)s | IP: %(ip)s\nMessage: %(message)s",
                "max_bytes": 5 * 1024 * 1024,
                "backup": 10,
            },
            {
                "name": "perf",
                "file": os.path.join(_LOGS_DIR, "performance.log"),
                "level": logging.INFO,
                "fmt": "[%(asctime)s] PERF - %(message)s",
                "max_bytes": 5 * 1024 * 1024,
                "backup": 5,
            },
        ]

        safe_filter = _SafeLogRecordFilter()

        for cfg in configs:
            handler = RotatingFileHandler(
                cfg["file"],
                maxBytes=cfg["max_bytes"],
                backupCount=cfg["backup"],
                encoding="utf-8",
            )
            handler.setLevel(cfg["level"])
            handler.setFormatter(
                logging.Formatter(cfg["fmt"], datefmt="%Y-%m-%d %H:%M:%S")
            )
            handler.addFilter(safe_filter)
            app.logger.addHandler(handler)
            cls._handlers[cfg["name"]] = handler

        app.logger.setLevel(logging.INFO if not app.debug else logging.DEBUG)

    @classmethod
    def _register_request_hooks(cls, app):
        """Register before_request / after_request hooks for performance timing.

        Note: g.request_id and g.request_start_time are also set by app.py's
        before_request hook (runs after this one, so it wins). The after_request
        only logs performance; X-Request-Id header is handled by app.py.
        """

        @app.before_request
        def _logging_before_request():
            if not hasattr(g, "request_start_time"):
                g.request_start_time = time.time()

        @app.after_request
        def _logging_after_request(response):
            start = getattr(g, "request_start_time", None)
            if start:
                elapsed = time.time() - float(start or 0)
                if elapsed > 1.0:
                    current_app.logger.warning(
                        "SLOW REQUEST: %s %s -> %d (%.0fms)",
                        request.method,
                        request.path,
                        response.status_code,
                        elapsed * 1000,
                    )
                elif elapsed > 0.5:
                    current_app.logger.info(
                        "REQUEST: %s %s -> %d (%.0fms)",
                        request.method,
                        request.path,
                        response.status_code,
                        elapsed * 1000,
                    )
            return response

    @classmethod
    def register_slow_query_listener(cls, app):
        """Register SQLAlchemy engine event listener for slow queries.

        Replaces utils/performance_tracker.py → log_slow_queries()
        """
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        @event.listens_for(Engine, "before_cursor_execute")
        def _before_cursor_execute(
            conn, cursor, statement, parameters, context, executemany
        ):
            conn.info.setdefault("query_start_time", []).append(time.time())

        @event.listens_for(Engine, "after_cursor_execute")
        def _after_cursor_execute(
            conn, cursor, statement, parameters, context, executemany
        ):
            total = time.time() - conn.info["query_start_time"].pop()
            if total > _SLOW_QUERY_THRESHOLD_S:
                logger.warning("Slow query (%.3fs): %s", total, statement[:200])

        app.logger.info(
            "[OK] Slow query listener registered (threshold=%.1fms)",
            _SLOW_QUERY_THRESHOLD_S * 1000,
        )

    @classmethod
    def _register_teardown(cls, app):
        @app.teardown_appcontext
        def _logging_teardown(exc):
            pass

    # ──────────────────────────────────────────────────────────────
    #  WARNINGS CAPTURE
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _capture_warnings(cls, app):
        """Route Python warnings through the logging system.

        Captures DeprecationWarning, UserWarning, etc. from all libraries.
        """
        logging.captureWarnings(True)
        warnings_logger = logging.getLogger("py.warnings")
        warnings_logger.setLevel(logging.WARNING)

        original_showwarning = None
        try:
            import warnings as _builtin_warnings

            original_showwarning = _builtin_warnings.showwarning

            def _log_warning(message, category, filename, lineno, file=None, line=None):
                category_name = getattr(category, "__name__", None) or repr(category)
                msg = f"{category_name}: {message}"
                if has_request_context():
                    try:
                        msg += f" | route={request.method} {request.path}"
                    except Exception:
                        pass
                logger.warning(msg)
                if original_showwarning:
                    original_showwarning(
                        message, category, filename, lineno, file, line
                    )

            _builtin_warnings.showwarning = _log_warning
            app.logger.info("[OK] Python warnings captured via logging")
        except Exception:
            app.logger.warning("[WARN] Could not hook warnings.showwarning")

    # ──────────────────────────────────────────────────────────────
    #  JSON LOGGING SETUP
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _setup_json_logging(cls, app):
        """Replace console formatters with JSON for log-aggregator pipelines."""
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setFormatter(_JsonFormatter())
        app.logger.info("[OK] JSON logging format active")

    # ──────────────────────────────────────────────────────────────
    #  SELF-DIAGNOSTICS
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _run_self_diagnostics(cls, app):
        """Verify log directory is writable and each handler file is accessible."""
        issues = []
        if not os.access(_LOGS_DIR, os.W_OK):
            issues.append(f"logs_dir={_LOGS_DIR} not writable")

        for name, handler in cls._handlers.items():
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                try:
                    base_path = handler.baseFilename
                    if os.path.exists(base_path):
                        if not os.access(base_path, os.W_OK):
                            issues.append(f"{name}={base_path} not writable")
                    else:
                        parent = os.path.dirname(base_path)
                        if parent and not os.access(parent, os.W_OK):
                            issues.append(f"{name}={parent} not writable")
                except Exception as e:
                    issues.append(f"{name}=check_failed:{e}")

        if issues:
            for issue in issues:
                app.logger.warning("[DIAG] %s", issue)
        else:
            app.logger.info("[OK] All log handlers verified writable")

    # ──────────────────────────────────────────────────────────────
    #  ALERT CALLBACKS
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def register_alert_callback(cls, fn):
        """Register a callable to be invoked on critical error escalation.

        The callable receives (category, level, message, occurrence_count).
        """
        cls._alert_callbacks.append(fn)

    @classmethod
    def _fire_alert_callbacks(cls, category: str, level: str, message: str, count: int):
        if not cls._alert_callbacks:
            return
        for fn in cls._alert_callbacks:
            try:
                fn(category, level, message, count)
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────
    #  TRACE ID PROPAGATION
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def set_trace_id(cls):
        """Read X-Trace-Id from request headers, persist in g for correlation.

        Call from a before_request hook (high priority) so frontend errors
        can be linked to backend requests.
        """
        if not has_request_context():
            return
        trace_id = request.headers.get("X-Trace-Id") or request.headers.get(
            "X-Request-Id"
        )
        if trace_id:
            g.request_id = trace_id
            g.trace_id = trace_id

    # ──────────────────────────────────────────────────────────────
    #  ERROR LOGGING (Database + File)
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def log_error(
        cls,
        message: str,
        *,
        category: str = "BACKEND",
        level: str = "ERROR",
        source: str = "unknown",
        exception: BaseException | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        """Persist error to database + file log."""
        exc_type = type(exception).__name__ if exception else None
        trace = None
        if exception:
            trace = "".join(
                traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            )

        row_id = cls._persist_error(
            message=message,
            category=category,
            level=level,
            source=source,
            exc_type=exc_type,
            stack_trace=trace,
            extra=extra,
        )
        try:
            logger.error(
                "[ErrorAuditLog %s] %s | source=%s | id=%s",
                category,
                message[:200],
                source,
                row_id,
            )
        except Exception:
            pass
        return row_id

    @classmethod
    def log_frontend_error(
        cls,
        message: str,
        *,
        level: str = "ERROR",
        source: str = "frontend.browser",
        url: str | None = None,
        user_agent: str | None = None,
        stack: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        """Called by the JS-error endpoint (pre-validated payload)."""
        if stack and len(stack) > _MAX_TRACE_LEN:
            stack = stack[:_MAX_TRACE_LEN] + "\n...[truncated]"
        return cls._persist_error(
            message=message,
            category="FRONTEND",
            level=level,
            source=source,
            url=url,
            user_agent=user_agent,
            stack_trace=stack,
            extra=extra,
        )

    @classmethod
    def _persist_error(
        cls,
        message: str,
        *,
        category: str,
        level: str,
        source: str,
        exception: BaseException | None = None,
        exc_type: str | None = None,
        url: str | None = None,
        method: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
        stack_trace: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        from extensions import db

        # Request context
        ctx = _get_request_context()
        _url = url or ctx["url"]
        _method = method or ctx["method"]
        _ua = user_agent or ctx["ua"]
        _ip = ip_address or ctx["ip"]
        _user_id = ctx["user_id"]
        _tenant_id = ctx["tenant_id"]

        environment = "production"
        app_version = ""
        try:
            environment = current_app.config.get("FLASK_ENV", "production")
            app_version = current_app.config.get("APP_VERSION", "")
        except Exception:
            pass

        # Request ID
        request_id = _get_request_id()

        # Sanitize request data
        request_data = None
        if extra:
            request_data = _sanitize_dict(extra)
        elif has_request_context() and request:
            payload: dict[str, Any] = {}
            try:
                if request.is_json:
                    payload = request.get_json(silent=True) or {}
                else:
                    payload = request.form.to_dict() if request.form else {}
            except Exception:
                pass
            request_data = _sanitize_dict(payload)

        endpoint_path = ""
        try:
            if category == "FRONTEND" and _url:
                endpoint_path = urlparse(_url).path or _url[:200]
            elif has_request_context() and request:
                endpoint_path = request.path or ""
        except Exception:
            pass

        # Fingerprint
        fp_message = message
        if category == "FRONTEND" and isinstance(request_data, dict):
            fp_message = str(request_data.get("fingerprint_key") or message)
        fingerprint = _make_fingerprint(
            category, exc_type or "", source, endpoint_path, fp_message
        )

        cls._rate_monitor.record(category)

        # Dedup check
        dup_id = cls._find_duplicate(fingerprint)
        if dup_id:
            new_count = cls._bump_duplicate(dup_id, message, stack_trace)
            if new_count and new_count >= _DEDUP_ESCALATION_THRESHOLD:
                cls._fire_alert_callbacks(category, level, message, new_count)
            return dup_id

        # Fresh INSERT
        from sqlalchemy import text

        sql = text("""
            INSERT INTO error_audit_logs (
                fingerprint, occurrence_count, first_seen_at, last_seen_at,
                level, category, source, message, exception_type,
                stack_trace, request_id, url, method, ip_address, user_agent,
                environment, app_version, user_id, tenant_id, request_data,
                is_resolved, created_at
            ) VALUES (
                :fingerprint, 1, :now, :now,
                :level, :category, :source, :message, :exception_type,
                :stack_trace, :request_id, :url, :method, :ip_address, :user_agent,
                :environment, :app_version, :user_id, :tenant_id, :request_data,
                false, :now
            ) RETURNING id
        """)

        params = {
            "fingerprint": fingerprint,
            "level": (level or "ERROR")[:20],
            "category": (category or "BACKEND")[:30],
            "source": (source or "unknown")[:100],
            "message": (message or "")[:_MAX_MESSAGE_LEN],
            "exception_type": (exc_type or "")[:200],
            "stack_trace": (stack_trace or "")[:_MAX_TRACE_LEN],
            "request_id": request_id,
            "url": (_url or "")[:_MAX_URL_LEN],
            "method": (_method or "")[:10],
            "ip_address": (_ip or "")[:50],
            "user_agent": (_ua or "")[:_MAX_UA_LEN],
            "environment": environment[:20],
            "app_version": (app_version or "")[:30],
            "user_id": _user_id,
            "tenant_id": _tenant_id,
            "request_data": (
                json.dumps(request_data, ensure_ascii=False, default=str)
                if request_data
                else None
            ),
            "now": datetime.now(timezone.utc),
        }

        # Exponential backoff on DB failure (up to _DB_RETRY_MAX_SECONDS total)
        last_exc = None
        delay = 0.1
        total_slept = 0.0
        for attempt in range(5):
            try:
                with db.engine.connect() as conn:
                    result = conn.execute(sql, params)
                    conn.commit()
                    row = result.fetchone()

                    # Check for rate spike after successful insert
                    if cls._rate_monitor.spike(category):
                        cls._fire_alert_callbacks(
                            category, level, message, cls._rate_monitor.count(category)
                        )

                    return row[0] if row else None
            except Exception as engine_exc:
                last_exc = engine_exc
                total_slept += delay
                if total_slept >= _DB_RETRY_MAX_SECONDS:
                    break
                time.sleep(delay)
                delay *= 2

        cls._fallback_write(
            f"[ERROR_AUDIT_FALLBACK] {category} | {message[:200]} | engine_error={last_exc}"
        )
        return None

    @classmethod
    def _find_duplicate(cls, fingerprint: str) -> int | None:
        from extensions import db
        from sqlalchemy import text

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(
                minutes=_DEDUP_WINDOW_MINUTES
            )
            sql = text("""
                SELECT id FROM error_audit_logs
                WHERE fingerprint = :fp AND is_resolved = false AND last_seen_at > :cutoff
                ORDER BY last_seen_at DESC LIMIT 1
            """)
            with db.engine.connect() as conn:
                row = conn.execute(
                    sql, {"fp": fingerprint, "cutoff": cutoff}
                ).fetchone()
                return row[0] if row else None
        except Exception:
            return None

    @classmethod
    def _bump_duplicate(
        cls, log_id: int, new_message: str, new_trace: str | None
    ) -> int | None:
        from extensions import db
        from sqlalchemy import text

        try:
            sql = text("""
                UPDATE error_audit_logs
                SET occurrence_count = occurrence_count + 1,
                    last_seen_at = :now,
                    message = :message,
                    stack_trace = COALESCE(:stack_trace, stack_trace)
                WHERE id = :log_id
                RETURNING occurrence_count
            """)
            with db.engine.connect() as conn:
                result = conn.execute(
                    sql,
                    {
                        "now": datetime.now(timezone.utc),
                        "message": (new_message or "")[:_MAX_MESSAGE_LEN],
                        "stack_trace": (
                            (new_trace or "")[:_MAX_TRACE_LEN] if new_trace else None
                        ),
                        "log_id": log_id,
                    },
                )
                conn.commit()
                row = result.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    @classmethod
    def _fallback_write(cls, msg: str):
        try:
            sys.stderr.write(msg + "\n")
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    #  ERROR QUERIES
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def get_error_logs(
        cls,
        category: str = "",
        level: str = "",
        is_resolved: str = "",
        source: str = "",
        from_date: str = "",
        to_date: str = "",
        search: str = "",
        page: int = 1,
        per_page: int = 50,
    ):
        from models.error_audit_log import ErrorAuditLog
        from extensions import db

        query = ErrorAuditLog.query
        if category:
            query = query.filter_by(category=category)
        if level:
            query = query.filter_by(level=level)
        if is_resolved == "1":
            query = query.filter_by(is_resolved=True)
        elif is_resolved == "0":
            query = query.filter_by(is_resolved=False)
        if source:
            query = query.filter(ErrorAuditLog.source.ilike(f"%{source}%"))
        if from_date:
            try:
                fd = datetime.strptime(from_date, "%Y-%m-%d")
                query = query.filter(ErrorAuditLog.created_at >= fd)
            except Exception:
                pass
        if to_date:
            try:
                td = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(ErrorAuditLog.created_at < td)
            except Exception:
                pass
        if search:
            query = query.filter(
                db.or_(
                    ErrorAuditLog.message.ilike(f"%{search}%"),
                    ErrorAuditLog.exception_type.ilike(f"%{search}%"),
                    ErrorAuditLog.url.ilike(f"%{search}%"),
                )
            )
        query = query.order_by(ErrorAuditLog.last_seen_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        categories = [
            r[0]
            for r in db.session.query(ErrorAuditLog.category)
            .distinct()
            .order_by(ErrorAuditLog.category)
            .all()
        ]
        levels = [
            r[0]
            for r in db.session.query(ErrorAuditLog.level)
            .distinct()
            .order_by(ErrorAuditLog.level)
            .all()
        ]
        sources = [
            r[0]
            for r in db.session.query(ErrorAuditLog.source)
            .distinct()
            .order_by(ErrorAuditLog.source)
            .all()
        ]
        stats = {
            "total": ErrorAuditLog.query.count(),
            "unresolved": ErrorAuditLog.query.filter_by(is_resolved=False).count(),
            "critical": ErrorAuditLog.query.filter_by(level="CRITICAL").count(),
        }

        return pagination.items, pagination, categories, levels, sources, stats

    @classmethod
    def export_error_logs(
        cls,
        category: str = "",
        level: str = "",
        is_resolved: str = "",
        source: str = "",
        from_date: str = "",
        to_date: str = "",
        search: str = "",
        fmt: str = "json",
    ):
        from models.error_audit_log import ErrorAuditLog
        from io import StringIO

        query = ErrorAuditLog.query
        if category:
            query = query.filter_by(category=category)
        if level:
            query = query.filter_by(level=level)
        if is_resolved == "1":
            query = query.filter_by(is_resolved=True)
        elif is_resolved == "0":
            query = query.filter_by(is_resolved=False)
        if source:
            query = query.filter(ErrorAuditLog.source.ilike(f"%{source}%"))
        if from_date:
            try:
                fd = datetime.strptime(from_date, "%Y-%m-%d")
                query = query.filter(ErrorAuditLog.created_at >= fd)
            except Exception:
                pass
        if to_date:
            try:
                td = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(ErrorAuditLog.created_at < td)
            except Exception:
                pass
        if search:
            from extensions import db

            query = query.filter(
                db.or_(
                    ErrorAuditLog.message.ilike(f"%{search}%"),
                    ErrorAuditLog.exception_type.ilike(f"%{search}%"),
                    ErrorAuditLog.url.ilike(f"%{search}%"),
                )
            )
        logs = query.order_by(ErrorAuditLog.last_seen_at.desc()).all()

        if fmt == "json":
            data = [log.to_dict() for log in logs]
            return (
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                "application/json",
                "error_audit_logs.json",
            )

        buf = StringIO()
        buf.write("=" * 80 + "\nError Audit Logs Export\n")
        buf.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
        buf.write(f"Count: {len(logs)}\n" + "=" * 80 + "\n\n")
        for log in logs:
            buf.write(f"ID: {log.id} | Level: {log.level} | Category: {log.category}\n")
            buf.write(
                f"Source: {log.source} | Time: {log.created_at.isoformat() if log.created_at else '-'}\n"
            )
            buf.write(f"Message: {log.message}\n")
            if log.stack_trace:
                buf.write(f"Stack: {log.stack_trace[:500]}\n")
            buf.write("-" * 80 + "\n\n")
        return (
            buf.getvalue().encode("utf-8"),
            "text/plain; charset=utf-8",
            "error_audit_logs.txt",
        )

    @classmethod
    def mark_error_resolved(cls, log_id: int, user_id: int, note: str = "") -> bool:
        from models.error_audit_log import ErrorAuditLog

        try:
            with atomic_transaction("mark_error_resolved"):
                log = ErrorAuditLog.query.filter_by(id=log_id).first()
                if log:
                    log.is_resolved = True
                    log.resolved_at = datetime.now(timezone.utc)
                    log.resolved_by = user_id
                    log.resolution_note = note[:500]
            return True
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────
    #  AUDIT LOGGING (Business Operations)
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def log_audit(
        cls,
        action: str,
        table_name: str | None = None,
        record_id: int | None = None,
        changes: dict | None = None,
        severity: str = "low",
    ) -> None:
        """Log a business operation to the audit_logs table.

        Replaces:
          - utils/helpers.py → create_audit_log()
          - utils/advanced_audit.py → log_sensitive_action()
        """
        from models.audit import AuditLog
        from extensions import db

        ctx = _get_request_context()
        try:
            entry = AuditLog(
                user_id=ctx["user_id"],
                tenant_id=ctx["tenant_id"],
                action=action,
                table_name=table_name,
                record_id=record_id,
                changes=changes,
                ip_address=ctx["ip"],
                user_agent=ctx["ua"],
            )
            db.session.add(entry)
            db.session.flush()
        except Exception as e:
            cls._fallback_write(
                f"[AUDIT_FALLBACK] action={action} table={table_name} error={e}"
            )

    # ──────────────────────────────────────────────────────────────
    #  AUDIT QUERIES
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def get_audit_logs(
        cls,
        tenant_id: int | None = None,
        page: int = 1,
        per_page: int = 50,
        action: str = "",
        user_id: int | None = None,
    ):
        from models.audit import AuditLog
        from models.user import User
        from extensions import db

        query = AuditLog.query
        if tenant_id:
            query = query.filter_by(tenant_id=tenant_id)
        if action:
            query = query.filter_by(action=action)
        if user_id:
            query = query.filter_by(user_id=user_id)

        pagination = query.order_by(AuditLog.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        base = AuditLog.query
        if tenant_id:
            base = base.filter_by(tenant_id=tenant_id)
        stats = {
            "total": base.count(),
            "today": base.filter(
                db.func.date(AuditLog.created_at) == db.func.current_date()
            ).count(),
            "creates": base.filter_by(action="create").count(),
            "updates": base.filter_by(action="update").count(),
            "deletes": base.filter_by(action="delete").count(),
        }

        users = User.query.filter_by(is_active=True)
        if tenant_id:
            users = users.filter_by(tenant_id=tenant_id)
        users = users.all()

        return pagination.items, pagination, stats, users

    # ──────────────────────────────────────────────────────────────
    #  SECURITY LOGGING
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def log_security(
        cls,
        event_type: str,
        message: str,
        *,
        user: str = "-",
        ip: str = "-",
        user_agent: str = "",
        severity: str = "medium",
    ) -> None:
        """Log security events to file + security_alerts table +
        ErrorAuditLog for CRITICAL / ERROR severity.

        Replaces:
          - utils/enhanced_logging.py → SecurityLogger
          - utils/advanced_audit.py → track_login_attempt (partial)
        """
        logging.warning(
            f"[SECURITY] {event_type}: {message}",
            extra={"user": user, "ip": ip},
        )

        try:
            from models.security_alert import SecurityAlert
            from extensions import db

            alert = SecurityAlert(
                alert_type=event_type,
                severity=severity,
                title=message[:200],
                description=message,
                ip_address=ip,
                username=str(user),
            )
            db.session.add(alert)
            with atomic_transaction("log_security"):
                db.session.flush()
        except Exception:
            pass

        if severity in ("critical", "high"):
            try:
                cls.log_error(
                    message=f"[SECURITY] {event_type}: {message}",
                    category="SECURITY",
                    level="CRITICAL" if severity == "critical" else "ERROR",
                    source=f"security.{event_type}",
                    extra={"event_type": event_type, "ip": ip, "username": str(user)},
                )
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────
    #  HEALTH CHECKS
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def health_check(cls) -> dict:
        """Return system health status.

        Replaces:
          - utils/monitoring.py → HealthCheck
          - services/monitoring_service.py → get_system_health()
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy",
            "database": cls._check_db(),
            "disk": cls._check_disk(),
            "memory": cls._check_memory(),
            "cpu": cls._check_cpu(),
        }

    @classmethod
    def _check_db(cls) -> dict:
        from extensions import db
        from sqlalchemy import text

        try:
            db.session.execute(text("SELECT 1"))
            return {"status": "connected", "healthy": True}
        except Exception as e:
            return {"status": "error", "healthy": False, "error": str(e)}

    @classmethod
    def _check_disk(cls) -> dict:
        try:
            import shutil

            total, used, free = shutil.disk_usage(os.path.abspath(os.sep))
            percent = (used / total) * 100
            return {
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round(free / (1024**3), 2),
                "percent": round(percent, 1),
                "healthy": percent < 90,
            }
        except Exception:
            return {"healthy": True, "error": "unavailable"}

    @classmethod
    def _check_memory(cls) -> dict:
        try:
            import psutil

            mem = psutil.virtual_memory()
            return {
                "total_mb": round(mem.total / (1024**2), 2),
                "used_mb": round(mem.used / (1024**2), 2),
                "percent": mem.percent,
                "healthy": mem.percent < 85,
            }
        except ImportError:
            return {"healthy": True, "error": "psutil not available"}

    @classmethod
    def _check_cpu(cls) -> dict:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0.5)
            return {"percent": cpu, "cores": psutil.cpu_count(), "healthy": cpu < 80}
        except ImportError:
            return {"healthy": True, "error": "psutil not available"}

    # ──────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def monitor_endpoint(cls, f):
        """Decorator to monitor individual endpoint performance.

        Replaces utils/monitoring.py → PerformanceMonitor.monitor_endpoint()
        and utils/performance_tracker.py → track_performance()
        """

        @wraps(f)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = f(*args, **kwargs)
                duration = (time.time() - start) * 1000
                cls._log_perf(f.__name__, duration)
                return result
            except Exception:
                duration = (time.time() - start) * 1000
                cls._log_perf(f"{f.__name__} (ERROR)", duration)
                raise

        return wrapper

    @classmethod
    def _log_perf(cls, name: str, duration_ms: float):
        if duration_ms > _PERF_THRESHOLD_WARN_MS:
            logger.warning(f"SLOW ENDPOINT {name}: {duration_ms:.2f}ms")
        elif duration_ms > 20:
            logger.debug(f"ENDPOINT {name}: {duration_ms:.2f}ms")

    @classmethod
    def log_slow_query(cls, query_str: str, duration: float):
        """Log slow database queries.

        Replaces utils/performance_tracker.py → log_slow_queries()
        and utils/monitoring.py → DatabaseMonitor.log_query()
        """
        if duration > _SLOW_QUERY_THRESHOLD_S:
            logger.warning(f"SLOW QUERY ({duration * 1000:.1f}ms): {query_str[:200]}")

    @classmethod
    def get_performance_metrics(cls) -> dict:
        """Read recent performance data from performance.log.

        Replaces services/monitoring_service.py → get_performance_metrics_data()
        """
        perf_file = os.path.join(_LOGS_DIR, "performance.log")
        slow = []
        if os.path.exists(perf_file):
            with open(perf_file, "r", encoding="utf-8") as f:
                for line in f.readlines()[-200:]:
                    if "SLOW" in line:
                        slow.append(line.strip())
        return {"slow_queries_count": len(slow), "slow_queries": slow[-20:]}

    # ──────────────────────────────────────────────────────────────
    #  APPLICATION METRICS
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def get_app_metrics(cls) -> dict:
        """High-level application metrics for dashboards.

        Replaces services/monitoring_service.py → get_application_metrics()
        """
        from models import Sale, Customer, Product

        try:
            return {
                "total_sales": Sale.query.count(),
                "total_customers": Customer.query.count(),
                "total_products": Product.query.count(),
                "active_customers": Customer.query.filter_by(is_active=True).count(),
                "low_stock_products": Product.query.filter(
                    Product.current_stock <= Product.min_stock_alert
                ).count(),
            }
        except Exception as e:
            return {"error": str(e)}

    # ──────────────────────────────────────────────────────────────
    #  SYSTEM HEALTH (from monitoring_service)
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def check_database(cls) -> dict:
        try:
            from extensions import db
            from sqlalchemy import text

            db.session.execute(text("SELECT 1"))
            return {"status": "connected", "healthy": True}
        except Exception as e:
            return {"status": "error", "healthy": False, "error": str(e)}

    @classmethod
    def get_disk_usage(cls) -> dict:
        try:
            import psutil

            disk = psutil.disk_usage("/")
            return {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": disk.percent,
                "healthy": disk.percent < 90,
            }
        except Exception:
            return {"healthy": True, "error": "unavailable"}

    @classmethod
    def get_memory_usage(cls) -> dict:
        try:
            import psutil

            memory = psutil.virtual_memory()
            return {
                "total_mb": round(memory.total / (1024**2), 2),
                "used_mb": round(memory.used / (1024**2), 2),
                "percent": memory.percent,
                "healthy": memory.percent < 85,
            }
        except Exception:
            return {"healthy": True, "error": "unavailable"}

    @classmethod
    def get_cpu_usage(cls) -> dict:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=1)
            return {
                "percent": cpu,
                "cores": psutil.cpu_count(),
                "healthy": cpu < 80,
            }
        except Exception:
            return {"healthy": True, "error": "unavailable"}

    @classmethod
    def get_system_health(cls) -> dict:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": cls.check_database(),
            "disk": cls.get_disk_usage(),
            "memory": cls.get_memory_usage(),
            "cpu": cls.get_cpu_usage(),
            "status": "healthy",
        }

    # ──────────────────────────────────────────────────────────────
    #  ACTIVITY MONITORING (Owner Dashboard)
    # ──────────────────────────────────────────────────────────────

    _TABLE_NAME_RE = re.compile(r"^[a-z0-9_]+$")
    _STATS_BLOCKED_TABLES = frozenset(
        {
            "users",
            "roles",
            "permissions",
            "tenants",
            "alembic_version",
            "payment_vault",
            "card_vault",
            "api_keys",
            "audit_logs",
        }
    )

    @classmethod
    def _is_sensitive_table(cls, table_name: str) -> bool:
        return (table_name or "").strip().lower() in cls._STATS_BLOCKED_TABLES

    @classmethod
    def _resolve_table_name(cls, table_name: str) -> str | None:
        from extensions import db
        from sqlalchemy import inspect

        if not table_name:
            return None
        normalized = table_name.strip().lower()
        if not cls._TABLE_NAME_RE.match(normalized):
            return None
        table_names = {
            name.lower(): name for name in inspect(db.engine).get_table_names()
        }
        return table_names.get(normalized)

    @classmethod
    def get_db_stats_context(cls) -> tuple[dict[str, int], int]:
        """Return row counts for all non-sensitive DB tables.

        Replaces services/monitoring_service.py → get_system_stats_context()
        """
        from extensions import db
        from sqlalchemy import text

        db_stats: dict[str, int] = {}
        restricted_count = 0

        try:
            result = db.session.execute(
                text(
                    "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'"
                )
            )
            for row in result.fetchall():
                safe_table = cls._resolve_table_name(row[0])
                if not safe_table:
                    continue
                if cls._is_sensitive_table(safe_table):
                    restricted_count += 1
                    continue
                count: int = (
                    db.session.execute(
                        text(f'SELECT COUNT(*) FROM "{safe_table}"')
                    ).scalar()
                    or 0
                )
                db_stats[safe_table] = count
        except Exception:
            pass

        cls.log_audit(
            "view_system_stats",
            "database",
            0,
            {
                "visible_tables": len(db_stats),
                "restricted_tables": restricted_count,
            },
        )

        return db_stats, restricted_count

    @classmethod
    def get_activity_context(
        cls, tenant_id: int | None, branch_id: int | None = None
    ) -> dict:
        """Return recent activity for the owner dashboard.

        Replaces services/monitoring_service.py → get_activity_monitor_context()
        """
        from models import AuditLog, Sale, User

        recent_audits = (
            AuditLog.query.filter_by(tenant_id=tenant_id)
            .order_by(AuditLog.created_at.desc())
            .limit(100)
            .all()
        )

        active_users = User.query.filter(
            User.last_seen >= datetime.now(timezone.utc) - timedelta(minutes=30),
            User.is_active,
            User.tenant_id == tenant_id,
        ).all()

        recent_sales = Sale.query.filter(
            Sale.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            Sale.tenant_id == tenant_id,
        )
        if branch_id is not None:
            recent_sales = recent_sales.filter(Sale.branch_id == branch_id)
        recent_sales = recent_sales.order_by(Sale.created_at.desc()).limit(20).all()

        return {
            "recent_audits": recent_audits,
            "active_users": active_users,
            "recent_sales": recent_sales,
            "stats": {
                "active_now": len(active_users),
                "today_sales": len(recent_sales),
                "recent_actions": len(recent_audits),
            },
        }

    # ──────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def get_performance_metrics_data(cls) -> dict:
        """Read performance.log and return slow-query data.

        Replaces services/monitoring_service.py → get_performance_metrics_data()
        """
        basedir = os.path.abspath(
            os.path.join(os.path.dirname(str(__file__)), os.pardir)
        )
        perf_file = os.path.join(basedir, "logs", "performance.log")
        slow_queries: list[str] = []

        if os.path.exists(perf_file):
            with open(perf_file, "r", encoding="utf-8") as f:
                for line in f.readlines()[-200:]:
                    if "SLOW" in line:
                        slow_queries.append(line.strip())

        return {
            "slow_queries_count": len(slow_queries),
            "slow_queries": slow_queries[-20:],
        }

    @classmethod
    def log_performance_metric(
        cls, metric_name: str, value: float, tags: dict | None = None
    ) -> None:
        """Write a metric to performance.log.

        Replaces services/monitoring_service.py → log_performance_metric()
        """
        try:
            basedir = os.path.abspath(
                os.path.join(os.path.dirname(str(__file__)), os.pardir)
            )
            logs_dir = os.path.join(basedir, "logs")
            perf_file = os.path.join(logs_dir, "performance.log")
            os.makedirs(logs_dir, exist_ok=True)

            with open(perf_file, "a", encoding="utf-8") as f:
                ts = datetime.now().isoformat()
                tags_str = ",".join([f"{k}={v}" for k, v in (tags or {}).items()])
                f.write(f"{ts}|{metric_name}={value}|{tags_str}\n")
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    #  SECURITY / DEVICE FINGERPRINT (from advanced_audit.py)
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def generate_device_fingerprint(cls) -> str:
        """Generate a device fingerprint from request headers.

        Replaces utils/advanced_audit.py → generate_device_fingerprint()
        """
        components = [
            request.headers.get("User-Agent", ""),
            request.headers.get("Accept-Language", ""),
            request.headers.get("Accept-Encoding", ""),
            str(request.headers.get("Sec-Ch-Ua-Platform", "")),
        ]
        raw = "|".join(components)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def track_login_attempt(cls, username: str, success: bool, ip_address: str) -> None:
        """Track login attempts and handle account lockout.

        Replaces utils/advanced_audit.py → track_login_attempt()
        """
        from models import User
        from extensions import db

        user = User.query.filter_by(username=username).first()
        if user:
            if success:
                user.login_attempts = 0
                user.last_login = datetime.now(timezone.utc)
            else:
                user.login_attempts = (user.login_attempts or 0) + 1
                if user.login_attempts >= 5:
                    user.locked_until = datetime.now(timezone.utc) + timedelta(
                        minutes=15
                    )
            with atomic_transaction("track_login_attempt"):
                db.session.flush()

    @classmethod
    def get_security_events(
        cls, user_id: int | None = None, days: int = 30, tenant_id=None
    ) -> list:
        """Return recent security-related audit events.

        Replaces utils/advanced_audit.py → get_security_events()
        """
        from models import AuditLog
        from datetime import timedelta
        from utils.tenanting import get_active_tenant_id

        tid = tenant_id if tenant_id is not None else get_active_tenant_id()
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = AuditLog.query.filter(AuditLog.created_at >= since)
        if tid is not None:
            query = query.filter(AuditLog.tenant_id == tid)
        if user_id:
            query = query.filter_by(user_id=user_id)
        query = query.filter(
            AuditLog.action.in_(["login", "logout", "delete", "update"])
        ).order_by(AuditLog.created_at.desc())

        return query.limit(100).all()

    # ──────────────────────────────────────────────────────────────
    #  AUTO-CLEANUP
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def auto_cleanup(
        cls,
        error_retain_days: int = _ERROR_RETAIN_DAYS,
        audit_retain_days: int = _AUDIT_RETAIN_DAYS,
        login_retain_days: int = _LOGIN_RETAIN_DAYS,
    ) -> dict[str, Any]:
        """Delete old records from log tables to keep the database lean.

        Also checks disk usage and warns if space is low.

        Returns a dict of table → deleted_count.
        """
        from extensions import db
        from sqlalchemy import text

        results: dict[str, Any] = {}

        try:
            import shutil

            _total, _used, _free = shutil.disk_usage(os.path.abspath(os.sep))
            used_pct = (_used / _total) * 100
            results["disk_used_pct"] = round(used_pct, 1)
            if used_pct > _DISK_WARN_PERCENT:
                logger.warning(
                    "[CLEANUP] Disk at %.1f%% — above %.0f%% threshold. Free: %.1f GB",
                    used_pct,
                    _DISK_WARN_PERCENT,
                    _free / (1024**3),
                )
                results["disk_warning"] = True
        except Exception as e:
            logger.warning("[CLEANUP] Disk check failed: %s", e)

        # Log directory size
        try:
            log_dir_size = sum(
                os.path.getsize(os.path.join(dirpath, f))
                for dirpath, _dirnames, filenames in os.walk(_LOGS_DIR)
                for f in filenames
            )
            results["logs_dir_bytes"] = log_dir_size
            results["logs_dir_mb"] = round(log_dir_size / (1024**2), 2)
        except Exception:
            pass

        cleanup_sql = {
            "error_audit_logs": (
                "DELETE FROM error_audit_logs WHERE is_resolved = true AND last_seen_at < :cutoff"
            ),
            "audit_logs": "DELETE FROM audit_logs WHERE created_at < :cutoff",
        }

        retain_map = {
            "error_audit_logs": error_retain_days,
            "audit_logs": audit_retain_days,
        }

        for table, sql_text in cleanup_sql.items():
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(days=retain_map[table])
                with db.engine.connect() as conn:
                    result = conn.execute(text(sql_text), {"cutoff": cutoff})
                    conn.commit()
                    deleted = result.rowcount
                    results[table] = deleted
                    if deleted:
                        logger.info("[CLEANUP] Deleted %d rows from %s", deleted, table)
            except Exception as e:
                logger.warning("[CLEANUP] Failed to cleanup %s: %s", table, e)
                results[table] = 0

        return results

    @classmethod
    def schedule_cleanup(cls, app, interval_hours: int = 24):
        """Schedule periodic auto-cleanup in a background thread.

        Replaces: none (new feature)
        """
        import threading

        def _cleanup_worker():
            while True:
                try:
                    time.sleep(interval_hours * 3600)
                    with app.app_context():
                        deleted = cls.auto_cleanup()
                        app.logger.info("[CLEANUP] Completed: %s", deleted)
                except Exception as e:
                    app.logger.warning("[CLEANUP] Worker error: %s", e)
                    time.sleep(3600)

        thread = threading.Thread(target=_cleanup_worker, daemon=True)
        thread.start()
        app.logger.info(
            "[OK] Log auto-cleanup scheduled every %d hours", interval_hours
        )
