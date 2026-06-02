"""Learning modules - continuous learning, quick learning, auto-retraining, external learning."""
from .continuous_learner import ContinuousLearner, continuous_learner
from .quick_learner import QuickLearner, quick_learner
from .auto_retraining import AutoRetrainingScheduler, auto_retraining
from .external_learning import get_external_learning, LEARNING_SOURCES_CATALOG

__all__ = [
    'ContinuousLearner',
    'continuous_learner',
    'QuickLearner',
    'quick_learner',
    'AutoRetrainingScheduler',
    'auto_retraining',
    'get_external_learning',
    'LEARNING_SOURCES_CATALOG',
]
