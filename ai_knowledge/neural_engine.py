"""Backward-compatible import shim.

``services.celery_tasks.train_neural_models`` imports
``ai_knowledge.neural_engine.get_neural_engine`` while the implementation
lives in ``ai_knowledge.neural.neural_engine``. This shim re-exports the
canonical symbols so background retraining resolves instead of raising
``ImportError`` at task runtime.
"""

from ai_knowledge.neural.neural_engine import (
    NEURAL_CACHE_SCHEMA_VERSION,
    NEURAL_RETRAIN_VOLUME_THRESHOLD,
    NEURAL_TRAIN_METHODS,
    AzadNeuralEngine,
    get_neural_engine,
)

__all__ = [
    "AzadNeuralEngine",
    "get_neural_engine",
    "NEURAL_CACHE_SCHEMA_VERSION",
    "NEURAL_RETRAIN_VOLUME_THRESHOLD",
    "NEURAL_TRAIN_METHODS",
]
