"""Core AI systems.
NOTE: learning_system is intentionally NOT re-exported here to avoid
shadowing the ai_knowledge.core.learning_system submodule with the
instance. Use ``from ai_knowledge.core.learning_system import ...`` directly.
"""

from ai_knowledge.core.memory_system import LongTermMemory, get_memory_system
from ai_knowledge.core.context_engine import context_engine
from ai_knowledge.core.conversation_manager import (
    ConversationManager,
    get_conversation_manager,
)
from ai_knowledge.core.reasoning_engine import ReasoningEngine, get_reasoning_engine
from ai_knowledge.core.system_integration import system_integrator

__all__ = [
    "LongTermMemory",
    "get_memory_system",
    "context_engine",
    "ConversationManager",
    "get_conversation_manager",
    "ReasoningEngine",
    "get_reasoning_engine",
    "system_integrator",
]
