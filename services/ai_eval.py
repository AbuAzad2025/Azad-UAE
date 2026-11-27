"""Reproducible local-first evaluation harness for the azad_erp AI assistant.

The harness drives the *actual* deterministic cognitive pipeline
(normalizer -> router -> RBAC firewall -> slot extraction -> grounded planner
-> composer) with in-memory, tenant-scoped fixtures. It never calls an
external LLM, never writes to the database, and never needs a request context.

Metrics produced:
  * intent classification accuracy (overall and per intent),
  * numeric grounding rate and ungrounded-number count,
  * RBAC denial accuracy (including "no query was attempted" on denial),
  * cross-tenant leak count.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import ai_knowledge.cognitive.planner as planner_module
from ai_knowledge.cognitive import engine as cognitive_engine
from ai_knowledge.cognitive.access import required_permission
from ai_knowledge.cognitive.contracts import CognitiveIntent, CognitiveResult
from ai_knowledge.cognitive.intent_router import route
from ai_knowledge.cognitive.normalizer import normalize_message

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_GROUND_TOLERANCE = 0.005


@dataclass(frozen=True)
class EvalCase:
    """One deterministic evaluation prompt and its expected contract."""

    prompt: str
    language: str
    expected_intent: CognitiveIntent
    expected_decision: str
    tenant_id: int = 1
    grounded_numbers: tuple[float, ...] = ()
    expected_permission: str = ""
    authenticated: bool = True
    permissions: frozenset[str] = frozenset()
    can_see_costs: bool = False


@dataclass(frozen=True)
class CaseResult:
    prompt: str
    language: str
    expected_intent: str
    actual_intent: str
    expected_decision: str
    actual_decision: str
    response: str
    grounded: bool | None
    query_calls: int


@dataclass(frozen=True)
class IntentMetric:
    total: int
    correct: int
    accuracy: float
    per_intent: dict[str, tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class GroundingMetric:
    evaluated: int
    grounded: int
    ungrounded_count: int
    rate: float


@dataclass(frozen=True)
class RbacMetric:
    checks: int
    correct: int
    accuracy: float
    queries_while_denied: int


@dataclass(frozen=True)
class TenantMetric:
    checks: int
    leaks: int


@dataclass(frozen=True)
class EvalReport:
    intent: IntentMetric
    grounding: GroundingMetric
    rbac: RbacMetric
    tenant: TenantMetric
    cases: tuple[CaseResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_accuracy": round(self.intent.accuracy, 4),
            "intent_accuracy_total": self.intent.total,
            "intent_accuracy_correct": self.intent.correct,
            "intent_per_intent": {
                name: {"correct": correct, "total": total, "accuracy": round(correct / total, 4)}
                for name, (correct, total) in sorted(self.intent.per_intent.items())
            },
            "grounded_rate": round(self.grounding.rate, 4),
            "grounding_evaluated": self.grounding.evaluated,
            "ungrounded_count": self.grounding.ungrounded_count,
            "rbac_checks": self.rbac.checks,
            "rbac_correct": self.rbac.correct,
            "rbac_accuracy": round(self.rbac.accuracy, 4),
            "queries_while_denied": self.rbac.queries_while_denied,
            "tenant_isolation_checks": self.tenant.checks,
            "tenant_leak_count": self.tenant.leaks,
        }


def _eval_user(
    tenant_id: int,
    permissions: Iterable[str],
    *,
    authenticated: bool = True,
    can_see_costs: bool = False,
) -> SimpleNamespace:
    """A minimal user object accepted by the real RBAC and tenant helpers."""

    allowed = frozenset(permissions)

    def has_permission(code: str) -> bool:
        return code in allowed or (code == "view_costs" and can_see_costs)

    def see_costs() -> bool:
        return can_see_costs

    return SimpleNamespace(
        id=None,
        tenant_id=tenant_id,
        is_authenticated=authenticated,
        is_owner=False,
        has_permission=has_permission,
        can_see_costs=see_costs,
        branch_id=None,
    )


def _fixture_rows() -> list[SimpleNamespace]:
    """In-memory rows with explicit tenant ownership; no DB access."""

    now = datetime.now(UTC)
    rows: list[SimpleNamespace] = []
    for tenant_id, name, balance, total, due, stock, alert, inflow, outflow in (
        (1, "Ahmad", 500.0, 150.0, 200.0, 5.0, 10.0, 300.0, 120.0),
        (2, "Laila", 9000.0, 777.0, 0.0, 50.0, 1.0, 900.0, 50.0),
    ):
        rows.append(SimpleNamespace(_model="Customer", tenant_id=tenant_id, id=tenant_id, name=name, balance=balance))
        rows.append(
            SimpleNamespace(
                _model="Sale",
                tenant_id=tenant_id,
                id=tenant_id + 100,
                customer_id=tenant_id,
                sale_date=now,
                created_at=now,
                total_amount=total,
                balance_due=due,
                tax_amount=5.0 if tenant_id == 1 else 0.0,
            )
        )
        rows.append(
            SimpleNamespace(
                _model="SaleLine",
                tenant_id=tenant_id,
                id=tenant_id + 300,
                sale_id=tenant_id + 100,
                product_id=tenant_id + 200,
                line_total=total,
                cost_price=90.0,
                quantity=1.0,
            )
        )
        rows.append(
            SimpleNamespace(
                _model="Product",
                tenant_id=tenant_id,
                id=tenant_id + 200,
                name=f"Product-{tenant_id}",
                is_active=True,
                current_stock=stock,
                min_stock_alert=alert,
            )
        )
        rows.append(
            SimpleNamespace(
                _model="Purchase",
                tenant_id=tenant_id,
                id=tenant_id + 400,
                created_at=now,
                tax_amount=2.0,
                total_amount=80.0,
            )
        )
        rows.append(
            SimpleNamespace(
                _model="Receipt",
                tenant_id=tenant_id,
                id=tenant_id + 500,
                receipt_date=now,
                amount_aed=inflow,
            )
        )
        rows.append(
            SimpleNamespace(
                _model="Payment",
                tenant_id=tenant_id,
                id=tenant_id + 600,
                payment_date=now,
                amount_aed=outflow,
                direction="outgoing",
            )
        )
    return rows


def _make_scoped_query(rows: list[SimpleNamespace]) -> Callable[[Any, Any], _FakeQuery]:
    def factory(model: Any, user: Any = None) -> _FakeQuery:
        tenant_id = getattr(user, "tenant_id", None)
        name = getattr(model, "__name__", "")
        matches = [
            row for row in rows if getattr(row, "_model", "") == name and getattr(row, "tenant_id", None) == tenant_id
        ]
        return _FakeQuery(matches)

    return factory


class _FakeQuery:
    """Minimal query surface used by the grounded planners."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = list(rows)

    def filter(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def filter_by(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def order_by(self, *_args: Any) -> _FakeQuery:
        return self

    def limit(self, count: int) -> _FakeQuery:
        self._rows = self._rows[:count]
        return self

    def all(self) -> list[SimpleNamespace]:
        return list(self._rows)

    def first(self) -> SimpleNamespace | None:
        return self._rows[0] if self._rows else None


_READ_PERMS = frozenset({"view_reports", "manage_customers", "manage_warehouse", "view_ledger"})

DEFAULT_CASES: tuple[EvalCase, ...] = (
    EvalCase("السلام عليكم", "ar", CognitiveIntent.GREETING, "conversational"),
    EvalCase("hello there", "en", CognitiveIntent.GREETING, "conversational"),
    EvalCase("كيف استخدم", "ar", CognitiveIntent.HELP, "conversational"),
    EvalCase("who are you", "en", CognitiveIntent.WHO_ARE_YOU, "conversational"),
    EvalCase(
        "ملخص المبيعات",
        "ar",
        CognitiveIntent.SALES_SUMMARY,
        "answer",
        grounded_numbers=(1.0, 30.0, 150.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "sales summary",
        "en",
        CognitiveIntent.SALES_SUMMARY,
        "answer",
        grounded_numbers=(1.0, 30.0, 150.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "مبيعات الشهر الماضي",
        "ar",
        CognitiveIntent.SALES_SUMMARY,
        "answer",
        grounded_numbers=(1.0, 60.0, 150.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "sales last week",
        "en",
        CognitiveIntent.SALES_SUMMARY,
        "answer",
        grounded_numbers=(1.0, 14.0, 150.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "رصيد العميل Ahmad",
        "ar",
        CognitiveIntent.CUSTOMER_BALANCE,
        "answer",
        grounded_numbers=(1.0, 200.0, 500.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "customer balance Ahmad",
        "en",
        CognitiveIntent.CUSTOMER_BALANCE,
        "answer",
        grounded_numbers=(1.0, 200.0, 500.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "رصيد العميل أحمد محمد",
        "ar",
        CognitiveIntent.CUSTOMER_BALANCE,
        "answer",
        grounded_numbers=(1.0, 200.0, 500.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "customer balance for Ahmad",
        "en",
        CognitiveIntent.CUSTOMER_BALANCE,
        "answer",
        grounded_numbers=(1.0, 200.0, 500.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "فحص المخزون",
        "ar",
        CognitiveIntent.INVENTORY_STATUS,
        "answer",
        grounded_numbers=(1.0, 2.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "stock check",
        "en",
        CognitiveIntent.INVENTORY_STATUS,
        "answer",
        grounded_numbers=(1.0, 2.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "ديون العملاء",
        "ar",
        CognitiveIntent.DEBT_OVERVIEW,
        "answer",
        grounded_numbers=(0.0, 1.0, 200.0, 500.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "receivables",
        "en",
        CognitiveIntent.DEBT_OVERVIEW,
        "answer",
        grounded_numbers=(0.0, 1.0, 200.0, 500.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "ملخص الضرائب",
        "ar",
        CognitiveIntent.TAX_SUMMARY,
        "answer",
        grounded_numbers=(1.0, 2.0, 5.0, 30.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "vat report",
        "en",
        CognitiveIntent.TAX_SUMMARY,
        "answer",
        grounded_numbers=(1.0, 2.0, 5.0, 30.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "التدفقات النقدية",
        "ar",
        CognitiveIntent.CASH_FLOW_SUMMARY,
        "answer",
        grounded_numbers=(1.0, 2.0, 30.0, 120.0, 180.0, 300.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "cash flow",
        "en",
        CognitiveIntent.CASH_FLOW_SUMMARY,
        "answer",
        grounded_numbers=(1.0, 2.0, 30.0, 120.0, 180.0, 300.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "cash flow",
        "en",
        CognitiveIntent.CASH_FLOW_SUMMARY,
        "answer",
        tenant_id=2,
        grounded_numbers=(2.0, 2.0, 30.0, 50.0, 850.0, 900.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "المخزون المنخفض",
        "ar",
        CognitiveIntent.LOW_STOCK_LIST,
        "answer",
        grounded_numbers=(1.0, 5.0, 10.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "low stock",
        "en",
        CognitiveIntent.LOW_STOCK_LIST,
        "answer",
        grounded_numbers=(1.0, 5.0, 10.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "أفضل العملاء",
        "ar",
        CognitiveIntent.TOP_CUSTOMERS,
        "answer",
        grounded_numbers=(1.0, 30.0, 150.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "top customers",
        "en",
        CognitiveIntent.TOP_CUSTOMERS,
        "answer",
        grounded_numbers=(1.0, 30.0, 150.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "أعلى المنتجات مبيعاً",
        "ar",
        CognitiveIntent.TOP_PRODUCTS,
        "answer",
        grounded_numbers=(1.0, 30.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "profit margin",
        "en",
        CognitiveIntent.PROFIT_MARGIN,
        "answer",
        grounded_numbers=(1.0, 30.0, 40.0, 60.0, 90.0, 150.0),
        permissions=_READ_PERMS,
        can_see_costs=True,
    ),
    EvalCase(
        "ملخص المبيعات",
        "ar",
        CognitiveIntent.SALES_SUMMARY,
        "denied",
        expected_permission="view_reports",
        permissions=frozenset(),
    ),
    EvalCase(
        "sales summary",
        "en",
        CognitiveIntent.SALES_SUMMARY,
        "answer",
        tenant_id=2,
        grounded_numbers=(1.0, 2.0, 30.0, 777.0),
        permissions=_READ_PERMS,
    ),
    EvalCase(
        "sales summary",
        "en",
        CognitiveIntent.SALES_SUMMARY,
        "denied",
        expected_permission="view_reports",
        authenticated=False,
    ),
    EvalCase(
        "فحص المخزون",
        "ar",
        CognitiveIntent.INVENTORY_STATUS,
        "denied",
        expected_permission="manage_warehouse",
        permissions=frozenset(),
    ),
    EvalCase(
        "هوامش الربح",
        "ar",
        CognitiveIntent.PROFIT_MARGIN,
        "denied",
        expected_permission="view_costs",
        permissions=frozenset({"view_reports"}),
        can_see_costs=False,
    ),
)


def _numbers_in(text: str) -> list[float]:
    values: list[float] = []
    for raw in _NUMBER_RE.findall(text or ""):
        try:
            values.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return values


def _all_numbers_grounded(text: str, grounded: tuple[float, ...]) -> bool:
    allowed = {float(value) for value in grounded}
    return all(any(abs(value - expected) <= _GROUND_TOLERANCE for expected in allowed) for value in _numbers_in(text))


def _evaluate_case(
    case: EvalCase, scoped_query: Callable[[Any, Any], _FakeQuery]
) -> tuple[CaseResult, CognitiveResult]:
    user = (
        _eval_user(
            case.tenant_id,
            case.permissions,
            authenticated=case.authenticated,
            can_see_costs=case.can_see_costs,
        )
        if case.authenticated
        else None
    )
    query_calls = 0

    def counting_query(model: Any, active_user: Any = None) -> _FakeQuery:
        nonlocal query_calls
        query_calls += 1
        return scoped_query(model, active_user)

    with patch.object(planner_module, "tenant_query", side_effect=counting_query):
        result = cognitive_engine.process(case.prompt, user)
    grounded = None
    if case.grounded_numbers and case.expected_decision == "answer":
        grounded = _all_numbers_grounded(result.response, case.grounded_numbers)
    return (
        CaseResult(
            prompt=case.prompt,
            language=case.language,
            expected_intent=case.expected_intent.value,
            actual_intent=result.intent,
            expected_decision=case.expected_decision,
            actual_decision=result.decision,
            response=result.response,
            grounded=grounded,
            query_calls=query_calls,
        ),
        result,
    )


def _run_eval_cases(case_list, scoped_query):
    intent_counts: dict[str, list[int]] = {}
    intent_correct = 0
    case_results: list[CaseResult] = []
    results: list[tuple[EvalCase, CaseResult, CognitiveResult]] = []
    for case in case_list:
        hypothesis = route(normalize_message(case.prompt))
        correct = hypothesis.intent == case.expected_intent
        intent_correct += int(correct)
        bucket = intent_counts.setdefault(case.expected_intent.value, [0, 0])
        bucket[1] += 1
        bucket[0] += int(correct)
        case_result, cognitive = _evaluate_case(case, scoped_query)
        case_results.append(case_result)
        results.append((case, case_result, cognitive))
    return intent_counts, intent_correct, case_results, results


def run_local_eval(
    cases: Iterable[EvalCase] = DEFAULT_CASES,
    *,
    rows: Iterable[SimpleNamespace] | None = None,
) -> EvalReport:
    """Run the deterministic local evaluation and return structured metrics."""

    from ai_knowledge.cognitive.followup import clear_context

    clear_context()
    case_list = tuple(cases)
    scoped_query = _make_scoped_query(list(rows if rows is not None else _fixture_rows()))

    intent_counts, intent_correct, case_results, results = _run_eval_cases(case_list, scoped_query)

    grounding_cases = [item for item in results if item[0].grounded_numbers and item[2].decision == "answer"]
    grounded_ok = sum(1 for item in grounding_cases if item[1].grounded is True)
    ungrounded = sum(
        1
        for item in grounding_cases
        for number in _numbers_in(item[2].response)
        if not any(abs(number - float(expected)) <= _GROUND_TOLERANCE for expected in item[0].grounded_numbers)
    )

    deny_cases = [item for item in results if item[0].expected_decision == "denied"]
    rbac_correct = 0
    queries_while_denied = 0
    for case, case_result, cognitive in deny_cases:
        expected_perm = case.expected_permission or required_permission(case.expected_intent)
        if (
            cognitive.decision == "denied"
            and cognitive.required_permission == expected_perm
            and case_result.query_calls == 0
        ):
            rbac_correct += 1
        queries_while_denied += case_result.query_calls

    primary_numbers = {
        150.0,
    }
    isolation_probes = 1
    tenant_leaks = 0
    foreign_user = _eval_user(2, ("view_reports",))
    with patch.object(planner_module, "tenant_query", side_effect=scoped_query):
        foreign_result = cognitive_engine.process("sales summary", foreign_user)
    for number in _numbers_in(foreign_result.response):
        if any(abs(number - expected) <= _GROUND_TOLERANCE for expected in primary_numbers):
            tenant_leaks += 1

    total = len(case_list)
    return EvalReport(
        intent=IntentMetric(
            total=total,
            correct=intent_correct,
            accuracy=(intent_correct / total) if total else 0.0,
            per_intent={name: (values[0], values[1]) for name, values in intent_counts.items()},
        ),
        grounding=GroundingMetric(
            evaluated=len(grounding_cases),
            grounded=grounded_ok,
            ungrounded_count=ungrounded,
            rate=(grounded_ok / len(grounding_cases)) if grounding_cases else 0.0,
        ),
        rbac=RbacMetric(
            checks=len(deny_cases),
            correct=rbac_correct,
            accuracy=(rbac_correct / len(deny_cases)) if deny_cases else 0.0,
            queries_while_denied=queries_while_denied,
        ),
        tenant=TenantMetric(checks=isolation_probes, leaks=tenant_leaks),
        cases=tuple(case_results),
    )


__all__ = [
    "DEFAULT_CASES",
    "CaseResult",
    "EvalCase",
    "EvalReport",
    "GroundingMetric",
    "IntentMetric",
    "RbacMetric",
    "TenantMetric",
    "run_local_eval",
]
