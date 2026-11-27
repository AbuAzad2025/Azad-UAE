"""Regressions for the security audit fixes: tenant scoping and SSRF redirects."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_cash_flow_refuses_missing_tenant_before_any_query():
    from services.cash_flow_service import CashFlowService

    with (
        patch("utils.gl_tenant.active_tenant_id", return_value=None),
        patch.object(CashFlowService, "_get_operating_activities") as operating,
    ):
        with pytest.raises(ValueError, match="active tenant"):
            CashFlowService.generate_cash_flow("2026-01-01", "2026-01-31")

    operating.assert_not_called()


def test_cash_flow_passes_resolved_tenant_to_all_aggregations():
    from services.cash_flow_service import CashFlowService

    empty = {
        "net_cash_from_operating": 0,
        "net_cash_from_investing": 0,
        "net_cash_from_financing": 0,
    }
    with (
        patch.object(CashFlowService, "_get_operating_activities", return_value=empty) as operating,
        patch.object(CashFlowService, "_get_investing_activities", return_value=empty) as investing,
        patch.object(CashFlowService, "_get_financing_activities", return_value=empty) as financing,
        patch.object(CashFlowService, "_get_cash_balance", return_value=0),
    ):
        CashFlowService.generate_cash_flow("2026-01-01", "2026-01-31", tenant_id=7)

    for mocked in (operating, investing, financing):
        assert mocked.call_args.kwargs["tenant_id"] == 7


@pytest.mark.parametrize(
    "method",
    ["predict_sales_trend", "analyze_profit_margins", "detect_sales_patterns", "get_exchange_rate_suggestion"],
)
def test_ai_analytics_fail_closed_without_tenant(method):
    from services.ai_service import AIService

    with patch("services.ai_service.get_active_tenant_id", return_value=None):
        result = (
            getattr(AIService, method)("USD")
            if method == "get_exchange_rate_suggestion"
            else getattr(AIService, method)()
        )

    assert result is not None
    assert result.get("success") is False or result.get("prediction") is None or result.get("rate") is None


def test_knowledge_import_does_not_follow_redirects():
    from ai_knowledge.expansion.knowledge_expansion import KnowledgeExpander

    response = MagicMock(status_code=302)
    with (
        patch("ai_knowledge.expansion.knowledge_expansion.is_public_http_url", return_value=True),
        patch("ai_knowledge.expansion.knowledge_expansion.requests.get", return_value=response) as get,
    ):
        result = KnowledgeExpander().add_website("https://public.example.com/page")

    assert result.get("success") is False
    get.assert_called_once()
    assert get.call_args.kwargs["allow_redirects"] is False


def test_integration_currency_test_rejects_private_url():
    from services.integration_service import IntegrationService

    settings = MagicMock()
    settings.get_config.return_value = {
        "api_url": "http://169.254.169.254/latest/meta-data/",
        "api_key": "",
        "base_currency": "USD",
    }
    with (
        patch("services.integration_service.IntegrationSettings.get_service_config", return_value=settings),
        patch("services.integration_service.requests.get") as get,
    ):
        ok, _msg = IntegrationService.test_currency_api()

    assert ok is False
    get.assert_not_called()
