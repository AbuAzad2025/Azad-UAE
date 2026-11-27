"""Deterministic Arabic-first message normalizer (pure, no DB, no I/O)."""

from __future__ import annotations

import re

from ai_knowledge.cognitive.contracts import NormalizedMessage

_AR_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
    }
)

_CURRENCY_RE = re.compile(r"(درهم|دولار|ريال|دينار|شيقل|شكل|ils|aed|usd|sar|a\.e\.d)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_PUNCT_RE = re.compile(r"[؟?!.،,؛:()\[\]\"'«»\-–—/\\|_*~`+=<>@#$%^&]")
_INTERROGATIVE_RE = re.compile(
    r"(^\s*(ما|ماذا|متى|لماذا|كيف|كم|أين|وين|هل|من)\b|"
    r"\b(what|when|why|how|who|which|can you tell|show me)\b|[؟?])",
    re.IGNORECASE,
)
_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")

# Relative windows mapped to a bounded look-back in days. Readers already
# accept a ``days`` slot, so this keeps every grounded reader period-aware
# without changing its contract.
RELATIVE_PERIODS: dict[str, tuple[int, str]] = {
    "today": (1, "today"),
    "yesterday": (2, "yesterday"),
    "this week": (7, "this_week"),
    "last week": (14, "last_week"),
    "this month": (30, "this_month"),
    "last month": (60, "last_month"),
    "this year": (365, "this_year"),
    "اليوم": (1, "today"),
    "امس": (2, "yesterday"),
    "هذا الاسبوع": (7, "this_week"),
    "الاسبوع الماضي": (14, "last_week"),
    "هذا الشهر": (30, "this_month"),
    "الشهر الماضي": (60, "last_month"),
    "هذه السنه": (365, "this_year"),
    "السنه الماضيه": (365, "last_year"),
}


def has_interrogative(raw: str) -> bool:
    """True for questions that must never be dispatched as write actions."""
    return bool(_INTERROGATIVE_RE.search(raw or ""))


def detect_locale(raw: str) -> str:
    """Coarse locale tag for cache keys and localized follow-ups."""
    return "ar" if _ARABIC_RE.search(raw or "") else "en"


_WRITE_ACTION_TYPES = frozenset(
    {
        "create_customer",
        "create_product",
        "create_sale",
        "receive_payment",
        "add_expense",
        "create_supplier",
        "create_employee",
        "create_purchase",
        "create_user",
        "transfer_stock",
        "cancel_sale",
    }
)


def interrogative_blocks_write(raw: str, action_type: str) -> bool:
    """A question must never be dispatched as a DB-mutating action."""
    return action_type in _WRITE_ACTION_TYPES and has_interrogative(raw)


def _normalize_arabic(text: str) -> str:
    cleaned = text.translate(_AR_MAP)
    cleaned = re.sub(r"[\u064B-\u0652\u0670]", "", cleaned)
    return cleaned


def normalize_message(raw: str) -> NormalizedMessage:
    source = raw or ""
    lowered = _normalize_arabic(source).lower()
    lowered = _PUNCT_RE.sub(" ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    tokens = frozenset(t for t in lowered.split(" ") if t)
    numbers: list[float] = []
    for match in _NUMBER_RE.findall(source):
        try:
            numbers.append(float(match.replace(",", "")))
        except ValueError:
            continue
    currencies = tuple(sorted({m.group(0).lower() for m in _CURRENCY_RE.finditer(source)}))
    relative_period = next(
        (value for phrase, value in RELATIVE_PERIODS.items() if phrase in lowered),
        None,
    )
    return NormalizedMessage(
        raw=source,
        text=lowered,
        tokens=tokens,
        numbers=tuple(numbers),
        currency_hints=currencies,
        locale=detect_locale(source),
        relative_period=relative_period,
    )
