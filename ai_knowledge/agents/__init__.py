"""Multi-agent systems - imports from dedicated modules."""
from ai_knowledge.agents.multi_agent_system import MultiAgentCoordinator, get_agent_coordinator
from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant, intelligent_assistant
from ai_knowledge.agents.master_brain import MasterBrain, get_master_brain, ask_azad, quick_calc, explain_concept

__all__ = [
    'MultiAgentCoordinator', 'get_agent_coordinator',
    'IntelligentAssistant', 'intelligent_assistant',
    'MasterBrain', 'get_master_brain', 'ask_azad', 'quick_calc', 'explain_concept',
]
