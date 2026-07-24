"""Multi-agent systems - imports from dedicated modules."""

from ai_knowledge.agents.intelligent_assistant import (
    IntelligentAssistant,
    intelligent_assistant,
)
from ai_knowledge.agents.master_brain import (
    MasterBrain,
    ask_azad,
    explain_concept,
    get_master_brain,
    quick_calc,
)
from ai_knowledge.agents.multi_agent_system import (
    MultiAgentCoordinator,
    get_agent_coordinator,
)

__all__ = [
    "IntelligentAssistant",
    "MasterBrain",
    "MultiAgentCoordinator",
    "ask_azad",
    "explain_concept",
    "get_agent_coordinator",
    "get_master_brain",
    "intelligent_assistant",
    "quick_calc",
]
