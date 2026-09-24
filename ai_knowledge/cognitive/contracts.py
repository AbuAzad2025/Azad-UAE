"""Cognitive engine contracts — single unified taxonomy and machine-readable trace."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CognitiveIntent(StrEnum):
    GREETING = "greeting"
    HELP = "help"
    WHO_ARE_YOU = "who_are_you"
    SALES_SUMMARY = "sales_summary"
    CUSTOMER_BALANCE = "customer_balance"
    INVENTORY_STATUS = "inventory_status"
    PURCHASE_SUMMARY = "purchase_summary"
    EXPENSE_SUMMARY = "expense_summary"
    PAYMENT_STATUS = "payment_status"
    CHEQUE_STATUS = "cheque_status"
    GL_BALANCE = "gl_balance"
    HR_SUMMARY = "hr_summary"
    VAULT_BALANCE = "vault_balance"
    PATTERN_ANALYSIS = "pattern_analysis"
    PROFIT_MARGIN = "profit_margin"
    DEAD_STOCK = "dead_stock"
    TOP_PRODUCTS = "top_products"
    DEBT_OVERVIEW = "debt_overview"
    TAX_SUMMARY = "tax_summary"
    SUPPLIER_STATUS = "supplier_status"
    SYSTEM_GUIDE = "system_guide"
    UNKNOWN = "unknown"


CONVERSATIONAL_INTENTS = frozenset(
    {
        CognitiveIntent.GREETING,
        CognitiveIntent.HELP,
        CognitiveIntent.WHO_ARE_YOU,
        CognitiveIntent.SYSTEM_GUIDE,
        CognitiveIntent.UNKNOWN,
    }
)

DATA_INTENTS = frozenset(set(CognitiveIntent) - CONVERSATIONAL_INTENTS)


@dataclass(frozen=True)
class IntentHypothesis:
    intent: CognitiveIntent
    confidence: float
    evidence: tuple[str, ...] = ()
    alternatives: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class NormalizedMessage:
    raw: str
    text: str
    tokens: frozenset[str]
    numbers: tuple[float, ...] = ()
    currency_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlotSet:
    values: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReasoningStep:
    name: str
    observation: str
    confidence: float
    provenance: str = ""


@dataclass(frozen=True)
class ReasoningTrace:
    plan: tuple[str, ...]
    steps: tuple[ReasoningStep, ...]
    conclusion: str
    confidence: float


@dataclass(frozen=True)
class Provenance:
    tenant_id: int | None
    queries: tuple[str, ...] = ()
    row_counts: tuple[int, ...] = ()


@dataclass(frozen=True)
class CognitiveResult:
    success: bool
    response: str
    intent: str
    confidence: float
    decision: str
    trace: ReasoningTrace | None = None
    provenance: Provenance | None = None
    needs_escalation: bool = False
    required_permission: str = ""
