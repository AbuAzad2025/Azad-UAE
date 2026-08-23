"""Dashboard chart JSON endpoints (/dashboard/api/charts/*)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest


@pytest.fixture
def charts_client(app_factory, bypass_permission_auth):
    from routes.main import main_bp

    app = app_factory(main_bp)
    return app.test_client()


def _series(days, total=100.0):
    return [{"date": date(2026, 8, day).isoformat(), "total_aed": total} for day in range(1, days + 1)]


class TestSalesTrendEndpoint:
    def test_envelope_and_series(self, charts_client):
        with (
            patch("routes.main.get_active_tenant_id", return_value=1),
            patch("routes.main.branch_scope_id", return_value=None),
            patch("routes.main.MainSiteService.sales_trend_daily", return_value=_series(14)) as svc,
        ):
            resp = charts_client.get("/dashboard/api/charts/sales-trend")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["days"] == 14
        assert len(body["data"]["series"]) == 14
        point = body["data"]["series"][0]
        assert set(point) == {"date", "total_aed"}
        kwargs = svc.call_args.kwargs
        assert kwargs["days"] == 14

    def test_days_param_clamped(self, charts_client):
        with (
            patch("routes.main.get_active_tenant_id", return_value=1),
            patch("routes.main.branch_scope_id", return_value=None),
            patch("routes.main.MainSiteService.sales_trend_daily", return_value=[]) as svc,
        ):
            resp_high = charts_client.get("/dashboard/api/charts/sales-trend?days=999")
            resp_low = charts_client.get("/dashboard/api/charts/sales-trend?days=1")

        assert resp_high.status_code == 200
        assert resp_low.status_code == 200
        assert svc.call_args_list[0].kwargs["days"] == 60
        assert svc.call_args_list[1].kwargs["days"] == 7

    def test_branch_scope_forwarded(self, charts_client):
        with (
            patch("routes.main.get_active_tenant_id", return_value=1),
            patch("routes.main.branch_scope_id", return_value=3),
            patch("routes.main.MainSiteService.sales_trend_daily", return_value=[]) as svc,
        ):
            charts_client.get("/dashboard/api/charts/sales-trend")

        assert svc.call_args.kwargs["branch_id"] == 3

    def test_unauthenticated_rejected(self, app_factory):
        from routes.main import main_bp
        from tests.unit.routes.conftest import unauthenticated_client

        app = app_factory(main_bp)
        client = app.test_client()
        with unauthenticated_client(client):
            resp = client.get("/dashboard/api/charts/sales-trend", follow_redirects=False)
        assert resp.status_code in (301, 302, 401)


class TestCashPositionEndpoint:
    def test_values_when_costs_visible(self, charts_client, bypass_permission_auth):
        bypass_permission_auth.can_see_costs.return_value = True
        with (
            patch("routes.main.get_active_tenant_id", return_value=1),
            patch("routes.main.branch_scope_id", return_value=None),
            patch(
                "routes.main.MainSiteService.liquidity_balance",
                side_effect=[1250.75, 5300.10],
            ) as liq,
        ):
            resp = charts_client.get("/dashboard/api/charts/cash-position")

        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["values"] == pytest.approx([1250.75, 5300.10])
        assert len(body["data"]["labels"]) == 2
        assert liq.call_args_list[0].args[0] == "cash"
        assert liq.call_args_list[1].args[0] == "bank"

    def test_empty_data_without_cost_visibility(self, charts_client, bypass_permission_auth):
        bypass_permission_auth.can_see_costs.return_value = False
        with (
            patch("routes.main.get_active_tenant_id", return_value=1),
            patch("routes.main.MainSiteService.liquidity_balance") as liq,
        ):
            resp = charts_client.get("/dashboard/api/charts/cash-position")

        body = resp.get_json()
        assert body["success"] is True
        assert body["data"] == {}
        liq.assert_not_called()


class TestTopCustomersEndpoint:
    def test_customers_shape(self, charts_client):
        customers = [
            {"customer_id": 1, "name": "Cust A", "total_aed": 900.5},
            {"customer_id": 2, "name": "Cust B", "total_aed": 300.0},
        ]
        with (
            patch("routes.main.get_active_tenant_id", return_value=1),
            patch("routes.main.branch_scope_id", return_value=None),
            patch("routes.main.MainSiteService.top_customers", return_value=customers) as svc,
        ):
            resp = charts_client.get("/dashboard/api/charts/top-customers")

        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["customers"] == customers
        assert body["data"]["days"] == 30
        kwargs = svc.call_args.kwargs
        assert kwargs["limit"] == 5
        assert kwargs["start_day"] is not None

    def test_limit_clamped(self, charts_client):
        with (
            patch("routes.main.get_active_tenant_id", return_value=1),
            patch("routes.main.branch_scope_id", return_value=None),
            patch("routes.main.MainSiteService.top_customers", return_value=[]) as svc,
        ):
            charts_client.get("/dashboard/api/charts/top-customers?limit=99&days=9999")

        assert svc.call_args.kwargs["limit"] == 10
        assert svc.call_args.kwargs["start_day"] is not None


class TestStockAlertsEndpoint:
    def test_summary_shape(self, charts_client):
        with patch("routes.main.MainSiteService.stock_alert_summary") as svc:
            svc.return_value = {
                "low_stock": [{"id": 1, "name": "Widget", "qty": 2.0, "min_qty": 5.0}],
                "out_of_stock": [{"id": 2, "name": "Gone", "qty": 0.0, "min_qty": 1.0}],
                "low_stock_count": 1,
                "out_of_stock_count": 1,
            }
            resp = charts_client.get("/dashboard/api/charts/stock-alerts")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert set(data) == {"low_stock", "out_of_stock", "low_stock_count", "out_of_stock_count"}
        assert data["low_stock"][0]["qty"] == pytest.approx(2.0)
        assert svc.call_args.kwargs["limit"] == 10

    def test_limit_clamped(self, charts_client):
        with patch("routes.main.MainSiteService.stock_alert_summary", return_value={}) as svc:
            charts_client.get("/dashboard/api/charts/stock-alerts?limit=500")
        assert svc.call_args.kwargs["limit"] == 25
