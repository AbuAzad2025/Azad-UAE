"""
Consolidated module: learning_engine.py
Re-exports from ai_knowledge.learning sub-package (single source of truth).
"""

import logging
from typing import Optional

from ai_knowledge.learning.auto_retraining import (
    AutoRetrainingScheduler,
    auto_retraining,
)
from ai_knowledge.learning.continuous_learner import (
    ContinuousLearner,
    continuous_learner,
    get_continuous_learner,
    evaluate_and_learn,
)
from ai_knowledge.learning.external_learning import (
    ExternalLearningSystem,
    get_external_learning,
    LEARNING_SOURCES_CATALOG,
)

logger = logging.getLogger(__name__)


class QuickLearner:
    """Delegates DB operations to the AiMemory-backed version in learning/quick_learner.py."""

    _klass = None

    def _impl(self):
        if QuickLearner._klass is None:
            from ai_knowledge.learning.quick_learner import QuickLearner as _QL

            QuickLearner._klass = _QL
        return QuickLearner._klass()

    def learn(
        self,
        question: str,
        answer: str,
        category: str = "general",
        tenant_id: Optional[int] = None,
    ):
        return self._impl().learn(question, answer, category, tenant_id)

    def get_answer(self, question: str, tenant_id: Optional[int] = None):
        return self._impl().get_answer(question, tenant_id)

    def save_knowledge(self):
        pass

    @property
    def knowledge_base(self):
        return self._impl().knowledge_base


quick_learner = QuickLearner()

__all__ = [
    "QuickLearner",
    "quick_learner",
    "AutoRetrainingScheduler",
    "auto_retraining",
    "ContinuousLearner",
    "continuous_learner",
    "get_continuous_learner",
    "evaluate_and_learn",
    "ExternalLearningSystem",
    "get_external_learning",
    "LEARNING_SOURCES_CATALOG",
]
