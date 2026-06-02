"""Multi-agent systems - coordination, intelligent assistant, master brain."""
from .multi_agent_system import MultiAgentCoordinator, get_agent_coordinator
from .intelligent_assistant import IntelligentAssistant, intelligent_assistant, intelligent_response
from .master_brain import MasterBrain, get_master_brain, ask_azad, quick_calc, explain_concept

__all__ = [
    'MultiAgentCoordinator',
    'get_agent_coordinator',
    'IntelligentAssistant',
    'intelligent_assistant',
    'intelligent_response',
    'MasterBrain',
    'get_master_brain',
    'ask_azad',
    'quick_calc',
    'explain_concept',
]
