from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_ONES = {
    0: "صفر",
    1: "واحد",
    2: "اثنان",
    3: "ثلاثة",
    4: "أربعة",
    5: "خمسة",
    6: "ستة",
    7: "سبعة",
    8: "ثمانية",
    9: "تسعة",
}

_TEENS = {
    10: "عشرة",
    11: "أحد عشر",
    12: "اثنا عشر",
    13: "ثلاثة عشر",
    14: "أربعة عشر",
    15: "خمسة عشر",
    16: "ستة عشر",
    17: "سبعة عشر",
    18: "ثمانية عشر",
    19: "تسعة عشر",
}

_TENS = {
    20: "عشرون",
    30: "ثلاثون",
    40: "أربعون",
    50: "خمسون",
    60: "ستون",
    70: "سبعون",
    80: "ثمانون",
    90: "تسعون",
}

_HUNDREDS = {
    1: "مائة",
    2: "مائتان",
    3: "ثلاثمائة",
    4: "أربعمائة",
    5: "خمسمائة",
    6: "ستمائة",
    7: "سبعمائة",
    8: "ثمانمائة",
    9: "تسعمائة",
}


def _join_parts(parts: list[str]) -> str:
    return " و ".join([p for p in parts if p])


def _to_words_under_1000(number: int) -> str:
    if number == 0:
        return ""

    parts: list[str] = []
    hundreds = number // 100
    remainder = number % 100

    if hundreds:
        parts.append(_HUNDREDS[hundreds])

    if remainder:
        if remainder < 10:
            parts.append(_ONES[remainder])
        elif remainder < 20:
            parts.append(_TEENS[remainder])
        else:
            ones = remainder % 10
            tens = remainder - ones
            if ones:
                parts.append(f"{_ONES[ones]} و {_TENS[tens]}")
            else:
                parts.append(_TENS[tens])

    return _join_parts(parts)


def _thousands_part(number: int) -> str:
    if number == 1:
        return "ألف"
    if number == 2:
        return "ألفان"
    if 3 <= number <= 10:
        return f"{_to_words_under_1000(number)} آلاف"
    return f"{_to_words_under_1000(number)} ألف"


def _millions_part(number: int) -> str:
    if number == 1:
        return "مليون"
    if number == 2:
        return "مليونان"
    if 3 <= number <= 10:
        return f"{_to_words_under_1000(number)} ملايين"
    return f"{_to_words_under_1000(number)} مليون"


def _to_words(number: int) -> str:
    if number == 0:
        return _ONES[0]

    parts: list[str] = []
    millions = number // 1_000_000
    thousands = (number % 1_000_000) // 1_000
    remainder = number % 1_000

    if millions:
        parts.append(_millions_part(millions))
    if thousands:
        parts.append(_thousands_part(thousands))
    if remainder:
        parts.append(_to_words_under_1000(remainder))

    return _join_parts(parts)


def _currency_labels(currency: str) -> tuple[str, str]:
    code = (currency or "").upper()
    labels = {
        "AED": ("درهم إماراتي", "فلس"),
        "USD": ("دولار", "سنت"),
        "ILS": ("شيقل", "أغورة"),
        "SAR": ("ريال", "هللة"),
        "KWD": ("دينار", "فلس"),
        "QAR": ("ريال", "درهم"),
        "BHD": ("دينار", "فلس"),
        "OMR": ("ريال", "بيسة"),
        "JOD": ("دينار", "فلس"),
        "EGP": ("جنيه", "قرش"),
        "GBP": ("جنيه", "بنس"),
        "EUR": ("يورو", "سنت"),
    }
    return labels.get(code, ("وحدة نقدية", "جزء"))


def number_to_arabic_words(amount: float | Decimal | int, currency: str = "AED") -> str:
    """
    Convert decimal money amount to Arabic words.

    Example:
    1500.75 -> "ألف و خمسمائة درهم إماراتي و خمسة و سبعون فلس فقط لا غير"
    """
    amount_decimal = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount_decimal < 0:
        return ""
    major = int(amount_decimal)
    minor = int((amount_decimal - Decimal(major)) * 100)
    major_label, minor_label = _currency_labels(currency)

    major_words = _to_words(major)
    if minor > 0:
        minor_words = _to_words(minor)
        return f"{major_words} {major_label} و {minor_words} {minor_label} فقط لا غير"
    return f"{major_words} {major_label} فقط لا غير"
