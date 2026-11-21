"""Regression tests for the API/SSE/warehouse audit findings.

Every test here targets a line changed by the audit fix and is meant to be run
on its own (the full suite is CI's job).
"""

from __future__ import annotations

import io
import queue
import threading
from unittest.mock import MagicMock

import pytest


class _FakeProductsQuery:
    """Query stub that records limit/offset so the route's pagination is testable."""

    def __init__(self, rows):
        self.rows = rows
        self.limit_value = None
        self.offset_value = None

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        self.limit_value = n
        return self

    def offset(self, n):
        self.offset_value = n
        return self

    def all(self):
        start = self.offset_value or 0
        return self.rows[start : start + (self.limit_value or 0)]


def _product(i):
    p = MagicMock()
    p.id = i
    p.name = f"Product {i}"
    p.sku = f"SKU-{i}"
    p.barcode = None
    p.regular_price = 10
    p.merchant_price = None
    p.partner_price = None
    p.cost_price = 4
    p.unit = "pcs"
    p.current_stock = 5
    p.is_low_stock.return_value = False
    p.has_serial_number = False
    return p


@pytest.fixture
def api_client(app_factory, mocker):
    user = MagicMock(is_authenticated=True, tenant_id=1, id=1)
    user.has_permission.return_value = True
    mocker.patch("flask_login.utils._get_user", return_value=user)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
    from routes.api import api_bp

    app = app_factory(
        api_bp,
        config_overrides={"APP_ENV": "development", "DEBUG": True},
    )
    return app.test_client()


class TestApiSearchProductPagination:
    """Finding 1: /api/search products must honour page and report has_more correctly."""

    def _search(self, client, mocker, rows, page):
        q = _FakeProductsQuery(rows)
        mocker.patch("routes.api.get_accessible_warehouse_ids", return_value=[1])
        mocker.patch("routes.api.get_branch_stock_map", return_value={})
        mocker.patch("routes.api.PlatformQueryService.products_base_query", return_value=q)
        resp = client.get(f"/api/search?type=products&q=prod&page={page}")
        return resp, q

    def test_page_offset_is_applied(self, api_client, mocker):
        # Exactly per_page rows exist on page 2 -> empty page, no more rows.
        rows = [_product(i) for i in range(20)]
        resp, q = self._search(api_client, mocker, rows, page=2)
        body = resp.get_json()
        assert resp.status_code == 200
        assert q.limit_value == 21
        assert q.offset_value == 20
        assert body["data"]["results"] == []
        assert body["data"]["has_more"] is False

    def test_has_more_true_only_when_an_extra_row_exists(self, api_client, mocker):
        rows = [_product(i) for i in range(21)]
        resp, q = self._search(api_client, mocker, rows, page=1)
        body = resp.get_json()
        assert q.limit_value == 21
        assert q.offset_value == 0
        assert len(body["data"]["results"]) == 20
        assert body["data"]["has_more"] is True


class TestAssistantFailedResultEnvelope:
    """Finding 2: a failed inner result must not be wrapped in success_response."""

    def test_failed_process_returns_error_envelope(self, ai_client, mocker):
        mocker.patch(
            "routes.ai_routes.assistant._process_excel_intelligently",
            return_value={"success": False, "error": "bad structure"},
        )
        resp = ai_client.post(
            "/ai/upload-excel",
            data={"file": (io.BytesIO(b"x"), "products.xlsx"), "warehouse_id": "5"},
            content_type="multipart/form-data",
        )
        body = resp.get_json()
        assert resp.status_code == 400
        assert body["success"] is False
        assert "bad structure" in body["message"]

    def test_successful_process_still_returns_success_envelope(self, ai_client, mocker):
        ok = {"success": True, "message": "ok", "details": {}}
        mocker.patch("routes.ai_routes.assistant._process_excel_intelligently", return_value=ok)
        resp = ai_client.post(
            "/ai/upload-excel",
            data={"file": (io.BytesIO(b"x"), "products.xlsx"), "warehouse_id": "5"},
            content_type="multipart/form-data",
        )
        body = resp.get_json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["success"] is True


class TestPaginationMeta:
    """Finding 3: verify paginated_response already carries has_next/has_prev."""

    def test_paginated_response_meta(self, app):
        from utils.api_response import paginated_response

        with app.app_context():
            body, code = paginated_response(items=[1, 2], page=2, per_page=2, total=5)
        meta = body.get_json()["meta"]["pagination"]
        assert code == 200
        assert meta["has_next"] is True
        assert meta["has_prev"] is True
        assert meta["page"] == 2
        assert meta["pages"] == 3


class TestSseSubscriberSafety:
    """Finding 4: lock-protected registries, cleanup, heartbeat, KDS backplane subscribe."""

    def test_lock_is_a_threading_lock(self):
        from routes import pos as pos_module

        assert isinstance(pos_module._SSE_SUBSCRIBERS_LOCK, type(threading.Lock()))

    def test_kds_stream_subscribes_and_cleans_up(self, app, mocker, bypass_permission_auth):
        from routes import pos as pos_module

        mocker.patch("routes.pos.get_active_tenant_id", return_value=7)
        unsub = MagicMock()
        subscribe = mocker.patch("routes.pos.sse_backplane.subscribe", return_value=unsub)
        real_q = queue.Queue()
        mocker.patch("routes.pos._queue.Queue", return_value=real_q)
        with app.test_request_context():
            gen, _ = pos_module.kds_stream()
            real_q.put({"type": "refresh", "tenant_id": 7})
            frame = next(gen)  # generator body (register + subscribe) runs here
            subscribe.assert_called_once_with("pos:kds:7", real_q)
            assert any(entry[1] is real_q for entry in pos_module._KDS_SUBSCRIBERS)
            assert '"refresh"' in frame
            gen.close()
        unsub.assert_called_once_with()
        assert not any(entry[1] is real_q for entry in pos_module._KDS_SUBSCRIBERS)

    def test_kds_stream_heartbeat_on_idle_timeout(self, app, mocker, bypass_permission_auth):
        from routes import pos as pos_module

        mocker.patch("routes.pos.get_active_tenant_id", return_value=7)
        mocker.patch("routes.pos.sse_backplane.subscribe", return_value=None)
        mocker.patch("routes.pos._SSE_HEARTBEAT_SECONDS", 0.01)
        before = len(pos_module._KDS_SUBSCRIBERS)
        with app.test_request_context():
            gen, _ = pos_module.kds_stream()
            try:
                assert next(gen) == ": keep-alive\n\n"
            finally:
                gen.close()
        assert len(pos_module._KDS_SUBSCRIBERS) == before

    def test_cfd_stream_cleans_up_on_close(self, app, mocker):
        from routes import pos as pos_module

        req = MagicMock()
        req.args.get = lambda key, *a, **k: (
            1 if key == "tenant_id" else ("tok" if key == "token" else k.get("default", None))
        )
        mocker.patch("routes.pos.request", req)
        mocker.patch("routes.pos.verify_customer_display_token", return_value=True)
        mocker.patch("routes.pos.db.session")
        mocker.patch("routes.pos.time.sleep")
        unsub = MagicMock()
        mocker.patch("routes.pos.sse_backplane.subscribe", return_value=unsub)
        with app.app_context():
            gen, _ = pos_module.customer_display_stream(11)
            next(gen)  # "waiting" for an empty session
            gen.close()
        unsub.assert_called_once_with()
        assert not any(entry[0:2] == (1, 11) for entry in pos_module._CFD_SUBSCRIBERS)


class TestWarehouseTenantConsistency:
    """Finding 5: the tenant/branch invariant holds without a request context."""

    def test_matching_tenant_and_branch_is_allowed(self, db_session, sample_tenant, sample_branch):
        from models.warehouse import Warehouse

        wh = Warehouse(name="Consistent", branch_id=sample_branch.id, tenant_id=sample_tenant.id)
        assert wh.tenant_id == sample_tenant.id

    def test_mismatch_is_rejected_even_with_no_request_context(self, db_session, sample_tenant, sample_branch, mocker):
        """Simulate CLI/Celery: has_request_context() is False. The old code
        skipped the check here; the unconditional validator must still reject."""
        mocker.patch("flask.has_request_context", return_value=False)
        from models.warehouse import Warehouse

        with pytest.raises(ValueError, match="must match"):
            Warehouse(name="Split brain", branch_id=sample_branch.id, tenant_id=sample_tenant.id + 99999)
