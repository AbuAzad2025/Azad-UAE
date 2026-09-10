"""Coverage-targeted POS routes (C) — guards, KDS/SSE fan-out, hardware, tables.

Targets routes/pos.py uncovered lines 1545, 1569, 1680, 1735, 2136, 2245 and
arcs 1722-1723, 1952-1953, 1976->1975, 1978->exit, 1997->1996, 2076->2078,
2133->2135, 2194, 2240-2242, 2278-2287, 2357-2360.

Real response paths via the Flask test client; mocks only at DB/external
boundaries (tenant queries, services, SSE backplane, logging).
"""

from unittest.mock import MagicMock, patch

import pytest

import routes.pos as pos_module
from services.pos_override_service import PosOverrideError
from tests.unit.routes.conftest import _chain_query
from tests.unit.routes.test_pos_v2_routes import _mock_session, _pos_api_patches


@pytest.fixture
def cov_client(app_factory, bypass_permission_auth):
    from routes.pos import pos_bp

    app = app_factory(pos_bp)
    return app.test_client()


class TestCovCJsonGuards:
    """Lines 1545/1569/1680/1735: malformed or non-JSON bodies."""

    def test_supervisor_pin_malformed_body_is_400(self, cov_client):
        with _pos_api_patches():
            resp = cov_client.post(
                "/pos/api/supervisor-pin",
                data="{bad",
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_drawer_open_requires_json(self, cov_client):
        with _pos_api_patches():
            resp = cov_client.post("/pos/api/drawer/open", data="{}", content_type="text/plain")
        assert resp.status_code == 415

    def test_cash_movement_requires_json(self, cov_client):
        with _pos_api_patches():
            resp = cov_client.post("/pos/api/cash-movements", data="{}", content_type="text/plain")
        assert resp.status_code == 415

    def test_void_line_requires_json(self, cov_client):
        with _pos_api_patches():
            resp = cov_client.post("/pos/api/carts/5/void-line", data="{}", content_type="text/plain")
        assert resp.status_code == 415


class TestCovCCashMovementValues:
    """Arc 1722-1723: service-level validation maps to 400."""

    def test_create_validation_error_is_400(self, cov_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosOverrideService.require_permission_or_override",
                return_value=77,
            ),
            patch(
                "routes.pos.PosCashMovementService.create_movement",
                side_effect=ValueError("amount required"),
            ),
        ):
            resp = cov_client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_in", "amount": "0"},
            )
        assert resp.status_code == 400


class TestCovCCustomerDisplayStream:
    """Line 2136 + arc 2133->2135: stream teardown unsubscribes exactly once."""

    def _get(self, client):
        return client.get("/pos/api/customer-display/11/stream?tenant_id=1&token=tok")

    def test_closed_session_unsubscribes_backplane(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.verify_customer_display_token", return_value=True),
            patch("routes.pos.sse_backplane") as backplane,
        ):
            unsub = MagicMock()
            backplane.subscribe.return_value = unsub
            resp = self._get(cov_client)
            body = resp.data
        assert resp.status_code == 200
        assert b"closed" in body
        unsub.assert_called_once_with()

    def test_missing_subscriber_skips_removal(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.verify_customer_display_token", return_value=True),
            patch("routes.pos.sse_backplane") as backplane,
        ):

            def _evict(channel, _queue):
                pos_module._CFD_SUBSCRIBERS[:] = []
                return None

            backplane.subscribe.side_effect = _evict
            resp = self._get(cov_client)
            body = resp.data
        assert resp.status_code == 200
        assert b"closed" in body


class TestCovCHardwareDrawer:
    """Line 2245 + arcs 2240-2242 (session guards) / 2278-2287 (override denial)."""

    def test_terminal_session_without_token_is_403(self, cov_client):
        session = _mock_session()
        session.terminal_id = "T-9"
        with _pos_api_patches(session=session):
            resp = cov_client.post("/pos/api/hardware/open-drawer", json={"reason": "jam"})
        assert resp.status_code == 403

    def test_paused_session_returns_409(self, cov_client):
        with _pos_api_patches(session=None, paused_session=_mock_session()):
            resp = cov_client.post("/pos/api/hardware/open-drawer", json={})
        assert resp.status_code == 409

    def test_missing_session_is_403(self, cov_client):
        with _pos_api_patches(session=None):
            resp = cov_client.post("/pos/api/hardware/open-drawer", json={})
        assert resp.status_code == 403

    def test_override_denial_is_audited_403(self, cov_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosOverrideService.require_permission_or_override",
                side_effect=PosOverrideError("supervisor required"),
            ),
            patch("routes.pos.log_security") as log_security,
        ):
            resp = cov_client.post("/pos/api/hardware/open-drawer", json={"reason": "x"})
        assert resp.status_code == 403
        assert log_security.call_count == 1


class TestCovCPrintTickets:
    """Line 2194: an unknown sale is a 404."""

    def test_missing_sale_is_404(self, cov_client):
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_get", return_value=None),
        ):
            resp = cov_client.get("/pos/api/sale/999/print-tickets")
        assert resp.status_code == 404


class TestCovCStockLookup:
    """Arc 1952-1953: invalid identifiers map to 400."""

    def test_service_validation_error_is_400(self, cov_client):
        with (
            _pos_api_patches(),
            patch(
                "routes.pos.PosRmaService.stock_breakdown",
                side_effect=ValueError("bad id"),
            ),
        ):
            resp = cov_client.get("/pos/api/stock/lookup?product_id=5")
        assert resp.status_code == 400


class TestCovCKdsFanout:
    """Arcs 1976->1975/1978->exit/1997->1996 + 2076->2078 via status updates."""

    def test_stale_subscriber_evicted_mid_broadcast(self, cov_client):
        evil = MagicMock()

        def _evict(message):
            pos_module._KDS_SUBSCRIBERS[:] = []
            raise RuntimeError("gone")

        evil.put_nowait.side_effect = _evict
        order = MagicMock(id=1)
        order.sale = None
        try:
            pos_module._KDS_SUBSCRIBERS[:] = [(1, evil)]
            with _pos_api_patches(tenant_query_models={"PosKdsOrder": _chain_query(first=order)}):
                resp = cov_client.post("/pos/api/kds/orders/1/status", json={"status": "ready"})
        finally:
            pos_module._KDS_SUBSCRIBERS[:] = []
        assert resp.status_code == 200

    def test_status_update_without_sale_skips_display_refresh(self, cov_client):
        order = MagicMock(id=1)
        order.sale = None
        with (
            _pos_api_patches(tenant_query_models={"PosKdsOrder": _chain_query(first=order)}),
            patch("routes.pos.get_active_tenant_id", return_value=None),
            patch("routes.pos.sse_backplane") as backplane,
        ):
            resp = cov_client.post("/pos/api/kds/orders/1/status", json={"status": "ready"})
        assert resp.status_code == 200
        backplane.publish.assert_not_called()

    def test_display_refresh_prunes_dead_subscribers(self, cov_client):
        order = MagicMock(id=1)
        order.sale = MagicMock(pos_session_id=11)
        dead_first = MagicMock()
        dead_first.put_nowait.side_effect = RuntimeError("gone")
        dead_second = MagicMock()
        dead_second.put_nowait.side_effect = RuntimeError("gone")
        try:
            pos_module._CFD_SUBSCRIBERS[:] = [(1, 11, dead_first), (1, 11, dead_second)]
            with _pos_api_patches(tenant_query_models={"PosKdsOrder": _chain_query(first=order)}):
                resp = cov_client.post("/pos/api/kds/orders/1/status", json={"status": "ready"})
        finally:
            pos_module._CFD_SUBSCRIBERS[:] = []
        assert resp.status_code == 200


class TestCovCTablesListing:
    """Range 2357-2360: table selector with and without floor linkage."""

    def _table(self, tid, floor):
        table = MagicMock()
        table.id = tid
        table.label = f"T{tid}"
        table.capacity = 4
        table.status = "free"
        table.floor = floor
        return table

    def test_lists_tables_with_mixed_floor_linkage(self, cov_client):
        floor = MagicMock()
        floor.name_ar = "الأرضي"
        query = _chain_query(all=[self._table(1, floor), self._table(2, None)])
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_query", return_value=query),
        ):
            resp = cov_client.get("/pos/api/tables")
        assert resp.status_code == 200
        rows = resp.get_json()["data"]
        assert [row["floor_name"] for row in rows] == ["الأرضي", ""]

    def test_empty_floor_lists_no_tables(self, cov_client):
        query = _chain_query(all=[])
        with (
            _pos_api_patches(),
            patch("routes.pos.tenant_query", return_value=query),
        ):
            resp = cov_client.get("/pos/api/tables")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == []
