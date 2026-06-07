"""Error Audit Service — logs errors independently of the main db.session.

Design principle: even if db.session is in a broken / rolled-back state,
this service MUST still be able to persist error records.

It uses db.engine.connect() directly (fresh connection) and performs an
explicit INSERT / UPDATE, bypassing the ORM session entirely.

Features:
- Deduplication: same fingerprint within 10 min → updates occurrence_count.
- Fingerprint: SHA-256 of category + exception_type + source + endpoint.
- Request ID: carried across app logs, error logs, and response headers.
- Sanitization: passwords, tokens, API keys redacted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import traceback
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlparse

from flask import current_app, g, has_request_context, request, render_template
from flask_login import current_user
from sqlalchemy import text, func
from models.error_audit_log import ErrorAuditLog
from io import StringIO, BytesIO
import json
from extensions import db

logger = logging.getLogger(__name__)

# ── Limits ──────────────────────────────────────────────────────
_MAX_MESSAGE_LEN = 4000
_MAX_TRACE_LEN = 4000  # smaller for client-side
_MAX_URL_LEN = 500
_MAX_UA_LEN = 255
_DEDUP_WINDOW_MINUTES = 10

# Sensitive field patterns (case-insensitive)
_SECRET_KEYS = frozenset(
    {
        "password", "password_hash", "password_confirmation",
        "current_password", "new_password", "token", "access_token",
        "refresh_token", "api_key", "api_secret", "secret", "secret_key",
        "csrf_token", "auth_token", "session_token", "credit_card",
        "cvv", "cvc", "card_number", "bank_account", "iban",
    }
)


class ErrorAuditService:
    """Unified error logger with deduplication and fingerprinting."""

    @staticmethod
    def get_logs_query(category: str, level: str, is_resolved: str):
        query = ErrorAuditLog.query
        if category:
            query = query.filter_by(category=category)
        if level:
            query = query.filter_by(level=level)
        if is_resolved == '1':
            query = query.filter_by(is_resolved=True)
        elif is_resolved == '0':
            query = query.filter_by(is_resolved=False)
        return query.order_by(ErrorAuditLog.created_at.desc())

    @staticmethod
    def get_dropdowns():
        categories = [r[0] for r in db.session.query(ErrorAuditLog.category).distinct().order_by(ErrorAuditLog.category).all()]
        levels = [r[0] for r in db.session.query(ErrorAuditLog.level).distinct().order_by(ErrorAuditLog.level).all()]
        return categories, levels

    @staticmethod
    def get_stats():
        return {
            'total': ErrorAuditLog.query.count(),
            'unresolved': ErrorAuditLog.query.filter_by(is_resolved=False).count(),
            'critical': ErrorAuditLog.query.filter_by(level='CRITICAL').count(),
        }

    @staticmethod
    def get_export_payload(category, level, is_resolved, fmt):
        query = ErrorAuditService.get_logs_query(category, level, is_resolved)
        logs = query.all()

        if fmt == 'json':
            data = [log.to_dict() for log in logs]
            return json.dumps(data, ensure_ascii=False, indent=2, default=str), 'application/json', "error_audit_logs.json"

        buf = StringIO()
        buf.write("=" * 80 + "\n")
        buf.write("Error Audit Logs Export\n")
        buf.write("Generated: " + datetime.now(timezone.utc).isoformat() + "\n")
        buf.write("Count: " + str(len(logs)) + "\n")
        buf.write("=" * 80 + "\n\n")

        for log in logs:
            buf.write(f"ID:         {log.id}\n")
            buf.write(f"Level:      {log.level}\n")
            buf.write(f"Category:   {log.category}\n")
            buf.write(f"Source:     {log.source}\n")
            buf.write(f"Time:       {log.created_at.isoformat() if log.created_at else '-'}\n")
            buf.write(f"URL:        {log.url or '-'}\n")
            buf.write(f"User:       {log.user_id or '-'} | Tenant: {log.tenant_id or '-'}\n")
            buf.write(f"Resolved:   {'YES' if log.is_resolved else 'NO'}\n")
            buf.write(f"Message:\n  {log.message}\n")
            if log.stack_trace:
                buf.write(f"Stack Trace:\n  {log.stack_trace[:500]}\n")
            if log.request_data:
                buf.write(f"Request Data:\n  {log.request_data}\n")
            buf.write("-" * 80 + "\n\n")

        return buf.getvalue().encode('utf-8'), 'text/plain; charset=utf-8', "error_audit_logs.txt"
    # ── Public API ──────────────────────────────────────────────

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
        """Persist one error record (or bump existing fingerprint)."""
        row_id = ErrorAuditService._persist(
            message=message,
            category=category,
            level=level,
            source=source,
            exception=exception,
            extra=extra,
        )
        try:
            logger.error(
                "[ErrorAuditLog %s] %s | source=%s | id=%s",
                category, message[:200], source, row_id,
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
        level: str = "ERROR",
        source: str = "frontend.browser",
        url: str | None = None,
        user_agent: str | None = None,
        stack: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        """Called by the JS-error endpoint (pre-validated payload)."""
        # Client-side stack traces can be huge — truncate
        if stack and len(stack) > _MAX_TRACE_LEN:
            stack = stack[:_MAX_TRACE_LEN] + "\n...[truncated]"
        return ErrorAuditService._persist(
            message=message,
            category="FRONTEND",
            level=level,
            source=source,
            url=url,
            user_agent=user_agent,
            stack_trace=stack,
            extra=extra,
        )

    @staticmethod
    def mark_resolved(log_id: int, user_id: int, note: str = "") -> bool:
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

    # ── Request ID ──────────────────────────────────────────────

    @staticmethod
    def get_or_create_request_id() -> str:
        """Return existing request_id or generate a new UUID-4."""
        if has_request_context():
            rid = getattr(g, "request_id", None)
            if rid:
                return rid
            rid = str(uuid.uuid4())
            g.request_id = rid
            return rid
        return str(uuid.uuid4())

    # ── Internal persistence with dedup ───────────────────────────

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

        # Request context
        _url = url
        _method = method
        _ua = user_agent
        _ip = ip_address
        if has_request_context() and request:
            _url = _url or request.url[:_MAX_URL_LEN]
            _method = _method or request.method
            _ua = _ua or (request.headers.get("User-Agent", "")[:_MAX_UA_LEN])
            _ip = _ip or (request.headers.get("X-Forwarded-For", request.remote_addr) or "")

        # User / tenant
        user_id = None
        tenant_id = None
        try:
            if has_request_context():
                if getattr(current_user, "is_authenticated", False):
                    user_id = int(current_user.get_id())
                    tenant_id = getattr(current_user, "tenant_id", None)
        except Exception:
            pass

        # Request ID
        request_id = ErrorAuditService.get_or_create_request_id()

        # Environment / version
        environment = "production"
        app_version = ""
        try:
            environment = current_app.config.get("FLASK_ENV", "production")
            app_version = current_app.config.get("APP_VERSION", "")
        except Exception:
            pass

        # Sanitize
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

        # Endpoint path (for fingerprint consistency)
        endpoint_path = ""
        try:
            if category == "FRONTEND" and _url:
                endpoint_path = urlparse(_url).path or _url[:200]
            elif has_request_context() and request:
                endpoint_path = request.path or ""
        except Exception:
            pass

        # Fingerprint
        fingerprint_message = message
        if category == "FRONTEND" and isinstance(request_data, dict):
            fingerprint_message = str(request_data.get("fingerprint_key") or message)
        fingerprint = ErrorAuditService._make_fingerprint(
            category, exc_type or "", source, endpoint_path, fingerprint_message
        )

        # ── Deduplication check ────────────────────────────────
        dup_id = ErrorAuditService._find_duplicate(fingerprint)
        if dup_id:
            updated = ErrorAuditService._bump_duplicate(dup_id, message, trace)
            if updated:
                return dup_id

        # ── Fresh INSERT ───────────────────────────────────────
        sql = text(
            """
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
            """
        )

        params = {
            "fingerprint": fingerprint,
            "level": (level or "ERROR")[:20],
            "category": (category or "BACKEND")[:30],
            "source": (source or "unknown")[:100],
            "message": (message or "")[:_MAX_MESSAGE_LEN],
            "exception_type": (exc_type or "")[:200],
            "stack_trace": (trace or "")[:_MAX_TRACE_LEN],
            "request_id": request_id,
            "url": (_url or "")[:_MAX_URL_LEN],
            "method": (_method or "")[:10],
            "ip_address": (_ip or "")[:50],
            "user_agent": (_ua or "")[:_MAX_UA_LEN],
            "environment": environment[:20],
            "app_version": (app_version or "")[:30],
            "user_id": user_id,
            "tenant_id": tenant_id,
            "request_data": json.dumps(request_data, ensure_ascii=False, default=str)
            if request_data else None,
            "now": datetime.now(timezone.utc),
        }

        try:
            with db.engine.connect() as conn:
                result = conn.execute(sql, params)
                conn.commit()
                row = result.fetchone()
                return row[0] if row else None
        except Exception as engine_exc:
            try:
                import sys
                sys.stderr.write(
                    f"[ERROR_AUDIT_FALLBACK] {category} | {message[:200]} | "
                    f"engine_error={engine_exc}\n"
                )
            except Exception:
                pass
            return None

    # ── Deduplication helpers ─────────────────────────────────────

    @staticmethod
    def _make_fingerprint(
        category: str,
        exc_type: str,
        source: str,
        endpoint: str,
        message: str = "",
    ) -> str:
        message_key = " ".join((message or "").split())[:160]
        raw = f"{category}::{exc_type}::{source}::{endpoint}::{message_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _find_duplicate(fingerprint: str) -> int | None:
        """Look for an existing unresolved record with same fingerprint within dedup window."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=_DEDUP_WINDOW_MINUTES)
            sql = text(
                """
                SELECT id FROM error_audit_logs
                WHERE fingerprint = :fp
                  AND is_resolved = false
                  AND last_seen_at > :cutoff
                ORDER BY last_seen_at DESC
                LIMIT 1
                """
            )
            with db.engine.connect() as conn:
                result = conn.execute(sql, {"fp": fingerprint, "cutoff": cutoff})
                row = result.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    @staticmethod
    def _bump_duplicate(log_id: int, new_message: str, new_trace: str | None) -> bool:
        """Increment occurrence_count and update last_seen_at / message."""
        try:
            sql = text(
                """
                UPDATE error_audit_logs
                SET occurrence_count = occurrence_count + 1,
                    last_seen_at = :now,
                    message = :message,
                    stack_trace = COALESCE(:stack_trace, stack_trace)
                WHERE id = :log_id
                """
            )
            with db.engine.connect() as conn:
                conn.execute(
                    sql,
                    {
                        "now": datetime.now(timezone.utc),
                        "message": (new_message or "")[:_MAX_MESSAGE_LEN],
                        "stack_trace": (new_trace or "")[:_MAX_TRACE_LEN] if new_trace else None,
                        "log_id": log_id,
                    },
                )
                conn.commit()
            return True
        except Exception:
            return False

    # ── Sanitization helpers ──────────────────────────────────────

    @staticmethod
    def _sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
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
