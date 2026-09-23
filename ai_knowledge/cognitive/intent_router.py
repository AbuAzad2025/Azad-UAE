"""Evidence-weighted deterministic intent router (pure, no DB).

Every hypothesis carries citable evidence tokens. Confidence is a bounded
sum of named signal weights — never a literal per-branch constant.
"""

from __future__ import annotations

from ai_knowledge.cognitive.contracts import CognitiveIntent, IntentHypothesis, NormalizedMessage

BASE_PRESENCE = 0.15
PHRASE_WEIGHT = 0.45
KEYWORD_WEIGHT = 0.22
MAX_KEYWORD_HITS = 2
COMPOUND_BONUS = 0.25
HISTORY_BONUS = 0.10
MAX_CONFIDENCE = 0.95

_ANSWER_THRESHOLD_DOC = "Decision gate (>=0.75 answer) lives in engine.py; router only scores."

_PHRASES: dict[CognitiveIntent, tuple[str, ...]] = {
    CognitiveIntent.GREETING: (
        "السلام عليكم",
        "صباح الخير",
        "مساء الخير",
        "هلا والله",
        "يا هلا",
        "هاي هلا",
    ),
    CognitiveIntent.HELP: ("كيف استخدم", "شو بتسوي", "what is", "how to"),
    CognitiveIntent.WHO_ARE_YOU: ("who are you", "what is your name", "مين انت", "من انت", "عرف عن نفسك"),
    CognitiveIntent.CUSTOMER_BALANCE: ("رصيد العميل", "رصيد الزبون", "customer balance"),
    CognitiveIntent.SALES_SUMMARY: ("ملخص المبيعات", "تقرير المبيعات", "sales summary", "sales report"),
    CognitiveIntent.INVENTORY_STATUS: ("فحص المخزون", "low stock", "stock check"),
    CognitiveIntent.GL_BALANCE: ("ميزان المراجعه", "trial balance"),
}

_KEYWORDS: dict[CognitiveIntent, frozenset[str]] = {
    CognitiveIntent.GREETING: frozenset(
        {"مرحبا", "هلا", "اهلا", "سلام", "هاي", "هلاو", "هلو", "هاو", "مرحبتين", "مراحب", "اهلين", "hi", "hello", "hey"}
    ),
    CognitiveIntent.HELP: frozenset({"مساعده", "ساعد", "شرح", "دليل", "help", "guide"}),
    CognitiveIntent.WHO_ARE_YOU: frozenset({"اسمك", "وظيفتك", "انت مين"}),
    CognitiveIntent.SALES_SUMMARY: frozenset({"مبيعات", "فاتوره", "بيع", "sales", "invoice", "ايراد", "ربح"}),
    CognitiveIntent.CUSTOMER_BALANCE: frozenset({"رصيد", "عميل", "زبون", "customer", "balance", "ديون", "ذمم"}),
    CognitiveIntent.INVENTORY_STATUS: frozenset({"مخزون", "inventory", "stock", "منتج", "بضاعه"}),
    CognitiveIntent.PURCHASE_SUMMARY: frozenset({"مشتريات", "شراء", "مورد", "purchase", "supplier"}),
    CognitiveIntent.EXPENSE_SUMMARY: frozenset({"مصروف", "مصاريف", "expense"}),
    CognitiveIntent.PAYMENT_STATUS: frozenset({"دفعه", "مدفوعات", "قبض", "payment", "receive"}),
    CognitiveIntent.CHEQUE_STATUS: frozenset({"شيك", "شك", "cheque", "check"}),
    CognitiveIntent.GL_BALANCE: frozenset({"قيد", "دفتر", "استاذ", "ميزانيه", "محاسبه", "gl", "ledger", "journal"}),
    CognitiveIntent.HR_SUMMARY: frozenset({"موظف", "راتب", "hr", "employee", "payroll", "salary"}),
    CognitiveIntent.VAULT_BALANCE: frozenset({"خزنه", "صندوق", "vault", "كاش", "cash"}),
}

_COMPOUNDS: dict[CognitiveIntent, tuple[frozenset[str], ...]] = {
    CognitiveIntent.CUSTOMER_BALANCE: (frozenset({"رصيد", "عميل"}), frozenset({"رصيد", "زبون"})),
    CognitiveIntent.SALES_SUMMARY: (frozenset({"مبيعات", "ملخص"}), frozenset({"مبيعات", "تقرير"})),
    CognitiveIntent.CHEQUE_STATUS: (frozenset({"شيك", "رصيد"}),),
    CognitiveIntent.GL_BALANCE: (frozenset({"قيد", "محاسبه"}),),
}


def _expanded(tokens: frozenset[str]) -> frozenset[str]:
    extra = set(tokens)
    for token in tokens:
        if token.startswith("ال") and len(token) > 4:
            extra.add(token[2:])
    return frozenset(extra)


def _phrase_evidence(text: str, intent: CognitiveIntent) -> list[str]:
    return [f"phrase:{p}" for p in _PHRASES.get(intent, ()) if p in text]


def _keyword_evidence(tokens: frozenset[str], intent: CognitiveIntent) -> list[str]:
    hits = [f"keyword:{t}" for t in sorted(_expanded(tokens) & _KEYWORDS.get(intent, frozenset()))]
    return hits[:MAX_KEYWORD_HITS]


def _compound_evidence(tokens: frozenset[str], intent: CognitiveIntent) -> list[str]:
    expanded = _expanded(tokens)
    found = []
    for group in _COMPOUNDS.get(intent, ()):
        if group <= expanded:
            found.append("compound:" + "+".join(sorted(group)))
    return found


def route(normalized: NormalizedMessage, previous_intent: str | None = None) -> IntentHypothesis:
    scored: list[tuple[CognitiveIntent, float, list[str]]] = []
    for intent in CognitiveIntent:
        if intent == CognitiveIntent.UNKNOWN:
            continue
        evidence = _phrase_evidence(normalized.text, intent)
        evidence += _keyword_evidence(normalized.tokens, intent)
        evidence += _compound_evidence(normalized.tokens, intent)
        if not evidence:
            continue
        score = BASE_PRESENCE
        score += PHRASE_WEIGHT if any(e.startswith("phrase:") for e in evidence) else 0.0
        score += KEYWORD_WEIGHT * sum(1 for e in evidence if e.startswith("keyword:"))
        score += COMPOUND_BONUS if any(e.startswith("compound:") for e in evidence) else 0.0
        if previous_intent == intent.value and len(normalized.tokens) <= 3:
            score += HISTORY_BONUS
            evidence.append("history:carryover")
        scored.append((intent, min(MAX_CONFIDENCE, score), evidence))
    if not scored:
        return IntentHypothesis(intent=CognitiveIntent.UNKNOWN, confidence=0.10, evidence=("no-signal",))
    scored.sort(key=lambda item: item[1], reverse=True)
    best_intent, best_score, best_evidence = scored[0]
    alternatives = tuple((item[0].value, round(item[1], 3)) for item in scored[1:4])
    return IntentHypothesis(
        intent=best_intent,
        confidence=round(best_score, 3),
        evidence=tuple(best_evidence),
        alternatives=alternatives,
    )
