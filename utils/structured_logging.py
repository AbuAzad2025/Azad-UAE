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


def _resolve_id(value):
    """Safely extract a numeric ID from a value that might be a model object."""
    if value is None:
        return None
    if isinstance(value, (int, str)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return str(value)
    # Check if it looks like a SQLAlchemy model instance (has .id)
    obj_id = getattr(value, 'id', None)
    if obj_id is not None:
        return obj_id
    return str(value)


def log_mutation(
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict | None = None,
    level: str = "info"
):
    """
    Log a mutation event with full context.

    Args:
        action: e.g., 'create', 'update', 'delete', 'approve', 'reject'
        entity_type: e.g., 'Sale', 'Purchase', 'Payment', 'User'
        entity_id: Primary key of affected entity (int, str, or model object with .id)
        details: Additional context (exclude sensitive data like passwords)
        level: logging level
    """
    # Defensively resolve entity_id in case a model object was passed
    resolved_id = _resolve_id(entity_id)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "mutation",
        "action": action,
        "entity_type": entity_type or '',
        "entity_id": resolved_id,
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
    extra: dict | None = None
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
    entity_id: int | None = None,
    access_type: str = "read",
    details: dict | None = None
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
