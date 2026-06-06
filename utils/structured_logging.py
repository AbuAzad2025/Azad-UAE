"""
Structured JSON Logging for Azad ERP
All mutations (create, update, delete) are logged with context.
"""
import json
import logging
from datetime import datetime, timezone
from flask import has_request_context, request
from flask_login import current_user

logger = logging.getLogger("azad_audit")


def _get_request_context():
    """Extract request context if available."""
    if not has_request_context():
        return {}
    return {
        "ip_address": request.remote_addr,
        "user_agent": request.headers.get("User-Agent", "")[:200],
        "endpoint": request.endpoint,
        "method": request.method,
        "url": request.url[:500],
    }


def _get_user_context():
    """Extract user context if available."""
    try:
        if current_user and current_user.is_authenticated:
            return {
                "user_id": getattr(current_user, "id", None),
                "username": getattr(current_user, "username", None),
                "tenant_id": getattr(current_user, "tenant_id", None),
                "is_owner": getattr(current_user, "is_owner", False),
            }
    except Exception:
        pass
    return {}


def log_mutation(
    action: str,
    entity_type: str,
    entity_id: int = None,
    details: dict = None,
    level: str = "info"
):
    """
    Log a mutation event with full context.

    Args:
        action: e.g., 'create', 'update', 'delete', 'approve', 'reject'
        entity_type: e.g., 'Sale', 'Purchase', 'Payment', 'User'
        entity_id: Primary key of affected entity
        details: Additional context (exclude sensitive data like passwords)
        level: logging level
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "mutation",
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details or {},
        "user": _get_user_context(),
        "request": _get_request_context(),
    }

    log_func = getattr(logger, level, logger.info)
    log_func(json.dumps(log_entry, ensure_ascii=False, default=str))


def log_security_event(
    event_type: str,
    description: str,
    severity: str = "info",
    extra: dict = None
):
    """Log security-related events (login attempts, permission denials, etc.)."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "security",
        "security_event": event_type,
        "description": description,
        "severity": severity,
        "user": _get_user_context(),
        "request": _get_request_context(),
        "extra": extra or {},
    }

    log_func = getattr(logger, severity if severity != "alert" else "warning", logger.info)
    log_func(json.dumps(log_entry, ensure_ascii=False, default=str))


def log_data_access(
    entity_type: str,
    entity_id: int = None,
    access_type: str = "read",
    details: dict = None
):
    """Log sensitive data access (for compliance auditing)."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "data_access",
        "access_type": access_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details or {},
        "user": _get_user_context(),
        "request": _get_request_context(),
    }
    logger.info(json.dumps(log_entry, ensure_ascii=False, default=str))
