"""Tests for context_engine and system_integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_knowledge.core.context_engine import ContextEngine, context_engine
from ai_knowledge.core.system_integration import SystemIntegrator, system_integrator


class TestContextEngine:
    def test_greeting_intent(self):
        assert ContextEngine.analyze_context("مرحبا")["intent"] == "greeting"

    def test_analysis_intent(self):
        with patch("ai_knowledge.core.context_engine.system_integrator") as mock_si:
            mock_si.get_system_summary.return_value = {"success": True, "data": {}}
            assert ContextEngine.analyze_context("حلل المبيعات")["intent"] == "analysis"

    def test_enhance_response_analysis(self):
        with patch("ai_knowledge.core.context_engine.data_analyzer") as mock_da:
            mock_da.get_financial_ratios.return_value = {
                "success": True,
                "ratios": {"gross_profit_margin": 25, "net_profit_margin": 10},
            }
            enhanced = ContextEngine.enhance_response("حلل", "تحليل", {})
            assert isinstance(enhanced, str)

    def test_enhance_response_exception_swallowed(self):
        with patch("ai_knowledge.core.context_engine.data_analyzer") as mock_da:
            mock_da.get_financial_ratios.side_effect = RuntimeError("fail")
            result = ContextEngine.enhance_response("حلل المبيعات", "base", {})
            assert "base" in result

    def test_smart_suggestions(self):
        assert len(ContextEngine.get_smart_suggestions("greeting")) >= 1

    def test_singleton(self):
        assert context_engine is not None


class TestSystemIntegrator:
    @pytest.fixture
    def integrator(self):
        return SystemIntegrator()

    def test_customer_balance_by_id(self, integrator):
        customer = MagicMock()
        customer.get_balance_aed.return_value = 500
        customer.name = "Ahmed"
        customer.sales.count.return_value = 1
        customer.sales.order_by.return_value.first.return_value = None
        customer.customer_type = "regular"
        customer.phone = "050"
        customer.email = "a@b.com"
        customer.id = 1
        with patch("models.Customer") as MockC, patch("models.Sale"):
            MockC.query.get.return_value = customer
            result = integrator.get_customer_balance("123")
            assert result["success"] is True

    def test_customer_not_found(self, integrator):
        with patch("models.Customer") as MockC, patch("models.Sale"):
            MockC.query.get.return_value = None
            MockC.query.filter.return_value.first.return_value = None
            assert integrator.get_customer_balance("999")["success"] is False

    def test_add_customer_missing_name(self, integrator):
        assert integrator.add_customer({})["success"] is False

    def test_add_customer_no_tenant(self, integrator):
        with patch("models.tenant.Tenant") as MockT:
            MockT.get_current.return_value = None
            result = integrator.add_customer({"name": "Test", "customer_type": "regular"})
            assert result["success"] is False

    def test_system_summary_returns_dict(self, integrator):
        result = integrator.get_system_summary()
        assert isinstance(result, dict)
        assert "success" in result

    def test_singleton(self):
        assert system_integrator is not None
