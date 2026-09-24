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
        "هلا فيك",
    ),
    CognitiveIntent.HELP: ("كيف استخدم", "شو بتسوي", "what is", "how to"),
    CognitiveIntent.WHO_ARE_YOU: ("who are you", "what is your name", "مين انت", "من انت", "عرف عن نفسك"),
    CognitiveIntent.CUSTOMER_BALANCE: ("رصيد العميل", "رصيد الزبون", "customer balance"),
    CognitiveIntent.SALES_SUMMARY: ("ملخص المبيعات", "تقرير المبيعات", "sales summary", "sales report"),
    CognitiveIntent.INVENTORY_STATUS: ("فحص المخزون", "low stock", "stock check"),
    CognitiveIntent.GL_BALANCE: ("ميزان المراجعه", "trial balance"),
    CognitiveIntent.PATTERN_ANALYSIS: ("انماط المبيعات", "تحليل الانماط", "اتجاه المبيعات", "sales patterns"),
    CognitiveIntent.PROFIT_MARGIN: ("هوامش الربح", "هامش الربح", "profit margin"),
    CognitiveIntent.DEAD_STOCK: ("الحركات الراكده", "المنتجات الراكده", "منتجات بدون مبيعات", "dead stock"),
    CognitiveIntent.TOP_PRODUCTS: ("اعلي المنتجات مبيعا", "الاكثر مبيعا", "الافضل مبيعا", "top products"),
    CognitiveIntent.DEBT_OVERVIEW: ("ديون العملاء", "ذمم العملاء", "رصيد العملاء", "كشف الديون"),
    CognitiveIntent.TAX_SUMMARY: ("ضريبه القيمه", "vat report", "tax summary"),
    CognitiveIntent.SUPPLIER_STATUS: ("كشف الموردين", "حساب المورد", "supplier statement"),
    CognitiveIntent.PURCHASE_SUMMARY: ("امر الشراء", "فاتوره الشراء"),
}

_GUIDE_TRIGGERS = frozenset({"وين", "اين", "خطوات", "اختصار", "اختصارات", "طريقه"})
_GUIDE_FEATURES = frozenset(
    {
        "قيد",
        "قيود",
        "فاتوره",
        "فواتير",
        "تقرير",
        "تقارير",
        "مخزون",
        "عميل",
        "عملاء",
        "منتج",
        "منتجات",
        "مورد",
        "موردين",
        "صلاحيه",
        "صلاحيات",
        "اعدادات",
        "شيك",
        "شيكات",
        "راتب",
        "رواتب",
        "حساب",
        "حسابات",
        "ميزان",
        "ضريبه",
        "مبيعات",
        "مشتريات",
        "مصروف",
    }
)


def _guide_compounds() -> tuple[frozenset[str], ...]:
    return tuple(frozenset({trigger, feature}) for trigger in _GUIDE_TRIGGERS for feature in _GUIDE_FEATURES) + (
        frozenset({"كيف", "انشي"}),
        frozenset({"كيف", "اسوي"}),
        frozenset({"كيف", "اعمل"}),
    )


_KEYWORDS: dict[CognitiveIntent, frozenset[str]] = {
    CognitiveIntent.GREETING: frozenset(
        {
            "مرحبا",
            "هلا",
            "اهلا",
            "سلام",
            "هاي",
            "هلاو",
            "هلو",
            "هاو",
            "مرحبتين",
            "مراحب",
            "اهلين",
            "كيفك",
            "شلونك",
            "اخبار",
            "hi",
            "hello",
            "hey",
        }
    ),
    CognitiveIntent.HELP: frozenset({"مساعده", "ساعد", "شرح", "دليل", "help", "guide"}),
    CognitiveIntent.WHO_ARE_YOU: frozenset({"اسمك", "وظيفتك", "انت مين"}),
    CognitiveIntent.SALES_SUMMARY: frozenset(
        {
            "مبيعات",
            "فاتوره",
            "فواتير",
            "بيع",
            "مبيع",
            "sales",
            "invoice",
            "invoices",
            "ايراد",
            "ايرادات",
            "ربح",
            "ارباح",
        }
    ),
    CognitiveIntent.CUSTOMER_BALANCE: frozenset({"رصيد", "عميل", "زبون", "customer", "balance", "ديون", "ذمم", "كشف"}),
    CognitiveIntent.INVENTORY_STATUS: frozenset(
        {"مخزون", "inventory", "stock", "منتج", "منتجات", "بضاعه", "بضائع", "جرد", "اصناف"}
    ),
    CognitiveIntent.PURCHASE_SUMMARY: frozenset({"مشتريات", "شراء", "توريد", "اوامر", "purchase"}),
    CognitiveIntent.EXPENSE_SUMMARY: frozenset({"مصروف", "مصاريف", "تكاليف", "تكلفه", "نثريات", "expense"}),
    CognitiveIntent.PAYMENT_STATUS: frozenset(
        {"دفعه", "دفعات", "مدفوعات", "قبض", "تحصيل", "سداد", "payment", "payments", "receive"}
    ),
    CognitiveIntent.CHEQUE_STATUS: frozenset({"شيك", "شيكات", "شك", "cheque", "cheques", "check"}),
    CognitiveIntent.GL_BALANCE: frozenset(
        {"قيد", "قيود", "دفتر", "دفاتر", "استاذ", "ميزانيه", "ميزان", "محاسبه", "حسابات", "gl", "ledger", "journal"}
    ),
    CognitiveIntent.HR_SUMMARY: frozenset(
        {"موظف", "موظفين", "راتب", "رواتب", "حضور", "اجازات", "hr", "employee", "payroll", "salary"}
    ),
    CognitiveIntent.VAULT_BALANCE: frozenset({"خزنه", "خزن", "صندوق", "صناديق", "سيوله", "vault", "cash"}),
    CognitiveIntent.PATTERN_ANALYSIS: frozenset(
        {"انماط", "نمط", "اتجاه", "اتجاهات", "تحليل", "مبيعات", "patterns", "trend", "trends", "analysis"}
    ),
    CognitiveIntent.PROFIT_MARGIN: frozenset({"هوامش", "هامش", "الربحيه", "ربحيه", "margin", "margins"}),
    CognitiveIntent.DEAD_STOCK: frozenset(
        {"راكد", "راكده", "ركود", "بطيء", "بطييه", "حركات", "dead", "slow", "stagnant"}
    ),
    CognitiveIntent.TOP_PRODUCTS: frozenset({"اعلي", "اكثر", "افضل", "مبيعا", "منتجات", "top", "best", "bestsellers"}),
    CognitiveIntent.DEBT_OVERVIEW: frozenset({"ديون", "ذمم", "مديونيه", "debt", "debts", "receivable", "receivables"}),
    CognitiveIntent.TAX_SUMMARY: frozenset({"ضريبه", "ضرايب", "القيمه", "vat", "tax", "taxes"}),
    CognitiveIntent.SUPPLIER_STATUS: frozenset({"مورد", "موردين", "supplier", "suppliers", "vendor", "vendors"}),
    CognitiveIntent.SYSTEM_GUIDE: _GUIDE_TRIGGERS,
}

_COMPOUNDS: dict[CognitiveIntent, tuple[frozenset[str], ...]] = {
    CognitiveIntent.CUSTOMER_BALANCE: (
        frozenset({"رصيد", "عميل"}),
        frozenset({"رصيد", "زبون"}),
        frozenset({"كشف", "عميل"}),
        frozenset({"حساب", "عميل"}),
    ),
    CognitiveIntent.SALES_SUMMARY: (frozenset({"مبيعات", "ملخص"}), frozenset({"مبيعات", "تقرير"})),
    CognitiveIntent.PURCHASE_SUMMARY: (frozenset({"فاتوره", "شراء"}),),
    CognitiveIntent.CHEQUE_STATUS: (frozenset({"شيك", "رصيد"}),),
    CognitiveIntent.GL_BALANCE: (frozenset({"قيد", "محاسبه"}),),
    CognitiveIntent.PATTERN_ANALYSIS: (frozenset({"انماط", "مبيعات"}), frozenset({"اتجاه", "مبيعات"})),
    CognitiveIntent.PROFIT_MARGIN: (frozenset({"هوامش", "ربح"}), frozenset({"هامش", "ربح"})),
    CognitiveIntent.DEAD_STOCK: (
        frozenset({"منتج", "راكد"}),
        frozenset({"مخزون", "راكد"}),
        frozenset({"بدون", "مبيعات"}),
    ),
    CognitiveIntent.TOP_PRODUCTS: (
        frozenset({"اكثر", "مبيعا"}),
        frozenset({"اعلي", "مبيعا"}),
        frozenset({"افضل", "مبيعا"}),
    ),
    CognitiveIntent.DEBT_OVERVIEW: (
        frozenset({"ديون", "عملاء"}),
        frozenset({"ذمم", "عملاء"}),
        frozenset({"رصيد", "عملاء"}),
    ),
    CognitiveIntent.SUPPLIER_STATUS: (frozenset({"حساب", "مورد"}), frozenset({"شراء", "مورد"})),
    CognitiveIntent.SYSTEM_GUIDE: _guide_compounds(),
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
