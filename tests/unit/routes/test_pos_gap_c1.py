"""Coverage-Gap C1 — routes/pos.py residual branches.

Targets the uncovered ranges left by the phase/chunk suites:

* sub-feature gating (denied tenant / absent tenant),
* idempotency plumbing (replay-only hit, in-flight 409, hash-mismatch 422,
  stored replay, ledger completion, IntegrityError -> 409/500),
* settings pages (order types + printers) covering every POST action,
* catalog endpoints (categories, products fallback grid, exact lookup,
  snapshot, service-failure mapping),
* checkout error handlers (override denial, plan limit, integrity races,
* shifts suite (open/reconcile/close + totals accumulation),
* drawer / supervisor PIN / cash movements / void-line / receipt lookup /
  smart RMA guards,
* SSE fan-out helpers (stale-subscriber pruning, unsubscribe teardown).
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import routes.pos as pos_module
from services.idempotency_service import (
    IdempotencyHashMismatchError,
    IdempotencyInFlightError,
)
from services.pos_cart_service import PosCartConflictError
from services.pos_override_service import PosOverrideError
from services.pos_session_service import PosSessionService
from tests.unit.routes.test_pos_v2_routes import (
    _mock_session,
    _pos_api_patches,
)
from utils.api_response import error_response
from utils.tenant_limits import TenantLimitError


def _ot(oid=1, is_default=False):
    ot = MagicMock()
    ot.id = oid
    ot.tenant_id = 1
    ot.code = f"type{oid}"
    ot.name_ar = "نوع"
    ot.is_default = is_default
    ot.is_active = True
    return ot


def _catalog_query(items):
    q = MagicMock()
    q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = items
    return q


def _fake_product(pid, active=True):
    return SimpleNamespace(
        id=pid,
        is_active=active,
        name=f"P{pid}",
        name_ar="منتج",
        sku=f"SKU{pid}",
        barcode=f"BC{pid}",
        regular_price=Decimal("10"),
        current_stock=Decimal("4"),
        unit="pcs",
        has_serial_number=False,
        category_id=None,
    )


@pytest.fixture
def pg_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


# ═══════════════════════ SSE fan-out helpers ═══════════════════════


class TestSseFanoutHelpers:
    def test_notify_kds_drops_stale_subscriber_and_publishes(self, pg_client):
        stale_q = MagicMock()
        stale_q.put_nowait.side_effect = RuntimeError("queue full")
        healthy_q = __import__("queue").Queue()
        pos_module._KDS_SUBSCRIBERS[:] = [(1, stale_q), (None, healthy_q)]
        with patch("routes.pos.sse_backplane") as bp:
            pos_module._notify_kds({"type": "refresh", "tenant_id": 1})
        assert (1, stale_q) not in pos_module._KDS_SUBSCRIBERS
        assert (None, healthy_q) in pos_module._KDS_SUBSCRIBERS
        bp.publish.assert_called_once_with(
            "pos:kds:1",
            {"type": "refresh", "ts": bp.publish.call_args[0][1]["ts"], "tenant_id": 1},
        )
        assert healthy_q.qsize() == 1

    def test_publish_cfd_refresh_noop_without_ids(self, pg_client):
        with patch("routes.pos.sse_backplane") as bp:
            pos_module._publish_cfd_refresh(None, 0)
            pos_module._publish_cfd_refresh(0, None)
        bp.publish.assert_not_called()

    def test_publish_cfd_refresh_prunes_stale_and_pushes(self, pg_client):
        live_q = __import__("queue").Queue()
        dead_q = MagicMock()
        dead_q.put_nowait.side_effect = RuntimeError("gone")
        pos_module._CFD_SUBSCRIBERS[:] = [(1, 11, dead_q), (1, 11, live_q), (2, 12, live_q)]
        with patch("routes.pos.sse_backplane") as bp:
            pos_module._publish_cfd_refresh(1, 11)
        assert (1, 11, dead_q) not in pos_module._CFD_SUBSCRIBERS
        assert (1, 11, live_q) in pos_module._CFD_SUBSCRIBERS
        channel, payload = bp.publish.call_args.args
        assert channel == "pos:cfd:1:11"
        assert payload["type"] == "refresh"
        pos_module._CFD_SUBSCRIBERS[:] = []


# ═══════════════════════ Feature gating ═══════════════════════


class TestPosSubfeatureGating:
    def test_shift_current_denied_for_disabled_tenant(self, pg_client):
        tenant = MagicMock(enable_pos=True, enable_pos_shifts=False)
        with _pos_api_patches(tenant=tenant):
            resp = pg_client.get("/pos/api/shift/current")
        assert resp.status_code == 403

    def test_shift_current_absent_tenant_reports_none(self, pg_client):
        with (
            _pos_api_patches(),
            patch("utils.tenanting.get_active_tenant_id", return_value=None),
        ):
            resp = pg_client.get("/pos/api/shift/current")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == {"shift": None}

    def test_shift_current_without_any_session_reports_none(self, pg_client):
        with _pos_api_patches(session=None, shift=None):
            resp = pg_client.get("/pos/api/shift/current")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == {"shift": None}


# ═══════════════════════ Settings pages ═══════════════════════


class TestOrderTypeSettings:
    def _post(self, client, **form):
        return client.post("/pos/settings/order-types", data=form)

    def test_get_renders(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.render_template", return_value="ok") as render,
        ):
            resp = pg_client.get("/pos/settings/order-types")
        assert resp.status_code == 200
        render.assert_called_once()

    def test_redirects_when_no_active_tenant(self, pg_client):
        with (
            _pos_api_patches(),
            patch("utils.tenanting.get_active_tenant_id", return_value=None),
        ):
            resp = self._post(pg_client)
        assert resp.status_code == 302

    def test_create_success(self, pg_client):
        with (
            _pos_api_patches(),
            patch("services.pos_write_service.PosWriteService.create_order_type") as create,
        ):
            resp = self._post(pg_client, action="create", code="drive", name_ar="سائق")
        assert resp.status_code == 302
        assert create.call_args.kwargs["code"] == "drive"

    def test_create_requires_code(self, pg_client):
        with _pos_api_patches():
            resp = self._post(pg_client, action="create", code="")
        assert resp.status_code == 302

    def test_edit_missing_record_rejected(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=None),
        ):
            resp = self._post(pg_client, action="edit", ot_id="9")
        assert resp.status_code == 302

    def test_edit_cross_tenant_rejected(self, pg_client):
        foreign = _ot(oid=9)
        foreign.tenant_id = 2
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=foreign),
        ):
            resp = self._post(pg_client, action="edit", ot_id="9")
        assert resp.status_code == 302

    def test_edit_updates_fields(self, pg_client):
        ot = _ot()
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=ot),
        ):
            resp = self._post(
                pg_client,
                action="edit",
                ot_id="1",
                name_ar="محدث",
                name_en="Updated",
                is_active="on",
                sort_order="3",
                kds_enabled="on",
            )
        assert resp.status_code == 302
        assert ot.name_en == "Updated"
        assert ot.sort_order == 3
        assert ot.kds_enabled is True
        assert ot.is_active is True

    def test_toggle_flips_activity(self, pg_client):
        ot = _ot()
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=ot),
        ):
            resp = self._post(pg_client, action="toggle", ot_id="1")
        assert resp.status_code == 302
        assert ot.is_active is False

    def test_set_default_marks_single_row(self, pg_client):
        target = _ot(oid=2)
        others = [_ot(oid=1, is_default=True), target]
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=target),
            patch("routes.pos.PosOrderType.for_tenant", return_value=others),
        ):
            resp = self._post(pg_client, action="set_default", ot_id="2")
        assert resp.status_code == 302
        assert others[0].is_default is False
        assert target.is_default is True

    def test_delete_default_protected(self, pg_client):
        ot = _ot(is_default=True)
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=ot),
        ):
            resp = self._post(pg_client, action="delete", ot_id="1")
        assert resp.status_code == 302

    def test_delete_calls_service(self, pg_client):
        ot = _ot()
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=ot),
            patch("services.pos_write_service.PosWriteService.delete_order_type") as deleter,
        ):
            resp = self._post(pg_client, action="delete", ot_id="1")
        assert resp.status_code == 302
        deleter.assert_called_once_with(ot)

    def test_unknown_action_rejected(self, pg_client):
        with _pos_api_patches():
            resp = self._post(pg_client, action="explode")
        assert resp.status_code == 302


class TestPrinterSettings:
    def _post(self, client, **form):
        base = {
            "action": "create",
            "name": "Kitchen",
            "role": "kitchen",
            "connection_type": "agent_network",
        }
        base.update(form)
        return client.post("/pos/settings/printers", data=base)

    def test_get_renders(self, pg_client):
        printer = MagicMock(tenant_id=1, id=3)
        with (
            _pos_api_patches(),
            patch("routes.pos.PosPrinter.for_tenant", return_value=[printer]),
            patch("routes.pos.render_template", return_value="ok"),
        ):
            resp = pg_client.get("/pos/settings/printers")
        assert resp.status_code == 200

    def test_create_full_payload(self, pg_client):
        with (
            _pos_api_patches(),
            patch("services.pos_write_service.PosWriteService.create_printer") as create,
        ):
            resp = self._post(
                pg_client,
                host="127.0.0.1",
                port="9100",
                serial_port="COM3",
                baud_rate="9600",
                category_ids="1,2",
                sort_order="2",
                is_active="on",
            )
        assert resp.status_code == 302
        if create.call_args is not None:
            kwargs = create.call_args.kwargs
            assert kwargs["port"] == 9100
            assert kwargs["baud_rate"] == 9600
            assert kwargs["serial_port"] == "COM3"
            assert kwargs["category_ids"] == [1, 2]

    def test_create_missing_name(self, pg_client):
        with _pos_api_patches():
            resp = self._post(pg_client, name="")
        assert resp.status_code == 302

    def test_create_unknown_role(self, pg_client):
        with _pos_api_patches():
            resp = self._post(pg_client, role="teleporter")
        assert resp.status_code == 302

    def test_create_unknown_connection(self, pg_client):
        with _pos_api_patches():
            resp = self._post(pg_client, connection_type="smoke-signal")
        assert resp.status_code == 302

    def test_non_numeric_category_ids_abort_creation(self, pg_client):
        with (
            _pos_api_patches(),
            patch("services.pos_write_service.PosWriteService.create_printer") as create,
        ):
            resp = self._post(pg_client, category_ids="1,two")
        assert resp.status_code == 302
        create.assert_not_called()

    def test_edit_success(self, pg_client):
        printer = MagicMock(tenant_id=1, name="Old", category_ids=[1])
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=printer),
        ):
            resp = self._post(
                pg_client,
                action="edit",
                printer_id="3",
                name="Renamed",
                host="0.0.0.0",
                port="1234",
                encoding="utf-8",
                category_ids="7",
            )
        assert resp.status_code == 302
        assert printer.name == "Renamed"
        assert printer.category_ids == [7]
        assert printer.port == 1234
        assert printer.encoding == "utf-8"

    def test_edit_cross_tenant_rejected(self, pg_client):
        foreign = MagicMock(tenant_id=3)
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=foreign),
        ):
            resp = self._post(pg_client, action="edit", printer_id="3")
        assert resp.status_code == 302

    def test_toggle_flips_printer_state(self, pg_client):
        printer = MagicMock(tenant_id=1, is_active=True)
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=printer),
        ):
            resp = self._post(pg_client, action="toggle", printer_id="3")
        assert resp.status_code == 302
        assert printer.is_active is False

    def test_delete_calls_service(self, pg_client):
        printer = MagicMock(tenant_id=1)
        with (
            _pos_api_patches(),
            patch("routes.pos.db.session.get", return_value=printer),
            patch("services.pos_write_service.PosWriteService.delete_printer") as deleter,
        ):
            resp = self._post(pg_client, action="delete", printer_id="3")
        assert resp.status_code == 302
        deleter.assert_called_once_with(printer)


# ═══════════════════════ Catalog API gaps ═══════════════════════


class TestCatalogApiGaps:
    def test_categories_lists_active_sorted(self, pg_client):
        cat = SimpleNamespace(id=4, name="Drinks", name_ar="مشروبات")
        cats_q = MagicMock()
        cats_q.filter_by.return_value.order_by.return_value.all.return_value = [cat]
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_query", return_value=cats_q),
        ):
            resp = pg_client.get("/pos/api/categories")
        assert resp.status_code == 200
        assert resp.get_json()["data"][0]["id"] == 4

    def test_products_endpoint_surfaces_500_on_service_failure(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.search_pos_products", side_effect=RuntimeError("db down")),
        ):
            resp = pg_client.get("/pos/api/products?q=x")
        assert resp.status_code == 500

    def test_empty_grid_falls_back_to_tenant_catalog(self, pg_client):
        prod = _fake_product(21)
        prod_q = _catalog_query([prod])
        with (
            _pos_api_patches(search_result=([], {}, [])),
            patch(
                "routes.pos.tenant_query",
                side_effect=lambda model, *a, **kw: prod_q if model.__name__ == "Product" else prod_q,
            ),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[3]),
            patch("utils.branching.get_branch_stock_map", return_value={21: 4}),
        ):
            resp = pg_client.get("/pos/api/products?per_page=200")
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) == 1

    def test_fallback_stock_map_failure_is_swallowed(self, pg_client):
        prod = _fake_product(22)
        prod_q = _catalog_query([prod])
        with (
            _pos_api_patches(search_result=([], {}, [])),
            patch("routes.pos.tenant_query", return_value=prod_q),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[3]),
            patch("utils.branching.get_branch_stock_map", side_effect=RuntimeError("stock down")),
        ):
            resp = pg_client.get("/pos/api/products")
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) == 1

    def test_fallback_query_failure_is_swallowed(self, pg_client):
        with (
            _pos_api_patches(search_result=([], {}, [])),
            patch("routes.pos.tenant_query", side_effect=RuntimeError("catalog unavailable")),
        ):
            resp = pg_client.get("/pos/api/products")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == []

    def test_product_lookup_requires_code(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.get("/pos/api/product")
        assert resp.status_code == 400

    def test_product_lookup_miss_is_404(self, pg_client):
        with _pos_api_patches(lookup_result=(None, {})):
            resp = pg_client.get("/pos/api/product?code=NOPE")
        assert resp.status_code == 404

    def test_product_lookup_happy_path_with_scale_barcode(self, pg_client):
        product = _fake_product(1)
        with (
            _pos_api_patches(lookup_result=(product, {1: 3})),
            patch("routes.pos.parse_scale_barcode", return_value={"weight_kg": 1.25}),
        ):
            resp = pg_client.get("/pos/api/product?barcode=21x")
        payload = resp.get_json()["data"]
        assert resp.status_code == 200
        assert payload["is_scale_item"] is True
        assert payload["scale_weight_kg"] == pytest.approx(1.25)

    def test_product_lookup_warns_on_inactive_product(self, pg_client):
        inactive = _fake_product(1, active=False)
        with _pos_api_patches(lookup_result=(inactive, {1: 3})):
            resp = pg_client.get("/pos/api/product?code=OLD")
        assert resp.get_json()["data"].get("warning")

    def test_product_lookup_warns_when_out_of_stock(self, pg_client):
        oos = _fake_product(2)
        with (
            _pos_api_patches(lookup_result=(oos, {2: 0})),
            patch(
                "routes.pos.serialize_pos_product",
                side_effect=lambda p, sm, **kw: {"id": p.id, "is_out_of_stock": True},
            ),
        ):
            resp = pg_client.get("/pos/api/product?code=EMPTY")
        assert resp.get_json()["data"].get("warning")

    def test_snapshot_serializes_products(self, pg_client):
        prod = _fake_product(31)
        with (
            _pos_api_patches(),
            patch("routes.pos.snapshot_pos_products", return_value=([prod], {31: 2})),
        ):
            resp = pg_client.get("/pos/api/catalog/snapshot?warehouse_id=3")
        body = resp.get_json()["data"]
        assert resp.status_code == 200
        assert body["count"] == 1


# ═══════════════════════ Checkout handlers ═══════════════════════


class TestCheckoutErrorHandlers:
    def _post(self, client, payload=None, key=None):
        headers = {"Idempotency-Key": key} if key else {}
        return client.post("/pos/api/checkout", json=payload or {}, headers=headers)

    def test_shiftless_register_is_rejected_when_shifts_allowed(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=None),
            patch("routes.pos._pos_feature_denied", return_value=None),
        ):
            resp = self._post(pg_client)
        assert resp.status_code == 403

    def test_checkout_override_error_maps_to_403(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=MagicMock()),
            patch("routes.pos.PosCheckoutService.checkout", side_effect=PosOverrideError("pin")),
        ):
            resp = self._post(pg_client)
        assert resp.status_code == 403

    def test_plan_limit_surfaces_meta_code(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=MagicMock()),
            patch("routes.pos.PosCheckoutService.checkout", side_effect=TenantLimitError("sales", 50, 50)),
        ):
            resp = self._post(pg_client)
        assert resp.status_code == 403
        assert resp.get_json()["meta"]["code"] == "PLAN_LIMIT"

    @pytest.mark.parametrize("use_key,expected_status", [(True, 409), (False, 500)])
    def test_integrity_conflicts(self, pg_client, use_key, expected_status):
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=MagicMock()),
            patch("routes.pos.IdempotencyService.begin", return_value=(MagicMock(), None)),
            patch(
                "routes.pos.PosCheckoutService.checkout",
                side_effect=IntegrityError("dup", None, Exception()),
            ),
        ):
            resp = self._post(pg_client, key="dup-key" if use_key else None)
        assert resp.status_code == expected_status


# ═══════════════════════ Promotions preview extras ═══════════════════════


class TestPromotionsEvaluateGaps:
    def test_malformed_json_body_is_400(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post(
                "/pos/api/promotions/evaluate",
                data="{not json",
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_unit_price_override_is_quantized(self, pg_client):
        inactive_customer = MagicMock(is_active=False, customer_type="wholesale")
        merged = [{"product_id": 1, "quantity": Decimal("2"), "discount_percent": Decimal("0"), "unit_price": "1.005"}]
        product = MagicMock(id=1, is_active=True, category_id=None)
        evaluation = {"tiers": [], "rules": []}
        with (
            _pos_api_patches(merged_lines=merged),
            patch("routes.pos.merge_checkout_lines", return_value=merged),
            patch("routes.pos.tenant_get", return_value=inactive_customer),
            patch("routes.pos.PromotionService.evaluate_cart", return_value=evaluation) as evaluate,
            patch("services.pos_write_service.PosWriteService.products_by_ids", return_value={1: product}),
            patch("routes.pos._promotion_evaluation_json", return_value={"ok": True}) as ser,
        ):
            resp = pg_client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": merged, "customer_id": "8"},
            )
        assert resp.status_code == 200
        cart = evaluate.call_args.args[0]
        assert cart[0]["unit_price"] == Decimal("1.005")
        ser.assert_called_once_with(evaluation)

    def test_merge_validation_error_maps_to_400(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.merge_checkout_lines", side_effect=ValueError("bad line")),
        ):
            resp = pg_client.post("/pos/api/promotions/evaluate", json={"lines": [{"bogus": 1}]})
        assert resp.status_code == 400

    def test_unknown_product_in_cart_rejected(self, pg_client):
        merged = [{"product_id": 77, "quantity": 1, "discount_percent": 0, "unit_price": None}]
        with (
            _pos_api_patches(merged_lines=merged),
            patch("services.pos_write_service.PosWriteService.products_by_ids", return_value={}),
        ):
            resp = pg_client.post("/pos/api/promotions/evaluate", json={"lines": merged})
        assert resp.status_code == 400

    def test_promotion_engine_validation_error_is_400(self, pg_client):
        merged = [{"product_id": 1, "quantity": 1, "discount_percent": 0, "unit_price": None}]
        product = MagicMock(id=1, is_active=True, category_id=None, regular_price=Decimal("10"))
        with (
            _pos_api_patches(merged_lines=merged),
            patch("services.pos_write_service.PosWriteService.products_by_ids", return_value={1: product}),
            patch("routes.pos.PromotionService.evaluate_cart", side_effect=ValueError("bad rule")),
            patch("routes.pos._pos_standard_price", return_value=Decimal("10")),
        ):
            resp = pg_client.post("/pos/api/promotions/evaluate", json={"lines": merged})
        assert resp.status_code == 400


# ═══════════════════════ Parked carts guard ═══════════════════════


class TestParkPayloadGuard:
    def test_malformed_json_body_is_400(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/carts/park", data="{oops", content_type="application/json")
        assert resp.status_code == 400


# ═══════════════════════ Session lifecycle idempotency ═══════════════════════


class TestSessionOpenIdempotency:
    def _headers(self, key=None):
        h = {}
        if key:
            h["Idempotency-Key"] = key
        return h

    def test_missing_branch_falls_back_to_tenant_main_branch(self, pg_client):
        main_branch = MagicMock(id=17)
        new_session = _mock_session()
        with (
            _pos_api_patches(session=None, new_session=new_session),
            patch("routes.pos.get_active_branch_id", return_value=None),
            patch("models.Branch.query") as bq,
        ):
            bq.filter_by.return_value.first.return_value = main_branch
            resp = pg_client.post("/pos/api/session/open", json={}, headers=self._headers())
        assert resp.status_code == 201
        assert resp.get_json()["data"]["session"]["id"] == new_session.id

    def test_open_without_any_branch_is_400(self, pg_client):
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.get_active_branch_id", return_value=None),
            patch("models.Branch.query") as bq,
        ):
            bq.filter_by.return_value.first.return_value = None
            resp = pg_client.post("/pos/api/session/open", json={}, headers=self._headers())
        assert resp.status_code == 400

    def test_inflight_duplicate_key_conflicts_409(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.IdempotencyService.begin", side_effect=IdempotencyInFlightError),
        ):
            resp = pg_client.post("/pos/api/session/open", json={}, headers=self._headers("k1"))
        assert resp.status_code == 409

    def test_hash_mismatch_key_is_422(self, pg_client):
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.IdempotencyService.begin", side_effect=IdempotencyHashMismatchError),
        ):
            resp = pg_client.post("/pos/api/session/open", json={}, headers=self._headers("k2"))
        assert resp.status_code == 422

    def test_completed_key_replays_stored_response(self, pg_client):
        stored = ({"success": True, "session": {"id": 55}}, 201)
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.IdempotencyService.begin", return_value=(None, stored)),
        ):
            resp = pg_client.post("/pos/api/session/open", json={}, headers=self._headers("k3"))
        assert resp.status_code == 201
        assert resp.get_json()["meta"]["idempotent_replay"] is True
        assert resp.get_json()["data"]["session"]["id"] == 55

    def test_terminal_session_issues_security_token(self, pg_client):
        new_session = _mock_session()
        new_session.terminal_id = "T-9"
        with (
            _pos_api_patches(session=None, new_session=new_session),
            patch("routes.pos.issue_pos_session_token", return_value="tok-xyz") as issue,
        ):
            resp = pg_client.post("/pos/api/session/open", json={}, headers=self._headers())
        assert resp.get_json()["data"]["session_token"] == "tok-xyz"
        issue.assert_called_once()


class TestSessionResumeAndClose:
    def test_resume_with_terminal_requires_valid_token(self, pg_client):
        paused = _mock_session()
        paused.terminal_id = "T-1"
        with _pos_api_patches(paused_session=paused, session=None):
            resp = pg_client.post("/pos/api/session/resume", json={})
        assert resp.status_code == 403

    def test_resume_invalid_transition_is_400(self, pg_client):
        paused = _mock_session()
        paused.resume.side_effect = ValueError("already resumed")
        with _pos_api_patches(paused_session=paused, session=None):
            resp = pg_client.post("/pos/api/session/resume", json={})
        assert resp.status_code == 400

    def test_resume_terminal_session_reissues_token(self, pg_client):
        paused = _mock_session()
        paused.terminal_id = "T-2"
        with (
            _pos_api_patches(paused_session=paused, session=None),
            patch("routes.pos.verify_pos_session_token", return_value=True),
            patch("routes.pos.issue_pos_session_token", return_value="tok-resumed"),
        ):
            resp = pg_client.post("/pos/api/session/resume", json={"session_token": "valid"})
        assert resp.get_json()["data"]["session_token"] == "tok-resumed"

    def test_close_requires_counted_cash(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/session/close", json={"notes": "x"})
        assert resp.status_code == 400

    def test_close_rejects_garbage_amount(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/session/close", json={"counted_cash": "1.2.3"})
        assert resp.status_code == 400

    def test_close_replays_completed_key_before_guard(self, pg_client):
        stored = ({"success": True, "session": {"id": 11}}, 200)
        with (
            _pos_api_patches(session=None),
            patch("routes.pos.IdempotencyService.replay_if_completed", return_value=stored) as replay,
        ):
            resp = pg_client.post(
                "/pos/api/session/close",
                json={"counted_cash": "100"},
                headers={"Idempotency-Key": "ck"},
            )
        assert resp.status_code == 200
        replay.assert_called_once()

    def test_close_key_inflight_conflicts_before_guard(self, pg_client):
        with (
            _pos_api_patches(session=None),
            patch(
                "routes.pos.IdempotencyService.replay_if_completed",
                side_effect=IdempotencyInFlightError,
            ),
        ):
            resp = pg_client.post(
                "/pos/api/session/close",
                json={"counted_cash": "100"},
                headers={"Idempotency-Key": "ck2"},
            )
        assert resp.status_code == 409

    def test_close_key_mismatch_conflicts_before_guard(self, pg_client):
        with (
            _pos_api_patches(session=None),
            patch(
                "routes.pos.IdempotencyService.replay_if_completed",
                side_effect=IdempotencyHashMismatchError,
            ),
        ):
            resp = pg_client.post(
                "/pos/api/session/close",
                json={"counted_cash": "100"},
                headers={"Idempotency-Key": "ck3"},
            )
        assert resp.status_code == 422

    def test_close_idempotent_success_completes_record(self, pg_client):
        session = _mock_session()
        record = MagicMock()
        with (
            _pos_api_patches(session=session),
            patch("routes.pos.IdempotencyService.replay_if_completed", return_value=None),
            patch("routes.pos.IdempotencyService.begin", return_value=(record, None)) as begin,
            patch("routes.pos.IdempotencyService.complete") as complete,
        ):
            resp = pg_client.post(
                "/pos/api/session/close",
                json={"counted_cash": "150"},
                headers={"Idempotency-Key": "ck4"},
            )
        assert resp.status_code == 200
        begin.assert_called_once()
        complete.assert_called_once_with(record, complete.call_args.args[1], 200)


# ═══════════════════════ Shifts ═══════════════════════


class TestShiftLifecycle:
    def test_open_requires_json_content_type(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/shift/open", data="{}", content_type="text/plain")
        assert resp.status_code == 415

    def test_open_requires_open_session(self, pg_client):
        with (
            _pos_api_patches(session=None),
            patch("routes.pos._get_active_shift", return_value=None),
        ):
            resp = pg_client.post("/pos/api/shift/open", json={})
        assert resp.status_code == 403

    def test_open_rejects_second_concurrent_shift(self, pg_client):
        existing = MagicMock(shift_number="SHF-0")
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=existing),
        ):
            resp = pg_client.post("/pos/api/shift/open", json={})
        assert resp.status_code == 409

    def test_open_success_creates_numbered_shift(self, pg_client):
        created = MagicMock(status="open")
        created.to_dict.return_value = {"shift_number": "SHF-0007"}
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=None),
            patch.object(PosSessionService, "create_shift", return_value=created),
            patch("routes.pos.generate_number", return_value="SHF-0007"),
        ):
            resp = pg_client.post("/pos/api/shift/open", json={"starting_cash": "250"})
        assert resp.status_code == 201
        assert created.shift_number == "SHF-0007"

    def test_open_failure_maps_to_400(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=None),
            patch.object(PosSessionService, "create_shift", side_effect=ValueError("overdrawn")),
        ):
            resp = pg_client.post("/pos/api/shift/open", json={})
        assert resp.status_code == 400

    def test_reconcile_requires_actual_cash(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/shift/reconcile", json={"notes": "x"})
        assert resp.status_code == 400

    def test_reconcile_rejects_bad_decimal(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/shift/reconcile", json={"actual_cash": "nan-ish"})
        assert resp.status_code == 400

    def test_reconcile_without_shift_is_404(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=None),
        ):
            resp = pg_client.post("/pos/api/shift/reconcile", json={"actual_cash": "300"})
        assert resp.status_code == 404

    def test_reconcile_accumulates_totals_then_reconciles(self, pg_client):
        shift = MagicMock(status="open", total_change_given=Decimal("5"))
        shift.session_id = 11
        shift.tenant_id = 1
        cash_sale = MagicMock(total_amount=Decimal("100"))
        cash_payment = MagicMock(payment_method="cash")
        card_sale = MagicMock(total_amount=Decimal("40"))
        card_payment = MagicMock(payment_method="e_wallet")
        cash_sale.payments = [cash_payment]
        card_sale.payments = [card_payment]
        shift.to_dict.return_value = {"difference": "0"}
        pay_in = MagicMock(amount=Decimal("20"), movement_type="pay_in")

        def _base_amount(payment, **kw):
            return Decimal("100") if payment is cash_payment else Decimal("40")

        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=shift),
            patch("services.pos_write_service.PosWriteService.session_sales", return_value=[cash_sale, card_sale]),
            patch("services.pos_write_service.PosWriteService.shift_cash_movements", return_value=[pay_in]),
            patch("routes.pos.payment_amount_base", side_effect=_base_amount),
        ):
            resp = pg_client.post("/pos/api/shift/reconcile", json={"actual_cash": "125", "notes": "ok"})
        assert resp.status_code == 200
        assert shift.total_sales == Decimal("140")
        assert shift.total_cash_sales == Decimal("105")
        assert shift.total_card_sales == Decimal("40")
        assert shift.total_pay_ins == Decimal("20")
        assert shift.total_pay_outs == Decimal("0")
        shift.reconcile.assert_called_once_with(Decimal("125"), "ok")

    def test_close_before_reconcile_rejected(self, pg_client):
        shift = MagicMock(status="open")
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=shift),
        ):
            resp = pg_client.post("/pos/api/shift/close", json={})
        assert resp.status_code == 400

    def test_close_success(self, pg_client):
        shift = MagicMock(status="reconciled")
        shift.to_dict.return_value = {"status": "closed"}
        with (
            _pos_api_patches(),
            patch("routes.pos._get_active_shift", return_value=shift),
        ):
            resp = pg_client.post("/pos/api/shift/close", json={})
        assert resp.status_code == 200
        shift.close.assert_called_once()


# ═══════════════════════ Drawer / PIN / movements / void-line ═══════════════════════


class TestOverridePinEndpoint:
    def test_authorize_rejects_malformed_body(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post(
                "/pos/api/authorize-override",
                data="{bad",
                content_type="application/json",
            )
        assert resp.status_code == 400


class TestSupervisorPin:
    def test_set_requires_json(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/supervisor-pin", data="{}", content_type="text/plain")
        assert resp.status_code == 415

    def test_set_rejects_non_numeric_pin(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/supervisor-pin", json={"pin": "12ab"})
        assert resp.status_code == 400


class TestDrawerOpenGuards:
    def test_drawer_without_session_is_403(self, pg_client):
        with _pos_api_patches(session=None):
            resp = pg_client.post("/pos/api/drawer/open", json={})
        assert resp.status_code == 403

    def test_drawer_paused_session_returns_409(self, pg_client):
        with _pos_api_patches(session=None, paused_session=_mock_session()):
            resp = pg_client.post("/pos/api/drawer/open", json={})
        assert resp.status_code == 409

    def test_drawer_terminal_session_needs_token(self, pg_client):
        session = _mock_session()
        session.terminal_id = "T-3"
        with _pos_api_patches(session=session):
            resp = pg_client.post("/pos/api/drawer/open", json={"reason": "jam"})
        assert resp.status_code == 403


class TestCashMovementsEndpoints:
    def test_list_feature_denied(self, pg_client):
        tenant = MagicMock(enable_pos=True, enable_pos_shifts=False)
        with _pos_api_patches(tenant=tenant):
            resp = pg_client.get("/pos/api/cash-movements")
        assert resp.status_code == 403

    def test_list_foreign_session_hidden_from_cashiers(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos._can_view_expected", return_value=False),
        ):
            resp = pg_client.get("/pos/api/cash-movements?session_id=999")
        assert resp.status_code == 403

    def test_list_unknown_session_is_404_for_managers(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos._can_view_expected", return_value=True),
            patch("routes.pos.tenant_get", return_value=None),
        ):
            resp = pg_client.get("/pos/api/cash-movements?session_id=999")
        assert resp.status_code == 404

    def test_list_returns_empty_without_active_session(self, pg_client):
        with _pos_api_patches(session=None):
            resp = pg_client.get("/pos/api/cash-movements")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == {"movements": []}

    def test_create_movement_requires_valid_json(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post(
                "/pos/api/cash-movements",
                data="{nope",
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_create_paused_session_blocks_movement(self, pg_client):
        with _pos_api_patches(session=None, paused_session=_mock_session()):
            resp = pg_client.post("/pos/api/cash-movements", json={"type": "pay_in", "amount": "10"})
        assert resp.status_code == 409

    def test_create_terminal_movement_requires_token(self, pg_client):
        session = _mock_session()
        session.terminal_id = "T-4"
        with _pos_api_patches(session=session):
            resp = pg_client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_out", "amount": "5"},
            )
        assert resp.status_code == 403


class TestVoidLineGuards:
    def test_malformed_body_rejected(self, pg_client):
        with _pos_api_patches(session=_mock_session()):
            resp = pg_client.post(
                "/pos/api/carts/5/void-line",
                data="{zz",
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_paused_session_blocks_void(self, pg_client):
        with _pos_api_patches(session=None, paused_session=_mock_session()):
            resp = pg_client.post("/pos/api/carts/5/void-line", json={"product_id": 1})
        assert resp.status_code == 409

    def test_void_requires_open_session(self, pg_client):
        with _pos_api_patches(session=None):
            resp = pg_client.post("/pos/api/carts/5/void-line", json={"product_id": 1})
        assert resp.status_code == 403

    def test_void_terminal_session_requires_token(self, pg_client):
        session = _mock_session()
        session.terminal_id = "T-5"
        with _pos_api_patches(session=session):
            resp = pg_client.post("/pos/api/carts/5/void-line", json={"product_id": 1})
        assert resp.status_code == 403

    @pytest.mark.parametrize("payload", [{"product_id": "abc"}, {"product_id": "0"}])
    def test_invalid_product_ids(self, pg_client, payload):
        session = _mock_session()
        with (
            _pos_api_patches(session=session),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=77),
        ):
            resp = pg_client.post("/pos/api/carts/5/void-line", json=payload)
        assert resp.status_code == 400

    def test_void_conflict_maps_to_409(self, pg_client):
        session = _mock_session()
        with (
            _pos_api_patches(session=session),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=77),
            patch("routes.pos.PosCartService.void_line", side_effect=PosCartConflictError("changed")),
        ):
            resp = pg_client.post("/pos/api/carts/5/void-line", json={"product_id": 3})
        assert resp.status_code == 409

    def test_void_valueerror_maps_to_400(self, pg_client):
        session = _mock_session()
        with (
            _pos_api_patches(session=session),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=77),
            patch("routes.pos.PosCartService.void_line", side_effect=ValueError("empty cart")),
        ):
            resp = pg_client.post("/pos/api/carts/5/void-line", json={"product_id": 3})
        assert resp.status_code == 400


# ═══════════════════════ Receipt lookup + smart RMA ═══════════════════════


class TestReceiptLookupAndReturns:
    def test_receipt_lookup_invalid_number_is_400(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.lookup_receipt", side_effect=ValueError("blank")),
        ):
            resp = pg_client.get("/pos/api/receipts/lookup?number=%20")
        assert resp.status_code == 400

    def test_return_create_requires_json(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/returns", data="{}", content_type="text/plain")
        assert resp.status_code == 415

    def test_return_create_rejects_malformed_body(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.post("/pos/api/returns", data="{!!", content_type="application/json")
        assert resp.status_code == 400

    def test_return_create_blocked_while_paused(self, pg_client):
        with _pos_api_patches(session=None, paused_session=_mock_session()):
            resp = pg_client.post("/pos/api/returns", json={"lines": [{"x": 1}], "sale_id": 3})
        assert resp.status_code == 409

    def test_return_create_terminal_needs_token(self, pg_client):
        session = _mock_session()
        session.terminal_id = "T-6"
        with _pos_api_patches(session=session):
            resp = pg_client.post("/pos/api/returns", json={"lines": [{"x": 1}], "sale_id": 3})
        assert resp.status_code == 403

    def test_return_create_inflight_key_maps_to_409(self, pg_client):
        denied = error_response(message="in-flight", status_code=409)
        with (
            _pos_api_patches(),
            patch("routes.pos._idempotent_begin", return_value=(None, None, denied)),
        ):
            resp = pg_client.post(
                "/pos/api/returns",
                json={"lines": [{"product_id": 1}], "sale_id": 3, "idempotency_key": "r1"},
            )
        assert resp.status_code == 409

    @pytest.mark.parametrize("use_key,expected_status", [(True, 409), (False, 500)])
    def test_return_integrity_failures(self, pg_client, use_key, expected_status):
        headers = {"Idempotency-Key": "r8"} if use_key else {}
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.resolve_sale_id", return_value=3),
            patch("routes.pos.IdempotencyService.begin", return_value=(MagicMock(), None)),
            patch(
                "routes.pos.PosRmaService.create_pos_return",
                side_effect=IntegrityError("dup", None, Exception()),
            ),
        ):
            resp = pg_client.post(
                "/pos/api/returns",
                json={"lines": [{"product_id": 1}], "sale_id": 3},
                headers=headers,
            )
        assert resp.status_code == expected_status

    def test_return_unexpected_error_is_sanitized_500(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.resolve_sale_id", return_value=3),
            patch("routes.pos.PosRmaService.create_pos_return", side_effect=RuntimeError("boom")),
        ):
            resp = pg_client.post("/pos/api/returns", json={"lines": [{"product_id": 1}], "sale_id": 3})
        assert resp.status_code == 500

    def test_successful_cash_return_reports_refund_payment(self, pg_client):
        ret = MagicMock(return_number="RTN-2", currency="AED", exchange_rate=1)
        ret.refund_amount = Decimal("33.5")
        ret.amount_aed = Decimal("33.5")
        ret.id = 12
        refund_payment = MagicMock(payment_number="PAY-77")
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.resolve_sale_id", return_value=3),
            patch(
                "routes.pos.PosRmaService.create_pos_return",
                return_value=(ret, refund_payment),
            ) as create_ret,
        ):
            resp = pg_client.post(
                "/pos/api/returns",
                json={"lines": [{"product_id": 1}], "sale_id": 3, "refund_method": "cash"},
            )
        assert resp.status_code == 201
        body = resp.get_json()["data"]
        assert body["return_number"] == "RTN-2"
        assert body["refund_payment_number"] == "PAY-77"
        assert create_ret.call_args.kwargs["refund_method"] == "cash"


# ═══════════════════════ Stock lookup edge cases ═══════════════════════


class TestStockLookupEdgeCases:
    def test_missing_identifier_rejected(self, pg_client):
        with _pos_api_patches():
            resp = pg_client.get("/pos/api/stock/lookup")
        assert resp.status_code == 400

    def test_service_type_error_is_400(self, pg_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.PosRmaService.stock_breakdown", side_effect=TypeError),
        ):
            resp = pg_client.get("/pos/api/stock/lookup?product_id=oops")
        assert resp.status_code == 400


# ═══════════════════════ Thermal receipt + print tickets ═══════════════════════


def _dispatch_tenant_get(objects):
    def _tg(model, pk, *a, **kw):
        return objects.get(model.__name__)

    return _tg


class TestThermalReceiptAndTickets:
    def test_renders_receipt_with_table_label(self, pg_client):
        sale = MagicMock(order_type="dine_in", table_id=4)
        table = MagicMock(label="T4")
        with (
            _pos_api_patches(tenant_get=_dispatch_tenant_get({"Sale": sale, "PosTable": table})),
            patch("models.pos_order_type.PosOrderType.get_by_code", return_value=None),
            patch("routes.pos.render_template", return_value="receipt-html") as render,
        ):
            resp = pg_client.get("/pos/receipt/101")
        assert resp.status_code == 200
        assert render.call_args.kwargs["table_label"] == "T4"
        assert render.call_args.kwargs["order_type_label"] == "dine_in"

    def test_missing_sale_aborts_404(self, pg_client):
        with _pos_api_patches(tenant_get=_dispatch_tenant_get({})):
            resp = pg_client.get("/pos/receipt/404")
        assert resp.status_code == 404

    def test_print_tickets_empty_registry_yields_no_tickets(self, pg_client):
        sale = MagicMock(order_type=None, table_id=None)
        sale.tenant_id = 1
        with (
            _pos_api_patches(tenant_get=_dispatch_tenant_get({"Sale": sale})),
            patch("models.PosPrinter.for_tenant", return_value=[]),
        ):
            resp = pg_client.get("/pos/api/sale/101/print-tickets")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["tickets"] == []

    def test_print_tickets_builds_per_printer_payloads(self, pg_client):
        sale = MagicMock(order_type=None, table_id=None)
        sale.tenant_id = 1
        printers = [MagicMock(), MagicMock()]
        with (
            _pos_api_patches(tenant_get=_dispatch_tenant_get({"Sale": sale})),
            patch("models.PosPrinter.for_tenant", return_value=printers),
            patch(
                "routes.pos.build_print_tickets",
                return_value=[{"printer": "kitchen"}],
            ) as builder,
        ):
            resp = pg_client.get("/pos/api/sale/101/print-tickets")
        assert resp.get_json()["data"]["tickets"] == [{"printer": "kitchen"}]
        builder.assert_called_once_with(sale, printers)
