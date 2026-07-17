"""
Consolidated module: core_engine.py
Re-exports from ai_knowledge.core sub-package (single source of truth).
"""

from ai_knowledge.core.context_engine import ContextEngine, context_engine
from ai_knowledge.core.conversation_manager import (
    ConversationManager,
    get_conversation_manager,
)
from ai_knowledge.core.memory_system import LongTermMemory, get_memory_system
from ai_knowledge.core.system_integration import SystemIntegrator, system_integrator
from ai_knowledge.core.reasoning_engine import ReasoningEngine, get_reasoning_engine

from ai_knowledge.analytics.data_analyzer import data_analyzer
from ai_knowledge.expansion.global_knowledge import global_connector
from ai_knowledge.expansion.knowledge_expansion import knowledge_expander
from ai_knowledge.generation.document_generator import document_generator
from ai_knowledge.specialized.advanced_laws import advanced_laws

import ai_knowledge.core.conversation_manager as _conversation_manager_mod
import ai_knowledge.core.memory_system as _memory_system_mod

__all__ = [
    "ContextEngine",
    "context_engine",
    "ConversationManager",
    "get_conversation_manager",
    "LongTermMemory",
    "get_memory_system",
    "SystemIntegrator",
    "system_integrator",
    "ReasoningEngine",
    "get_reasoning_engine",
    "data_analyzer",
    "global_connector",
    "knowledge_expander",
    "document_generator",
    "advanced_laws",
]


def __getattr__(name):
    if name == "_conversation_manager_instance":
        return _conversation_manager_mod._conversation_manager_instance
    if name == "_memory_instance":
        return _memory_system_mod._memory_instance
    if name in ("AzadLearningSystem", "learning_system"):
        import importlib

        mod = importlib.import_module("ai_knowledge.core.learning_system")
        val = getattr(mod, name)
        import sys as _sys

        setattr(_sys.modules[__name__], name, val)
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
