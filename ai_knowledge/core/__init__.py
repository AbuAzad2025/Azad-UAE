"""Core AI systems - consolidated in core_engine.py"""
from ai_knowledge.core_engine import (
    learning_system,
    LongTermMemory, get_memory_system,
    context_engine,
    ConversationManager, get_conversation_manager,
    ReasoningEngine, get_reasoning_engine,
    system_integrator,
)

__all__ = [
    'learning_system', 'LongTermMemory', 'get_memory_system',
    'context_engine', 'ConversationManager', 'get_conversation_manager',
    'ReasoningEngine', 'get_reasoning_engine', 'system_integrator',
]
