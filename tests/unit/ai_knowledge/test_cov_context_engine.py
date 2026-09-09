"""Coverage tests for context_engine uncovered arcs 111->156, 121->156, 148->156."""

from __future__ import annotations

from unittest.mock import patch

from ai_knowledge.core.context_engine import ContextEngine


def _patch_all(data=None, summary=None, search=None, learning=None):
    data = data if data is not None else {"success": False}
    summary = summary if summary is not None else {"success": False}
    search = search if search is not None else {"success": False}
    learning = learning if learning is not None else {"total_interactions": 0}
    return (
        patch("ai_knowledge.core.context_engine.data_analyzer", **{"get_financial_ratios.return_value": data}),
        patch("ai_knowledge.core.context_engine.system_integrator", **{"get_system_summary.return_value": summary}),
        patch("ai_knowledge.core.context_engine.knowledge_expander", **{"search_knowledge.return_value": search}),
        patch("ai_knowledge.core.context_engine.learning_system", **{"get_learning_insights.return_value": learning}),
    )


def test_cov_ctx_analysis_empty_ratios_skips_to_learning():
    """Arc 111->156: analysis intent, success True but ratios empty."""
    p_da, p_si, p_ke, p_ls = _patch_all(data={"success": True, "ratios": {}})
    with p_da, p_si, p_ke, p_ls:
        out = ContextEngine.enhance_response("حلل المبيعات", "base", {})
    assert "معلومات إضافية" in out
    assert "هامش الربح" not in out


def test_cov_ctx_analysis_failed_ratios_skips_to_learning():
    """Arc 111->156 complement: success False takes outer-false path."""
    p_da, p_si, p_ke, p_ls = _patch_all(data={"success": False})
    with p_da, p_si, p_ke, p_ls:
        out = ContextEngine.enhance_response("حلل المبيعات", "base", {})
    assert out == "base"


def test_cov_ctx_analysis_ratios_present_true_side():
    """True side of 111: ratios non-empty appends margin lines."""
    p_da, p_si, p_ke, p_ls = _patch_all(
        data={"success": True, "ratios": {"gross_profit_margin": 42.0, "net_profit_margin": 17.5}}
    )
    with p_da, p_si, p_ke, p_ls:
        out = ContextEngine.enhance_response("حلل المبيعات", "base", {})
    assert "هامش الربح الإجمالي" in out
    assert "هامش الربح الصافي" in out


def test_cov_ctx_data_query_failed_summary_skips_to_learning():
    """Arc 121->156: data_query intent, summary success False."""
    p_da, p_si, p_ke, p_ls = _patch_all(summary={"success": False})
    with p_da, p_si, p_ke, p_ls:
        out = ContextEngine.enhance_response("كم عدد العملاء", "base", {})
    assert out == "base"


def test_cov_ctx_data_query_summary_present_true_side():
    """True side of 121: summary success appends system state lines."""
    p_da, p_si, p_ke, p_ls = _patch_all(
        summary={"success": True, "summary": {"total_customers": 3, "total_products": 5, "today_sales": 9}}
    )
    with p_da, p_si, p_ke, p_ls:
        out = ContextEngine.enhance_response("كم عدد العملاء", "base", {})
    assert "إجمالي العملاء" in out
    assert "إجمالي المنتجات" in out


def test_cov_ctx_search_empty_results_skips_to_learning():
    """Arc 148->156: search intent, success True but empty results."""
    p_da, p_si, p_ke, p_ls = _patch_all(search={"success": True, "results": []})
    with p_da, p_si, p_ke, p_ls:
        out = ContextEngine.enhance_response("ابحث عن دليل النظام", "base", {})
    assert out == "base"


def test_cov_ctx_search_failed_skips_to_learning():
    """Arc 148->156 complement: search success False."""
    p_da, p_si, p_ke, p_ls = _patch_all(search={"success": False})
    with p_da, p_si, p_ke, p_ls:
        out = ContextEngine.enhance_response("ابحث عن دليل النظام", "base", {})
    assert out == "base"


def test_cov_ctx_search_results_present_true_side():
    """True side of 148: results non-empty appends titles."""
    p_da, p_si, p_ke, p_ls = _patch_all(search={"success": True, "results": [{"title": "دليل المنتجات"}]})
    with p_da, p_si, p_ke, p_ls:
        out = ContextEngine.enhance_response("ابحث عن دليل النظام", "base", {})
    assert "دليل المنتجات" in out
