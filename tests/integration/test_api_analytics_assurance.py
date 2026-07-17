"""Deep assurance — routes/api_analytics.py metrics and branch scoping."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestAnalyticsAuth:
    """Analytics endpoints require authentication."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/analytics/overdue-payments",
            "/api/analytics/daily-stats",
            "/api/analytics/top-customers",
            "/api/analytics/low-stock-products",
            "/api/analytics/revenue-trend",
        ],
    )
    def test_anonymous_blocked(self, app, client, path):
        with app.app_context():
            resp = client.get(path)
        assert resp.status_code in (302, 401, 403)


class TestAnalyticsEndpoints:
    """Authenticated analytics — zero-data and boundary params."""

    def test_overdue_payments_empty(self, app, auth_client, sample_customer):
        with app.app_context():
            resp = auth_client.get("/api/analytics/overdue-payments")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] >= 0

    def test_daily_stats_zero_data(self, app, auth_client):
        with app.app_context():
            resp = auth_client.get("/api/analytics/daily-stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["sales"]["count"] >= 0
        assert body["payments"]["count"] >= 0

    def test_top_customers_limit_param(self, app, auth_client, sample_customer):
        with app.app_context():
            resp = auth_client.get("/api/analytics/top-customers?limit=3")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert len(data["customers"]) <= 3

    def test_low_stock_products(self, app, auth_client, sample_product, db_session):
        sample_product.current_stock = Decimal("0")
        sample_product.min_stock_alert = Decimal("5")
        with app.app_context():
            from extensions import db

            db.session.commit()
            resp = auth_client.get("/api/analytics/low-stock-products")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        if data["count"]:
            assert data["products"][0]["urgency"] in ("critical", "high")

    def test_revenue_trend_days_boundary(self, app, auth_client):
        with app.app_context():
            resp = auth_client.get("/api/analytics/revenue-trend?days=7")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert isinstance(resp.get_json()["data"], list)

    def test_revenue_trend_with_sales(
        self, app, auth_client, db_session, sample_tenant, sample_user, sample_branch
    ):
        from models import Sale, Customer

        cust = Customer(
            tenant_id=sample_tenant.id, name="Analytics Cust", phone="050111"
        )
        db_session.add(cust)
        db_session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="AN-001",
            customer_id=cust.id,
            seller_id=sample_user.id,
            branch_id=sample_branch.id,
            status="confirmed",
            total_amount=Decimal("250"),
            amount=Decimal("250"),
            amount_aed=Decimal("250"),
            sale_date=datetime.now(timezone.utc),
        )
        db_session.add(sale)
        db_session.commit()

        with app.app_context():
            resp = auth_client.get("/api/analytics/revenue-trend?days=30")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_apply_branch_scope_filters(self, app):
        from routes.api_analytics import _apply_branch_scope

        mock_query = MagicMock()
        mock_model = MagicMock()
        mock_model.branch_id = MagicMock()
        with app.app_context():
            with patch("routes.api_analytics.branch_scope_id_for", return_value=5):
                result = _apply_branch_scope(mock_query, mock_model)
        mock_query.filter.assert_called_once()
        assert result is mock_query.filter.return_value
