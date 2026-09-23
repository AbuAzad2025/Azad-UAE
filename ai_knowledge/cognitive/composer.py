"""Deterministic response composer — text is a pure function of the trace."""

from __future__ import annotations

from ai_knowledge.cognitive.contracts import (
    CognitiveIntent,
    IntentHypothesis,
    Provenance,
    ReasoningTrace,
    SlotSet,
)

_SLOT_LABELS = {"customer_name": "اسم العميل", "days": "عدد الأيام"}

_CAPABILITIES = (
    "ملخص المبيعات",
    "رصيد عميل",
    "حالة المخزون",
    "ملخص المشتريات",
    "ملخص المصروفات",
    "حالة المدفوعات",
    "حالة الشيكات",
    "أرصدة الحسابات",
    "ملخص الموظفين",
    "أرصدة الصناديق",
)


def _provenance_line(provenance: Provenance | None) -> str:
    if provenance is None or provenance.tenant_id is None:
        return ""
    queries = ", ".join(provenance.queries) if provenance.queries else "no-query"
    counts = ", ".join(str(c) for c in provenance.row_counts) if provenance.row_counts else "0"
    return f"\n<sub>المصدر: نطاق الشركة {provenance.tenant_id} — {queries} (صفوف: {counts})</sub>"


def compose_conversational(intent: CognitiveIntent) -> str:
    if intent == CognitiveIntent.GREETING:
        return "يا هلا! أنا أزاد، مساعدك المعرفي. اسألني عن المبيعات أو الأرصدة أو المخزون وسأجيب من بيانات شركتك."
    if intent == CognitiveIntent.WHO_ARE_YOU:
        return "أنا أزاد — محرك معرفي مرتبط ببيانات شركتك: أقرأ السجلات ضمن صلاحياتك وأعلل كل رقم بمصدره."
    return "أقدر أساعدك في: " + "، ".join(_CAPABILITIES) + ". اذكر ما تريد بدقة (مثال: رصيد العميل أحمد)."


def compose_data(intent: CognitiveIntent, trace: ReasoningTrace, provenance: Provenance | None) -> str:
    titles = {
        CognitiveIntent.SALES_SUMMARY: "ملخص المبيعات",
        CognitiveIntent.CUSTOMER_BALANCE: "رصيد العميل",
        CognitiveIntent.INVENTORY_STATUS: "حالة المخزون",
        CognitiveIntent.PURCHASE_SUMMARY: "ملخص المشتريات",
        CognitiveIntent.EXPENSE_SUMMARY: "ملخص المصروفات",
        CognitiveIntent.PAYMENT_STATUS: "حالة المدفوعات",
        CognitiveIntent.CHEQUE_STATUS: "حالة الشيكات",
        CognitiveIntent.GL_BALANCE: "أرصدة الحسابات",
        CognitiveIntent.HR_SUMMARY: "ملخص الموظفين",
        CognitiveIntent.VAULT_BALANCE: "أرصدة الصناديق",
    }
    title = titles.get(intent, intent.value)
    return f"{title}:\n{trace.conclusion}{_provenance_line(provenance)}"


def compose_need_slots(intent: CognitiveIntent, slots: SlotSet) -> str:
    names = ", ".join(_SLOT_LABELS.get(s, s) for s in slots.missing)
    if intent == CognitiveIntent.CUSTOMER_BALANCE:
        return "لأعرض الرصيد بدقة: ما اسم العميل؟ (مثال: رصيد العميل أحمد)."
    return f"أحتاج ({names}) قبل الاستعلام. حددها وسأنفذ فورا."


def compose_no_tenant() -> str:
    return "لا يوجد سياق شركة نشط — سجل الدخول إلى شركتك لعرض البيانات. الأسئلة العامة فقط متاحة الآن."


def compose_denied(intent: CognitiveIntent, required: str) -> str:
    pivot = "يمكنني مساعدتك في الأسئلة العامة أو ملخصات ضمن صلاحياتك."
    if required:
        return f"صلاحية غير كافية لعرض ({intent.value}). الصلاحية المطلوبة: {required}. {pivot}"
    return f"صلاحية غير كافية لعرض ({intent.value}). {pivot}"


def compose_unknown(hypothesis: IntentHypothesis) -> str:
    if hypothesis.alternatives:
        top = " أو ".join(name for name, _ in hypothesis.alternatives[:2])
        return f"لم أتحقق من القصد بدقة. هل تقصد: {top}؟ أو اختر من: " + "، ".join(_CAPABILITIES) + "."
    return "لم أتحقق من القصد. اختر من: " + "، ".join(_CAPABILITIES) + "."
