"""Persist conversation context in DB instead of a global dict."""
from datetime import datetime, timezone, timedelta
import json
from extensions import db
from models.ai import AiMemory


def _get_ctx_key(user_id: int) -> str:
    return f"conversation_context:{user_id}"


def get_context(user_id: int, tenant_id: int = None):
    """Retrieve saved conversation context from DB."""
    mem = AiMemory.query.filter_by(
        key=_get_ctx_key(user_id),
        tenant_id=tenant_id,
        is_active=True,
        category="conversation",
    ).first()
    if not mem:
        return None
    try:
        data = json.loads(mem.value)
        updated = mem.last_accessed or mem.created_at
        if updated and datetime.now(timezone.utc) - updated > timedelta(hours=2):
            mem.is_active = False
            db.session.commit()
            return None
        mem.access_count = (mem.access_count or 0) + 1
        mem.last_accessed = datetime.now(timezone.utc)
        db.session.commit()
        return data
    except Exception:
        return None


def set_context(user_id: int, data: dict, tenant_id: int = None):
    """Persist conversation context in DB."""
    key = _get_ctx_key(user_id)
    mem = AiMemory.query.filter_by(
        key=key,
        tenant_id=tenant_id,
        category="conversation",
    ).first()
    if mem:
        mem.value = json.dumps(data, ensure_ascii=False)
        mem.is_active = True
        mem.updated_at = datetime.now(timezone.utc)
    else:
        mem = AiMemory(
            key=key,
            value=json.dumps(data, ensure_ascii=False),
            category="conversation",
            tenant_id=tenant_id,
            confidence=1.0,
            source="conversation_store",
            is_active=True,
        )
        db.session.add(mem)
    db.session.commit()


def clear_context(user_id: int, tenant_id: int = None):
    """Expire conversation context."""
    key = _get_ctx_key(user_id)
    mem = AiMemory.query.filter_by(
        key=key,
        tenant_id=tenant_id,
        category="conversation",
    ).first()
    if mem:
        mem.is_active = False
        mem.updated_at = datetime.now(timezone.utc)
        db.session.commit()
