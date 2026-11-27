"""Slot extraction with history carryover (pure text ops; DB grounding lives in planner)."""

from __future__ import annotations

import re

from ai_knowledge.cognitive.contracts import CognitiveIntent, NormalizedMessage, SlotSet

REQUIRED_SLOTS: dict[CognitiveIntent, tuple[str, ...]] = {
    CognitiveIntent.CUSTOMER_BALANCE: ("customer_name",),
}

_NAME_AFTER_MARKER = re.compile(
    r"(?:العميل|الزبون|عميل|زبون|customer)\s+([^\d،,؛:()]{2,60}?)"
    r"(?=\s+(?:شيقل|شكل|دولار|درهم|ريال|ils|aed|usd|sar|sku|فاتورة|invoice|cheque|شيك|رقم)\b|\s*[؟?]|$)",
    re.IGNORECASE,
)
_SUPPLIER_MARKER = re.compile(
    r"(?:المورد|مورد|supplier|vendor)\s+([^\d،,؛:()]{2,60}?)(?:\s+[؟?]|$)",
    re.IGNORECASE,
)
_COLON_FORM = re.compile(r"^(?:رصيد|balance)\s*[:：=]\s*(.+)$", re.IGNORECASE)
_DAYS_RE = re.compile(r"(\d+)\s*(?:يوم|days?)", re.IGNORECASE)
_ENGLISH_NAME_RE = re.compile(
    r"\b(?:for customer|customer named|customer)\s+(?!balance\b)([A-Za-z][A-Za-z\s'\-]{1,60}?)(?:\?|$)",
    re.IGNORECASE,
)
_SKU_RE = re.compile(r"\b(?:sku)\s*[:=]?\s*([A-Za-z0-9][A-Za-z0-9\-]{1,30})", re.IGNORECASE)
_REFERENCE_RE = re.compile(r"\b(?:invoice|فاتورة|cheque|شيك|reference|رقم)\s*#?\s*(\d{2,})", re.IGNORECASE)
_CURRENCY_CODES = {
    "درهم": "AED",
    "aed": "AED",
    "a.e.d": "AED",
    "دولار": "USD",
    "usd": "USD",
    "ريال": "SAR",
    "sar": "SAR",
    "دينار": "DINAR",
    "شيقل": "ILS",
    "شكل": "ILS",
    "ils": "ILS",
}


def _clean_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value).strip(" ؟?.,؛:()\"'«»")
    stop = {
        "اليوم",
        "هالشهر",
        "الشهر",
        "امس",
        "أمس",
        "هالاسبوع",
        "balance",
        "for",
        "named",
        "رصيد",
        "account",
        "حساب",
    }
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
            else:
                english = _ENGLISH_NAME_RE.search(normalized.raw)
                if english and english.group(1).strip():
                    values["customer_name"] = _clean_name(english.group(1))
        if not values.get("customer_name") and previous_slots:
            carried = (previous_slots.get("customer_name") or "").strip()
            if carried and len(normalized.tokens) <= 4:
                values["customer_name"] = carried
                values["carried_from_history"] = "1"
    if intent == CognitiveIntent.SUPPLIER_STATUS:
        marker = _SUPPLIER_MARKER.search(normalized.raw)
        if marker and marker.group(1).strip():
            values["supplier_name"] = _clean_name(marker.group(1))
        if not values.get("supplier_name") and previous_slots:
            carried = (previous_slots.get("supplier_name") or "").strip()
            if carried and len(normalized.tokens) <= 4:
                values["supplier_name"] = carried
                values["carried_from_history"] = "1"
    days = _DAYS_RE.search(normalized.raw)
    if days:
        values["days"] = days.group(1)
    elif normalized.relative_period:
        values["days"] = str(normalized.relative_period[0])
        values["period_label"] = normalized.relative_period[1]
    for hint in normalized.currency_hints:
        code = _CURRENCY_CODES.get(hint)
        if code:
            values["currency"] = code
            break
    sku = _SKU_RE.search(normalized.raw)
    if sku:
        values["sku"] = sku.group(1)
    reference = _REFERENCE_RE.search(normalized.raw)
    if reference:
        values["reference_number"] = reference.group(1)
    missing = tuple(s for s in REQUIRED_SLOTS.get(intent, ()) if not values.get(s))
    return SlotSet(values=values, missing=missing)
