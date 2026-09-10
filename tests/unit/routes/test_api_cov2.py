"""Coverage for routes/api.py uncovered lines/arcs.

Targets (production lines/arcs):
- line 545 (exchange_rates_display base-not-in-symbols prepend)
- line 685 (_sanitize_breadcrumbs skips non-dict crumb)
- line 690 (_sanitize_breadcrumbs 12-key cap break)
- line 712 (ingest_telemetry_logs origin rejection)
- line 715 (ingest_telemetry_logs payload too large -> 413)
- line 733 (ingest_telemetry_logs skips non-dict event)
- line 737 (ingest_telemetry_logs skips empty-message event)
- lines 760-763 (ingest_telemetry_logs per-event exception -> continue)
- arcs 344->352, 387->397, 426->435 (search with empty query skips filter)
- arc 797->799 (warehouses with empty q skips filter)
- arc 806->814 (products with empty q skips filter)
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def api_cov2_client(app_factory, mocker):
    user = MagicMock(is_authenticated=True, tenant_id=1, id=1)
    user.has_permission.return_value = True
    mocker.patch("flask_login.utils._get_user", return_value=user)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
    from routes.api import api_bp

    app = app_factory(
        api_bp,
        config_overrides={
            "APP_ENV": "development",
            "DEBUG": True,
            "CLIENT_ERROR_TRUSTED_ORIGINS": ["http://localhost:5000"],
        },
    )
    return app.test_client()


def _valid_telemetry_event(**overrides):
    event = {"category": "SOFTWARE_EXCEPTION", "message": "boom"}
    event.update(overrides)
    return event


class TestExchangeRatesDisplayBasePrepend:
    def test_base_prepended_when_missing_from_symbols_line_545(self, api_cov2_client, mocker):
        """Line 545: symbols = (base,) + symbols when base not in symbols."""
        mocker.patch(
            "services.platform_query_service.PlatformQueryService.tenant_base_currency",
            return_value="USD",
        )
        get_rates = mocker.patch(
            "services.exchange_rate_service.ExchangeRateService.get_online_rates_for_display",
            return_value={"base": "USD", "rates": {}},
        )
        resp = api_cov2_client.get("/api/exchange-rates/display?base=USD&symbols=AED,EUR")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["tenant_base_currency"] == "USD"
        assert get_rates.call_count == 1
        kwargs = get_rates.call_args.kwargs
        assert kwargs["base"] == "USD"
        assert kwargs["symbols"][0] == "USD"
        assert "AED" in kwargs["symbols"]


class TestSanitizeBreadcrumbsViaTelemetry:
    def test_non_dict_crumb_skipped_line_685(self, api_cov2_client, mocker):
        """Line 685: non-dict breadcrumb is skipped via route."""
        log_event = mocker.patch("routes.api.log_event")
        payload = {
            "events": [
                _valid_telemetry_event(breadcrumbs=["not-a-dict", {"k": "v"}]),
            ]
        }
        resp = api_cov2_client.post("/api/v1/telemetry/logs", json=payload)
        assert resp.status_code == 202
        assert resp.get_json()["data"]["accepted"] == 1
        assert log_event.call_count == 1
        assert log_event.call_args.kwargs["breadcrumbs"] == [{"k": "v"}]

    def test_breadcrumb_key_cap_break_line_690(self, api_cov2_client, mocker):
        """Line 690: breadcrumb dict capped at 12 keys via route."""
        log_event = mocker.patch("routes.api.log_event")
        big = {f"k{i}": f"v{i}" for i in range(15)}
        payload = {"events": [_valid_telemetry_event(breadcrumbs=[big])]}
        resp = api_cov2_client.post("/api/v1/telemetry/logs", json=payload)
        assert resp.status_code == 202
        assert resp.get_json()["data"]["accepted"] == 1
        crumbs = log_event.call_args.kwargs["breadcrumbs"]
        assert len(crumbs) == 1
        assert len(crumbs[0]) == 12


class TestIngestTelemetryGuards:
    def test_origin_rejected_line_712(self, api_cov2_client):
        """Line 712: origin allowlist rejection returns the origin error."""
        resp = api_cov2_client.post(
            "/api/v1/telemetry/logs",
            json={"events": [_valid_telemetry_event()]},
            headers={"Origin": "http://evil.test"},
        )
        assert resp.status_code == 403
        assert resp.get_json()["success"] is False

    def test_payload_too_large_line_715(self, api_cov2_client):
        """Line 715: oversized content-length returns 413."""
        resp = api_cov2_client.post(
            "/api/v1/telemetry/logs",
            data="x" * (60 * 1024),
            content_type="application/json",
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code == 413

    def test_non_dict_event_skipped_line_733(self, api_cov2_client, mocker):
        """Line 733: non-dict event in batch is skipped."""
        log_event = mocker.patch("routes.api.log_event")
        payload = {"events": ["not-a-dict", _valid_telemetry_event(message="ok")]}
        resp = api_cov2_client.post("/api/v1/telemetry/logs", json=payload)
        assert resp.status_code == 202
        assert resp.get_json()["data"]["accepted"] == 1
        assert log_event.call_count == 1

    def test_empty_message_skipped_line_737(self, api_cov2_client, mocker):
        """Line 737: event with blank message is skipped."""
        log_event = mocker.patch("routes.api.log_event")
        payload = {
            "events": [
                _valid_telemetry_event(message="   "),
                _valid_telemetry_event(message="second-ok"),
            ]
        }
        resp = api_cov2_client.post("/api/v1/telemetry/logs", json=payload)
        assert resp.status_code == 202
        assert resp.get_json()["data"]["accepted"] == 1
        assert log_event.call_count == 1
        assert log_event.call_args.args[1] == "second-ok"

    def test_poisoned_event_continues_lines_760_763(self, api_cov2_client, mocker):
        """Lines 760-763: one poisoned event must not kill the batch."""
        log_event = mocker.patch(
            "routes.api.log_event",
            side_effect=[RuntimeError("boom"), None],
        )
        payload = {
            "events": [
                _valid_telemetry_event(message="first"),
                _valid_telemetry_event(message="second"),
            ]
        }
        resp = api_cov2_client.post("/api/v1/telemetry/logs", json=payload)
        assert resp.status_code == 202
        assert resp.get_json()["data"]["accepted"] == 1
        assert log_event.call_count == 2


class TestSearchEmptyQueryArcs:
    def test_products_empty_query_arc_344_352(self, api_cov2_client, mocker):
        """Arc 344->352: products search with no q skips the ilike filter."""
        product = SimpleNamespace(
            id=1,
            name="Widget",
            sku="W1",
            barcode="111",
            regular_price=Decimal("10"),
            merchant_price=None,
            partner_price=None,
            cost_price=Decimal("5"),
            unit="pc",
            current_stock=Decimal("3"),
            has_serial_number=False,
        )
        product.is_low_stock = lambda: False
        products_q = MagicMock()
        products_q.filter.return_value = products_q
        products_q.order_by.return_value = products_q
        products_q.limit.return_value.all.return_value = [product]
        mocker.patch(
            "services.platform_query_service.PlatformQueryService.products_base_query",
            return_value=products_q,
        )
        mocker.patch("routes.api.get_accessible_warehouse_ids", return_value=[1])
        mocker.patch("routes.api.get_branch_stock_map", return_value={1: Decimal("3")})
        resp = api_cov2_client.get("/api/search?type=products")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"][0]["name"] == "Widget"
        products_q.filter.assert_not_called()

    def test_suppliers_empty_query_arc_387_397(self, api_cov2_client, mocker):
        """Arc 387->397: suppliers search with no q skips the query filter."""
        supplier = SimpleNamespace(
            id=2,
            name="Sup",
            company_name="Co",
            phone="050",
            email="a@t.com",
            supplier_type="local",
            rating=5,
            is_verified=True,
        )
        supplier.get_type_display = lambda: "Local"
        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.order_by.return_value = base_q
        base_q.limit.return_value.offset.return_value.all.return_value = [supplier]
        mocker.patch("routes.api._scoped_supplier_query", return_value=base_q)
        mocker.patch("routes.api._supplier_balance", return_value=0.0)
        resp = api_cov2_client.get("/api/search?type=suppliers")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"][0]["id"] == 2

    def test_customers_empty_query_arc_426_435(self, api_cov2_client, mocker):
        """Arc 426->435: customers search with no q skips the query filter."""
        customer = SimpleNamespace(
            id=3,
            name="Cust",
            phone="050",
            email="c@t.com",
            customer_type="retail",
        )
        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.order_by.return_value = base_q
        base_q.limit.return_value.offset.return_value.all.return_value = [customer]
        mocker.patch("routes.api._scoped_customer_query", return_value=base_q)
        mocker.patch("routes.api._customer_balance", return_value=12.0)
        resp = api_cov2_client.get("/api/search?type=customers")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"][0]["id"] == 3


class TestQueryHelperEmptyQArcs:
    def test_warehouses_empty_q_arc_797_799(self, api_cov2_client, mocker):
        """Arc 797->799: warehouses listing with no q skips name filter."""
        import routes.api as api_module

        wh = SimpleNamespace(id=1, name="Main")
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [wh]
        mocker.patch.object(api_module, "get_accessible_warehouses", return_value=mock_q)
        resp = api_cov2_client.get("/api/warehouses")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"][0]["id"] == 1
        mock_q.filter.assert_not_called()

    def test_products_empty_q_arc_806_814(self, api_cov2_client, mocker):
        """Arc 806->814: products listing with no q skips name filter."""
        product = SimpleNamespace(
            id=1,
            name="Item",
            sku="SKU",
            barcode=None,
            regular_price=Decimal("5"),
            current_stock=Decimal("2"),
        )
        products_q = MagicMock()
        products_q.filter.return_value = products_q
        products_q.order_by.return_value = products_q
        products_q.limit.return_value.all.return_value = [product]
        mocker.patch(
            "routes.api.StockService.get_visible_products_query",
            return_value=products_q,
        )
        mocker.patch("routes.api.get_accessible_warehouse_ids", return_value=[1])
        mocker.patch("routes.api.get_branch_stock_map", return_value={1: Decimal("2")})
        resp = api_cov2_client.get("/api/products")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"][0]["id"] == 1
        products_q.filter.assert_not_called()
