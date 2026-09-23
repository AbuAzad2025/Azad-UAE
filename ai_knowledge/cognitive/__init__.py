"""Native cognitive engine — deterministic, RBAC-gated, ERP-grounded."""

from __future__ import annotations

from ai_knowledge.cognitive import engine
from ai_knowledge.cognitive.contracts import CognitiveResult

__all__ = ["CognitiveResult", "engine", "process_cognitive_message"]


def process_cognitive_message(message: str, user: object | None = None) -> CognitiveResult:
    return engine.process(message, user)
