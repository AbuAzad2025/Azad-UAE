"""Coverage-targeted POS routes (A) — gating, settings pages, catalog, register.

Targets routes/pos.py uncovered lines 127, 139, 424, 430, 437, 462, 528, 534, 540
and arcs/ranges 292-293, 327->333, 366-371, 386-387, 448-449, 477-478, 543-544,
602->621, 676->686, 691->693.

Real response paths via the Flask test client; mocks only at DB/external
boundaries (tenant queries, write services, currency/tax helpers).
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query
from tests.unit.routes.test_pos_v2_routes import _pos_api_patches


@pytest.fixture
def cov_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


class TestCovACurrentTenantGating:
    """Lines 127/139 + arc 327->333: no active tenant skips gating entirely."""

    def test_shift_current_without_tenant_id_reports_none(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.get_active_tenant_id", return_value=None),
            patch("utils.tenanting.get_active_tenant_id", return_value=None),
        ):
            resp = cov_client.get("/pos/api/shift/current")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == {"shift": None}


class TestCovAOrderTypeApi:
    """Arc 366-371: /api/order-types with and without an active tenant."""

    def test_lists_configured_types(self, cov_client):
        order_type = MagicMock()
        order_type.to_dict.return_value = {"code": "dine_in", "name": "Dine in"}
        default = MagicMock(code="dine_in")
        with (
            _pos_api_patches(),
            patch("routes.pos.PosOrderType.for_tenant", return_value=[order_type]),
            patch("routes.pos.PosOrderType.default_for_tenant", return_value=default),
        ):
            resp = cov_client.get("/pos/api/order-types")
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert body["order_types"] == [{"code": "dine_in", "name": "Dine in"}]
        assert body["default_code"] == "dine_in"

    def test_rejects_request_without_tenant(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.get_active_tenant_id", return_value=None),
        ):
            resp = cov_client.get("/pos/api/order-types")
        assert resp.status_code == 400


class TestCovAOrderTypeSettingsFailures:
    """Lines 424/430/437 (missing records) + arcs 386-387/448-449."""

    def _post(self, client, **form):
        return client.post("/pos/settings/order-types", data=form)

    def test_get_redirects_without_tenant(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.get_active_tenant_id", return_value=None),
        ):
            resp = cov_client.get("/pos/settings/order-types")
        assert resp.status_code == 302

    def test_toggle_missing_record_rejected(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=None),
        ):
            resp = self._post(cov_client, action="toggle", ot_id="404")
        assert resp.status_code == 302

    def test_set_default_missing_record_rejected(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=None),
        ):
            resp = self._post(cov_client, action="set_default", ot_id="404")
        assert resp.status_code == 302

    def test_delete_missing_record_rejected(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=None),
        ):
            resp = self._post(cov_client, action="delete", ot_id="404")
        assert resp.status_code == 302

    def test_create_unexpected_error_surfaces_danger_flash(self, cov_client):
        with (
            _pos_api_patches(),
            patch(
                "services.pos_write_service.PosWriteService.create_order_type",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = self._post(cov_client, action="create", code="drive")
        assert resp.status_code == 302


class TestCovAPrinterSettingsFailures:
    """Lines 462/528/534/540 + arcs 477-478/543-544."""

    def _post(self, client, **form):
        base = {
            "action": "create",
            "name": "Counter",
            "role": "kitchen",
            "connection_type": "agent_network",
        }
        base.update(form)
        return client.post("/pos/settings/printers", data=base)

    def test_get_redirects_without_tenant(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.get_active_tenant_id", return_value=None),
        ):
            resp = cov_client.get("/pos/settings/printers")
        assert resp.status_code == 302

    def test_create_skips_blank_category_chunks(self, cov_client):
        with (
            _pos_api_patches(),
            patch("services.pos_write_service.PosWriteService.create_printer") as create,
        ):
            resp = self._post(cov_client, category_ids="1,,2")
        assert resp.status_code == 302
        assert create.call_args.kwargs["category_ids"] == [1, 2]

    def test_toggle_missing_printer_rejected(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=None),
        ):
            resp = self._post(cov_client, action="toggle", printer_id="404")
        assert resp.status_code == 302

    def test_delete_missing_printer_rejected(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=None),
        ):
            resp = self._post(cov_client, action="delete", printer_id="404")
        assert resp.status_code == 302

    def test_unknown_action_rejected(self, cov_client):
        with _pos_api_patches():
            resp = self._post(cov_client, action="explode")
        assert resp.status_code == 302

    def test_create_unexpected_error_surfaces_danger_flash(self, cov_client):
        with (
            _pos_api_patches(),
            patch(
                "services.pos_write_service.PosWriteService.create_printer",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = self._post(cov_client)
        assert resp.status_code == 302


class TestCovACustomerListing:
    """Arcs 676->686 (unfiltered list) and 691->693 (customer without phone)."""

    def _customer(self, phone):
        customer = MagicMock()
        customer.id = 2
        customer.name = "Sara"
        customer.phone = phone
        customer.customer_type = "regular"
        return customer

    def test_lists_without_query_and_handles_missing_phone(self, cov_client):
        query = _chain_query(all=[self._customer(None)])
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_query", return_value=query),
        ):
            resp = cov_client.get("/pos/api/customers")
        assert resp.status_code == 200
        assert resp.get_json()["data"][0]["text"] == "Sara"

    def test_query_filters_and_formats_phone_label(self, cov_client):
        query = _chain_query(all=[self._customer("050123")])
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_query", return_value=query),
        ):
            resp = cov_client.get("/pos/api/customers?q=sara&per_page=5")
        assert resp.status_code == 200
        assert resp.get_json()["data"][0]["text"] == "Sara - 050123"


class TestCovAProductsFallback:
    """Arc 602->621: an empty tenant catalog keeps the grid empty."""

    def test_empty_fallback_grid_stays_empty(self, cov_client):
        prod_q = MagicMock()
        prod_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        with (
            _pos_api_patches(search_result=([], {}, [])),
            patch("routes.pos.tenant_query", return_value=prod_q),
        ):
            resp = cov_client.get("/pos/api/products")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == []


class TestCovARegisterContextFallback:
    """Arc 292-293: currency-symbol lookup failure falls back to the code."""

    def test_index_renders_with_symbol_fallback(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.Tenant.get_current", return_value=None),
            patch(
                "utils.currency_utils.get_currency_symbol",
                side_effect=RuntimeError("fx down"),
            ),
            patch("utils.tax_settings.get_prices_include_vat", return_value=False),
        ):
            resp = cov_client.get("/pos/")
        assert resp.status_code == 200
