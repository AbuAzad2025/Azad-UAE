"""Learning modules - consolidated in learning_engine.py"""
from ai_knowledge.learning_engine import (
    ContinuousLearner, continuous_learner,
    QuickLearner, quick_learner,
    AutoRetrainingScheduler, auto_retraining,
    get_external_learning, LEARNING_SOURCES_CATALOG,
)

__all__ = [
    'ContinuousLearner', 'continuous_learner',
    'QuickLearner', 'quick_learner',
    'AutoRetrainingScheduler', 'auto_retraining',
    'get_external_learning', 'LEARNING_SOURCES_CATALOG',
]
