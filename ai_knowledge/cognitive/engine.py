"""Cognitive engine — the single decision point for local understanding.

Pipeline: normalize -> route -> RBAC firewall -> slots -> grounded plan ->
deterministic compose -> decision gate. Read-only: never writes to the DB.
"""

from __future__ import annotations

import logging
from typing import Any

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
    user_id = getattr(user, "id", None) if user is not None else None
    if not user_id:
        return []
    try:
        from models.ai import AiInteraction
        from utils.tenanting import tenant_query

        rows = (
            tenant_query(AiInteraction, user)
            .filter(AiInteraction.user_id == user_id)
            .order_by(AiInteraction.id.desc())
            .limit(limit)
            .all()
        )
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(minutes=15)
        result: list[tuple[str, str | None]] = []
        for row in rows:
            created = getattr(row, "created_at", None)
            if created is not None:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                if created < cutoff:
                    continue
            result.append((row.query or "", row.intent))
        return result
    except Exception as exc:
        logger.debug("Cognitive history unavailable: %s", exc)
        return []


def _previous_slots(
    intent: CognitiveIntent,
    past: list[tuple[str, str | None]],
    stored: dict[str, str] | None = None,
) -> dict[str, str]:
    wanted = "customer_name" if intent == CognitiveIntent.CUSTOMER_BALANCE else "supplier_name"
    if stored and stored.get(wanted):
        return {wanted: stored[wanted]}
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


def _resolve_slots(
    intent: CognitiveIntent,
    normalized: NormalizedMessage,
    past: list[tuple[str, str | None]],
    stored: dict[str, str] | None = None,
):
    slots = extract_slots(intent, normalized, _previous_slots(intent, past, stored))
    carried = _previous_slots(intent, past, stored)
    if stored:
        for key in ("days", "period_label", "currency"):
            if stored.get(key) and not slots.values.get(key):
                slots.values[key] = stored[key]
    elif carried:
        slots.values.update({key: value for key, value in carried.items() if not slots.values.get(key)})
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
    if status == "cost_denied":
        return CognitiveResult(
            success=True,
            response=composer.compose_denied(intent, "view_costs"),
            intent=intent.value,
            confidence=1.0,
            decision="denied",
            required_permission="view_costs",
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


def _conversational_result(intent, hypothesis, normalized) -> CognitiveResult:
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


def _unknown_result(hypothesis, normalized, user) -> CognitiveResult:
    from ai_knowledge.cognitive.fallback import try_dynamic_fallback

    dynamic = try_dynamic_fallback(normalized, user)
    if dynamic is not None:
        return dynamic
    return CognitiveResult(
        success=True,
        response=composer.compose_unknown(hypothesis),
        intent=CognitiveIntent.UNKNOWN.value,
        confidence=hypothesis.confidence,
        decision="clarify",
        needs_escalation=hypothesis.confidence < CLARIFY_THRESHOLD,
        trace=_trace_note("No reliable signal; asking targeted clarification.", hypothesis.confidence),
        provenance=Provenance(tenant_id=None),
    )


def process(message: str, user: object | None = None, cache: Any | None = None) -> CognitiveResult:
    from ai_knowledge.cognitive.followup import (
        clear_context,
        get_context,
        is_reset,
        permission_signature,
        set_context,
    )
    from utils.tenanting import get_active_tenant_id

    normalized = normalize_message(message)
    tenant_id = get_active_tenant_id(user)
    user_id = getattr(user, "id", None)
    signature = permission_signature(user)
    stored: dict[str, str] = {}
    if is_reset(message):
        clear_context(tenant_id, user_id)
        past = []
    else:
        stored = get_context(tenant_id, user_id, signature)
        past = _history(user)
    previous_intent = past[0][1] if past else None
    hypothesis = route(normalized, previous_intent)
    intent = hypothesis.intent

    if intent in CONVERSATIONAL_INTENTS and intent != CognitiveIntent.UNKNOWN:
        return _conversational_result(intent, hypothesis, normalized)
    if intent == CognitiveIntent.UNKNOWN:
        return _unknown_result(hypothesis, normalized, user)

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

    slots = _resolve_slots(intent, normalized, past, stored)
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

    set_context(tenant_id, user_id, signature, dict(slots.values))

    from ai_knowledge.cognitive.read_cache import get_default_cache, make_key

    active_cache = cache if cache is not None else get_default_cache()
    cache_key = make_key(normalized, intent, slots, user)
    if cache_key is not None:
        cached = active_cache.get(cache_key, user)
        if cached is not None:
            return cached
    result = _answer_data(intent, hypothesis, slots, user, required)
    if cache_key is not None and result.decision == "answer":
        active_cache.set(cache_key, result)
    return result
