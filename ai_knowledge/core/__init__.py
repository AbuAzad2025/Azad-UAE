"""Core AI systems - consolidated in core_engine.py.
NOTE: learning_system is intentionally NOT re-exported here to avoid
shadowing the ai_knowledge.core.learning_system submodule with the
instance. Use ``from ai_knowledge.core.learning_system import ...`` directly.
"""
from ai_knowledge.core_engine import (  # noqa: F401
    LongTermMemory, get_memory_system,
    context_engine,
    ConversationManager, get_conversation_manager,
    ReasoningEngine, get_reasoning_engine,
    system_integrator,
)

__all__ = [
    'LongTermMemory', 'get_memory_system',
    'context_engine', 'ConversationManager', 'get_conversation_manager',
    'ReasoningEngine', 'get_reasoning_engine', 'system_integrator',
]
