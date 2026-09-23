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

_CURRENCY_RE = re.compile(r"(درهم|دولار|ريال|دينار|aed|usd|sar|a\.e\.d)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_PUNCT_RE = re.compile(r"[؟?!.،,؛:()\[\]\"'«»\-–—/\\|_*~`+=<>@#$%^&]")


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
    return NormalizedMessage(
        raw=source,
        text=lowered,
        tokens=tokens,
        numbers=tuple(numbers),
        currency_hints=currencies,
    )
