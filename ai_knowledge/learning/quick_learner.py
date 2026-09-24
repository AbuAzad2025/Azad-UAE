"""
🧠 Quick Learner - المتعلم السريع
الآن يستخدم قاعدة البيانات بدلاً من ملف JSON.
"""

import difflib
import logging
from datetime import UTC

logger = logging.getLogger(__name__)


class QuickLearner:
    def __init__(self):
        pass

    @staticmethod
    def learn(
        question: str,
        answer: str,
        category: str = "general",
        tenant_id: int | None = None,
    ):
        """تعلم معلومة جديدة وحفظها في قاعدة البيانات."""
        from extensions import db
        from models.ai import AiMemory

        existing = AiMemory.query.filter_by(key=question.strip().lower(), tenant_id=tenant_id).first()
        if existing:
            existing.value = answer
            existing.category = category
            existing.confidence = 1.0
            existing.source = "quick_learner"
        else:
            mem = AiMemory(
                key=question.strip().lower(),
                value=answer,
                category=category,
                tenant_id=tenant_id,
                confidence=1.0,
                source="quick_learner",
                is_active=True,
            )
            db.session.add(mem)
        db.session.flush()
        return True

    def get_answer(self, question: str, tenant_id: int | None = None) -> str | None:
        """البحث عن إجابة — مطابقة تامة ثم جزئية ثم ضبابية، كلها داخل نطاق المستأجر.

        When ``tenant_id`` is given, only that tenant's rows are considered —
        global (NULL-tenant) rows are never returned to a tenanted caller.
        Callers without a tenant (system seeding) keep the legacy scope.
        """
        from models.ai import AiMemory

        key = question.strip().lower()
        query = AiMemory.query.filter_by(is_active=True)
        if tenant_id is not None:
            query = query.filter(AiMemory.tenant_id == tenant_id)
        rows = query.all()
        for row in rows:
            if row.key == key:
                self._bump_access(row)
                return row.value
        ordered = sorted(rows, key=lambda row: len(row.key or ""), reverse=True)
        for row in ordered:
            candidate = row.key or ""
            if candidate and candidate != key and (candidate in key or key in candidate):
                self._bump_access(row)
                return row.value
        if ordered:
            keys = [row.key for row in ordered if row.key]
            close = difflib.get_close_matches(key, keys, n=1, cutoff=0.6)
            if close:
                for row in ordered:
                    if row.key == close[0]:
                        self._bump_access(row)
                        return row.value
        return None

    @property
    def knowledge_base(self):
        """Backward compatibility: provide dict-like access for trainer.get_stats()."""
        return {}

    @staticmethod
    def _bump_access(row):
        from extensions import db

        row.access_count = (row.access_count or 0) + 1
        from datetime import datetime

        row.last_accessed = datetime.now(UTC)
        db.session.flush()


quick_learner = QuickLearner()
