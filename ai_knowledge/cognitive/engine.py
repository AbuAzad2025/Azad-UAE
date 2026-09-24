"""Cognitive engine — the single decision point for local understanding.

Pipeline: normalize -> route -> RBAC firewall -> slots -> grounded plan ->
deterministic compose -> decision gate. Read-only: never writes to the DB.
"""

from __future__ import annotations

import logging

from ai_knowledge.cognitive import composer
from ai_knowledge.cognitive.access import check_access
from ai_knowledge.cognitive.contracts import (
    CONVERSATIONAL_INTENTS,
    CognitiveIntent,
    CognitiveResult,
    NormalizedMessage,
    Provenance,
    ReasoningTrace,
)
from ai_knowledge.cognitive.intent_router import route
from ai_knowledge.cognitive.normalizer import normalize_message
from ai_knowledge.cognitive.planner import plan_and_execute
from ai_knowledge.cognitive.slots import extract_slots

logger = logging.getLogger(__name__)

ANSWER_THRESHOLD = 0.75
CLARIFY_THRESHOLD = 0.40


def _history(user: object | None, limit: int = 6) -> list[tuple[str, str | None]]:
    if user is None or not getattr(user, "id", None):
        return []
    try:
        from models.ai import AiInteraction
        from utils.tenanting import tenant_query

        rows = (
            tenant_query(AiInteraction, user)
            .filter(AiInteraction.user_id == user.id)  # type: ignore[union-attr]
            .order_by(AiInteraction.id.desc())
            .limit(limit)
            .all()
        )
        return [(r.query or "", r.intent) for r in rows]
    except Exception as exc:
        logger.debug("Cognitive history unavailable: %s", exc)
        return []


def _previous_slots(intent: CognitiveIntent, past: list[tuple[str, str | None]]) -> dict[str, str]:
    wanted = "customer_name" if intent == CognitiveIntent.CUSTOMER_BALANCE else "supplier_name"
    for query, _saved in past:
        if not query:
            continue
        found = extract_slots(intent, normalize_message(query), None)
        if found.values.get(wanted):
            return {wanted: found.values[wanted]}
    return {}


def _single_token_name(normalized: NormalizedMessage, past: list[tuple[str, str | None]]) -> str:
    if len(normalized.tokens) != 1:
        return ""
    if not past or past[0][1] != CognitiveIntent.CUSTOMER_BALANCE.value:
        return ""
    token = next(iter(normalized.tokens)).strip("و؟?")
    return token if len(token) >= 2 else ""


def _trace_note(text: str, confidence: float) -> ReasoningTrace:
    from ai_knowledge.cognitive.contracts import ReasoningStep

    step = ReasoningStep("decision", text, confidence)
    return ReasoningTrace(plan=("decision",), steps=(step,), conclusion=text, confidence=confidence)


def _resolve_slots(intent: CognitiveIntent, normalized: NormalizedMessage, past: list[tuple[str, str | None]]):
    slots = extract_slots(intent, normalized, _previous_slots(intent, past))
    if intent == CognitiveIntent.CUSTOMER_BALANCE and slots.missing:
        rescued = _single_token_name(normalized, past)
        if rescued:
            slots = extract_slots(intent, normalized, {"customer_name": rescued})
    return slots


def _answer_data(intent, hypothesis, slots, user, required: str) -> CognitiveResult:
    status, trace, provenance, _data = plan_and_execute(intent, slots, user)
    if status == "no_tenant":
        return CognitiveResult(
            success=True,
            response=composer.compose_no_tenant(),
            intent=intent.value,
            confidence=hypothesis.confidence,
            decision="no_tenant",
            trace=trace,
            provenance=provenance,
        )
    response = composer.compose_data(intent, trace, provenance)
    return CognitiveResult(
        success=True,
        response=response,
        intent=intent.value,
        confidence=round(min(hypothesis.confidence, trace.confidence), 3),
        decision="answer",
        needs_escalation=hypothesis.confidence < ANSWER_THRESHOLD,
        trace=trace,
        provenance=provenance,
        required_permission=required,
    )


def process(message: str, user: object | None = None) -> CognitiveResult:
    normalized = normalize_message(message)
    past = _history(user)
    previous_intent = past[0][1] if past else None
    hypothesis = route(normalized, previous_intent)
    intent = hypothesis.intent

    if intent in CONVERSATIONAL_INTENTS and intent != CognitiveIntent.UNKNOWN:
        if intent == CognitiveIntent.SYSTEM_GUIDE:
            from ai_knowledge.cognitive.guide import resolve_guide_topic

            topic = resolve_guide_topic(normalized.tokens)
            return CognitiveResult(
                success=True,
                response=composer.compose_guide(topic),
                intent=intent.value,
                confidence=hypothesis.confidence,
                decision="conversational",
                trace=_trace_note(f"Guide topic={topic or 'index'}.", hypothesis.confidence),
                provenance=Provenance(tenant_id=None),
            )
        return CognitiveResult(
            success=True,
            response=composer.compose_conversational(intent),
            intent=intent.value,
            confidence=hypothesis.confidence,
            decision="conversational",
            trace=_trace_note(f"Conversational intent={intent.value}.", hypothesis.confidence),
            provenance=Provenance(tenant_id=None),
        )
    if intent == CognitiveIntent.UNKNOWN:
        from ai_knowledge.cognitive.fallback import try_dynamic_fallback

        dynamic = try_dynamic_fallback(normalized, user)
        if dynamic is not None:
            return dynamic
        return CognitiveResult(
            success=True,
            response=composer.compose_unknown(hypothesis),
            intent=intent.value,
            confidence=hypothesis.confidence,
            decision="clarify",
            needs_escalation=hypothesis.confidence < CLARIFY_THRESHOLD,
            trace=_trace_note("No reliable signal; asking targeted clarification.", hypothesis.confidence),
            provenance=Provenance(tenant_id=None),
        )

    allowed, required = check_access(intent, user)
    if not allowed:
        return CognitiveResult(
            success=True,
            response=composer.compose_denied(intent, required),
            intent=intent.value,
            confidence=hypothesis.confidence,
            decision="denied",
            required_permission=required,
            trace=_trace_note(f"RBAC denial; requires {required}. No data touched.", 1.0),
            provenance=Provenance(tenant_id=None),
        )

    slots = _resolve_slots(intent, normalized, past)
    if slots.missing:
        return CognitiveResult(
            success=True,
            response=composer.compose_need_slots(intent, slots),
            intent=intent.value,
            confidence=hypothesis.confidence,
            decision="clarify",
            trace=_trace_note(f"Missing slots: {', '.join(slots.missing)}.", 1.0),
            provenance=Provenance(tenant_id=None),
        )

    return _answer_data(intent, hypothesis, slots, user, required)
