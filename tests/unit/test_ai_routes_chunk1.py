"""
tests/unit/test_ai_routes_chunk1.py — Chunk 1 AI route unit tests.

Covers the first 3 JSON API endpoints in ``routes/ai.py``:
  1. POST /recommend-price
  2. POST /check-stock
  3. GET  /analyze-customer/<id>

All AI / LLM calls are mocked via ``mock_ai_service``.  No real API is hit.
"""
import json

import pytest


# ===========================================================================
# POST /recommend-price
# ===========================================================================


class TestRecommendPrice:
    """POST /recommend-price — AI price recommendation."""

    RECOMMENDED = {
        "recommended_price": 125.0,
        "base_price": 100.0,
        "customer_avg": 150.0,
        "reason": "سعر موصى به لـ test بناءً على السجل",
    }

    def test_happy_path_returns_recommendation(self, ai_client, mock_ai_service):
        mock_ai_service.recommend_price.return_value = self.RECOMMENDED
        resp = ai_client.post(
            "/ai/recommend-price",
            json={"product_id": 1, "customer_id": 2},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["recommended_price"] == 125.0
        assert body["base_price"] == 100.0
        mock_ai_service.recommend_price.assert_called_once_with(1, 2)

    def test_missing_json_body_returns_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/recommend-price",
            data=b"not-json",
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "JSON" in resp.get_json()["error"]
        mock_ai_service.recommend_price.assert_not_called()

    def test_empty_json_body_returns_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/recommend-price",
            json={},
        )
        assert resp.status_code == 400
        assert "JSON" in resp.get_json()["error"]
        mock_ai_service.recommend_price.assert_not_called()

    def test_missing_product_id_returns_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/recommend-price",
            json={"customer_id": 2},
        )
        assert resp.status_code == 400
        mock_ai_service.recommend_price.assert_not_called()

    def test_missing_customer_id_returns_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/recommend-price",
            json={"product_id": 1},
        )
        assert resp.status_code == 400
        mock_ai_service.recommend_price.assert_not_called()

    def test_service_returns_none_returns_404(self, ai_client, mock_ai_service):
        mock_ai_service.recommend_price.return_value = None
        resp = ai_client.post(
            "/ai/recommend-price",
            json={"product_id": 999, "customer_id": 999},
        )
        assert resp.status_code == 404
        assert "Not found" in resp.get_json()["error"]

    def test_timeout_error_returns_503(self, ai_client, mock_ai_service):
        mock_ai_service.recommend_price.side_effect = TimeoutError("API timeout")
        resp = ai_client.post(
            "/ai/recommend-price",
            json={"product_id": 1, "customer_id": 2},
        )
        assert resp.status_code == 503
        assert "timed out" in resp.get_json()["error"]

    def test_generic_exception_returns_503(self, ai_client, mock_ai_service):
        mock_ai_service.recommend_price.side_effect = RuntimeError("connection reset")
        resp = ai_client.post(
            "/ai/recommend-price",
            json={"product_id": 1, "customer_id": 2},
        )
        assert resp.status_code == 503
        assert "error" in resp.get_json()["error"]

    def test_content_type_not_json_returns_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/recommend-price",
            data="plain text",
            content_type="text/plain",
        )
        assert resp.status_code == 400
        assert "JSON" in resp.get_json()["error"]
        mock_ai_service.recommend_price.assert_not_called()


# ===========================================================================
# POST /check-stock
# ===========================================================================


class TestCheckStock:
    """POST /check-stock — AI stock availability check."""

    def test_stock_sufficient_returns_success(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.return_value = None
        resp = ai_client.post(
            "/ai/check-stock",
            json={"product_id": 1, "quantity": 5},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["type"] == "success"
        mock_ai_service.check_stock_alert.assert_called_once_with(1, 5)

    def test_low_stock_warning(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.return_value = {
            "type": "warning",
            "message": "⚡ تحذير: المخزون سينخفض لـ 2 (أقل من الحد الأدنى 10)",
        }
        resp = ai_client.post(
            "/ai/check-stock",
            json={"product_id": 1, "quantity": 10},
        )
        assert resp.status_code == 200
        assert resp.get_json()["type"] == "warning"

    def test_insufficient_stock_error(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.return_value = {
            "type": "error",
            "message": "⚠️ المخزون غير كافٍ! متوفر: 3, مطلوب: 10",
        }
        resp = ai_client.post(
            "/ai/check-stock",
            json={"product_id": 1, "quantity": 10},
        )
        assert resp.status_code == 200
        assert resp.get_json()["type"] == "error"

    def test_missing_json_body_returns_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/check-stock",
            data=b"not-json",
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "JSON" in resp.get_json()["error"]
        mock_ai_service.check_stock_alert.assert_not_called()

    def test_empty_json_body_returns_400(self, ai_client, mock_ai_service):
        resp = ai_client.post("/ai/check-stock", json={})
        assert resp.status_code == 400
        mock_ai_service.check_stock_alert.assert_not_called()

    def test_missing_product_id_returns_400(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/check-stock",
            json={"quantity": 5},
        )
        assert resp.status_code == 400
        mock_ai_service.check_stock_alert.assert_not_called()

    def test_invalid_quantity_returns_422(self, ai_client, mock_ai_service):
        resp = ai_client.post(
            "/ai/check-stock",
            json={"product_id": 1, "quantity": "abc"},
        )
        assert resp.status_code == 422
        assert "number" in resp.get_json()["error"].lower()
        mock_ai_service.check_stock_alert.assert_not_called()

    def test_quantity_negative_allowed(self, ai_client, mock_ai_service):
        """Negative quantity is technically allowed as input to the service."""
        mock_ai_service.check_stock_alert.return_value = None
        resp = ai_client.post(
            "/ai/check-stock",
            json={"product_id": 1, "quantity": -5},
        )
        assert resp.status_code == 200
        mock_ai_service.check_stock_alert.assert_called_once_with(1, -5)

    def test_timeout_error_returns_503(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.side_effect = TimeoutError("API timeout")
        resp = ai_client.post(
            "/ai/check-stock",
            json={"product_id": 1, "quantity": 5},
        )
        assert resp.status_code == 503
        assert "timed out" in resp.get_json()["error"]

    def test_generic_exception_returns_503(self, ai_client, mock_ai_service):
        mock_ai_service.check_stock_alert.side_effect = RuntimeError("service down")
        resp = ai_client.post(
            "/ai/check-stock",
            json={"product_id": 1, "quantity": 5},
        )
        assert resp.status_code == 503
        assert "error" in resp.get_json()["error"]


# ===========================================================================
# GET /analyze-customer/<customer_id>
# ===========================================================================


class TestAnalyzeCustomer:
    """GET /analyze-customer/<id> — AI customer-behaviour analysis."""

    ANALYSIS = {
        "customer_name": "test-customer",
        "total_sales_aed": 5000.0,
        "total_paid_aed": 4500.0,
        "balance_aed": 500.0,
        "avg_days_to_pay": 15.0,
        "risk_level": "low",
    }

    def test_happy_path_returns_analysis(self, ai_client, mock_ai_service):
        mock_ai_service.analyze_customer_behavior.return_value = self.ANALYSIS
        resp = ai_client.get("/ai/analyze-customer/42")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["customer_name"] == "test-customer"
        assert body["risk_level"] == "low"
        mock_ai_service.analyze_customer_behavior.assert_called_once_with(42)

    def test_customer_not_found_returns_404(self, ai_client, mock_ai_service):
        mock_ai_service.analyze_customer_behavior.return_value = None
        resp = ai_client.get("/ai/analyze-customer/999")
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"].lower()

    def test_timeout_error_returns_503(self, ai_client, mock_ai_service):
        mock_ai_service.analyze_customer_behavior.side_effect = TimeoutError("API timeout")
        resp = ai_client.get("/ai/analyze-customer/1")
        assert resp.status_code == 503
        assert "timed out" in resp.get_json()["error"]

    def test_generic_exception_returns_503(self, ai_client, mock_ai_service):
        mock_ai_service.analyze_customer_behavior.side_effect = RuntimeError("LLM unavailable")
        resp = ai_client.get("/ai/analyze-customer/1")
        assert resp.status_code == 503
        assert "error" in resp.get_json()["error"]

    def test_non_existent_route_returns_404(self, ai_client):
        resp = ai_client.get("/ai/analyze-customer/abc")
        assert resp.status_code == 404
