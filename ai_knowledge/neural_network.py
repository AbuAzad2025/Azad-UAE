"""
Consolidated module: neural_network.py
Re-exports from ai_knowledge.neural sub-package (single source of truth).
"""

from ai_knowledge.neural.vision_processor import VisionProcessor, get_vision_processor
from ai_knowledge.neural.transformers_brain import TransformersBrain, get_transformers_brain
from ai_knowledge.neural.semantic_matcher import (
    SemanticMatcher,
    semantic_matcher,
    understand_message,
    get_intent,
    get_confidence,
)
from ai_knowledge.neural.neural_engine import AzadNeuralEngine, get_neural_engine

__all__ = [
    'VisionProcessor', 'get_vision_processor',
    'TransformersBrain', 'get_transformers_brain',
    'SemanticMatcher', 'semantic_matcher', 'understand_message', 'get_intent', 'get_confidence',
    'AzadNeuralEngine', 'get_neural_engine',
]
