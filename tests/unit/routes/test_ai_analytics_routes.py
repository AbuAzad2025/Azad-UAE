"""Unit tests for routes/ai_routes/analytics.py — AI analytics endpoints.

Real-login tests against the full app: the AI access gate and permission
decorators run for real; only the AIService computation layer is mocked.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def no_perm_client(client, db_session, sample_tenant):
    """Authenticated tenant user whose role has zero permissions."""
    from models import Role, User

    unique = str(uuid.uuid4())[:8]
    role = Role(name=f"No Perms {unique}", slug=f"no_perms_{unique}", is_active=True)
    db_session.add(role)
    db_session.flush()
    user = User(
        username=f"noperm-{unique}",
        email=f"noperm-{unique}@example.com",
        full_name="No Perms",
        tenant_id=sample_tenant.id,
        role_id=role.id,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    return client


class TestAccessContract:
    def test_anonymous_redirected(self, client):
        resp = client.get("/ai/predict-sales")
        assert resp.status_code == 302

    def test_anonymous_json_gets_403(self, client):
        resp = client.get("/ai/predict-sales", headers={"Accept": "application/json"})
        assert resp.status_code == 403
        assert resp.get_json()["success"] is False

    def test_user_without_permission_gets_403(self, no_perm_client):
        resp = no_perm_client.get("/ai/predict-sales")
        assert resp.status_code == 403

    def test_permission_checked_per_endpoint(self, no_perm_client):
        # inventory-health requires manage_warehouse, churn manage_customers.
        assert no_perm_client.get("/ai/inventory-health").status_code == 403
        assert no_perm_client.get("/ai/churn-prediction").status_code == 403


class TestReadEndpoints:
    def test_predict_sales_default_days(self, auth_client, mocker):
        predict = mocker.patch(
            "services.ai_service.AIService.predict_sales_trend",
            return_value={"forecast": [1, 2]},
        )
        resp = auth_client.get("/ai/predict-sales")
        assert resp.status_code == 200
        assert resp.get_json() == {"forecast": [1, 2]}
        predict.assert_called_once_with(7)

    def test_predict_sales_custom_days(self, auth_client, mocker):
        predict = mocker.patch(
            "services.ai_service.AIService.predict_sales_trend",
            return_value={"forecast": []},
        )
        resp = auth_client.get("/ai/predict-sales?days=14")
        assert resp.status_code == 200
        predict.assert_called_once_with(14)

    def test_analyze_margins(self, auth_client, mocker):
        analyze = mocker.patch(
            "services.ai_service.AIService.analyze_profit_margins",
            return_value={"margins": []},
        )
        resp = auth_client.get("/ai/analyze-margins")
        assert resp.status_code == 200
        assert resp.get_json() == {"margins": []}
        analyze.assert_called_once_with()

    def test_detect_patterns(self, auth_client, mocker):
        detect = mocker.patch(
            "services.ai_service.AIService.detect_sales_patterns",
            return_value={"patterns": ["weekly"]},
        )
        resp = auth_client.get("/ai/detect-patterns")
        assert resp.status_code == 200
        assert resp.get_json() == {"patterns": ["weekly"]}
        detect.assert_called_once_with()

    def test_inventory_health(self, auth_client, mocker):
        health = mocker.patch(
            "services.ai_service.AIService.analyze_inventory_health",
            return_value={"health": "ok"},
        )
        resp = auth_client.get("/ai/inventory-health")
        assert resp.status_code == 200
        assert resp.get_json() == {"health": "ok"}
        health.assert_called_once_with()

    def test_deep_analysis(self, auth_client, mocker):
        deep = mocker.patch(
            "services.ai_service.AIService.deep_business_analysis",
            return_value={"score": 90},
        )
        resp = auth_client.get("/ai/deep-analysis")
        assert resp.status_code == 200
        assert resp.get_json() == {"score": 90}
        deep.assert_called_once_with()

    def test_cash_flow_prediction_days_param(self, auth_client, mocker):
        flow = mocker.patch(
            "services.ai_service.AIService.predict_cash_flow",
            return_value={"flow": []},
        )
        resp = auth_client.get("/ai/cash-flow-prediction?days=45")
        assert resp.status_code == 200
        flow.assert_called_once_with(45)

    def test_churn_prediction(self, auth_client, mocker):
        churn = mocker.patch(
            "services.ai_service.AIService.predict_customer_churn",
            return_value={"at_risk": []},
        )
        resp = auth_client.get("/ai/churn-prediction")
        assert resp.status_code == 200
        assert resp.get_json() == {"at_risk": []}
        churn.assert_called_once_with()

    def test_optimize_inventory(self, auth_client, mocker):
        optimize = mocker.patch(
            "services.ai_service.AIService.optimize_inventory_levels",
            return_value={"tips": []},
        )
        resp = auth_client.get("/ai/optimize-inventory")
        assert resp.status_code == 200
        assert resp.get_json() == {"tips": []}
        optimize.assert_called_once_with()


@pytest.fixture
def view_products_client(client, db_session, sample_tenant):
    """Authenticated tenant user whose role holds only view_products."""
    from models import Permission, Role, User

    unique = str(uuid.uuid4())[:8]
    perm = Permission.query.filter_by(code="view_products").first()
    if perm is None:
        perm = Permission(
            code="view_products",
            name="view_products",
            name_ar="view_products",
            category="test",
        )
        db_session.add(perm)
        db_session.flush()
    role = Role(name=f"Viewer {unique}", slug=f"viewer_{unique}", is_active=True)
    role.permissions.append(perm)
    db_session.add(role)
    db_session.flush()
    user = User(
        username=f"viewer-{unique}",
        email=f"viewer-{unique}@example.com",
        full_name="Viewer",
        tenant_id=sample_tenant.id,
        role_id=role.id,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    return client


class TestSmartPrice:
    def test_missing_fields_400(self, view_products_client):
        resp = view_products_client.post("/ai/smart-price", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Product and Customer required"

    def test_non_json_body_400_not_500(self, view_products_client):
        """Regression: unguarded get_json(silent=True) used to 500 on non-JSON."""
        resp = view_products_client.post("/ai/smart-price", data="not json", content_type="text/plain")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Product and Customer required"

    def test_not_found_404(self, view_products_client, mocker):
        mocker.patch("services.ai_service.AIService.smart_pricing_engine", return_value=None)
        resp = view_products_client.post("/ai/smart-price", json={"product_id": 1, "customer_id": 2})
        assert resp.status_code == 404

    def test_success_payload_and_call_args(self, view_products_client, mocker):
        engine = mocker.patch(
            "services.ai_service.AIService.smart_pricing_engine",
            return_value={"price": 42},
        )
        resp = view_products_client.post(
            "/ai/smart-price",
            json={"product_id": 1, "customer_id": 2, "quantity": 5},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"price": 42}
        engine.assert_called_once_with(1, 2, 5)


class TestBusinessInsights:
    def test_insights_formatted_with_icons(self, auth_client, mocker):
        mocker.patch(
            "services.ai_service.AIService.generate_business_insights",
            return_value=[
                {
                    "type": "warning",
                    "title": "Low stock",
                    "message": "Item X low",
                    "action": "Reorder",
                },
                {
                    "type": "info",
                    "title": "Sales up",
                    "message": "Good week",
                    "action": "Keep going",
                },
            ],
        )
        resp = auth_client.get("/ai/business-insights")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["insights"] == [
            {
                "icon": "⚠️",
                "title": "Low stock",
                "insight": "Item X low",
                "action": "Reorder",
            },
            {
                "icon": "ℹ️",
                "title": "Sales up",
                "insight": "Good week",
                "action": "Keep going",
            },
        ]
