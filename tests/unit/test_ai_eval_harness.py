"""Deterministic tests for the local-first AI evaluation harness."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from services.ai_eval import DEFAULT_CASES, run_local_eval


def test_baseline_metrics_are_reproducible():
    first = run_local_eval().to_dict()
    second = run_local_eval().to_dict()

    assert first == second
    assert first["intent_accuracy"] == 1.0
    assert first["intent_accuracy_total"] == 32
    assert first["intent_accuracy_correct"] == 32
    assert first["grounded_rate"] == 1.0
    assert first["grounding_evaluated"] == 24
    assert first["ungrounded_count"] == 0
    assert first["rbac_checks"] == 4
    assert first["rbac_correct"] == 4
    assert first["rbac_accuracy"] == 1.0
    assert first["queries_while_denied"] == 0
    assert first["tenant_isolation_checks"] == 1
    assert first["tenant_leak_count"] == 0


def test_arabic_and_english_cases_are_both_covered():
    report = run_local_eval()

    languages = {case.language for case in report.cases}
    assert languages == {"ar", "en"}
    assert sum(1 for case in report.cases if case.language == "ar") == 16
    assert sum(1 for case in report.cases if case.language == "en") == 16
    assert set(report.intent.per_intent) == {
        "cash_flow_summary",
        "customer_balance",
        "debt_overview",
        "greeting",
        "help",
        "inventory_status",
        "low_stock_list",
        "profit_margin",
        "sales_summary",
        "tax_summary",
        "top_customers",
        "top_products",
        "who_are_you",
    }
    assert all(values[0] == values[1] for values in report.intent.per_intent.values())


def test_permission_denials_never_query_data():
    report = run_local_eval()

    denied = [case for case in report.cases if case.expected_decision == "denied"]
    assert len(denied) == 4
    assert all(case.actual_decision == "denied" for case in denied)
    assert all(case.query_calls == 0 for case in denied)
    assert all("150.00" not in case.response for case in denied)


def test_zero_cross_tenant_leak():
    report = run_local_eval()
    foreign = next(case for case in report.cases if case.expected_decision == "answer" and "777.00" in case.response)

    assert report.tenant.leaks == 0
    assert "777.00" in foreign.response
    assert "150.00" not in foreign.response
    assert "500.00" not in foreign.response


def test_harness_is_local_only_and_does_not_mutate_persistence():
    with (
        patch("requests.post", side_effect=AssertionError("external provider call")),
        patch("extensions.db.session.add", side_effect=AssertionError("DB write")),
        patch("extensions.db.session.commit", side_effect=AssertionError("DB commit")),
    ):
        report = run_local_eval()

    assert report.intent.correct == report.intent.total
    assert report.grounding.ungrounded_count == 0
    assert report.rbac.queries_while_denied == 0


def test_report_is_json_serializable():
    payload = run_local_eval().to_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_custom_case_can_detect_an_ungrounded_number():
    from ai_knowledge.cognitive.contracts import CognitiveIntent
    from services.ai_eval import EvalCase

    case = EvalCase(
        "sales summary",
        "en",
        CognitiveIntent.SALES_SUMMARY,
        "answer",
        grounded_numbers=(30.0,),
        permissions=frozenset({"view_reports"}),
    )
    report = run_local_eval((case,))

    assert report.grounding.ungrounded_count > 0
    assert report.grounding.grounded == 0
    assert report.grounding.rate == 0.0
    assert len(DEFAULT_CASES) == 32


@pytest.mark.parametrize("language", ["ar", "en"])
def test_each_language_has_grounded_and_denied_cases(language):
    cases = [case for case in DEFAULT_CASES if case.language == language]
    assert any(case.grounded_numbers for case in cases)
    assert any(case.expected_decision == "denied" for case in cases)


def test_expanded_reads_are_grounded_and_localized():
    report = run_local_eval()
    expectations = {
        "cash_flow_summary": ("300.00", "120.00", "180.00"),
        "low_stock_list": ("Product-1", "5.00"),
        "top_customers": ("Ahmad", "150.00"),
        "debt_overview": ("200.00", "500.00"),
        "tax_summary": ("5.00", "2.00"),
    }
    for intent, needles in expectations.items():
        cases = [case for case in report.cases if case.actual_intent == intent and case.expected_decision == "answer"]
        assert cases, intent
        for case in cases:
            # The tenant-2 cash-flow probe deliberately carries different
            # amounts; it is asserted separately in the isolation test.
            if intent == "cash_flow_summary" and "900.00" in case.response:
                continue
            assert case.grounded is True, case.response
            for needle in needles:
                assert needle in case.response, (intent, needle)


def test_cost_visibility_gate_hides_margin_without_permission():
    report = run_local_eval()

    denied = [
        case for case in report.cases if case.actual_intent == "profit_margin" and case.expected_decision == "denied"
    ]
    assert len(denied) == 1
    assert denied[0].query_calls == 0
    for needle in ("150.00", "90.00", "60.00", "40.0"):
        assert needle not in denied[0].response

    allowed = [
        case for case in report.cases if case.actual_intent == "profit_margin" and case.expected_decision == "answer"
    ]
    assert len(allowed) == 1
    assert "90.00" in allowed[0].response


def test_expanded_read_tenant_isolation():
    report = run_local_eval()
    foreign_cash = [
        case for case in report.cases if case.actual_intent == "cash_flow_summary" and "900.00" in case.response
    ]

    assert report.tenant.leaks == 0
    assert len(foreign_cash) == 1
    for needle in ("300.00", "120.00", "180.00"):
        assert needle not in foreign_cash[0].response
