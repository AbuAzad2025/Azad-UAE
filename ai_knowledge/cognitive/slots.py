"""Slot extraction with history carryover (pure text ops; DB grounding lives in planner)."""

from __future__ import annotations

import re

from ai_knowledge.cognitive.contracts import CognitiveIntent, NormalizedMessage, SlotSet

REQUIRED_SLOTS: dict[CognitiveIntent, tuple[str, ...]] = {
    CognitiveIntent.CUSTOMER_BALANCE: ("customer_name",),
}

_NAME_AFTER_MARKER = re.compile(
    r"(?:العميل|الزبون|عميل|زبون|customer)\s+([^\d،,؛:()]{2,60}?)(?:\s+[؟?]|$)",
    re.IGNORECASE,
)
_COLON_FORM = re.compile(r"^(?:رصيد|balance)\s*[:：=]\s*(.+)$", re.IGNORECASE)
_DAYS_RE = re.compile(r"(\d+)\s*(?:يوم|days?)", re.IGNORECASE)


def _clean_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value).strip(" ؟?.,؛:()\"'«»")
    stop = {"اليوم", "هالشهر", "الشهر", "امس", "أمس", "هالاسبوع"}
    return " ".join(t for t in name.split(" ") if t and t not in stop)[:60]


def extract_slots(
    intent: CognitiveIntent,
    normalized: NormalizedMessage,
    previous_slots: dict[str, str] | None = None,
) -> SlotSet:
    values: dict[str, str] = {}
    if intent == CognitiveIntent.CUSTOMER_BALANCE:
        colon = _COLON_FORM.match(normalized.raw.strip())
        if colon and colon.group(1).strip():
            values["customer_name"] = _clean_name(colon.group(1))
        else:
            marker = _NAME_AFTER_MARKER.search(normalized.raw)
            if marker and marker.group(1).strip():
                values["customer_name"] = _clean_name(marker.group(1))
        if not values.get("customer_name") and previous_slots:
            carried = (previous_slots.get("customer_name") or "").strip()
            if carried and len(normalized.tokens) <= 4:
                values["customer_name"] = carried
                values["carried_from_history"] = "1"
    days = _DAYS_RE.search(normalized.raw)
    if days:
        values["days"] = days.group(1)
    missing = tuple(s for s in REQUIRED_SLOTS.get(intent, ()) if not values.get(s))
    return SlotSet(values=values, missing=missing)
