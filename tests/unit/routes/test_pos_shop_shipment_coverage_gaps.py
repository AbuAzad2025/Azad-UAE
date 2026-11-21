"""Coverage-gap tests for routes/pos.py, shop.py, shipments.py and payment_vault.py.

Each test targets a specific miss reported by the combined coverage run. The
tests stay at the route boundary: services / DB / template boundaries are
mocked, and the real route functions are exercised through a Flask test
client (or, for generator helpers, by driving the generator directly).
"""

from __future__ import annotations

import queue as _queue
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from tests.unit.routes.test_pos_v2_routes import _pos_api_patches

SLUG = "demo-store"
BASE = f"/s/{SLUG}"


@contextmanager
def _noop_txn(*args, **kwargs):
    yield


def _account(aid=5, customer_id=20):
    a = MagicMock()
    a.id = aid
    a.customer_id = customer_id
    a.name = "Shop User"
    a.email = "shop@test.com"
    a.phone = "+9715"
    a.address = "Dubai"
    return a


# ─────────────────────────────────────────────────────────────────────────────
# routes/shipments.py
# ─────────────────────────────────────────────────────────────────────────────


class TestShipmentCoverageGaps:
    @pytest.fixture
    def client(self, app_factory, bypass_permission_auth):
        from routes.shipments import shipment_bp

        app = app_factory(shipment_bp)
        return app.test_client()

    def test_tenant_id_exception_returns_none(self):
        """Line 27-28: _tenant_id() swallows a resolver exception."""
        from routes.shipments import _tenant_id

        with patch("routes.shipments.get_active_tenant_id", side_effect=RuntimeError("resolver down")):
            assert _tenant_id() is None

    @pytest.mark.parametrize(
        "url",
        ["/shipments", "/shipments/create", "/shipments/api/warehouses", "/shipments/api/products"],
    )
    def test_no_tenant_aborts_403(self, client, url):
        """Lines 37-39, 131-133, 234-236, 252-254: every tenant gate aborts."""
        with patch("routes.shipments._tenant_id", return_value=None):
            resp = client.get(url)
        assert resp.status_code == 403

    def test_view_without_shipment_id_attribute(self, client):
        """Branch 57->66: a Sale model without shipment_id skips the query."""
        s = MagicMock(id=7, tenant_id=1)

        class _LegacySale:
            pass

        with (
            patch("models.sale.Sale", _LegacySale),
            patch("routes.shipments.tenant_get_or_404", return_value=s),
            patch("routes.shipments.render_template", return_value="ok") as render,
        ):
            resp = client.get("/shipments/7")
        assert resp.status_code == 200
        assert render.call_args[1]["sales"] == []

    def test_create_line_with_zero_quantity_is_skipped(self, client):
        """Branch 84->86: a line with qty=0 is not appended."""
        with (
            patch("routes.shipments.flash") as flash,
            patch("routes.shipments.ShipmentService.create_field_shipment") as create,
        ):
            resp = client.post(
                "/shipments/create",
                data={"lines[0][product_id]": "5", "lines[0][quantity]": "0"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        create.assert_not_called()
        flash.assert_called()

    def test_create_audit_failure_is_tolerated(self, client):
        """Lines 114-117: a failing audit log must not fail the shipment."""
        created = MagicMock(id=9, shipment_number="SH-9")
        with (
            patch("routes.shipments.get_active_tenant_id", return_value=1),
            patch("routes.shipments.ShipmentService.create_field_shipment", return_value=created),
            patch("routes.shipments.atomic_transaction", _noop_txn),
            patch("services.logging_core.LoggingCore.log_audit", side_effect=RuntimeError("audit down")),
            patch("routes.shipments.flash"),
        ):
            resp = client.post(
                "/shipments/create",
                data={"lines[0][product_id]": "5", "lines[0][quantity]": "2", "lines[0][unit_price]": "3"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    @pytest.mark.parametrize(
        ("result", "flash_contains"),
        [
            ({"success": True}, "updated"),
            ({"success": False, "error": "carrier timeout"}, "carrier timeout"),
            ({"success": False}, "Could not update"),
        ],
    )
    def test_sync_tracking_branches(self, client, result, flash_contains):
        """Lines 183-194: the whole sync-tracking route, both result branches."""
        with (
            patch("routes.shipments.tenant_get_or_404", return_value=MagicMock(id=4)),
            patch("routes.shipments.get_active_tenant_id", return_value=1),
            patch("routes.shipments.atomic_transaction", _noop_txn),
            patch("services.carrier_tracking_service.CarrierTrackingService.sync_shipment", return_value=result),
            patch("routes.shipments.flash") as flash,
        ):
            resp = client.post("/shipments/4/sync-tracking", follow_redirects=False)
        assert resp.status_code == 302
        assert flash_contains in str(flash.call_args[0][0])

    def test_sync_tracking_exception_is_flashed(self, client):
        """Lines 195-196: a carrier exception becomes a danger flash."""
        with (
            patch("routes.shipments.tenant_get_or_404", return_value=MagicMock(id=4)),
            patch("routes.shipments.get_active_tenant_id", return_value=1),
            patch("routes.shipments.atomic_transaction", _noop_txn),
            patch(
                "services.carrier_tracking_service.CarrierTrackingService.sync_shipment",
                side_effect=RuntimeError("carrier offline"),
            ),
            patch("routes.shipments.flash") as flash,
        ):
            resp = client.post("/shipments/4/sync-tracking", follow_redirects=False)
        assert resp.status_code == 302
        flash.assert_called_once()
        assert flash.call_args[0][1] == "danger"


# ─────────────────────────────────────────────────────────────────────────────
# routes/pos.py
# ─────────────────────────────────────────────────────────────────────────────


class TestPosCoverageGaps:
    @pytest.fixture
    def client(self, app_factory, bypass_permission_auth):
        from routes.pos import pos_bp

        app = app_factory(pos_bp)
        return app.test_client()

    def test_closable_session_falls_back_to_paused(self, mock_user):
        """Lines 275-276: ValueError falls back to the paused-session lock."""
        from routes.pos import _get_closable_session_locked

        paused = MagicMock(id=3)
        with (
            patch("routes.pos.get_active_session_locked", side_effect=ValueError("no open session")),
            patch("routes.pos.get_paused_session_locked", return_value=paused) as get_paused,
        ):
            assert _get_closable_session_locked(mock_user) is paused
        get_paused.assert_called_once_with(mock_user)

    @pytest.mark.parametrize("tid", [0, 1])
    def test_register_context_invoice_preview_guards(self, tid):
        """Branch 309->315 and lines 312-314: missing sequence never blocks."""
        from routes.pos import _pos_register_context

        tenant = MagicMock(name_ar="متجر", name="Store")
        with (
            patch("routes.pos.get_accessible_warehouses", return_value=[]),
            patch("routes.pos.Tenant.get_current", return_value=tenant),
            patch("utils.currency_utils.resolve_default_currency", return_value="AED"),
            patch("utils.currency_utils.get_currency_symbol", return_value="د.إ"),
            patch("utils.tax_settings.get_prices_include_vat", return_value=True),
            patch("services.industry_service.get_pos_profile", return_value={}),
            patch("routes.pos.get_active_branch_id", return_value=2),
            patch("utils.branching.get_active_branch", return_value=None),
            patch("routes.pos.get_active_tenant_id", return_value=tid),
            patch(
                "services.document_sequence_service.DocumentSequenceService.preview",
                side_effect=RuntimeError("no sequence row"),
            ),
            patch("routes.pos.current_app") as app,
        ):
            ctx = _pos_register_context()
        assert ctx["branch_name"] == "متجر"
        assert ctx["invoice_preview"] == ""
        if tid:
            app.logger.debug.assert_called()

    def test_quick_customer_create_failure(self, client):
        """Lines 768-770: a service failure is a 400, never a 500."""
        with (
            _pos_api_patches(),
            patch("routes.pos.atomic_transaction", _noop_txn),
            patch(
                "services.customer_service.CustomerService.create_customer",
                side_effect=RuntimeError("create failed"),
            ),
        ):
            resp = client.post("/pos/api/customers/create", json={"name": "New Customer"})
        assert resp.status_code == 400

    def test_stock_summary_failure(self, client):
        """Lines 793-795: a stock-service failure is a 400."""
        with (
            _pos_api_patches(),
            patch(
                "services.stock_service.StockService.get_low_stock_products",
                side_effect=RuntimeError("stock down"),
            ),
        ):
            resp = client.get("/pos/api/stock/summary")
        assert resp.status_code == 400

    def test_checkout_session_lost_inside_transaction(self, client):
        """Line 859: the drawer can disappear between the pre-check and the lock."""
        with _pos_api_patches(), patch("routes.pos.get_active_session_locked", return_value=None):
            resp = client.post("/pos/api/checkout", json={"lines": []})
        assert resp.status_code == 403
        assert "جلسة كاشير" in str(resp.get_json()["message"])

    def test_session_report_other_user_is_forbidden(self, client):
        """Line 1413: a cashier cannot read another cashier's drawer."""
        session = MagicMock(id=7, user_id=999, branch_id=2)
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_get", return_value=session),
            patch("routes.pos._can_view_expected", return_value=False),
        ):
            resp = client.get("/pos/api/session/report?session_id=7")
        assert resp.status_code == 403

    def test_session_report_other_branch_is_forbidden(self, client):
        """Line 1416: branch scope also gates explicit session reads."""
        session = MagicMock(id=7, user_id=42, branch_id=2)
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_get", return_value=session),
            patch("routes.pos._can_view_expected", return_value=True),
            patch("routes.pos.branch_scope_id", return_value=9),
        ):
            resp = client.get("/pos/api/session/report?session_id=7")
        assert resp.status_code == 403

    def test_cash_movement_idempotent_replay(self, client):
        """Lines 1839-1845: a stored response is replayed verbatim."""
        stored = ({"success": True, "movement": {"id": 5}}, 201)
        record = MagicMock()
        with (
            _pos_api_patches(),
            patch("routes.pos.atomic_transaction", _noop_txn),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos._idempotent_begin", return_value=(record, stored, None)),
            patch("routes.pos.PosCashMovementService.create_movement") as create,
        ):
            resp = client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_in", "amount": "10"},
                headers={"Idempotency-Key": "cash-replay-1"},
            )
        assert resp.status_code == 201
        assert resp.get_json()["meta"]["idempotent_replay"] is True
        create.assert_not_called()

    def test_cash_movement_idempotency_error(self, client):
        """Arc 1840->1841: a conflict from the idempotency layer is returned."""
        from utils.api_response import error_response

        refused = error_response(message="idempotency conflict", status_code=409)
        with (
            _pos_api_patches(),
            patch("routes.pos.atomic_transaction", _noop_txn),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos._idempotent_begin", return_value=(None, None, refused)),
            patch("routes.pos.PosCashMovementService.create_movement") as create,
        ):
            resp = client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_in", "amount": "10"},
                headers={"Idempotency-Key": "cash-error-1"},
            )
        assert resp.status_code == 409
        create.assert_not_called()

    def test_cash_movement_completes_idempotency(self, client):
        """Line 1866: a fresh movement completes its idempotency record."""
        record = MagicMock()
        movement = MagicMock()
        movement.to_dict.return_value = {"id": 8, "movement_type": "pay_in"}
        with (
            _pos_api_patches(),
            patch("routes.pos.atomic_transaction", _noop_txn),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos._idempotent_begin", return_value=(record, None, None)),
            patch("routes.pos.PosCashMovementService.create_movement", return_value=movement),
            patch("routes.pos.IdempotencyService.complete") as complete,
        ):
            resp = client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_in", "amount": "10"},
                headers={"Idempotency-Key": "cash-fresh-1"},
            )
        assert resp.status_code == 201
        complete.assert_called_once()

    def test_cash_movement_integrity_with_key_is_conflict(self, client):
        """Lines 1872-1873: integrity error with a key is a 409 replay conflict."""
        err = IntegrityError("INSERT", {}, Exception("dup"))
        with (
            _pos_api_patches(),
            patch("routes.pos.atomic_transaction", _noop_txn),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos._idempotent_begin", return_value=(MagicMock(), None, None)),
            patch("routes.pos.PosCashMovementService.create_movement", side_effect=err),
            patch("routes.pos._idempotency_conflict_response", return_value=("conflict", 409)),
        ):
            resp = client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_in", "amount": "10"},
                headers={"Idempotency-Key": "cash-conflict-1"},
            )
        assert resp.status_code == 409

    def test_cash_movement_integrity_without_key_propagates(self, client):
        """Lines 1874-1875: without a key the integrity error is re-raised."""
        err = IntegrityError("INSERT", {}, Exception("dup"))
        with (
            _pos_api_patches(),
            patch("routes.pos.atomic_transaction", _noop_txn),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos._idempotent_begin", return_value=(None, None, None)),
            patch("routes.pos.PosCashMovementService.create_movement", side_effect=err),
            pytest.raises(IntegrityError),
        ):
            client.post("/pos/api/cash-movements", json={"type": "pay_in", "amount": "10"})

    def test_cash_movement_unexpected_error_propagates(self, client):
        """Arc 1836->exit: an uncaught exception unwinds the transaction."""
        with (
            _pos_api_patches(),
            patch("routes.pos.atomic_transaction", _noop_txn),
            patch("routes.pos.PosOverrideService.require_permission_or_override", return_value=None),
            patch("routes.pos._idempotent_begin", return_value=(None, None, None)),
            patch("routes.pos.PosCashMovementService.create_movement", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            client.post("/pos/api/cash-movements", json={"type": "pay_in", "amount": "10"})

    def test_publish_cfd_stale_entry_not_registered(self):
        """Arc 2162->2161: a stale subscriber already removed is skipped."""
        from routes import pos as pos_module

        class _FakeSubs(list):
            def __contains__(self, item):
                return False

        q = MagicMock()
        q.put_nowait.side_effect = RuntimeError("queue full")
        original = pos_module._CFD_SUBSCRIBERS
        pos_module._CFD_SUBSCRIBERS = _FakeSubs([(1, 11, q)])
        try:
            with patch.object(pos_module.sse_backplane, "publish"):
                pos_module._publish_cfd_refresh(1, 11)
        finally:
            pos_module._CFD_SUBSCRIBERS = original

    def test_kds_heartbeat_resume_and_missing_subscriber(self, app, bypass_permission_auth):
        """Line 2202 and arc 2208->2207: resume after keep-alive; missing slot."""
        from routes import pos as pos_module

        real_q = _queue.Queue()
        unsub = MagicMock()
        with (
            patch("routes.pos.get_active_tenant_id", return_value=7),
            patch("routes.pos.sse_backplane.subscribe", return_value=unsub),
            patch("routes.pos._SSE_HEARTBEAT_SECONDS", 0.01),
            patch("routes.pos._queue.Queue", return_value=real_q),
            app.test_request_context(),
        ):
            gen, _ = pos_module.kds_stream()
            try:
                assert next(gen) == ": keep-alive\n\n"
                # Resuming executes the `continue` on line 2202.
                assert next(gen) == ": keep-alive\n\n"
                # Drop the slot so the finally-block check on 2208 is False.
                pos_module._KDS_SUBSCRIBERS[:] = [
                    entry for entry in pos_module._KDS_SUBSCRIBERS if entry[1] is not real_q
                ]
            finally:
                gen.close()
        unsub.assert_called_once_with()

    def test_cfd_heartbeat_when_idle(self, app):
        """Lines 2338-2339: idle display streams emit a keep-alive frame."""
        from routes import pos as pos_module

        req = MagicMock()
        req.args.get = lambda key, *a, **k: (
            1 if key == "tenant_id" else ("tok" if key == "token" else k.get("default", a[0] if a else None))
        )
        session = MagicMock(tenant_id=1)
        with (
            patch("routes.pos.request", req),
            patch("routes.pos.verify_customer_display_token", return_value=True),
            patch("routes.pos.db.session") as sess,
            patch("services.pos_write_service.PosWriteService.recent_session_sales", return_value=[]),
            patch("routes.pos.time.sleep"),
            patch("routes.pos._SSE_HEARTBEAT_SECONDS", -1),
            patch("routes.pos.sse_backplane.subscribe", return_value=None),
            app.app_context(),
        ):
            sess.get.return_value = session
            gen, _ = pos_module.customer_display_stream(1)
            try:
                assert '"waiting"' in next(gen)
                assert next(gen) == ": keep-alive\n\n"
                # Resume once more so the timestamp update on line 2339 runs.
                assert next(gen) == ": keep-alive\n\n"
            finally:
                gen.close()


# ─────────────────────────────────────────────────────────────────────────────
# routes/shop.py
# ─────────────────────────────────────────────────────────────────────────────


class TestShopCoverageGaps:
    @pytest.fixture
    def client(self, app_factory, bypass_shop_auth):
        from routes.shop import shop_bp

        app = app_factory(shop_bp)
        with app.test_client() as test_client:
            yield test_client

    def test_plan_gate_closes_store(self, client, mock_store):
        """Line 95: an authenticated tenant without enable_store gets the plan gate."""
        from routes.shop import _require_open_store

        tenant = MagicMock(
            is_active=True,
            is_suspended=False,
            enable_store=False,
            brand_color_primary="#1B7A4E",
            brand_color_secondary="#CE1126",
        )
        app = client.application
        with (
            app.test_request_context(),
            patch("routes.shop.db.session.get", return_value=tenant),
        ):
            from flask import g

            g.active_tenant_id = 1
            blocked = _require_open_store(mock_store)
        assert blocked[1] == 503

    def test_customer_type_uses_customer_tenant(self, client, mock_store):
        """Lines 108-112: a priced account resolves its tier from the customer."""
        from routes.shop import _shop_customer_type

        customer = MagicMock(tenant_id=1, customer_type="vip")
        with patch("routes.shop.db.session.get", return_value=customer):
            assert _shop_customer_type(mock_store, _account()) == "vip"
        foreign = MagicMock(tenant_id=2, customer_type="vip")
        with patch("routes.shop.db.session.get", return_value=foreign):
            assert _shop_customer_type(mock_store, _account(customer_id=99)) == "regular"

    def test_safe_color_fallback(self, client, mock_store):
        """Line 142: an invalid brand colour falls back to the theme default."""
        from routes.shop import _store_context

        tenant = MagicMock(
            brand_color_primary="not-a-colour",
            brand_color_secondary="rgb(1,2,3)",
        )
        with patch("routes.shop.db.session.get", return_value=tenant):
            ctx = _store_context(mock_store)
        assert ctx["theme_primary"] == "#1B7A4E"
        assert ctx["theme_secondary"] == "#CE1126"

    def test_wishlist_inactive_product_404(self, client):
        """Line 271: an inactive product cannot be wish-listed."""
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.active_product", return_value=None),
        ):
            resp = client.post(f"{BASE}/wishlist/add/10", json={})
        assert resp.status_code == 404

    def test_wishlist_existing_entry_skips_insert(self, client):
        """Arc 274->282: an existing wishlist entry is not inserted twice."""
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.active_product", return_value=MagicMock(id=10)),
            patch("routes.shop.StoreService.wishlist_entry", return_value=MagicMock(id=1)),
            patch("routes.shop.StoreService.wishlist_count", return_value=1),
            patch("routes.shop.db.session.add") as add,
        ):
            resp = client.post(f"{BASE}/wishlist/add/10", json={})
        assert resp.status_code == 200
        add.assert_not_called()

    def test_api_search_closed_store(self, client):
        """Line 550: a closed store answers an empty search."""
        with patch("routes.shop._require_open_store", return_value=("closed", 503)):
            resp = client.get(f"{BASE}/api/search?q=abc")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"] == []

    def test_product_detail_with_review(self, client):
        """Arc 618->-618: the rating generator expression is consumed."""
        product = MagicMock(
            id=10,
            tenant_id=1,
            is_active=True,
            has_serial_number=False,
            regular_price=Decimal("99"),
        )
        review = MagicMock(rating=5)
        with (
            patch("routes.shop.StoreService.active_product_or_404", return_value=product),
            patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("5")}),
            patch("routes.shop.StoreService.approved_reviews", return_value=[review]),
            patch("routes.shop.StoreService.get_related_products", return_value=[]),
            patch("routes.shop.StoreService.get_recently_viewed_products", return_value=[]),
            patch("routes.shop.StoreService.get_product_variants", return_value=[]),
            patch("routes.shop.ShopCustomerAuthService.whatsapp_order_url", return_value="https://wa.me/"),
        ):
            resp = client.get(f"{BASE}/p/10")
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("post", f"{BASE}/p/10/review/add"),
            ("post", f"{BASE}/stock-alert/10"),
            ("post", f"{BASE}/newsletter/subscribe"),
            ("post", f"{BASE}/cart/remove/10"),
            ("get", f"{BASE}/quick-view/10"),
            ("post", f"{BASE}/order/reorder/5"),
        ],
    )
    def test_closed_store_aborts(self, client, method, url):
        """Lines 662, 697, 725, 906, 1129, 1324."""
        with patch("routes.shop._require_open_store", return_value=("closed", 503)):
            resp = getattr(client, method)(url)
        assert resp.status_code == 503

    def test_add_review_missing_product_404(self, client):
        """Line 669: review submission for an inactive product is a 404."""
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.active_product", return_value=None),
        ):
            resp = client.post(f"{BASE}/p/10/review/add", data={"rating": "5"})
        assert resp.status_code == 404

    def test_stock_alert_missing_product_404(self, client):
        """Line 706: stock alert for an inactive product is a 404."""
        with patch("routes.shop.StoreService.active_product", return_value=None):
            resp = client.post(f"{BASE}/stock-alert/10", data={"email": "a@b.com"})
        assert resp.status_code == 404

    def test_newsletter_existing_subscriber_skips_insert(self, client):
        """Arc 733->737: an existing newsletter subscriber is not re-added."""
        with (
            patch("routes.shop.StoreService.newsletter_subscriber", return_value=MagicMock(id=1)),
            patch("routes.shop.db.session.add") as add,
        ):
            resp = client.post(f"{BASE}/newsletter/subscribe", data={"email": "a@b.com"})
        assert resp.status_code == 302
        add.assert_not_called()

    def test_cart_update_non_integer_cart_key(self, client):
        """Lines 844-845: malformed cart keys reset the stock lookup list."""
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"abc": 1}),
            patch("routes.shop.StoreService.online_stock_map", return_value={}) as stock_map,
            patch("routes.shop.StoreService.save_cart"),
            patch("routes.shop._track_cart_activity"),
        ):
            resp = client.post(f"{BASE}/cart/update", data={"qty_abc": "1"})
        assert resp.status_code == 302
        stock_map.assert_called_once()

    def test_cart_update_unparseable_stock(self, client):
        """Lines 862-863: an unparseable stock value falls back to zero."""
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 2}),
            patch("routes.shop.StoreService.online_stock_map", return_value={"10": "bad"}),
            patch("routes.shop.StoreService.save_cart") as save,
            patch("routes.shop._track_cart_activity"),
        ):
            resp = client.post(f"{BASE}/cart/update", data={"qty_10": "1"})
        assert resp.status_code == 302
        assert save.call_args[0][-1] == {}

    def test_cart_count_closed_store(self, client):
        """Line 928: a closed store reports zero cart items."""
        with patch("routes.shop._require_open_store", return_value=("closed", 503)):
            resp = client.get(f"{BASE}/cart/count")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["count"] == 0

    def test_checkout_used_token_is_refused(self, client):
        """Lines 968-969: a consumed checkout token blocks the POST."""
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 1}),
            patch(
                "routes.shop.StoreService.cart_totals",
                return_value={"lines": [{"id": 10}], "subtotal": Decimal("10")},
            ),
            patch("routes.shop._consume_checkout_token", return_value=False),
        ):
            resp = client.post(f"{BASE}/checkout", data={"checkout_token": "stale", "address": "Dubai"})
        assert resp.status_code == 302

    def test_checkout_below_minimum_order(self, client, mock_store):
        """Line 990: the minimum-order check rejects a small cart."""
        mock_store.min_order_amount = Decimal("100")
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 1}),
            patch(
                "routes.shop.StoreService.cart_totals",
                return_value={"lines": [{"id": 10}], "subtotal": Decimal("10")},
            ),
            patch("routes.shop._consume_checkout_token", return_value=True),
            patch("routes.shop.render_template", return_value="ok"),
        ):
            resp = client.post(f"{BASE}/checkout", data={"address": "Dubai"})
        assert resp.status_code == 200

    def test_checkout_payment_hint_lambda(self, client):
        """Arc 1074->-1074: the payment-hint lambda is invoked by templates."""
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 1}),
            patch(
                "routes.shop.StoreService.cart_totals",
                return_value={"lines": [{"id": 10}], "subtotal": Decimal("10")},
            ),
            patch(
                "routes.shop.StorePaymentMethodService.format_checkout_instructions",
                return_value="Pay on delivery",
            ) as fmt,
            patch("routes.shop.render_template", return_value="ok") as render,
        ):
            resp = client.get(f"{BASE}/checkout")
            assert resp.status_code == 200
            hint = render.call_args[1]["payment_hint"]
            assert hint(MagicMock()) == "Pay on delivery"
            fmt.assert_called_once()

    def test_forgot_password_closed_store(self, client):
        """Line 1212: a closed store short-circuits the reset request."""
        with patch("routes.shop._require_open_store", return_value=("closed", 503)):
            resp = client.post(f"{BASE}/account/forgot-password", data={"email": "a@b.com"})
        assert resp.status_code == 503

    def test_forgot_password_unknown_email(self, client):
        """Arc 1221->1231: no account means no reset e-mail is sent."""
        with (
            patch("routes.shop._require_open_store", return_value=None),
            patch("routes.shop.ShopCustomerAuthService.request_password_reset", return_value=None),
            patch("routes.shop.ShopCustomerAuthService.send_password_reset_email") as send,
        ):
            resp = client.post(f"{BASE}/account/forgot-password", data={"email": "a@b.com"})
        assert resp.status_code == 302
        send.assert_not_called()

    def test_reset_password_closed_store(self, client):
        """Line 1249: a closed store short-circuits the reset confirmation."""
        with patch("routes.shop._require_open_store", return_value=("closed", 503)):
            resp = client.post(f"{BASE}/account/reset-password/tok", data={"password": "newpass123"})
        assert resp.status_code == 503

    def test_save_payment_unknown_method(self, client):
        """Line 1289: an unknown payment method is a 400."""
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StorePaymentMethodService.get_by_code", return_value=None),
        ):
            resp = client.post(f"{BASE}/account/payments/save", data={"method_code": "unknown"})
        assert resp.status_code == 400

    def test_reorder_multiple_lines(self, client):
        """Arc 1340->1338: the reorder loop iterates over more than one line."""
        sale = MagicMock(id=5, customer_id=20)
        lines = [
            MagicMock(product_id=10, quantity=Decimal("1")),
            MagicMock(product_id=11, quantity=Decimal("2")),
            MagicMock(product_id=12, quantity=Decimal("3")),
        ]
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.online_order_or_404", return_value=sale),
            patch("routes.shop.StoreService.online_order_lines", return_value=lines),
            # The third line is out of stock, so the `if available > 0` false
            # branch jumps straight back to the loop header (arc 1340->1338).
            patch("routes.shop.StoreService.online_stock_map", return_value={10: 5, 11: 5}),
            patch("routes.shop.StoreService.get_cart", return_value={}),
            patch("routes.shop.StoreService.save_cart") as save,
        ):
            resp = client.post(f"{BASE}/order/reorder/5")
        assert resp.status_code == 302
        cart = save.call_args[0][-1]
        assert set(cart) == {"10", "11"}


# ─────────────────────────────────────────────────────────────────────────────
# routes/payment_vault.py
# ─────────────────────────────────────────────────────────────────────────────


class TestPaymentVaultCoverageGaps:
    @pytest.fixture(autouse=True)
    def _patch_db(self, mock_db):
        return mock_db

    @pytest.fixture(autouse=True)
    def _patch_render(self, mocker):
        mocker.patch("routes.payment_vault.render_template", return_value="ok")

    @pytest.fixture
    def unlocked_vault(self, mocker):
        vault = MagicMock()
        vault.id = 1
        vault.is_locked = False
        vault.nowpayments_ipn_secret = "ipn-secret"
        vault.stripe_webhook_secret = "whsec"
        mocker.patch("routes.payment_vault._get_vault_for_current_tenant", return_value=vault)
        return vault

    def test_webhook_event_id_without_payload(self):
        """Line 90: an empty payload has no dedup id."""
        from routes.payment_vault import _webhook_event_id

        assert _webhook_event_id("stripe", None) is None
        assert _webhook_event_id("nowpayments", {}) is None

    def test_donation_invalid_amount(self, vault_owner_client, mocker):
        """Lines 1409-1410: a truthy but non-numeric amount is a 400."""
        mocker.patch("routes.payment_vault._validate_public_api_origin", return_value=None)
        mocker.patch("routes.payment_vault._validate_api_key", return_value=None)
        resp = vault_owner_client.post(
            "/payment-vault/api/donation",
            json={"amount": "abc", "payment_method": "crypto"},
        )
        assert resp.status_code == 400

    def test_donation_integer_donation_id(self, vault_owner_client, mocker):
        """Arc 1480->1482: an integer donation id is kept as-is."""
        mocker.patch("routes.payment_vault._validate_public_api_origin", return_value=None)
        mocker.patch("routes.payment_vault._validate_api_key", return_value=None)
        mocker.patch("routes.payment_vault._check_idempotency_key", return_value=None)
        mocker.patch("routes.payment_vault._save_idempotency_key")
        mocker.patch("routes.payment_vault.LoggingCore.log_audit")
        mocker.patch("routes.payment_vault.atomic_transaction", _noop_txn)
        svc = MagicMock()
        svc.create_payment.return_value = {
            "success": True,
            "payment_id": "np_int_id",
            "pay_address": "addr",
            "pay_amount": 10.0,
            "invoice_url": "https://example.test/invoice",
        }
        mocker.patch("routes.payment_vault.NOWPaymentsService", return_value=svc)
        donation_q = MagicMock()
        donation_q.filter_by.return_value.order_by.return_value.first.return_value = MagicMock(id=123)
        mocker.patch("routes.payment_vault.Donation.query", donation_q)

        resp = vault_owner_client.post(
            "/payment-vault/api/donation",
            json={"amount": 20, "payment_method": "crypto"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["donation_id"] == 123

    def test_nowpayments_dedup_unavailable(self, vault_owner_client, mocker, unlocked_vault):
        """Lines 2036-2037: a down dedup backend fails closed with 503."""
        from routes.payment_vault import WebhookDedupUnavailable

        mocker.patch("routes.payment_vault._reject_stale_webhook_timestamp", return_value=None)
        mocker.patch(
            "services.webhook_service.WebhookService.verify_nowpayments_signature",
            return_value=True,
        )
        mocker.patch(
            "routes.payment_vault._is_duplicate_webhook",
            side_effect=WebhookDedupUnavailable("redis down"),
        )
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        resp = vault_owner_client.post(
            "/payment-vault/webhook/nowpayments",
            json={"payment_id": "np1", "payment_status": "finished"},
            headers={"x-nowpayments-sig": "sig"},
        )
        assert resp.status_code == 503

    def test_stripe_dedup_unavailable(self, vault_owner_client, mocker, unlocked_vault):
        """Lines 2097-2098: the Stripe webhook fails closed the same way."""
        from routes.payment_vault import WebhookDedupUnavailable

        mocker.patch("routes.payment_vault._reject_stale_webhook_timestamp", return_value=None)
        mocker.patch(
            "services.webhook_service.WebhookService.verify_stripe_signature",
            return_value=True,
        )
        mocker.patch(
            "routes.payment_vault._is_duplicate_webhook",
            side_effect=WebhookDedupUnavailable("redis down"),
        )
        resp = vault_owner_client.post(
            "/payment-vault/webhook/stripe",
            json={"id": "evt_1"},
            content_type="application/json",
            headers={"Stripe-Signature": "sig"},
        )
        assert resp.status_code == 503

    def test_stripe_unsuccessful_result_skips_marker(self, vault_owner_client, mocker, unlocked_vault):
        """Arc 2102->2110: a failed webhook result does not persist a marker."""
        mocker.patch("routes.payment_vault._reject_stale_webhook_timestamp", return_value=None)
        mocker.patch("routes.payment_vault._is_duplicate_webhook", return_value=False)
        mocker.patch(
            "services.webhook_service.WebhookService.verify_stripe_signature",
            return_value=True,
        )
        mocker.patch(
            "services.webhook_service.WebhookService.process_stripe_webhook",
            return_value={"success": False},
        )
        mocker.patch("routes.payment_vault.PaymentLog.log_action")
        with patch("routes.payment_vault._mark_webhook_processed") as mark:
            resp = vault_owner_client.post(
                "/payment-vault/webhook/stripe",
                json={"id": "evt_failed"},
                content_type="application/json",
                headers={"Stripe-Signature": "sig"},
            )
        assert resp.status_code == 400
        mark.assert_not_called()
