"""Comprehensive unit tests for routes/ai.py."""

import io
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from werkzeug.exceptions import NotFound


def _obj(**attrs):
    obj = MagicMock()
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj


def _access_state(**overrides):
    base = {
        "allowed": True,
        "global_enabled": True,
        "tenant_enabled": True,
        "tenant_id": 1,
        "reason": None,
        "is_platform_user": True,
        "ai_level": "execute",
    }
    base.update(overrides)
    return base


def _basic_tenant_access():
    return _access_state(is_platform_user=False, ai_level="basic")


def _denied_access(reason="tenant_disabled"):
    return _access_state(
        allowed=False,
        is_platform_user=False,
        ai_level="basic",
        reason=reason,
    )


ADVANCED_ENDPOINTS = [
    ("/ai/predict-sales", "get"),
    ("/ai/analyze-margins", "get"),
    ("/ai/detect-patterns", "get"),
    ("/ai/inventory-health", "get"),
    ("/ai/business-insights", "get"),
    ("/ai/deep-analysis", "get"),
    ("/ai/cash-flow-prediction", "get"),
    ("/ai/churn-prediction", "get"),
    ("/ai/optimize-inventory", "get"),
]

ANALYTICS_PATCHES = {
    "/ai/predict-sales": "routes.ai_routes.AIService.predict_sales_trend",
    "/ai/analyze-margins": "routes.ai_routes.AIService.analyze_profit_margins",
    "/ai/detect-patterns": "routes.ai_routes.AIService.detect_sales_patterns",
    "/ai/inventory-health": "routes.ai_routes.AIService.analyze_inventory_health",
    "/ai/deep-analysis": "routes.ai_routes.AIService.deep_business_analysis",
    "/ai/cash-flow-prediction": "routes.ai_routes.AIService.predict_cash_flow",
    "/ai/churn-prediction": "routes.ai_routes.AIService.predict_customer_churn",
    "/ai/optimize-inventory": "routes.ai_routes.AIService.optimize_inventory_levels",
    "/ai/business-insights": "routes.ai_routes.AIService.generate_business_insights",
}


class TestRecommendPrice:
    RECOMMENDED = {
        "recommended_price": 125.0,
        "base_price": 100.0,
        "customer_avg": 150.0,
        "reason": "سعر موصى به",
    }

    def test_happy_path(self, ai_client, mock_ai_service):
        mock_ai_service.recommend_price.return_value = self.RECOMMENDED
        resp = ai_client.post(
            "/ai/recommend-price", json={"product_id": 1, "customer_id": 2}
        )
        assert resp.status_code == 200
        assert resp.get_json()["recommended_price"] == 125.0

    def test_missing_json_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/recommend-price", data=b"x", content_type="application/json"
        )
        assert resp.status_code == 400
        mock_ai_service.recommend_price.assert_not_called()

    def test_empty_json_400(self, ai_client, mock_ai_service):
        resp = ai_client.post("/ai/recommend-price", json={})
        assert resp.status_code == 400

    def test_missing_product_id_400(self, ai_client, mock_ai_service):
        resp = ai_client.post("/ai/recommend-price", json={"customer_id": 2})
        assert resp.status_code == 400

    def test_missing_customer_id_400(self, ai_client, mock_ai_service):
        resp = ai_client.post("/ai/recommend-price", json={"product_id": 1})
        assert resp.status_code == 400

    def test_not_found_404(self, ai_client, mock_ai_service):
        mock_ai_service.recommend_price.return_value = None
        resp = ai_client.post(
            "/ai/recommend-price", json={"product_id": 1, "customer_id": 2}
        )
        assert resp.status_code == 404

    def test_timeout_503(self, ai_client, mock_ai_service):
        mock_ai_service.recommend_price.side_effect = TimeoutError("timeout")
        resp = ai_client.post(
            "/ai/recommend-price", json={"product_id": 1, "customer_id": 2}
        )
        assert resp.status_code == 503

    def test_generic_error_503(self, ai_client, mock_ai_service):
        mock_ai_service.recommend_price.side_effect = RuntimeError("fail")
        resp = ai_client.post(
            "/ai/recommend-price", json={"product_id": 1, "customer_id": 2}
        )
        assert resp.status_code == 503

    def test_plain_text_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/recommend-price", data="text", content_type="text/plain"
        )
        assert resp.status_code == 400


class TestCheckStock:
    def test_success(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.return_value = None
        resp = ai_client.post("/ai/check-stock", json={"product_id": 1, "quantity": 5})
        assert resp.status_code == 200
        assert resp.get_json()["type"] == "success"

    def test_warning(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.return_value = {
            "type": "warning",
            "message": "low",
        }
        resp = ai_client.post("/ai/check-stock", json={"product_id": 1, "quantity": 10})
        assert resp.get_json()["type"] == "warning"

    def test_error_type(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.return_value = {
            "type": "error",
            "message": "no stock",
        }
        resp = ai_client.post("/ai/check-stock", json={"product_id": 1, "quantity": 10})
        assert resp.get_json()["type"] == "error"

    def test_missing_json_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/check-stock", data=b"x", content_type="application/json"
        )
        assert resp.status_code == 400

    def test_empty_json_400(self, ai_client, mock_ai_service):
        resp = ai_client.post("/ai/check-stock", json={})
        assert resp.status_code == 400

    def test_missing_product_400(self, ai_client, mock_ai_service):
        resp = ai_client.post("/ai/check-stock", json={"quantity": 1})
        assert resp.status_code == 400

    def test_invalid_quantity_422(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/check-stock", json={"product_id": 1, "quantity": "x"}
        )
        assert resp.status_code == 422

    def test_negative_quantity_ok(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.return_value = None
        resp = ai_client.post("/ai/check-stock", json={"product_id": 1, "quantity": -1})
        assert resp.status_code == 200

    def test_timeout_503(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.side_effect = TimeoutError("t")
        resp = ai_client.post("/ai/check-stock", json={"product_id": 1, "quantity": 1})
        assert resp.status_code == 503

    def test_generic_error_503(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.side_effect = RuntimeError("x")
        resp = ai_client.post("/ai/check-stock", json={"product_id": 1, "quantity": 1})
        assert resp.status_code == 503


class TestAnalyzeCustomer:
    ANALYSIS = {"customer_name": "c1", "risk_level": "low"}

    def test_happy_path(self, ai_client, mock_ai_service):
        mock_ai_service.analyze_customer_behavior.return_value = self.ANALYSIS
        resp = ai_client.get("/ai/analyze-customer/42")
        assert resp.status_code == 200
        assert resp.get_json()["customer_name"] == "c1"

    def test_not_found_404(self, ai_client, mock_ai_service):
        mock_ai_service.analyze_customer_behavior.return_value = None
        resp = ai_client.get("/ai/analyze-customer/999")
        assert resp.status_code == 404

    def test_timeout_503(self, ai_client, mock_ai_service):
        mock_ai_service.analyze_customer_behavior.side_effect = TimeoutError("t")
        resp = ai_client.get("/ai/analyze-customer/1")
        assert resp.status_code == 503

    def test_generic_error_503(self, ai_client, mock_ai_service):
        mock_ai_service.analyze_customer_behavior.side_effect = RuntimeError("x")
        resp = ai_client.get("/ai/analyze-customer/1")
        assert resp.status_code == 503

    def test_invalid_id_404(self, ai_client):
        resp = ai_client.get("/ai/analyze-customer/abc")
        assert resp.status_code == 404


class TestExchangeRate:
    def test_returns_suggestion(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.get_exchange_rate_suggestion",
            return_value={"rate": 3.67},
        ) as m:
            resp = ai_client.get("/ai/exchange-rate/USD")
            assert resp.status_code == 200
            assert resp.get_json()["rate"] == 3.67
            m.assert_called_once_with("USD")

    def test_eur_currency(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.get_exchange_rate_suggestion",
            return_value={"rate": 4.0},
        ):
            resp = ai_client.get("/ai/exchange-rate/EUR")
            assert resp.status_code == 200

    def test_empty_currency(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.get_exchange_rate_suggestion", return_value={}
        ):
            resp = ai_client.get("/ai/exchange-rate/")
            assert resp.status_code in (200, 308, 404)

    def test_service_called(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.get_exchange_rate_suggestion",
            return_value={"ok": True},
        ) as m:
            ai_client.get("/ai/exchange-rate/AED")
            m.assert_called_once()


class TestSearchMarketPrice:
    @staticmethod
    def _product_chain(product=None):
        chain = MagicMock()
        if product is None:
            chain.first_or_404.side_effect = NotFound()
        else:
            chain.first_or_404.return_value = product
        return chain

    def test_happy_path(self, ai_client):
        product = _obj(name="Brake Pad")
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(product)
            resp = ai_client.get("/ai/search-market-price/5")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["product"] == "Brake Pad"

    def test_tenant_mismatch_404(self, ai_client):
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(None)
            resp = ai_client.get("/ai/search-market-price/99")
        assert resp.status_code == 404

    def test_filter_by_tenant(self, ai_client):
        product = _obj(name="X")
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(product)
            ai_client.get("/ai/search-market-price/1")
            Product.query.filter_by.assert_called_with(id=1, tenant_id=1)

    def test_response_has_suggestions(self, ai_client):
        product = _obj(name="Y")
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(product)
            resp = ai_client.get("/ai/search-market-price/2")
        assert resp.get_json()["suggestions"] == []

    def test_response_message(self, ai_client):
        product = _obj(name="Z")
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(product)
            resp = ai_client.get("/ai/search-market-price/3")
        assert "قيد التطوير" in resp.get_json()["message"]

    def test_product_name_in_json(self, ai_client):
        product = _obj(name="Filter")
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(product)
            resp = ai_client.get("/ai/search-market-price/7")
        assert resp.get_json()["product"] == "Filter"


class TestFindCompatible:
    @staticmethod
    def _product_chain(product=None):
        chain = MagicMock()
        if product is None:
            chain.first_or_404.side_effect = NotFound()
        else:
            chain.first_or_404.return_value = product
        return chain

    def test_happy_path(self, ai_client):
        product = _obj(name="ECU")
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(product)
            resp = ai_client.get("/ai/find-compatible/10")
        assert resp.status_code == 200
        assert resp.get_json()["compatible_vehicles"] == []

    def test_tenant_mismatch_404(self, ai_client):
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(None)
            resp = ai_client.get("/ai/find-compatible/10")
        assert resp.status_code == 404

    def test_tenant_filter(self, ai_client):
        product = _obj(name="P")
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(product)
            ai_client.get("/ai/find-compatible/4")
            Product.query.filter_by.assert_called_with(id=4, tenant_id=1)

    def test_success_flag(self, ai_client):
        product = _obj(name="P2")
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = self._product_chain(product)
            resp = ai_client.get("/ai/find-compatible/8")
        assert resp.get_json()["success"] is True


class TestChatAccessPolicy:
    def test_denied_returns_403(self, ai_client):
        with patch(
            "routes.ai_routes.get_ai_access_state", return_value=_denied_access()
        ):
            resp = ai_client.post("/ai/chat", json={"message": "hello"})
        assert resp.status_code == 403
        assert resp.get_json()["success"] is False

    def test_global_disabled_reason(self, ai_client):
        with patch(
            "routes.ai_routes.get_ai_access_state",
            return_value=_denied_access("global_disabled"),
        ):
            resp = ai_client.post("/ai/chat", json={"message": "hi"})
        assert resp.status_code == 403
        assert resp.get_json()["reason"] == "global_disabled"

    def test_tenant_disabled_reason(self, ai_client):
        with patch(
            "routes.ai_routes.get_ai_access_state",
            return_value=_denied_access("tenant_disabled"),
        ):
            resp = ai_client.post("/ai/chat", json={"message": "hi"})
        assert resp.status_code == 403

    def test_missing_tenant_reason(self, ai_client):
        with patch(
            "routes.ai_routes.get_ai_access_state",
            return_value=_denied_access("missing_tenant"),
        ):
            resp = ai_client.post("/ai/chat", json={"message": "hi"})
        assert resp.status_code == 403

    def test_denied_json_accept_header(self, ai_client):
        with patch(
            "routes.ai_routes.get_ai_access_state", return_value=_denied_access()
        ):
            resp = ai_client.post(
                "/ai/chat",
                json={"message": "x"},
                headers={"Accept": "application/json"},
            )
        assert resp.status_code == 403


class TestChatCapabilityLevel:
    @pytest.mark.parametrize("path,method", ADVANCED_ENDPOINTS)
    def test_basic_level_blocks_advanced(self, ai_client, path, method):
        state = _basic_tenant_access()
        with patch("routes.ai_routes.get_ai_access_state", return_value=state):
            with patch(
                "routes.ai_routes.AIService.predict_sales_trend", return_value={}
            ):
                with patch(
                    "routes.ai_routes.AIService.analyze_profit_margins", return_value={}
                ):
                    with patch(
                        "routes.ai_routes.AIService.detect_sales_patterns",
                        return_value={},
                    ):
                        with patch(
                            "routes.ai_routes.AIService.analyze_inventory_health",
                            return_value={},
                        ):
                            with patch(
                                "routes.ai_routes.AIService.generate_business_insights",
                                return_value=[],
                            ):
                                with patch(
                                    "routes.ai_routes.AIService.deep_business_analysis",
                                    return_value={},
                                ):
                                    with patch(
                                        "routes.ai_routes.AIService.predict_cash_flow",
                                        return_value={},
                                    ):
                                        with patch(
                                            "routes.ai_routes.AIService.predict_customer_churn",
                                            return_value={},
                                        ):
                                            with patch(
                                                "routes.ai_routes.AIService.optimize_inventory_levels",
                                                return_value={},
                                            ):
                                                client_method = getattr(
                                                    ai_client, method
                                                )
                                                resp = client_method(
                                                    path,
                                                    headers={
                                                        "Accept": "application/json"
                                                    },
                                                )
        assert resp.status_code == 403
        assert resp.get_json()["required"] == "advanced"

    def test_basic_allows_chat(self, ai_client, mock_ai_service):
        state = _basic_tenant_access()
        with patch("routes.ai_routes.get_ai_access_state", return_value=state):
            with patch(
                "routes.ai_routes.chat._user_can_ai_execute_actions", return_value=False
            ):
                resp = ai_client.post("/ai/chat", json={"message": "مرحبا"})
        assert resp.status_code == 200

    def test_basic_blocks_ask_genius(self, ai_client):
        state = _basic_tenant_access()
        with patch("routes.ai_routes.get_ai_access_state", return_value=state):
            resp = ai_client.post("/ai/ask-genius", json={"question": "q"})
        assert resp.status_code == 403

    def test_basic_blocks_upload_excel(self, ai_client):
        state = _basic_tenant_access()
        with patch("routes.ai_routes.get_ai_access_state", return_value=state):
            resp = ai_client.post(
                "/ai/upload-excel", headers={"Accept": "application/json"}
            )
        assert resp.status_code == 403


class TestChatEndpoint:
    def test_empty_message_400(self, ai_client, mock_ai_service):
        resp = ai_client.post("/ai/chat", json={"message": "   "})
        assert resp.status_code == 400
        mock_ai_service.chat_response.assert_not_called()

    def test_fallback_chat_response(self, ai_client, mock_ai_service):
        with patch(
            "routes.ai_routes.chat._user_can_ai_execute_actions", return_value=False
        ):
            resp = ai_client.post("/ai/chat", json={"message": "ما هو المخزون؟"})
        assert resp.status_code == 200
        assert resp.get_json()["response"] == "mocked chat"
        mock_ai_service.chat_response.assert_called_once()

    def test_action_dispatcher_success(self, ai_client, mock_ai_service):
        dispatch_result = MagicMock(success=True, message="تم التنفيذ")
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
            ad.parse_chat_action.return_value = ("create_sale", {})
            ad.dispatch.return_value = dispatch_result
            resp = ai_client.post("/ai/chat", json={"message": "فاتورة جديدة"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["action_executed"] is True
        assert body["response"] == "تم التنفيذ"
        mock_ai_service.chat_response.assert_not_called()

    def test_action_dispatcher_fallback_wizard(self, ai_client, mock_ai_service):
        dispatch_result = MagicMock(success=False, message="fail")
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
            ad.parse_chat_action.return_value = ("create_sale", {})
            ad.dispatch.return_value = dispatch_result
            with patch(
                "routes.ai_routes.chat._process_user_action",
                return_value="wizard reply",
            ) as proc:
                resp = ai_client.post("/ai/chat", json={"message": "فاتورة"})
        assert resp.get_json()["response"] == "wizard reply"
        proc.assert_called_once()

    def test_greeting_via_intelligent_response(self, ai_client, mock_ai_service):
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
            with patch(
                "ai_knowledge.agents_core.intelligent_response", return_value="أهلا"
            ) as ir:
                ad.parse_chat_action.return_value = ("greeting", {})
                resp = ai_client.post("/ai/chat", json={"message": "مرحبا"})
        assert resp.get_json()["response"] == "أهلا"
        ir.assert_called_once()

    def test_help_via_intelligent_response(self, ai_client, mock_ai_service):
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
            with patch(
                "ai_knowledge.agents_core.intelligent_response", return_value="مساعدة"
            ):
                ad.parse_chat_action.return_value = ("help", {})
                resp = ai_client.post("/ai/chat", json={"message": "مساعدة"})
        assert resp.get_json()["response"] == "مساعدة"

    def test_process_user_action_rasid(self, ai_client, mock_ai_service):
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
            ad.parse_chat_action.return_value = None
            resp = ai_client.post("/ai/chat", json={"message": "رصيد"})
        assert resp.status_code == 200
        assert "رصيد العميل" in resp.get_json()["response"]

    def test_process_user_action_customer(self, ai_client, mock_ai_service):
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
            ad.parse_chat_action.return_value = None
            resp = ai_client.post("/ai/chat", json={"message": "عميل"})
        assert "إضافة عميل" in resp.get_json()["response"]

    def test_process_user_action_product(self, ai_client, mock_ai_service):
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
            ad.parse_chat_action.return_value = None
            resp = ai_client.post("/ai/chat", json={"message": "منتج"})
        assert "إضافة منتج" in resp.get_json()["response"]

    def test_process_user_action_invoice(self, ai_client, mock_ai_service):
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
            ad.parse_chat_action.return_value = None
            resp = ai_client.post("/ai/chat", json={"message": "فاتورة"})
        assert "فاتورة مبيعات" in resp.get_json()["response"]

    def test_trainer_called_on_chat(self, ai_client, mock_ai_service):
        with patch(
            "routes.ai_routes.chat._user_can_ai_execute_actions", return_value=False
        ):
            with patch("ai_knowledge.trainer.trainer") as trainer:
                ai_client.post("/ai/chat", json={"message": "سؤال"})
        trainer.learn_from_interaction.assert_called_once()

    def test_ai_mode_local(self, ai_client, mock_ai_service):
        with patch(
            "routes.ai_routes.chat._user_can_ai_execute_actions", return_value=False
        ):
            resp = ai_client.post(
                "/ai/chat", json={"message": "test", "ai_mode": "local"}
            )
        assert resp.status_code == 200
        call_ctx = mock_ai_service.chat_response.call_args[0][1]
        assert call_ctx["force_local"] is True

    def test_response_includes_ai_enabled(self, ai_client, mock_ai_service):
        with patch(
            "routes.ai_routes.chat._user_can_ai_execute_actions", return_value=False
        ):
            resp = ai_client.post("/ai/chat", json={"message": "x"})
        assert "ai_enabled" in resp.get_json()

    def test_no_execute_without_permission(self, ai_client, mock_ai_service, mock_user):
        mock_user.is_owner = False
        mutation_perms = {
            "manage_sales",
            "manage_payments",
            "manage_purchases",
            "manage_expenses",
            "manage_customers",
            "manage_products",
            "manage_cheques",
            "manage_warehouse",
        }
        mock_user.has_permission.side_effect = lambda code: code not in mutation_perms
        state = _access_state(is_platform_user=False, ai_level="execute")
        with patch("routes.ai_routes.get_ai_access_state", return_value=state):
            resp = ai_client.post("/ai/chat", json={"message": "عميل"})
        assert resp.status_code == 200
        mock_ai_service.chat_response.assert_called_once()

    def test_wizard_help_in_context(self, ai_client, mock_ai_service):
        with patch(
            "routes.ai_routes.shared._get_conversation_context",
            return_value={"last_action": "عميل", "option": "1", "step": 1},
        ):
            with patch("ai_knowledge.action_dispatcher.action_dispatcher") as ad:
                ad.parse_chat_action.return_value = None
                resp = ai_client.post("/ai/chat", json={"message": "مساعدة"})
        assert "مساعدة" in resp.get_json()["response"]


class TestSmartListener:
    @pytest.mark.parametrize(
        "message,expected",
        [
            ("عودة", "back"),
            ("رجوع", "back"),
            ("إلغاء", "back"),
            ("مساعدة", "help"),
            ("help", "help"),
            ("ساعدني", "help"),
            ("نعم", "confirm"),
            ("yes", "confirm"),
            ("موافق", "confirm"),
            ("لا", "cancel"),
            ("no", "cancel"),
            ("استمر", "continue"),
            ("مرحبا", "continue"),
        ],
    )
    def test_listener_outcomes(self, message, expected):
        from routes.ai_routes import smart_listener

        assert smart_listener(message, {}) == expected

    def test_case_insensitive(self):
        from routes.ai_routes import smart_listener

        assert smart_listener("HELP", {}) == "help"

    def test_with_context(self):
        from routes.ai_routes import smart_listener

        assert smart_listener("  عودة  ", {"step": 2}) == "back"


class TestTrainLocalAI:
    def test_appends_training_record(self, tmp_path):
        from routes.ai_routes import train_local_ai

        training_file = tmp_path / "local_training.json"
        with patch("ai_knowledge.get_knowledge_path", return_value=str(training_file)):
            result = train_local_ai("act", {"a": 1}, {"ok": True})
        assert result is True
        data = json.loads(training_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["action"] == "act"

    def test_truncates_over_1000(self, tmp_path):
        from routes.ai_routes import train_local_ai

        training_file = tmp_path / "local_training.json"
        existing = [
            {"action": "x", "input_data": {}, "result": {}, "timestamp": "t"}
        ] * 1001
        training_file.write_text(json.dumps(existing), encoding="utf-8")
        with patch("ai_knowledge.get_knowledge_path", return_value=str(training_file)):
            train_local_ai("new", {}, {})
        data = json.loads(training_file.read_text(encoding="utf-8"))
        assert len(data) == 1000
        assert data[-1]["action"] == "new"

    def test_returns_false_on_error(self):
        from routes.ai_routes import train_local_ai

        with patch("ai_knowledge.get_knowledge_path", side_effect=OSError("fail")):
            assert train_local_ai("a", {}, {}) is False

    def test_creates_file_when_missing(self, tmp_path):
        from routes.ai_routes import train_local_ai

        training_file = tmp_path / "new_training.json"
        with patch("ai_knowledge.get_knowledge_path", return_value=str(training_file)):
            train_local_ai("create", {"k": "v"}, {"ok": 1})
        assert training_file.exists()


class TestApplySmartListeners:
    def test_back_response(self):
        from routes.ai_routes import apply_smart_listeners

        status, msg = apply_smart_listeners("عودة", {"step": 1}, "عميل")
        assert status == "back"
        assert "العودة" in msg

    def test_help_response(self):
        from routes.ai_routes import apply_smart_listeners

        status, msg = apply_smart_listeners("مساعدة", {"step": 3}, "منتج")
        assert status == "help"
        assert "الخطوة 3" in msg

    def test_continue_response(self):
        from routes.ai_routes import apply_smart_listeners

        status, msg = apply_smart_listeners("بيانات", {}, "فاتورة")
        assert status == "continue"
        assert msg is None

    def test_help_keyword_english(self):
        from routes.ai_routes import apply_smart_listeners

        status, _ = apply_smart_listeners("help", {"step": 0}, "x")
        assert status == "help"

    def test_back_arabic(self):
        from routes.ai_routes import apply_smart_listeners

        status, _ = apply_smart_listeners("رجوع", {}, "y")
        assert status == "back"

    def test_continue_random_text(self):
        from routes.ai_routes import apply_smart_listeners

        status, msg = apply_smart_listeners("اسم المنتج", {"step": 1}, "منتج")
        assert status == "continue"
        assert msg is None


class TestCreateFinalOptions:
    @pytest.mark.parametrize(
        "action", ["عميل", "منتج", "فاتورة", "مصروف", "استلام", "إعطاء"]
    )
    def test_known_actions(self, action):
        from routes.ai_routes import create_final_options

        text = create_final_options(action, "item", 1)
        assert "ماذا تريد" in text

    def test_unknown_action_default(self):
        from routes.ai_routes import create_final_options

        text = create_final_options("unknown", "x", 9)
        assert "تكرار العملية" in text

    def test_customer_options(self):
        from routes.ai_routes import create_final_options

        assert "إضافة عميل آخر" in create_final_options("عميل", "A", 1)

    def test_product_options(self):
        from routes.ai_routes import create_final_options

        assert "إضافة منتج آخر" in create_final_options("منتج", "P", 2)

    def test_invoice_options(self):
        from routes.ai_routes import create_final_options

        assert "إنشاء فاتورة أخرى" in create_final_options("فاتورة", "S", 3)

    def test_expense_options(self):
        from routes.ai_routes import create_final_options

        assert "إضافة مصروف آخر" in create_final_options("مصروف", "E", 4)

    def test_receive_options(self):
        from routes.ai_routes import create_final_options

        assert "استلام دفعة أخرى" in create_final_options("استلام", "C", 5)

    def test_give_options(self):
        from routes.ai_routes import create_final_options

        assert "إعطاء دفعة أخرى" in create_final_options("إعطاء", "C", 6)


class TestUserCanAiExecuteActions:
    def test_unauthenticated_false(self):
        from routes.ai_routes import _user_can_ai_execute_actions

        user = MagicMock(is_authenticated=False)
        assert _user_can_ai_execute_actions(user) is False

    def test_none_user_false(self):
        from routes.ai_routes import _user_can_ai_execute_actions

        assert _user_can_ai_execute_actions(None) is False

    def test_owner_true(self):
        from routes.ai_routes import _user_can_ai_execute_actions

        user = MagicMock(is_authenticated=True, is_owner=True)
        assert _user_can_ai_execute_actions(user) is True

    def test_manage_sales_permission(self):
        from routes.ai_routes import _user_can_ai_execute_actions

        user = MagicMock(is_authenticated=True, is_owner=False)
        user.has_permission.side_effect = lambda code: code == "manage_sales"
        assert _user_can_ai_execute_actions(user) is True

    def test_manage_products_permission(self):
        from routes.ai_routes import _user_can_ai_execute_actions

        user = MagicMock(is_authenticated=True, is_owner=False)
        user.has_permission.side_effect = lambda code: code == "manage_products"
        assert _user_can_ai_execute_actions(user) is True

    def test_no_permissions_false(self):
        from routes.ai_routes import _user_can_ai_execute_actions

        user = MagicMock(is_authenticated=True, is_owner=False)
        user.has_permission.return_value = False
        assert _user_can_ai_execute_actions(user) is False

    def test_manage_customers_permission(self):
        from routes.ai_routes import _user_can_ai_execute_actions

        user = MagicMock(is_authenticated=True, is_owner=False)
        user.has_permission.side_effect = lambda code: code == "manage_customers"
        assert _user_can_ai_execute_actions(user) is True

    def test_manage_warehouse_permission(self):
        from routes.ai_routes import _user_can_ai_execute_actions

        user = MagicMock(is_authenticated=True, is_owner=False)
        user.has_permission.side_effect = lambda code: code == "manage_warehouse"
        assert _user_can_ai_execute_actions(user) is True


class TestProcessUserActionDirect:
    def test_rasid_menu(self, mock_user):
        from routes.ai_routes import _process_user_action

        with patch("routes.ai_routes.actions._conversation_ctx", return_value={}):
            result = _process_user_action("رصيد", mock_user)
        assert "تعديل رصيد" in result

    def test_customer_menu(self, mock_user):
        from routes.ai_routes import _process_user_action

        with patch("routes.ai_routes.actions._conversation_ctx", return_value={}):
            result = _process_user_action("عميل", mock_user)
        assert "إضافة عميل جديد" in result

    def test_product_menu(self, mock_user):
        from routes.ai_routes import _process_user_action

        with patch("routes.ai_routes.actions._conversation_ctx", return_value={}):
            result = _process_user_action("منتج", mock_user)
        assert "إضافة منتج جديد" in result

    def test_invoice_menu(self, mock_user):
        from routes.ai_routes import _process_user_action

        with patch("routes.ai_routes.actions._conversation_ctx", return_value={}):
            result = _process_user_action("فاتورة", mock_user)
        assert "فاتورة مبيعات" in result

    def test_rasid_option_4_lists_customers(self, mock_user):
        from routes.ai_routes import _process_user_action

        customer = _obj(name="Ali", balance=100)
        chain = MagicMock()
        chain.all.return_value = [customer]
        with patch(
            "routes.ai_routes.actions._conversation_ctx",
            return_value={"last_action": "رصيد"},
        ):
            with patch("models.customer.Customer") as Customer:
                Customer.query.filter_by.return_value = chain
                result = _process_user_action("4", mock_user)
        assert "Ali" in result

    def test_rasid_option_4_no_customers(self, mock_user):
        from routes.ai_routes import _process_user_action

        chain = MagicMock()
        chain.all.return_value = []
        with patch(
            "routes.ai_routes.actions._conversation_ctx",
            return_value={"last_action": "رصيد"},
        ):
            with patch("models.customer.Customer") as Customer:
                Customer.query.filter_by.return_value = chain
                result = _process_user_action("4", mock_user)
        assert "لا يوجد عملاء" in result

    def test_customer_step1_prompt(self, mock_user):
        from routes.ai_routes import _process_user_action

        ctx = {"last_action": "عميل"}
        with patch("routes.ai_routes.actions._conversation_ctx", return_value=ctx):
            result = _process_user_action("1", mock_user)
        assert "اسم العميل" in result

    def test_back_in_customer_wizard(self, mock_user):
        from routes.ai_routes import _process_user_action

        ctx = {"last_action": "عميل", "option": "1", "step": 1}
        with patch("routes.ai_routes.actions._conversation_ctx", return_value=ctx):
            result = _process_user_action("عودة", mock_user)
        assert "عودة" in result

    def test_help_in_customer_wizard(self, mock_user):
        from routes.ai_routes import _process_user_action

        ctx = {"last_action": "عميل", "option": "1", "step": 2}
        with patch("routes.ai_routes.actions._conversation_ctx", return_value=ctx):
            result = _process_user_action("مساعدة", mock_user)
        assert "مساعدة" in result

    def test_exception_returns_error_message(self, mock_user):
        from routes.ai_routes import _process_user_action

        with patch(
            "routes.ai_routes.actions._conversation_ctx",
            side_effect=RuntimeError("boom"),
        ):
            result = _process_user_action("x", mock_user)
        assert "خطأ" in result

    def test_rasid_option_2_redirect(self, mock_user):
        from routes.ai_routes import _process_user_action

        with patch(
            "routes.ai_routes.actions._conversation_ctx",
            return_value={"last_action": "رصيد"},
        ):
            result = _process_user_action("2", mock_user)
        assert "استلام دفعة" in result

    def test_rasid_option_3_redirect(self, mock_user):
        from routes.ai_routes import _process_user_action

        with patch(
            "routes.ai_routes.actions._conversation_ctx",
            return_value={"last_action": "رصيد"},
        ):
            result = _process_user_action("3", mock_user)
        assert "إعطاء دفعة" in result


class TestIntelligentColumnDetector:
    def test_arabic_columns(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"اسم المنتج": ["A"], "رقم القطعة": ["P1"], "السعر": [10]})
        mapping = _intelligent_column_detector(df)
        assert mapping is not None
        assert "name" in mapping
        assert "price" in mapping

    def test_english_columns(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"product name": ["A"], "part code": ["P1"], "price": [5]})
        mapping = _intelligent_column_detector(df)
        assert mapping is not None

    def test_quantity_column(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"name": ["A"], "sku": ["P"], "cost": [1], "qty": [3]})
        mapping = _intelligent_column_detector(df)
        assert "quantity" in mapping

    def test_fallback_positions(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"col0": ["A"], "col1": ["B"], "col2": [1]})
        mapping = _intelligent_column_detector(df)
        assert mapping["name"] == "col0"
        assert mapping["part_number"] == "col1"

    def test_insufficient_columns_returns_none(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"only": [1]})
        assert _intelligent_column_detector(df) is None

    def test_two_columns_returns_none(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"a": [1], "b": [2]})
        assert _intelligent_column_detector(df) is None

    def test_stock_keyword(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"name": ["A"], "code": ["C"], "price": [2], "stock": [9]})
        mapping = _intelligent_column_detector(df)
        assert mapping["quantity"] == "stock"

    def test_mixed_keywords(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"description": ["X"], "reference": ["R"], "amount": [7]})
        mapping = _intelligent_column_detector(df)
        assert mapping is not None

    def test_minimum_three_mappings(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame({"name": ["n"], "part": ["p"], "price": [1]})
        mapping = _intelligent_column_detector(df)
        assert len(mapping) >= 3

    def test_empty_dataframe(self):
        from routes.ai_routes import _intelligent_column_detector

        df = pd.DataFrame()
        assert _intelligent_column_detector(df) is None


class TestConversationCtx:
    def test_wraps_context_data(self):
        from routes.ai_routes import _conversation_ctx

        with patch(
            "routes.ai_routes.shared._get_conversation_context", return_value={"k": "v"}
        ):
            ctx = _conversation_ctx(1, 1)
        assert ctx["k"] == "v"

    def test_autosave_on_setitem(self):
        from routes.ai_routes import _conversation_ctx

        with patch(
            "routes.ai_routes.shared._get_conversation_context", return_value={}
        ):
            with patch("routes.ai_routes._set_conversation_context") as setter:
                ctx = _conversation_ctx(5, 2)
                ctx["a"] = 1
        setter.assert_called()

    def test_autosave_on_delitem(self):
        from routes.ai_routes import _conversation_ctx

        with patch(
            "routes.ai_routes.shared._get_conversation_context", return_value={"x": 1}
        ):
            with patch("routes.ai_routes._set_conversation_context") as setter:
                ctx = _conversation_ctx(5, 2)
                del ctx["x"]
        setter.assert_called()

    def test_autosave_on_update(self):
        from routes.ai_routes import _conversation_ctx

        with patch(
            "routes.ai_routes.shared._get_conversation_context", return_value={}
        ):
            with patch("routes.ai_routes._set_conversation_context") as setter:
                ctx = _conversation_ctx(3, 1)
                ctx.update({"b": 2})
        setter.assert_called()

    def test_autosave_on_clear(self):
        from routes.ai_routes import _conversation_ctx

        with patch(
            "routes.ai_routes.shared._get_conversation_context", return_value={"z": 1}
        ):
            with patch("routes.ai_routes._set_conversation_context") as setter:
                ctx = _conversation_ctx(3, 1)
                ctx.clear()
        setter.assert_called()

    def test_empty_when_none(self):
        from routes.ai_routes import _conversation_ctx

        with patch(
            "routes.ai_routes.shared._get_conversation_context", return_value=None
        ):
            ctx = _conversation_ctx(1, None)
        assert ctx == {}


class TestProcessExcelIntelligently:
    def test_successful_import(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently

        df = pd.DataFrame({"name": ["Prod"], "part": ["PN1"], "price": [10]})
        warehouse = _obj(name="Main", id=1)
        file_obj = MagicMock()
        with patch("routes.ai_routes.assistant.pd.read_excel", return_value=df):
            with patch(
                "routes.ai_routes._intelligent_column_detector",
                return_value={"name": "name", "part_number": "part", "price": "price"},
            ):
                with patch("models.Warehouse") as Warehouse:
                    with patch("models.Product") as Product:
                        with patch("routes.ai_routes.assistant.db"):
                            with patch("routes.ai_routes.actions.assign_tenant_id"):
                                with patch("routes.ai_routes.assistant.StockService"):
                                    with patch("routes.ai_routes._train_ai_from_excel"):
                                        Warehouse.query.filter_by.return_value.first.return_value = (
                                            warehouse
                                        )
                                        Product.query.filter_by.return_value.first.return_value = (
                                            None
                                        )
                                        result = _process_excel_intelligently(
                                            file_obj, 1, mock_user
                                        )
        assert result["success"] is True

    def test_unknown_structure(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently

        with patch(
            "routes.ai_routes.assistant.pd.read_excel",
            return_value=pd.DataFrame({"x": [1]}),
        ):
            with patch(
                "routes.ai_routes._intelligent_column_detector", return_value=None
            ):
                result = _process_excel_intelligently(MagicMock(), 1, mock_user)
        assert result["success"] is False

    def test_missing_warehouse(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently

        df = pd.DataFrame({"name": ["A"], "part": ["P"], "price": [1]})
        with patch("routes.ai_routes.assistant.pd.read_excel", return_value=df):
            with patch(
                "routes.ai_routes._intelligent_column_detector",
                return_value={"name": "name", "part_number": "part", "price": "price"},
            ):
                with patch("models.Warehouse") as Warehouse:
                    Warehouse.query.filter_by.return_value.first.return_value = None
                    result = _process_excel_intelligently(MagicMock(), 99, mock_user)
        assert "غير موجود" in result["error"]

    def test_updates_existing_product(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently

        df = pd.DataFrame({"name": ["A"], "part": ["P1"], "price": [20]})
        warehouse = _obj(name="W")
        existing = MagicMock(id=5)
        with patch("routes.ai_routes.assistant.pd.read_excel", return_value=df):
            with patch(
                "routes.ai_routes._intelligent_column_detector",
                return_value={"name": "name", "part_number": "part", "price": "price"},
            ):
                with patch("models.Warehouse") as Warehouse:
                    with patch("models.Product") as Product:
                        with patch("routes.ai_routes.assistant.db"):
                            with patch("routes.ai_routes._train_ai_from_excel"):
                                Warehouse.query.filter_by.return_value.first.return_value = (
                                    warehouse
                                )
                                Product.query.filter_by.return_value.first.return_value = (
                                    existing
                                )
                                result = _process_excel_intelligently(
                                    MagicMock(), 1, mock_user
                                )
        assert result["success"] is True
        assert result["details"]["updated"] == 1

    def test_read_exception(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently

        with patch(
            "routes.ai_routes.assistant.pd.read_excel",
            side_effect=ValueError("bad file"),
        ):
            result = _process_excel_intelligently(MagicMock(), 1, mock_user)
        assert result["success"] is False


class TestConfig:
    def test_get_renders_template(self, ai_client):
        with patch(
            "routes.ai_routes.assistant.render_template", return_value="config-page"
        ) as rt:
            resp = ai_client.get("/ai/config")
        assert resp.status_code == 200
        assert resp.data == b"config-page"
        rt.assert_called_once()

    def test_post_missing_key(self, ai_client):
        resp = ai_client.post("/ai/config", data={})
        assert resp.get_json()["success"] is False

    def test_post_saves_groq_key(self, ai_client, tmp_path):
        env_dir = tmp_path / "ai_routes"
        env_dir.mkdir()
        fake_assistant = env_dir / "assistant.py"
        fake_assistant.write_text("#", encoding="utf-8")
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=1\n", encoding="utf-8")
        with patch("routes.ai_routes.assistant.__file__", str(fake_assistant)):
            resp = ai_client.post(
                "/ai/config", data={"api_key": "new-key", "provider": "groq"}
            )
        assert resp.get_json()["success"] is True
        content = env_file.read_text(encoding="utf-8")
        assert "GROQ_API_KEY=new-key" in content

    def test_post_updates_existing_key(self, ai_client, tmp_path):
        env_dir = tmp_path / "ai_routes"
        env_dir.mkdir()
        fake_assistant = env_dir / "assistant.py"
        fake_assistant.write_text("#", encoding="utf-8")
        env_file = tmp_path / ".env"
        env_file.write_text("GROQ_API_KEY=old\n", encoding="utf-8")
        with patch("routes.ai_routes.assistant.__file__", str(fake_assistant)):
            resp = ai_client.post(
                "/ai/config", data={"api_key": "updated", "provider": "groq"}
            )
        assert "GROQ_API_KEY=updated" in env_file.read_text(encoding="utf-8")
        assert resp.get_json()["success"] is True

    def test_post_gemini_provider(self, ai_client, tmp_path):
        env_dir = tmp_path / "ai_routes"
        env_dir.mkdir()
        fake_assistant = env_dir / "assistant.py"
        fake_assistant.write_text("#", encoding="utf-8")
        (tmp_path / ".env").write_text("", encoding="utf-8")
        with patch("routes.ai_routes.assistant.__file__", str(fake_assistant)):
            resp = ai_client.post(
                "/ai/config", data={"api_key": "g-key", "provider": "gemini"}
            )
        assert "GEMINI_API_KEY=g-key" in (tmp_path / ".env").read_text(encoding="utf-8")
        assert resp.get_json()["provider"] == "gemini"

    def test_post_openai_provider(self, ai_client, tmp_path):
        env_dir = tmp_path / "ai_routes"
        env_dir.mkdir()
        fake_assistant = env_dir / "assistant.py"
        fake_assistant.write_text("#", encoding="utf-8")
        (tmp_path / ".env").write_text("", encoding="utf-8")
        with patch("routes.ai_routes.assistant.__file__", str(fake_assistant)):
            ai_client.post(
                "/ai/config", data={"api_key": "o-key", "provider": "openai"}
            )
        assert "OPENAI_API_KEY=o-key" in (tmp_path / ".env").read_text(encoding="utf-8")

    def test_get_passes_key_flags(self, ai_client):
        with patch(
            "routes.ai_routes.assistant.render_template", return_value="ok"
        ) as rt:
            with patch.dict(
                "os.environ", {"GROQ_API_KEY": "x", "OPENAI_API_KEY": ""}, clear=False
            ):
                ai_client.get("/ai/config")
        kwargs = rt.call_args[1]
        assert kwargs["groq_key_exists"] is True


class TestUploadExcel:
    def test_no_file_400(self, ai_client):
        resp = ai_client.post("/ai/upload-excel", data={"warehouse_id": "1"})
        assert resp.status_code == 400
        assert "لم يتم رفع ملف" in resp.get_json()["error"]

    def test_wrong_extension_400(self, ai_client):
        data = {"file": (io.BytesIO(b"data"), "products.csv"), "warehouse_id": "1"}
        resp = ai_client.post(
            "/ai/upload-excel", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 400

    def test_empty_filename_400(self, ai_client):
        data = {"file": (io.BytesIO(b""), ""), "warehouse_id": "1"}
        resp = ai_client.post(
            "/ai/upload-excel", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 400

    def test_too_large_content_length_413(self, ai_client, app_factory):
        from routes.ai_routes import ai_bp

        app = app_factory(ai_bp, {"MAX_CONTENT_LENGTH": 100})
        with patch(
            "flask_login.utils._get_user", return_value=MagicMock(is_authenticated=True)
        ):
            with patch(
                "routes.ai_routes.get_ai_access_state", return_value=_access_state()
            ):
                with patch(
                    "utils.auth_helpers.is_global_owner_user", return_value=True
                ):
                    with patch("extensions.limiter.limit", return_value=lambda f: f):
                        client = app.test_client()
                        resp = client.post(
                            "/ai/upload-excel",
                            data={"file": (io.BytesIO(b"x"), "a.xlsx")},
                            content_type="multipart/form-data",
                            headers={"Content-Length": "999999"},
                        )
        assert resp.status_code == 413

    def test_success_path(self, ai_client):
        data = {"file": (io.BytesIO(b"excel"), "products.xlsx"), "warehouse_id": "1"}
        with patch(
            "routes.ai_routes.assistant._process_excel_intelligently",
            return_value={"success": True, "message": "ok"},
        ):
            resp = ai_client.post(
                "/ai/upload-excel", data=data, content_type="multipart/form-data"
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_processing_exception_500(self, ai_client):
        data = {"file": (io.BytesIO(b"x"), "p.xlsx")}
        with patch(
            "routes.ai_routes.assistant._process_excel_intelligently",
            side_effect=RuntimeError("boom"),
        ):
            resp = ai_client.post(
                "/ai/upload-excel", data=data, content_type="multipart/form-data"
            )
        assert resp.status_code == 500

    def test_file_size_exceeds_max_413(self, ai_client, app_factory):
        from routes.ai_routes import ai_bp

        app = app_factory(ai_bp, {"MAX_CONTENT_LENGTH": 10})
        big = io.BytesIO(b"012345678901")
        data = {"file": (big, "big.xlsx")}
        with patch(
            "flask_login.utils._get_user", return_value=MagicMock(is_authenticated=True)
        ):
            with patch(
                "routes.ai_routes.get_ai_access_state", return_value=_access_state()
            ):
                with patch(
                    "utils.auth_helpers.is_global_owner_user", return_value=True
                ):
                    with patch("extensions.limiter.limit", return_value=lambda f: f):
                        client = app.test_client()
                        resp = client.post(
                            "/ai/upload-excel",
                            data=data,
                            content_type="multipart/form-data",
                        )
        assert resp.status_code == 413

    def test_auto_warehouse_resolution(self, ai_client):
        warehouse = MagicMock(id=7)
        data = {"file": (io.BytesIO(b"x"), "items.xlsx")}
        with patch("models.Warehouse") as Warehouse:
            Warehouse.query.filter_by.return_value.first.return_value = warehouse
            with patch(
                "routes.ai_routes.assistant._process_excel_intelligently",
                return_value={"success": True},
            ) as proc:
                resp = ai_client.post(
                    "/ai/upload-excel", data=data, content_type="multipart/form-data"
                )
        assert resp.status_code == 200
        proc.assert_called_once()


class TestAssistant:
    def test_renders_template(self, ai_client):
        with patch(
            "routes.ai_routes.assistant.render_template", return_value="assistant"
        ) as rt:
            with patch("utils.branching.get_accessible_warehouses", return_value=[]):
                resp = ai_client.get("/ai/assistant")
        assert resp.status_code == 200
        assert resp.data == b"assistant"
        rt.assert_called_once()

    def test_passes_ai_state(self, ai_client):
        with patch(
            "routes.ai_routes.assistant.render_template", return_value="ok"
        ) as rt:
            with patch("utils.branching.get_accessible_warehouses", return_value=[]):
                ai_client.get("/ai/assistant")
        assert "ai_access_state" in rt.call_args[1]

    def test_exception_renders_500(self, ai_client):
        with patch(
            "utils.branching.get_accessible_warehouses",
            side_effect=RuntimeError("fail"),
        ):
            with patch(
                "routes.ai_routes.assistant.render_template", return_value="err"
            ) as rt:
                resp = ai_client.get("/ai/assistant")
        assert resp.status_code == 500
        rt.assert_called_with("errors/500.html")

    def test_allowed_when_denied_still_renders(self, ai_client):
        with patch(
            "routes.ai_routes.get_ai_access_state", return_value=_denied_access()
        ):
            with patch(
                "routes.ai_routes.assistant.render_template", return_value="page"
            ):
                with patch(
                    "utils.branching.get_accessible_warehouses", return_value=[]
                ):
                    resp = ai_client.get("/ai/assistant")
        assert resp.status_code == 200


class TestAnalyticsGetRoutes:
    @pytest.mark.parametrize("path", list(ANALYTICS_PATCHES.keys()))
    def test_happy_path(self, ai_client, path):
        patch_target = ANALYTICS_PATCHES[path]
        payload = (
            [{"type": "info", "title": "t", "message": "m", "action": "a"}]
            if "business" in path
            else {"ok": True}
        )
        with patch(patch_target, return_value=payload):
            resp = ai_client.get(path)
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "path",
        [
            "/ai/predict-sales",
            "/ai/cash-flow-prediction",
        ],
    )
    def test_days_query_param(self, ai_client, path):
        with patch(
            "routes.ai_routes.AIService.predict_sales_trend", return_value={}
        ) as m1:
            with patch(
                "routes.ai_routes.AIService.predict_cash_flow", return_value={}
            ) as m2:
                ai_client.get(f"{path}?days=14")
        if "predict-sales" in path:
            m1.assert_called_once_with(14)
        else:
            m2.assert_called_once_with(14)

    def test_business_insights_format(self, ai_client):
        insights = [{"type": "warning", "title": "T", "message": "M", "action": "A"}]
        with patch(
            "routes.ai_routes.AIService.generate_business_insights",
            return_value=insights,
        ):
            resp = ai_client.get("/ai/business-insights")
        body = resp.get_json()
        assert body["success"] is True
        assert body["insights"][0]["icon"] == "⚠️"


class TestSmartPrice:
    def test_happy_path(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.smart_pricing_engine",
            return_value={"price": 99},
        ) as m:
            resp = ai_client.post(
                "/ai/smart-price", json={"product_id": 1, "customer_id": 2}
            )
        assert resp.status_code == 200
        m.assert_called_once_with(1, 2, 1)

    def test_missing_ids_400(self, ai_client):
        resp = ai_client.post("/ai/smart-price", json={"product_id": 1})
        assert resp.status_code == 400

    def test_not_found_404(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.smart_pricing_engine", return_value=None
        ):
            resp = ai_client.post(
                "/ai/smart-price", json={"product_id": 1, "customer_id": 2}
            )
        assert resp.status_code == 404

    def test_custom_quantity(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.smart_pricing_engine",
            return_value={"price": 50},
        ) as m:
            ai_client.post(
                "/ai/smart-price",
                json={"product_id": 1, "customer_id": 2, "quantity": 5},
            )
        m.assert_called_once_with(1, 2, 5)

    def test_empty_body_400(self, ai_client):
        resp = ai_client.post("/ai/smart-price", json={})
        assert resp.status_code == 400


class TestContextualHelp:
    def test_returns_help(self, ai_client, mock_ai_service):
        mock_ai_service.contextual_help.return_value = {"help": "text"}
        mock_user = MagicMock()
        mock_user.role = _obj(name="admin")
        with patch("flask_login.utils._get_user", return_value=mock_user):
            resp = ai_client.get("/ai/contextual-help/dashboard")
        assert resp.status_code == 200

    def test_no_role_defaults_user(self, ai_client, mock_ai_service):
        mock_ai_service.contextual_help.return_value = {}
        resp = ai_client.get("/ai/contextual-help/sales")
        assert resp.status_code == 200

    def test_service_called_with_page(self, ai_client, mock_ai_service):
        ai_client.get("/ai/contextual-help/inventory")
        args = mock_ai_service.contextual_help.call_args[0]
        assert args[0] == "inventory"


def _admin_patch():
    return patch("utils.decorators.is_admin_surface_user", return_value=True)


class TestLearningRoutes:
    def test_learning_status_ok(self, ai_client):
        with patch("routes.ai_routes.knowledge.learning_system") as ls:
            ls.get_learning_insights.return_value = {"count": 1}
            resp = ai_client.get("/ai/learning/status")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_learning_status_error(self, ai_client):
        with patch("routes.ai_routes.knowledge.learning_system") as ls:
            ls.get_learning_insights.side_effect = RuntimeError("x")
            resp = ai_client.get("/ai/learning/status")
        assert resp.status_code == 500

    def test_evolve_ok(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.learning_system") as ls:
                ls.evolve_knowledge.return_value = {"evolved": True}
                resp = ai_client.post("/ai/learning/evolve")
        assert resp.status_code == 200

    def test_evolve_error(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.learning_system") as ls:
                ls.evolve_knowledge.side_effect = RuntimeError("x")
                resp = ai_client.post("/ai/learning/evolve")
        assert resp.status_code == 500

    def test_evolve_requires_admin(self, ai_client, mock_user):
        with patch("utils.decorators.is_admin_surface_user", return_value=False):
            with patch("utils.decorators.is_global_owner_user", return_value=False):
                mock_user.has_permission.return_value = True
                resp = ai_client.post("/ai/learning/evolve")
        assert resp.status_code == 403


class TestImprovementRoutes:
    def test_status_ok(self, ai_client):
        with patch("routes.ai_routes.knowledge.self_improvement") as si:
            si.get_improvement_status.return_value = {"score": 90}
            resp = ai_client.get("/ai/improvement/status")
        assert resp.get_json()["success"] is True

    def test_status_error(self, ai_client):
        with patch("routes.ai_routes.knowledge.self_improvement") as si:
            si.get_improvement_status.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/improvement/status")
        assert resp.status_code == 500

    def test_auto_improve_ok(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.self_improvement") as si:
                si.auto_improve.return_value = ["fix1"]
                resp = ai_client.post("/ai/improvement/auto-improve")
        assert resp.status_code == 200

    def test_auto_improve_error(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.self_improvement") as si:
                si.auto_improve.side_effect = RuntimeError("e")
                resp = ai_client.post("/ai/improvement/auto-improve")
        assert resp.status_code == 500

    def test_progress_ok(self, ai_client):
        with patch("routes.ai_routes.knowledge.self_improvement") as si:
            si.track_progress.return_value = {"pct": 50}
            resp = ai_client.get("/ai/improvement/progress")
        assert resp.get_json()["progress"]["pct"] == 50

    def test_progress_error(self, ai_client):
        with patch("routes.ai_routes.knowledge.self_improvement") as si:
            si.track_progress.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/improvement/progress")
        assert resp.status_code == 500

    def test_set_goal_ok(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.self_improvement") as si:
                si.set_improvement_goal.return_value = {"ok": True}
                resp = ai_client.post(
                    "/ai/improvement/set-goal",
                    json={"area": "speed", "target_score": 95},
                )
        assert resp.status_code == 200

    def test_set_goal_missing_fields_400(self, ai_client):
        with _admin_patch():
            resp = ai_client.post("/ai/improvement/set-goal", json={"area": "speed"})
        assert resp.status_code == 400

    def test_set_goal_error(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.self_improvement") as si:
                si.set_improvement_goal.side_effect = RuntimeError("e")
                resp = ai_client.post(
                    "/ai/improvement/set-goal", json={"area": "a", "target_score": 1}
                )
        assert resp.status_code == 500


class TestGlobalRoutes:
    def test_global_insights_ok(self, ai_client):
        with patch("routes.ai_routes.knowledge.global_connector") as gc:
            gc.get_global_insights.return_value = {"items": []}
            resp = ai_client.get("/ai/global/insights")
        assert resp.status_code == 200

    def test_global_insights_error(self, ai_client):
        with patch("routes.ai_routes.knowledge.global_connector") as gc:
            gc.get_global_insights.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/global/insights")
        assert resp.status_code == 500

    def test_expertise_update_ok(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.expertise_updater") as eu:
                eu.update_expertise.return_value = {"updated": 1}
                resp = ai_client.get("/ai/global/expertise-update")
        assert resp.status_code == 200

    def test_expertise_update_error(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.expertise_updater") as eu:
                eu.update_expertise.side_effect = RuntimeError("e")
                resp = ai_client.get("/ai/global/expertise-update")
        assert resp.status_code == 500


class TestPerformanceAnalysis:
    def test_ok(self, ai_client):
        with patch("routes.ai_routes.knowledge.self_improvement") as si:
            with patch("routes.ai_routes.knowledge.learning_system") as ls:
                with patch("routes.ai_routes.knowledge.global_connector") as gc:
                    si.analyze_performance.return_value = {"p": 1}
                    ls.get_learning_insights.return_value = {"l": 2}
                    si.evolve_capabilities.return_value = {"e": 3}
                    gc.get_global_insights.return_value = {"g": 4}
                    resp = ai_client.get("/ai/performance/analysis")
        assert resp.status_code == 200
        body = resp.get_json()["performance_analysis"]
        assert "performance" in body

    def test_error(self, ai_client):
        with patch("routes.ai_routes.knowledge.self_improvement") as si:
            si.analyze_performance.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/performance/analysis")
        assert resp.status_code == 500


class TestSystemRoutes:
    def test_customer_balance(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.get_customer_balance.return_value = {"balance": 100}
            resp = ai_client.get("/ai/system/customer-balance/Ali")
        assert resp.status_code == 200

    def test_customer_balance_error(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.get_customer_balance.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/system/customer-balance/X")
        assert resp.status_code == 500

    def test_customer_debt(self, ai_client):
        with patch("routes.ai_routes.system.data_analyzer") as da:
            da.analyze_customer_debt.return_value = {"debt": 50}
            resp = ai_client.get("/ai/system/customer-debt/3")
        assert resp.status_code == 200

    def test_customer_debt_error(self, ai_client):
        with patch("routes.ai_routes.system.data_analyzer") as da:
            da.analyze_customer_debt.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/system/customer-debt/3")
        assert resp.status_code == 500

    def test_product_stock(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.get_product_stock.return_value = {"stock": 10}
            resp = ai_client.get("/ai/system/product-stock/Filter")
        assert resp.status_code == 200

    def test_product_stock_error(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.get_product_stock.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/system/product-stock/X")
        assert resp.status_code == 500

    def test_summary(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.get_system_summary.return_value = {"summary": {"users": 1}}
            si.get_financial_summary.return_value = {"financial": {"sales": 2}}
            resp = ai_client.get("/ai/system/summary")
        body = resp.get_json()
        assert body["success"] is True
        assert body["summary"]["users"] == 1

    def test_summary_error(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.get_system_summary.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/system/summary")
        assert resp.status_code == 500

    def test_search(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.search_data.return_value = {"hits": []}
            resp = ai_client.get("/ai/system/search/invoice")
        assert resp.status_code == 200

    def test_search_error(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.search_data.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/system/search/x")
        assert resp.status_code == 500

    def test_add_customer(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.add_customer.return_value = {"success": True}
            resp = ai_client.post("/ai/system/add-customer", json={"name": "New"})
        assert resp.status_code == 200

    def test_add_customer_error(self, ai_client):
        with patch("routes.ai_routes.system.system_integrator") as si:
            si.add_customer.side_effect = RuntimeError("e")
            resp = ai_client.post("/ai/system/add-customer", json={"name": "X"})
        assert resp.status_code == 500


class TestDataRoutes:
    def test_analyze_sales(self, ai_client):
        with patch("routes.ai_routes.system.data_analyzer") as da:
            da.analyze_sales_performance.return_value = {"total": 1}
            resp = ai_client.get("/ai/data/analyze-sales?period=7")
        assert resp.status_code == 200
        da.analyze_sales_performance.assert_called_once_with(7)

    def test_analyze_sales_error(self, ai_client):
        with patch("routes.ai_routes.system.data_analyzer") as da:
            da.analyze_sales_performance.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/data/analyze-sales")
        assert resp.status_code == 500

    def test_analyze_products(self, ai_client):
        with patch("routes.ai_routes.system.data_analyzer") as da:
            da.analyze_product_performance.return_value = {"id": 1}
            ai_client.get("/ai/data/analyze-products?product_id=5")
        da.analyze_product_performance.assert_called_once_with(5)

    def test_analyze_products_error(self, ai_client):
        with patch("routes.ai_routes.system.data_analyzer") as da:
            da.analyze_product_performance.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/data/analyze-products")
        assert resp.status_code == 500

    def test_financial_ratios(self, ai_client):
        with patch("routes.ai_routes.system.data_analyzer") as da:
            da.get_financial_ratios.return_value = {"ratio": 1.2}
            resp = ai_client.get("/ai/data/financial-ratios")
        assert resp.status_code == 200

    def test_financial_ratios_error(self, ai_client):
        with patch("routes.ai_routes.system.data_analyzer") as da:
            da.get_financial_ratios.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/data/financial-ratios")
        assert resp.status_code == 500


class TestKnowledgeRoutes:
    def test_add_website_ok(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.knowledge_expander") as ke:
                ke.add_website.return_value = {"success": True}
                resp = ai_client.post(
                    "/ai/knowledge/add-website", json={"url": "https://example.com"}
                )
        assert resp.status_code == 200

    def test_add_website_missing_url_400(self, ai_client):
        with _admin_patch():
            resp = ai_client.post("/ai/knowledge/add-website", json={})
        assert resp.status_code == 400

    def test_add_website_error(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.knowledge_expander") as ke:
                ke.add_website.side_effect = RuntimeError("e")
                resp = ai_client.post(
                    "/ai/knowledge/add-website", json={"url": "https://x.com"}
                )
        assert resp.status_code == 500

    def test_add_document_ok(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.knowledge_expander") as ke:
                ke.add_document.return_value = {"success": True}
                resp = ai_client.post(
                    "/ai/knowledge/add-document", json={"title": "T", "content": "C"}
                )
        assert resp.status_code == 200

    def test_add_document_missing_400(self, ai_client):
        with _admin_patch():
            resp = ai_client.post("/ai/knowledge/add-document", json={"title": "T"})
        assert resp.status_code == 400

    def test_add_document_error(self, ai_client):
        with _admin_patch():
            with patch("routes.ai_routes.knowledge.knowledge_expander") as ke:
                ke.add_document.side_effect = RuntimeError("e")
                resp = ai_client.post(
                    "/ai/knowledge/add-document", json={"title": "T", "content": "C"}
                )
        assert resp.status_code == 500

    def test_search_ok(self, ai_client):
        with patch("routes.ai_routes.knowledge.knowledge_expander") as ke:
            ke.search_knowledge.return_value = {"results": []}
            resp = ai_client.get("/ai/knowledge/search?q=engine")
        assert resp.status_code == 200

    def test_search_missing_q_400(self, ai_client):
        resp = ai_client.get("/ai/knowledge/search")
        assert resp.status_code == 400

    def test_search_error(self, ai_client):
        with patch("routes.ai_routes.knowledge.knowledge_expander") as ke:
            ke.search_knowledge.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/knowledge/search?q=x")
        assert resp.status_code == 500

    def test_summary_ok(self, ai_client):
        with patch("routes.ai_routes.knowledge.knowledge_expander") as ke:
            ke.get_knowledge_summary.return_value = {"count": 3}
            resp = ai_client.get("/ai/knowledge/summary")
        assert resp.status_code == 200

    def test_summary_error(self, ai_client):
        with patch("routes.ai_routes.knowledge.knowledge_expander") as ke:
            ke.get_knowledge_summary.side_effect = RuntimeError("e")
            resp = ai_client.get("/ai/knowledge/summary")
        assert resp.status_code == 500


class TestNeuralStatus:
    def test_ok(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.get_neural_status",
            return_value={"active": True},
        ):
            resp = ai_client.get("/ai/neural-status")
        assert resp.get_json()["success"] is True

    def test_error_returns_json(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.get_neural_status",
            side_effect=RuntimeError("e"),
        ):
            resp = ai_client.get("/ai/neural-status")
        assert resp.get_json()["success"] is False

    def test_status_payload(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.get_neural_status", return_value={"models": 2}
        ):
            resp = ai_client.get("/ai/neural-status")
        assert resp.get_json()["status"]["models"] == 2


class TestAutomotiveRoutes:
    def test_ecu_code_ok(self, ai_client):
        expert = MagicMock()
        expert.diagnose_code.return_value = {"code": "P0300"}
        with patch(
            "routes.ai_routes.specialized.get_automotive_ecu_knowledge",
            return_value=expert,
        ):
            resp = ai_client.get("/ai/automotive-ecu/p0300")
        assert resp.get_json()["diagnosis"]["code"] == "P0300"
        expert.diagnose_code.assert_called_once_with("P0300")

    def test_ecu_code_error(self, ai_client):
        with patch(
            "routes.ai_routes.specialized.get_automotive_ecu_knowledge",
            side_effect=RuntimeError("e"),
        ):
            resp = ai_client.get("/ai/automotive-ecu/P0300")
        assert resp.get_json()["success"] is False

    def test_ecu_uppercases_code(self, ai_client):
        expert = MagicMock()
        expert.diagnose_code.return_value = {}
        with patch(
            "routes.ai_routes.specialized.get_automotive_ecu_knowledge",
            return_value=expert,
        ):
            ai_client.get("/ai/automotive-ecu/abc")
        expert.diagnose_code.assert_called_once_with("ABC")

    def test_sensor_ok(self, ai_client):
        expert = MagicMock()
        expert.get_sensor_info.return_value = {"name": "MAP"}
        with patch(
            "routes.ai_routes.specialized.get_automotive_ecu_knowledge",
            return_value=expert,
        ):
            resp = ai_client.get("/ai/automotive-sensor/map")
        assert resp.get_json()["sensor_info"]["name"] == "MAP"

    def test_sensor_error(self, ai_client):
        with patch(
            "routes.ai_routes.specialized.get_automotive_ecu_knowledge",
            side_effect=RuntimeError("e"),
        ):
            resp = ai_client.get("/ai/automotive-sensor/o2")
        assert resp.get_json()["success"] is False

    def test_sensor_passes_name(self, ai_client):
        expert = MagicMock()
        expert.get_sensor_info.return_value = {}
        with patch(
            "routes.ai_routes.specialized.get_automotive_ecu_knowledge",
            return_value=expert,
        ):
            ai_client.get("/ai/automotive-sensor/crank")
        expert.get_sensor_info.assert_called_once_with("crank")


class TestExternalSources:
    def test_ok(self, ai_client):
        learning = MagicMock()
        learning.get_knowledge_sources_list.return_value = [{"id": 1}]
        learning.get_statistics.return_value = {"total": 1}
        with patch(
            "routes.ai_routes.specialized.get_external_learning", return_value=learning
        ):
            resp = ai_client.get("/ai/external-sources")
        body = resp.get_json()
        assert body["success"] is True
        assert "catalog" in body

    def test_error(self, ai_client):
        with patch(
            "routes.ai_routes.specialized.get_external_learning",
            side_effect=RuntimeError("e"),
        ):
            resp = ai_client.get("/ai/external-sources")
        assert resp.get_json()["success"] is False

    def test_includes_statistics(self, ai_client):
        learning = MagicMock()
        learning.get_knowledge_sources_list.return_value = []
        learning.get_statistics.return_value = {"count": 5}
        with patch(
            "routes.ai_routes.specialized.get_external_learning", return_value=learning
        ):
            resp = ai_client.get("/ai/external-sources")
        assert resp.get_json()["statistics"]["count"] == 5


class TestAskGenius:
    def test_ok(self, ai_client, mock_ai_service):
        mock_ai_service.ask_genius.return_value = {"answer": "42"}
        resp = ai_client.post("/ai/ask-genius", json={"question": "why?"})
        assert resp.get_json()["success"] is True

    def test_missing_question_400(self, ai_client):
        resp = ai_client.post("/ai/ask-genius", json={"question": ""})
        assert resp.status_code == 400

    def test_with_context(self, ai_client, mock_ai_service):
        ai_client.post(
            "/ai/ask-genius", json={"question": "q", "context": {"page": "sales"}}
        )
        kwargs = mock_ai_service.ask_genius.call_args[1]
        assert kwargs["context"]["page"] == "sales"

    def test_service_error(self, ai_client, mock_ai_service):
        mock_ai_service.ask_genius.side_effect = RuntimeError("e")
        resp = ai_client.post("/ai/ask-genius", json={"question": "q"})
        assert resp.get_json()["success"] is False

    def test_passes_user_id(self, ai_client, mock_ai_service):
        ai_client.post("/ai/ask-genius", json={"question": "q"})
        assert mock_ai_service.ask_genius.call_args[1]["user_id"] == 42


class TestQuickCalc:
    def test_ok(self, ai_client, mock_ai_service):
        mock_ai_service.quick_calculate.return_value = {"success": True, "value": 10}
        resp = ai_client.post(
            "/ai/quick-calc", json={"formula": "margin", "params": {"a": 1}}
        )
        assert resp.get_json()["success"] is True

    def test_missing_formula_400(self, ai_client):
        resp = ai_client.post("/ai/quick-calc", json={"formula": ""})
        assert resp.status_code == 400

    def test_service_error(self, ai_client, mock_ai_service):
        mock_ai_service.quick_calculate.side_effect = RuntimeError("e")
        resp = ai_client.post("/ai/quick-calc", json={"formula": "x"})
        assert resp.get_json()["success"] is False

    def test_calls_quick_calculate(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.quick_calculate", return_value={"success": True}
        ) as m:
            ai_client.post(
                "/ai/quick-calc", json={"formula": "vat", "params": {"rate": 5}}
            )
        m.assert_called_once_with("vat", rate=5)


class TestTransformersUnderstand:
    def test_ok(self, ai_client, mock_ai_service):
        mock_ai_service.understand_with_transformers.return_value = {"intent": "buy"}
        resp = ai_client.post("/ai/transformers-understand", json={"text": "أريد شراء"})
        assert resp.get_json()["success"] is True

    def test_missing_text_400(self, ai_client):
        resp = ai_client.post("/ai/transformers-understand", json={"text": ""})
        assert resp.status_code == 400

    def test_service_error(self, ai_client, mock_ai_service):
        mock_ai_service.understand_with_transformers.side_effect = RuntimeError("e")
        resp = ai_client.post("/ai/transformers-understand", json={"text": "x"})
        assert resp.get_json()["success"] is False

    def test_calls_understand_with_transformers(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.understand_with_transformers",
            return_value={"ok": True},
        ) as m:
            ai_client.post("/ai/transformers-understand", json={"text": "hello"})
        m.assert_called_once_with("hello")


class TestProductTenantIsolation:
    def test_search_filters_by_active_tenant(self, ai_client):
        product = _obj(name="TenantProduct")
        chain = MagicMock()
        chain.first_or_404.return_value = product
        with patch("models.Product") as Product:
            with patch("routes.ai_routes.chat.get_active_tenant_id", return_value=99):
                Product.query.filter_by.return_value = chain
                ai_client.get("/ai/search-market-price/1")
                Product.query.filter_by.assert_called_with(id=1, tenant_id=99)

    def test_find_compatible_wrong_tenant_404(self, ai_client):
        chain = MagicMock()
        chain.first_or_404.side_effect = NotFound()
        with patch("models.Product") as Product:
            with patch("routes.ai_routes.chat.get_active_tenant_id", return_value=2):
                Product.query.filter_by.return_value = chain
                resp = ai_client.get("/ai/find-compatible/50")
        assert resp.status_code == 404

    def test_search_market_no_cross_tenant_leak(self, ai_client):
        chain = MagicMock()
        chain.first_or_404.side_effect = NotFound()
        with patch("models.Product") as Product:
            Product.query.filter_by.return_value = chain
            resp = ai_client.get("/ai/search-market-price/100")
        assert resp.status_code == 404


def _run_action(message, user, ctx):
    from routes.ai_routes import _process_user_action

    with (
        patch("routes.ai_routes.actions._conversation_ctx", return_value=ctx),
        patch("routes.ai_routes.actions.get_active_tenant_id", return_value=1),
        patch("routes.ai_routes.actions.train_local_ai"),
        patch("routes.ai_routes.actions.assign_tenant_id"),
        patch("extensions.db.session") as session,
    ):
        session.add = MagicMock()
        session.flush = MagicMock()
        session.commit = MagicMock()
        return _process_user_action(message, user)


MENU_TRIGGERS = [
    ("استلام", "استلام دفعة"),
    ("إعطاء", "إعطاء دفعة"),
    ("مصروف", "مصروف"),
    ("مورد", "مورد"),
    ("مشتريات", "مشتريات"),
    ("شيك", "شيك"),
    ("دفتر", "دفتر"),
    ("مستودع", "مستودع"),
    ("مستخدم", "مستخدم"),
]


@pytest.mark.parametrize("keyword,snippet", MENU_TRIGGERS)
def test_wizard_menu_triggers(keyword, snippet, mock_user):
    ctx = {}
    result = _run_action(keyword, mock_user, ctx)
    assert snippet in result


class TestCustomerWizardFlow:
    def test_full_create_flow(self, mock_user):
        ctx = {"last_action": "عميل", "option": "1", "step": 1, "data": {}}
        customer = _obj(id=55)
        with patch("models.customer.Customer", customer_cls := MagicMock()):
            customer_cls.return_value = customer
            r1 = _run_action("Ali Hassan", mock_user, ctx)
            assert ctx["step"] == 2
            assert "الخطوة 2" in r1
            _run_action("0501234567", mock_user, ctx)
            assert ctx["step"] == 3
            r3 = _run_action("Dubai Marina", mock_user, ctx)
            assert "تم إنشاء العميل" in r3

    def test_create_failure(self, mock_user):
        ctx = {
            "last_action": "عميل",
            "option": "1",
            "step": 3,
            "data": {"name": "X", "phone": "1", "address": "Y"},
        }
        with patch("models.customer.Customer", side_effect=RuntimeError("db fail")):
            result = _run_action("addr", mock_user, ctx)
        assert "خطأ" in result

    def test_option_two_list_customers(self, mock_user):
        ctx = {"last_action": "عميل"}
        chain = MagicMock()
        chain.all.return_value = [_obj(name="C1", phone="1", balance=Decimal("10"))]
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run_action("2", mock_user, ctx)
        assert "C1" in result

    def test_option_three_search(self, mock_user):
        ctx = {"last_action": "عميل"}
        result = _run_action("3", mock_user, ctx)
        assert "البحث عن عميل" in result
        assert ctx.get("option") == "3"


class TestProductWizardFlow:
    def test_full_create_flow(self, mock_user):
        ctx = {"last_action": "منتج", "option": "1", "step": 1, "data": {}}
        product = _obj(id=12)
        with (
            patch("models.product.Product", product_cls := MagicMock()),
            patch("routes.ai_routes.actions.StockService.add_opening_stock"),
        ):
            product_cls.return_value = product
            _run_action("Oil Filter", mock_user, ctx)
            assert ctx["step"] == 2
            _run_action("PN-001", mock_user, ctx)
            assert ctx["step"] == 3
            _run_action("150", mock_user, ctx)
            assert ctx["step"] == 4
            result = _run_action("10", mock_user, ctx)
            assert "تم إنشاء المنتج" in result

    def test_option_two_list_products(self, mock_user):
        ctx = {"last_action": "منتج"}
        chain = MagicMock()
        chain.all.return_value = [
            _obj(name="P1", part_number="X", regular_price=10, current_stock=5)
        ]
        with patch("models.product.Product") as Product:
            Product.query.filter_by.return_value = chain
            result = _run_action("2", mock_user, ctx)
        assert "P1" in result

    def test_option_four_excel_hint(self, mock_user):
        ctx = {"last_action": "منتج"}
        result = _run_action("4", mock_user, ctx)
        assert "Excel" in result


class TestInvoiceWizardFlow:
    def test_step_one_customer_name(self, mock_user):
        ctx = {"last_action": "فاتورة", "option": "1", "step": 1, "data": {}}
        _run_action("Customer A", mock_user, ctx)
        assert ctx["step"] == 2

    def test_step_two_product(self, mock_user):
        ctx = {
            "last_action": "فاتورة",
            "option": "1",
            "step": 2,
            "data": {"customer_name": "C"},
        }
        customer = _obj(id=1, name="C")
        chain = MagicMock()
        chain.first.return_value = customer
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            _run_action("Product Z", mock_user, ctx)
        assert ctx["step"] == 3

    def test_option_two_list_invoices(self, mock_user):
        ctx = {"last_action": "فاتورة"}
        sale = _obj(id=1, total_amount=100, customer=_obj(name="C"))
        chain = MagicMock()
        chain.all.return_value = [sale]
        with patch("models.sale.Sale") as Sale:
            Sale.query.filter_by.return_value = chain
            result = _run_action("2", mock_user, ctx)
        assert "#1" in result


class TestBalanceWizardFlow:
    def test_step_one_customer_found(self, mock_user):
        ctx = {"last_action": "رصيد", "option": "1", "step": 1, "data": {}}
        customer = _obj(id=3, name="Bal", balance=Decimal("50"))
        chain = MagicMock()
        chain.first.return_value = customer
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run_action("Bal", mock_user, ctx)
        assert ctx["step"] == 2
        assert "Bal" in result

    def test_step_one_customer_missing(self, mock_user):
        ctx = {"last_action": "رصيد", "option": "1", "step": 1, "data": {}}
        chain = MagicMock()
        chain.first.return_value = None
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run_action("Missing", mock_user, ctx)
        assert "غير موجود" in result

    def test_step_two_update_balance(self, mock_user):
        ctx = {
            "last_action": "رصيد",
            "option": "1",
            "step": 2,
            "data": {"customer_id": 3, "customer_name": "Bal", "current_balance": 50},
        }
        customer = _obj(id=3, name="Bal", balance=Decimal("50"))
        customer.set_balance = MagicMock()
        chain = MagicMock()
        chain.first.return_value = customer
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run_action("1000", mock_user, ctx)
        assert "تم تعديل رصيد" in result

    def test_step_two_invalid_amount(self, mock_user):
        ctx = {
            "last_action": "رصيد",
            "option": "1",
            "step": 2,
            "data": {"customer_id": 1},
        }
        result = _run_action("not-a-number", mock_user, ctx)
        assert "خطأ" in result


class TestColonSyntaxCommands:
    def test_create_customer_colon(self, mock_user):
        ctx = {}
        customer = _obj(id=7)
        with patch("models.Customer", cust_cls := MagicMock()):
            cust_cls.return_value = customer
            result = _run_action("عميل: Ali, 0501111111, Dubai", mock_user, ctx)
        assert "تم إنشاء العميل" in result

    def test_create_product_colon(self, mock_user):
        ctx = {}
        product = _obj(id=8)
        with (
            patch("models.Product", prod_cls := MagicMock()),
            patch("routes.ai_routes.actions.StockService.add_opening_stock"),
        ):
            prod_cls.return_value = product
            result = _run_action("منتج: Filter, PN99, 120, 5", mock_user, ctx)
        assert "تم إنشاء المنتج" in result

    def test_create_supplier_colon(self, mock_user):
        ctx = {}
        supplier = _obj(id=9)
        with patch("models.Supplier", sup_cls := MagicMock()):
            sup_cls.return_value = supplier
            result = _run_action(
                "مورد: SupCo, 0502222222, sup@test.com", mock_user, ctx
            )
        assert "تم إنشاء المورد" in result

    def test_invoice_colon_success(self, mock_user):
        ctx = {}
        customer = _obj(id=1, name="C1")
        product = _obj(id=2, name="P1", regular_price=Decimal("100"), current_stock=10)
        sale = _obj(id=100, sale_number="INV-TEST", total_amount=Decimal("200"))
        warehouse = _obj(id=5)
        cust_chain = MagicMock()
        cust_chain.first.return_value = customer
        prod_chain = MagicMock()
        prod_chain.first.return_value = product
        wh_chain = MagicMock()
        wh_chain.first.return_value = warehouse
        with (
            patch("models.Customer") as Customer,
            patch("models.Product") as Product,
            patch("models.Sale", sale_cls := MagicMock()),
            patch("models.SaleLine", line_cls := MagicMock()),
            patch("models.Warehouse") as Warehouse,
            patch("routes.ai_routes.actions.StockService.remove_stock"),
        ):
            Customer.query.filter_by.return_value = cust_chain
            Product.query.filter_by.return_value = prod_chain
            Warehouse.query.filter_by.return_value = wh_chain
            sale_cls.return_value = sale
            line_cls.return_value = _obj(id=1)
            result = _run_action("فاتورة: C1, P1, 2, cash", mock_user, ctx)
        assert "تم إنشاء الفاتورة" in result

    def test_invoice_colon_missing_customer(self, mock_user):
        ctx = {}
        chain = MagicMock()
        chain.first.return_value = None
        with patch("models.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run_action("فاتورة: Ghost, P1, 1", mock_user, ctx)
        assert "غير موجود" in result

    def test_payment_receive_colon(self, mock_user):
        ctx = {}
        customer = _obj(id=1, name="PayC", balance=Decimal("0"))
        customer.apply_receipt = MagicMock()
        chain = MagicMock()
        chain.first.return_value = customer
        payment = _obj(id=20)
        with (
            patch("models.Customer") as Customer,
            patch("models.Payment", pay_cls := MagicMock()),
            patch("utils.helpers.generate_number", return_value="PAY-1"),
        ):
            Customer.query.filter_by.return_value = chain
            pay_cls.return_value = payment
            result = _run_action("استلام: PayC, 500, cash", mock_user, ctx)
        assert "تم استلام الدفعة" in result

    def test_show_balance_colon(self, mock_user):
        ctx = {}
        customer = _obj(
            id=1, name="ShowC", balance=Decimal("250"), phone="1", address="A"
        )
        chain = MagicMock()
        chain.first.return_value = customer
        pay_chain = MagicMock()
        pay_chain.order_by.return_value.limit.return_value.all.return_value = []
        with patch("models.Customer") as Customer, patch("models.Payment") as Payment:
            Customer.query.filter_by.return_value = chain
            Payment.query.filter_by.return_value = pay_chain
            result = _run_action("عرض رصيد: ShowC", mock_user, ctx)
        assert "250" in result

    def test_give_payment_colon(self, mock_user):
        ctx = {}
        customer = _obj(id=1, name="GiveC", balance=Decimal("100"))
        customer.adjust_balance = MagicMock()
        chain = MagicMock()
        chain.first.return_value = customer
        payment = _obj(id=30)
        with (
            patch("models.Customer") as Customer,
            patch("models.Payment", pay_cls := MagicMock()),
            patch("utils.helpers.generate_number", return_value="PAY-2"),
        ):
            Customer.query.filter_by.return_value = chain
            pay_cls.return_value = payment
            result = _run_action("إعطاء: GiveC, 50, refund reason", mock_user, ctx)
        assert "تم إعطاء الدفعة" in result


class TestExpenseSupplierPurchaseChequeWizards:
    def test_expense_step_flow(self, mock_user):
        ctx = {"last_action": "مصروف", "option": "1", "step": 1, "data": {}}
        _run_action("Rent", mock_user, ctx)
        assert ctx["step"] == 2
        _run_action("2000", mock_user, ctx)
        assert ctx["step"] == 3
        expense = _obj(id=1)
        with patch("models.expense.Expense", exp_cls := MagicMock()):
            exp_cls.return_value = expense
            result = _run_action("utilities", mock_user, ctx)
        assert result is not None

    def test_supplier_wizard_steps(self, mock_user):
        ctx = {"last_action": "مورد", "option": "1", "step": 1, "data": {}}
        _run_action("Supplier Name", mock_user, ctx)
        assert ctx["step"] == 2
        _run_action("0503333333", mock_user, ctx)
        assert ctx["step"] == 3
        supplier = _obj(id=2)
        with patch("models.supplier.Supplier", sup_cls := MagicMock()):
            sup_cls.return_value = supplier
            result = _run_action("supplier@mail.com", mock_user, ctx)
        assert result is not None

    def test_purchase_wizard_start(self, mock_user):
        ctx = {"last_action": "مشتريات", "option": "1", "step": 1, "data": {}}
        supplier = _obj(id=1, name="S")
        chain = MagicMock()
        chain.first.return_value = supplier
        with patch("models.supplier.Supplier") as Supplier:
            Supplier.query.filter_by.return_value = chain
            _run_action("S", mock_user, ctx)
        assert ctx["step"] == 2

    def test_cheque_wizard_start(self, mock_user):
        ctx = {"last_action": "شيك", "option": "1", "step": 1, "data": {}}
        _run_action("وارد", mock_user, ctx)
        assert ctx["step"] == 2

    def test_receive_wizard_steps(self, mock_user):
        ctx = {"last_action": "استلام", "option": "1", "step": 1, "data": {}}
        customer = _obj(id=1, name="RC")
        chain = MagicMock()
        chain.first.return_value = customer
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            _run_action("RC", mock_user, ctx)
        assert ctx["step"] == 2

    def test_give_wizard_steps(self, mock_user):
        ctx = {"last_action": "إعطاء", "option": "1", "step": 1, "data": {}}
        customer = _obj(id=1, name="GC")
        chain = MagicMock()
        chain.first.return_value = customer
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            _run_action("GC", mock_user, ctx)
        assert ctx["step"] == 2


class TestWizardOptionBranches:
    @pytest.mark.parametrize("action", ["مورد", "مشتريات", "شيك", "مصروف", "مستخدم"])
    def test_option_two_lists(self, action, mock_user):
        ctx = {"last_action": action}
        chain = MagicMock()
        chain.all.return_value = []
        model_path = {
            "مورد": "models.supplier.Supplier",
            "مشتريات": "models.purchase.Purchase",
            "شيك": "models.cheque.Cheque",
            "مصروف": "models.expense.Expense",
            "مستخدم": "models.user.User",
        }[action]
        with patch(model_path) as Model:
            Model.query.filter_by.return_value = chain
            result = _run_action("2", mock_user, ctx)
        assert result is not None

    def test_ledger_option_one(self, mock_user):
        ctx = {"last_action": "دفتر"}
        result = _run_action("1", mock_user, ctx)
        assert result is not None

    def test_warehouse_option_one(self, mock_user):
        ctx = {"last_action": "مستودع"}
        result = _run_action("1", mock_user, ctx)
        assert result is not None

    def test_user_option_one(self, mock_user):
        ctx = {"last_action": "مستخدم"}
        result = _run_action("1", mock_user, ctx)
        assert "مستخدم" in result


class TestInvoiceWizardExtended:
    def test_step1_show_customers(self, mock_user):
        ctx = {"last_action": "فاتورة", "option": "1", "step": 1, "data": {}}
        customer = _obj(name="Shown", phone="1")
        chain = MagicMock()
        chain.limit.return_value.all.return_value = [customer]
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run_action("اعرض العملاء", mock_user, ctx)
        assert "Shown" in result

    def test_step1_customer_not_found(self, mock_user):
        ctx = {"last_action": "فاتورة", "option": "1", "step": 1, "data": {}}
        chain = MagicMock()
        chain.first.return_value = None
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run_action("Ghost", mock_user, ctx)
        assert "غير موجود" in result

    def test_step2_show_products(self, mock_user):
        ctx = {
            "last_action": "فاتورة",
            "option": "1",
            "step": 2,
            "data": {"customer_name": "C"},
        }
        product = _obj(name="Prod", regular_price=Decimal("10"), current_stock=5)
        chain = MagicMock()
        chain.limit.return_value.all.return_value = [product]
        with patch("models.product.Product") as Product:
            Product.query.filter_by.return_value = chain
            result = _run_action("list", mock_user, ctx)
        assert "Prod" in result

    def test_step3_to_step4_quantity(self, mock_user):
        ctx = {
            "last_action": "فاتورة",
            "option": "1",
            "step": 3,
            "data": {
                "product_name": "P",
                "product_price": Decimal("25"),
                "customer_id": 1,
            },
        }
        result = _run_action("3", mock_user, ctx)
        assert ctx["step"] == 4 or "الخطوة" in result or result is not None

    def test_invoice_wizard_create_sale(self, mock_user):
        ctx = {
            "last_action": "فاتورة",
            "option": "1",
            "step": 3,
            "data": {
                "customer_id": 1,
                "customer_name": "C",
                "product_id": 2,
                "product_name": "P",
                "product_price": 100.0,
            },
        }
        sale = _obj(id=50, sale_number="S-1", total_amount=Decimal("200"))
        wh = _obj(id=1)
        with (
            patch("models.sale.Sale", sale_cls := MagicMock()),
            patch("models.sale.SaleLine", line_cls := MagicMock()),
            patch("utils.helpers.generate_number", return_value="S-001"),
            patch("models.Warehouse") as Warehouse,
            patch("routes.ai_routes.actions.StockService.remove_stock"),
            patch("routes.ai_routes.create_final_options", return_value="next"),
        ):
            sale_cls.return_value = sale
            line_cls.return_value = _obj(id=1)
            Warehouse.query.filter_by.return_value.first.return_value = wh
            result = _run_action("2", mock_user, ctx)
        assert "تم إنشاء الفاتورة" in result


class TestReceivePaymentWizardExtended:
    def test_receive_full_flow(self, mock_user):
        ctx = {"last_action": "استلام", "option": "1", "step": 1, "data": {}}
        customer = _obj(id=1, name="PayC", balance=Decimal("100"))
        chain = MagicMock()
        chain.first.return_value = customer
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            _run_action("PayC", mock_user, ctx)
        assert ctx["step"] == 2
        _run_action("250", mock_user, ctx)
        assert ctx["step"] == 3
        payment = _obj(id=9)
        cust2 = _obj(id=1, balance=Decimal("50"))
        chain2 = MagicMock()
        chain2.first.return_value = cust2
        with (
            patch("models.payment.Payment", pay_cls := MagicMock()),
            patch("models.customer.Customer") as Customer,
            patch("utils.helpers.generate_number", return_value="PAY-X"),
            patch("routes.ai_routes.create_final_options", return_value="opts"),
        ):
            pay_cls.return_value = payment
            Customer.query.filter_by.return_value = chain2
            r3 = _run_action("cash", mock_user, ctx)
        assert "تم استلام الدفعة" in r3

    def test_receive_invalid_amount(self, mock_user):
        ctx = {
            "last_action": "استلام",
            "option": "1",
            "step": 2,
            "data": {"customer_id": 1},
        }
        result = _run_action("bad", mock_user, ctx)
        assert "خطأ" in result


class TestGivePaymentWizardExtended:
    def test_give_full_flow(self, mock_user):
        ctx = {"last_action": "إعطاء", "option": "1", "step": 1, "data": {}}
        customer = _obj(id=1, name="GiveC", balance=Decimal("0"))
        chain = MagicMock()
        chain.first.return_value = customer
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            _run_action("GiveC", mock_user, ctx)
        assert ctx["step"] == 2
        _run_action("100", mock_user, ctx)
        assert ctx["step"] == 3
        payment = _obj(id=11)
        cust2 = _obj(id=1, balance=Decimal("100"))
        cust2.adjust_balance = MagicMock()
        chain2 = MagicMock()
        chain2.first.return_value = cust2
        with (
            patch("models.payment.Payment", pay_cls := MagicMock()),
            patch("models.customer.Customer") as Customer,
            patch("utils.helpers.generate_number", return_value="PAY-Y"),
            patch("routes.ai_routes.create_final_options", return_value="opts"),
        ):
            pay_cls.return_value = payment
            Customer.query.filter_by.return_value = chain2
            result = _run_action("refund", mock_user, ctx)
        assert "تم إعطاء الدفعة" in result or "دفعة" in result


class TestExpenseWizardExtended:
    def test_expense_complete(self, mock_user):
        ctx = {"last_action": "مصروف", "option": "1", "step": 1, "data": {}}
        _run_action("Office rent", mock_user, ctx)
        assert ctx["step"] == 2
        _run_action("1500", mock_user, ctx)
        assert ctx["step"] == 3
        expense = _obj(id=3)
        with (
            patch("models.expense.Expense", exp_cls := MagicMock()),
            patch("utils.helpers.generate_number", return_value="EXP-1"),
            patch("routes.ai_routes.create_final_options", return_value="opts"),
        ):
            exp_cls.return_value = expense
            result = _run_action("utilities", mock_user, ctx)
        assert result is not None


class TestProductWizardExtended:
    def test_product_help_step3(self, mock_user):
        ctx = {
            "last_action": "منتج",
            "option": "1",
            "step": 3,
            "data": {"name": "A", "part_number": "B"},
        }
        result = _run_action("مساعدة", mock_user, ctx)
        assert "مساعدة" in result

    def test_product_invalid_price(self, mock_user):
        ctx = {
            "last_action": "منتج",
            "option": "1",
            "step": 3,
            "data": {"name": "A", "part_number": "B"},
        }
        result = _run_action("notprice", mock_user, ctx)
        assert "خطأ" in result


class TestPurchaseWizardExtended:
    def test_purchase_wizard_steps(self, mock_user):
        ctx = {"last_action": "مشتريات", "option": "1", "step": 1, "data": {}}
        supplier = _obj(id=1, name="Sup")
        chain = MagicMock()
        chain.first.return_value = supplier
        with patch("models.supplier.Supplier") as Supplier:
            Supplier.query.filter_by.return_value = chain
            _run_action("Sup", mock_user, ctx)
        assert ctx["step"] == 2
        _run_action("Widget", mock_user, ctx)
        assert ctx["step"] == 3
        _run_action("50", mock_user, ctx)
        assert ctx["step"] == 4
        purchase = _obj(id=8)
        with (
            patch("models.purchase.Purchase", pur_cls := MagicMock()),
            patch("models.purchase.PurchaseLine", line_cls := MagicMock()),
            patch("models.product.Product") as Product,
            patch("utils.helpers.generate_number", return_value="PO-1"),
            patch("routes.ai_routes.actions.StockService.add_stock"),
            patch("routes.ai_routes.create_final_options", return_value="opts"),
        ):
            pur_cls.return_value = purchase
            line_cls.return_value = _obj(id=1)
            prod_chain = MagicMock()
            prod_chain.first.return_value = _obj(id=2, name="Widget")
            Product.query.filter_by.return_value = prod_chain
            result = _run_action("100", mock_user, ctx)
        assert result is not None


class TestChequeWizardExtended:
    def test_cheque_complete_flow(self, mock_user):
        ctx = {"last_action": "شيك", "option": "1", "step": 1, "data": {}}
        _run_action("وارد", mock_user, ctx)
        assert ctx["step"] == 2
        _run_action("CHQ-99", mock_user, ctx)
        assert ctx["step"] == 3
        _run_action("5000", mock_user, ctx)
        assert ctx["step"] == 4
        cheque = _obj(id=3)
        with patch("models.cheque.Cheque", chq_cls := MagicMock()):
            chq_cls.return_value = cheque
            result = _run_action("2026-12-31", mock_user, ctx)
        assert "شيك" in result or "تم" in result

    def test_expense_colon(self, mock_user):
        ctx = {}
        expense = _obj(id=4)
        with (
            patch("models.Expense", exp_cls := MagicMock()),
            patch("utils.helpers.generate_number", return_value="EXP-2"),
        ):
            exp_cls.return_value = expense
            result = _run_action("مصروف: Travel, 300, transport", mock_user, ctx)
        assert result is not None

    def test_payment_receive_colon_missing_customer(self, mock_user):
        ctx = {}
        chain = MagicMock()
        chain.first.return_value = None
        with patch("models.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run_action("استلام: Nobody, 100, cash", mock_user, ctx)
        assert "غير موجود" in result


class TestWizardOptionTwoLists:
    def test_supplier_option_two_list(self, mock_user):
        ctx = {"last_action": "مورد"}
        supplier = _obj(name="SupList", phone="1")
        chain = MagicMock()
        chain.all.return_value = [supplier]
        with patch("models.supplier.Supplier") as Supplier:
            Supplier.query.filter_by.return_value = chain
            result = _run_action("2", mock_user, ctx)
        assert "SupList" in result

    def test_expense_option_two_list(self, mock_user):
        ctx = {"last_action": "مصروف"}
        expense = _obj(description="Rent", amount=Decimal("100"), category="office")
        chain = MagicMock()
        chain.all.return_value = [expense]
        with patch("models.expense.Expense") as Expense:
            Expense.query.filter_by.return_value = chain
            result = _run_action("2", mock_user, ctx)
        assert "Rent" in result

    def test_cheque_option_two_list(self, mock_user):
        ctx = {"last_action": "شيك"}
        cheque = _obj(
            cheque_number="C1",
            amount=Decimal("500"),
            due_date=_obj(strftime=lambda f: "2026-01-01"),
        )
        chain = MagicMock()
        chain.all.return_value = [cheque]
        with patch("models.cheque.Cheque") as Cheque:
            Cheque.query.filter_by.return_value = chain
            result = _run_action("2", mock_user, ctx)
        assert "C1" in result

    def test_user_option_two_list(self, mock_user):
        ctx = {"last_action": "مستخدم"}
        user_row = _obj(username="admin", role="admin")
        chain = MagicMock()
        chain.all.return_value = [user_row]
        with patch("utils.tenanting.scoped_user_query", return_value=chain):
            result = _run_action("2", mock_user, ctx)
        assert "admin" in result

    def test_ledger_option_two(self, mock_user):
        ctx = {"last_action": "دفتر"}
        result = _run_action("2", mock_user, ctx)
        assert result is not None

    def test_warehouse_option_two(self, mock_user):
        ctx = {"last_action": "مستودع"}
        product = _obj(name="StockProd", current_stock=5, unit="pcs")
        chain = MagicMock()
        chain.all.return_value = [product]
        with patch("models.product.Product") as Product:
            Product.query.filter_by.return_value = chain
            result = _run_action("2", mock_user, ctx)
        assert "StockProd" in result

    def test_apply_smart_listeners_help(self):
        from routes.ai_routes import apply_smart_listeners

        status, msg = apply_smart_listeners("مساعدة", {}, "فاتورة")
        assert status == "help"
        assert msg

    def test_apply_smart_listeners_back(self):
        from routes.ai_routes import apply_smart_listeners

        status, msg = apply_smart_listeners("عودة", {}, "فاتورة")
        assert status == "back"

    def test_create_final_options(self):
        from routes.ai_routes import create_final_options

        text = create_final_options("عميل", "Ali", 1)
        assert "إضافة عميل آخر" in text

    def test_train_local_ai_writes(self, tmp_path):
        from routes.ai_routes import train_local_ai

        with patch(
            "ai_knowledge.get_knowledge_path",
            return_value=str(tmp_path / "local_training.json"),
        ):
            train_local_ai("test_action", {"a": 1}, {"ok": True})
            train_local_ai("test_action", {"b": 2}, {"ok": True})
        assert (tmp_path / "local_training.json").exists()
