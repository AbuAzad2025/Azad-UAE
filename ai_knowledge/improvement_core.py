"""
Consolidated module: improvement_core.py
Re-exports from ai_knowledge.improvement sub-package (single source of truth).
"""

from ai_knowledge.improvement.self_reflection import SelfReflectionEngine, get_reflection_engine
from ai_knowledge.improvement.self_improvement import AzadSelfImprovement, self_improvement

__all__ = [
    'SelfReflectionEngine', 'get_reflection_engine',
    'AzadSelfImprovement', 'self_improvement',
]
