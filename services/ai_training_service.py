"""Owner AI-training service — tenant-scoped memory management.

Pure business logic: flush-only, never commit/rollback (the caller wraps
writes in ``atomic_transaction``).
"""

from __future__ import annotations

import logging

from extensions import db
from models.ai import AiMemory
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = frozenset({"general", "learned", "corrected", "expertise", "system"})
LIST_LIMIT = 200
SEARCH_LIMIT = 60


def _clean(value: object, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def list_memories(
    tenant_id: int,
    search: str = "",
    category: str = "",
    include_inactive: bool = False,
) -> list[dict]:
    """Tenant-scoped memory rows for the owner training table."""
    query = tenant_query(AiMemory).filter(AiMemory.tenant_id == int(tenant_id))
    if not include_inactive:
        query = query.filter(AiMemory.is_active.is_(True))
    if category in ALLOWED_CATEGORIES:
        query = query.filter(AiMemory.category == category)
    term = _clean(search, SEARCH_LIMIT).lower()
    if term:
        like = f"%{term}%"
        query = query.filter(db.or_(AiMemory.key.ilike(like), AiMemory.value.ilike(like)))
    rows = query.order_by(AiMemory.updated_at.desc()).limit(LIST_LIMIT).all()
    return [row.to_dict() for row in rows]


def count_memories(tenant_id: int) -> dict[str, int]:
    """Small stats block for the training dashboard header."""
    rows = tenant_query(AiMemory).filter(AiMemory.tenant_id == int(tenant_id)).limit(5000).all()
    stats: dict[str, int] = {"total": 0, "active": 0, "corrected": 0}
    for row in rows:
        stats["total"] += 1
        if row.is_active:
            stats["active"] += 1
        if row.category == "corrected":
            stats["corrected"] += 1
    return stats


def add_qa(question: str, answer: str, category: str, tenant_id: int) -> dict:
    """Create or refresh one tenant-scoped Q&A pair (flush only)."""
    key = _clean(question, 255).lower()
    value = _clean(answer, 4000)
    if not key or not value:
        raise ValueError("السؤال والإجابة مطلوبان.")
    if category not in ALLOWED_CATEGORIES or category in ("system", "expertise"):
        category = "general"
    existing = tenant_query(AiMemory).filter(AiMemory.tenant_id == int(tenant_id), AiMemory.key == key).first()
    if existing:
        existing.value = value
        existing.category = category
        existing.confidence = 1.0
        existing.source = "owner_training"
        existing.is_active = True
        db.session.flush()
        logger.info("Owner refreshed AI memory key=%s tenant=%s", key[:40], tenant_id)
        return existing.to_dict()
    mem = AiMemory(
        key=key,
        value=value,
        category=category,
        tenant_id=int(tenant_id),
        confidence=1.0,
        source="owner_training",
        is_active=True,
    )
    db.session.add(mem)
    db.session.flush()
    logger.info("Owner added AI memory key=%s tenant=%s", key[:40], tenant_id)
    return mem.to_dict()


def toggle_memory(memory_id: int, tenant_id: int, active: bool) -> dict:
    """Activate/deactivate one memory row after a tenant-ownership check."""
    from flask import abort

    mem = db.session.get(AiMemory, int(memory_id))
    if mem is None or int(mem.tenant_id or 0) != int(tenant_id):
        abort(404)
    mem.is_active = bool(active)
    db.session.flush()
    logger.info("Owner toggled AI memory id=%s active=%s tenant=%s", mem.id, active, tenant_id)
    return mem.to_dict()


def submit_correction(question: str, correct_answer: str, tenant_id: int, user_id: int | None) -> dict:
    """Store an owner correction via the trainer (flush only, tenant-scoped)."""
    from ai_knowledge.trainer import trainer

    key = _clean(question, 255)
    value = _clean(correct_answer, 4000)
    if not key or not value:
        raise ValueError("السؤال والتصحيح مطلوبان.")
    trainer.train_from_feedback(key, value, user_id=user_id, tenant_id=int(tenant_id))
    logger.info("Owner corrected AI answer tenant=%s", tenant_id)
    return {"question": key, "corrected": True}
