"""Error Audit Service — logs errors independently of the main db.session.

Design principle: even if db.session is in a broken / rolled-back state,
this service MUST still be able to persist error records.

It uses db.engine.connect() directly (fresh connection) and performs an
explicit INSERT, bypassing the ORM session entirely.  This is a deliberate
trade-off: we lose ORM convenience but gain crash-proof durability.

Sanitization: passwords, tokens, API keys, and other secrets are
redacted from request_data before storage.
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from flask import has_request_context, request
from flask_login import current_user
from sqlalchemy import text

from extensions import db

logger = logging.getLogger(__name__)

# Sensitive field patterns (case-insensitive)
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
    }
)

_MAX_MESSAGE_LEN = 4000
_MAX_TRACE_LEN = 16000
_MAX_URL_LEN = 500
_MAX_UA_LEN = 255


class ErrorAuditService:
    """Unified error logger — backend, DB, frontend, system-init, API."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def log(
        message: str,
        *,
        category: str = "BACKEND",
        level: str = "ERROR",
        source: str = "unknown",
        exception: BaseException | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        """
        Persist one error record using a FRESH engine connection.

        Returns the inserted row id, or None if even the raw connection fails.
        """
        row_id = ErrorAuditService._persist(
            message=message,
            category=category,
            level=level,
            source=source,
            exception=exception,
            extra=extra,
        )
        # Also mirror to Python logger so file logs stay complete
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

    @staticmethod
    def log_exception(
        exc: BaseException,
        *,
        category: str = "BACKEND",
        source: str = "unknown",
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        """Convenience: derive message & traceback from an exception."""
        message = str(exc) or f"{type(exc).__name__} (no message)"
        return ErrorAuditService.log(
            message=message,
            category=category,
            level="ERROR",
            source=source,
            exception=exc,
            extra=extra,
        )

    @staticmethod
    def log_frontend(
        message: str,
        *,
        url: str | None = None,
        user_agent: str | None = None,
        stack: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        """Called by the JS-error endpoint."""
        return ErrorAuditService._persist(
            message=message,
            category="FRONTEND",
            level="ERROR",
            source="frontend.browser",
            url=url,
            user_agent=user_agent,
            stack_trace=stack,
            extra=extra,
        )

    @staticmethod
    def mark_resolved(log_id: int, user_id: int, note: str = "") -> bool:
        """Mark an error record as resolved."""
        try:
            sql = text(
                """
                UPDATE error_audit_logs
                SET is_resolved = true,
                    resolved_at = :now,
                    resolved_by = :user_id,
                    resolution_note = :note
                WHERE id = :log_id
                """
            )
            with db.engine.connect() as conn:
                conn.execute(
                    sql,
                    {
                        "now": datetime.now(timezone.utc),
                        "user_id": user_id,
                        "note": note[:500],
                        "log_id": log_id,
                    },
                )
                conn.commit()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal: raw INSERT via fresh engine connection
    # ------------------------------------------------------------------

    @staticmethod
    def _persist(
        message: str,
        *,
        category: str,
        level: str,
        source: str,
        exception: BaseException | None = None,
        url: str | None = None,
        method: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
        stack_trace: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        exc_type = type(exception).__name__ if exception else None
        trace = stack_trace
        if exception and not trace:
            trace = traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
            trace = "".join(trace)

        # Gather request context if inside a request
        if has_request_context() and request:
            url = url or request.url[:_MAX_URL_LEN]
            method = method or request.method
            user_agent = user_agent or (
                request.headers.get("User-Agent", "")[:_MAX_UA_LEN]
            )
            ip_address = ip_address or (
                request.headers.get("X-Forwarded-For", request.remote_addr) or ""
            )

        # Resolve user / tenant from current request context
        user_id = None
        tenant_id = None
        try:
            if has_request_context():
                from flask_login import current_user

                if getattr(current_user, "is_authenticated", False):
                    user_id = int(current_user.get_id())
                    tenant_id = getattr(current_user, "tenant_id", None)
        except Exception:
            pass

        # Sanitize request data
        request_data = None
        if extra:
            request_data = ErrorAuditService._sanitize_dict(extra)
        elif has_request_context() and request:
            payload: dict[str, Any] = {}
            try:
                if request.is_json:
                    payload = request.get_json(silent=True) or {}
                else:
                    payload = request.form.to_dict() if request.form else {}
            except Exception:
                pass
            request_data = ErrorAuditService._sanitize_dict(payload)

        sql = text(
            """
            INSERT INTO error_audit_logs (
                level, category, source, message, exception_type,
                stack_trace, url, method, ip_address, user_agent,
                user_id, tenant_id, request_data, is_resolved, created_at
            ) VALUES (
                :level, :category, :source, :message, :exception_type,
                :stack_trace, :url, :method, :ip_address, :user_agent,
                :user_id, :tenant_id, :request_data, false, :now
            ) RETURNING id
            """
        )

        params = {
            "level": (level or "ERROR")[:20],
            "category": (category or "BACKEND")[:30],
            "source": (source or "unknown")[:100],
            "message": (message or "")[:_MAX_MESSAGE_LEN],
            "exception_type": (exc_type or "")[:200],
            "stack_trace": (trace or "")[:_MAX_TRACE_LEN],
            "url": (url or "")[:_MAX_URL_LEN],
            "method": (method or "")[:10],
            "ip_address": (ip_address or "")[:50],
            "user_agent": (user_agent or "")[:_MAX_UA_LEN],
            "user_id": user_id,
            "tenant_id": tenant_id,
            "request_data": json.dumps(request_data, ensure_ascii=False, default=str)
            if request_data
            else None,
            "now": datetime.now(timezone.utc),
        }

        # ---- CRITICAL: use a FRESH engine connection, NOT db.session ----
        try:
            with db.engine.connect() as conn:
                result = conn.execute(sql, params)
                conn.commit()
                row = result.fetchone()
                return row[0] if row else None
        except Exception as engine_exc:
            # Even the raw engine failed — write to stderr as last resort
            try:
                import sys

                sys.stderr.write(
                    f"[ERROR_AUDIT_FALLBACK] {category} | {message[:200]} | "
                    f"engine_error={engine_exc}\n"
                )
            except Exception:
                pass
            return None

    # ------------------------------------------------------------------
    # Sanitization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
        """Return a copy with sensitive keys redacted."""
        if not isinstance(data, dict):
            return {}
        clean: dict[str, Any] = {}
        for key, value in data.items():
            k_lower = str(key).lower()
            if any(sk in k_lower for sk in _SECRET_KEYS):
                clean[key] = "***REDACTED***"
            elif isinstance(value, dict):
                clean[key] = ErrorAuditService._sanitize_dict(value)
            elif isinstance(value, list):
                clean[key] = [
                    ErrorAuditService._sanitize_dict(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                clean[key] = value
        return clean

    @staticmethod
    def _sanitize_string(value: str | None) -> str:
        if not value:
            return ""
        s = str(value)
        # Simple pattern redaction for common secret formats
        for pattern in (
            r"password['\"\s]*[:=]['\"\s]*[^\s&\"']+",
            r"token['\"\s]*[:=]['\"\s]*[^\s&\"']+",
            r"api_key['\"\s]*[:=]['\"\s]*[^\s&\"']+",
            r"Bearer\s+\S+",
        ):
            try:
                import re

                s = re.sub(pattern, "***REDACTED***", s, flags=re.IGNORECASE)
            except Exception:
                pass
        return s
