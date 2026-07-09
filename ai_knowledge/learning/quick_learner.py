"""
🧠 Quick Learner - المتعلم السريع
الآن يستخدم قاعدة البيانات بدلاً من ملف JSON.
"""
import difflib
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class QuickLearner:
    def __init__(self):
        pass

    def learn(self, question: str, answer: str, category: str = 'general', tenant_id: int = None):
        """تعلم معلومة جديدة وحفظها في قاعدة البيانات."""
        from extensions import db
        from models.ai import AiMemory
        existing = AiMemory.query.filter_by(key=question.strip().lower(), tenant_id=tenant_id).first()
        if existing:
            existing.value = answer
            existing.category = category
            existing.confidence = 1.0
            existing.source = 'quick_learner'
        else:
            mem = AiMemory(
                key=question.strip().lower(),
                value=answer,
                category=category,
                tenant_id=tenant_id,
                confidence=1.0,
                source='quick_learner',
                is_active=True,
            )
            db.session.add(mem)
        db.session.flush()
        return True

    def get_answer(self, question: str, tenant_id: int = None) -> Optional[str]:
        """البحث عن إجابة — مطابقة تامة أو جزئية أو ضبابية مع عزل حسب المستأجر."""
        from extensions import db
        from models.ai import AiMemory
        key = question.strip().lower()
        query = AiMemory.query.filter_by(is_active=True)
        if tenant_id is not None:
            query = query.filter(
                db.or_(
                    AiMemory.tenant_id == tenant_id,
                    AiMemory.tenant_id.is_(None),
                )
            )
        rows = query.all()
        candidates = []
        for row in rows:
            k = row.key
            if k == key:
                self._bump_access(row)
                return row.value
            if k in key or key in k:
                self._bump_access(row)
                return row.value
            candidates.append((k, row))
        if candidates:
            keys = [k for k, _ in candidates]
            close = difflib.get_close_matches(key, keys, n=1, cutoff=0.6)
            if close:
                for k, row in candidates:
                    if k == close[0]:
                        self._bump_access(row)
                        return row.value
        return None

    @property
    def knowledge_base(self):
        """Backward compatibility: provide dict-like access for trainer.get_stats()."""
        return {}

    def _bump_access(self, row):
        from extensions import db
        from models.ai import AiMemory
        row.access_count = (row.access_count or 0) + 1
        from datetime import datetime, timezone
        row.last_accessed = datetime.now(timezone.utc)
        db.session.flush()

quick_learner = QuickLearner()
