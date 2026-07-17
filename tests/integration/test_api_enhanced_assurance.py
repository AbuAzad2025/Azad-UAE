"""Deep assurance — routes/api_enhanced.py v2 API, search, AI analytics."""

from __future__ import annotations

from decimal import Decimal
import pytest


class TestEnhancedAuth:
    """v2 API requires login and permissions."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v2/sales",
            "/api/v2/customers",
            "/api/v2/products/search?q=test",
            "/api/v2/analytics/sales-forecast",
            "/api/v2/analytics/profit-margins",
        ],
    )
    def test_anonymous_blocked(self, app, client, path):
        with app.app_context():
            resp = client.get(path)
        assert resp.status_code in (302, 401, 403)


class TestEnhancedSalesCustomers:
    """Paginated sales/customers and detail lookup."""

    def test_sales_list_empty(self, app, auth_client):
        with app.app_context():
            resp = auth_client.get("/api/v2/sales?page=1&per_page=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert isinstance(data["sales"], list)

    def test_sale_detail_not_found(self, app, auth_client):
        from werkzeug.exceptions import NotFound

        with app.app_context():
            try:
                resp = auth_client.get("/api/v2/sales/999999999")
            except NotFound:
                pass
            else:
                assert resp.status_code == 404

    def test_customers_list(self, app, auth_client, sample_customer):
        with app.app_context():
            resp = auth_client.get("/api/v2/customers?per_page=10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["total"] >= 1

    def test_product_search_requires_query(self, app, auth_client):
        with app.app_context():
            resp = auth_client.get("/api/v2/products/search")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is False

    def test_product_search_results(self, app, auth_client, sample_product):
        with app.app_context():
            resp = auth_client.get("/api/v2/products/search?q=Test&limit=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] >= 1


class TestEnhancedAnalytics:
    """AI forecast endpoints — mocked service layer."""

    def test_sales_forecast(self, app, auth_client, mocker):
        mocker.patch(
            "services.ai_service.AIService.predict_sales_trend",
            return_value={"success": True, "forecast": []},
        )
        with app.app_context():
            resp = auth_client.get("/api/v2/analytics/sales-forecast?days=14")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_profit_margins(self, app, auth_client, mocker):
        mocker.patch(
            "services.ai_service.AIService.analyze_profit_margins",
            return_value={"success": True, "margins": []},
        )
        with app.app_context():
            resp = auth_client.get("/api/v2/analytics/profit-margins")
        assert resp.status_code == 200

    def test_sale_detail_with_sale(
        self,
        app,
        auth_client,
        db_session,
        sample_tenant,
        sample_user,
        sample_branch,
        sample_customer,
    ):
        from datetime import datetime, timezone
        from models import Sale

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="V2-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            branch_id=sample_branch.id,
            status="confirmed",
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            sale_date=datetime.now(timezone.utc),
            is_active=True,
        )
        db_session.add(sale)
        db_session.commit()

        with app.app_context():
            resp = auth_client.get(f"/api/v2/sales/{sale.id}")
        assert resp.status_code == 200
        assert resp.get_json()["sale"]["id"] == sale.id
