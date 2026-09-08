"""Coverage-99 boost for routes/warehouse.py.

Covers: movements with items (168-173), view stock loop (223->218),
edit empty name/location (256-257, 265-266), create online (327-334,
417-420), duplicate code (356-366), bad/inactive parent (377-388),
api_transfer (557-606), api_exchange (614-661).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models import Warehouse


@pytest.fixture
def wh_admin_client(app_factory, bypass_admin_auth):
    from routes.warehouse import warehouse_bp

    app = app_factory(warehouse_bp)
    return app.test_client()


def _movement(mid):
    m = MagicMock()
    m.id = mid
    return m


class TestMovementsWithItems:
    def test_movements_none_and_tuple_balances(self, wh_admin_client):
        items = [_movement(1), _movement(2)]
        pagination = MagicMock()
        pagination.items = items
        with (
            patch("routes.warehouse.StockService.get_branch_warehouse_ids", return_value=None),
            patch("routes.warehouse.StockService.movements_query") as mq,
            patch(
                "routes.warehouse.StockService.get_movement_running_balances",
                return_value={1: None, 2: (5, 8)},
            ),
            patch("routes.warehouse.StockService.list_active_warehouses", return_value=[]),
            patch("routes.warehouse.render_template", return_value="ok"),
            patch("routes.warehouse.branch_scope_id", return_value=None),
            patch("routes.warehouse.get_active_tenant_id", return_value=1),
        ):
            mq.return_value.paginate.return_value = pagination
            resp = wh_admin_client.get("/warehouse/movements")
        assert resp.status_code == 200
        assert items[0].before_qty is None
        assert items[1].before_qty == 5
        assert items[1].after_qty == 8


class TestViewWarehouseStock:
    def test_view_with_stock_rows(self, wh_admin_client):
        wh = MagicMock(spec=Warehouse)
        wh.branch_id = None
        wh.tenant_id = 1
        with (
            patch("routes.warehouse.tenant_get_or_404", return_value=wh),
            patch("routes.warehouse.branch_scope_id", return_value=None),
            patch(
                "routes.warehouse.StockService.get_warehouse_stock_totals",
                return_value=[(10, 3), (11, 0), (12, None)],
            ),
            patch("routes.warehouse.StockService.get_tenant_product") as gp,
            patch("routes.warehouse.render_template", return_value="ok") as rt,
        ):
            gp.side_effect = [MagicMock(), None, MagicMock()]
            resp = wh_admin_client.get("/warehouse/99")
        assert resp.status_code == 200
        stock = rt.call_args[1]["stock"]
        assert len(stock) == 1
        assert stock[0]["quantity"] == 3.0


class TestEditValidation:
    def _post_edit(self, client, data):
        wh = MagicMock(spec=Warehouse)
        wh.id = 7
        with (
            patch("routes.warehouse.tenant_get_or_404", return_value=wh),
            patch("routes.warehouse.StockService.list_parent_warehouses", return_value=[]),
            patch("routes.warehouse.scoped_user_query") as sq,
            patch("routes.warehouse.get_accessible_branches_query") as bq,
            patch("routes.warehouse.render_template", return_value="form") as rt,
        ):
            sq.return_value.all.return_value = []
            bq.return_value.order_by.return_value.all.return_value = []
            resp = client.post("/warehouse/7/edit", data=data)
        return resp, rt

    def test_edit_empty_name(self, wh_admin_client):
        resp, rt = self._post_edit(wh_admin_client, {"name": "", "location": "Dubai"})
        assert resp.status_code == 200
        assert rt.call_args[0][0] == "warehouse/edit_warehouse.html"

    def test_edit_empty_location(self, wh_admin_client):
        resp, rt = self._post_edit(wh_admin_client, {"name": "WH", "location": ""})
        assert resp.status_code == 200
        assert rt.call_args[0][0] == "warehouse/edit_warehouse.html"


class TestCreateOnlineAndDuplicates:
    def _post_create(self, client, data, existing_code=None, parent=None):
        with (
            patch("routes.warehouse.StockService.list_parent_warehouses", return_value=[]),
            patch("routes.warehouse.scoped_user_query") as sq,
            patch("routes.warehouse.get_accessible_branches_query") as bq,
            patch("routes.warehouse.StockService.find_warehouse_by_code", return_value=existing_code),
            patch("routes.warehouse.StockService.get_tenant_warehouse", return_value=parent),
            patch("routes.warehouse.get_active_tenant_id", return_value=1),
            patch("routes.warehouse.render_template", return_value="form") as rt,
        ):
            sq.return_value.all.return_value = []
            bq.return_value.order_by.return_value.all.return_value = []
            resp = client.post("/warehouse/create", data=data)
        return resp, rt

    def test_create_online_defaults_location(self, wh_admin_client):
        from services.store_service import StoreService

        with (
            patch.object(StoreService, "assert_single_online_warehouse", return_value=None),
            patch("routes.warehouse.db.session"),
            patch.object(StoreService, "get_tenant_store") as gs,
            patch("utils.tenant_limits.check_warehouses_limit", return_value=None),
        ):
            store = MagicMock(warehouse_id=1)
            gs.return_value = store
            resp, _ = self._post_create(
                wh_admin_client,
                {"name": "Online WH", "location": "", "warehouse_type": "online"},
            )
        assert resp.status_code in (302, 303)

    def test_create_duplicate_code(self, wh_admin_client):
        resp, rt = self._post_create(
            wh_admin_client,
            {"name": "WH", "location": "Dubai", "code": "DUP"},
            existing_code=MagicMock(),
        )
        assert resp.status_code == 200
        assert rt.call_args[0][0] == "warehouse/create_warehouse.html"

    def test_create_missing_parent(self, wh_admin_client):
        resp, rt = self._post_create(
            wh_admin_client,
            {"name": "WH", "location": "Dubai", "parent_id": "999"},
            parent=None,
        )
        assert resp.status_code == 200

    def test_create_inactive_parent(self, wh_admin_client):
        parent = MagicMock(is_active=False)
        resp, rt = self._post_create(
            wh_admin_client,
            {"name": "WH", "location": "Dubai", "parent_id": "5"},
            parent=parent,
        )
        assert resp.status_code == 200


class TestApiTransfer:
    def _post(self, client, payload=None, as_json=True):
        if as_json:
            return client.post("/warehouse/transfer", json=payload or {})
        return client.post("/warehouse/transfer", data="x", content_type="text/plain")

    def test_transfer_not_json(self, wh_admin_client):
        resp = self._post(wh_admin_client, as_json=False)
        assert resp.status_code == 415

    def test_transfer_missing_fields(self, wh_admin_client):
        resp = self._post(wh_admin_client, {"product_id": 1})
        assert resp.status_code == 400

    def test_transfer_success(self, wh_admin_client):
        out_m = MagicMock(tenant_id=1)
        in_m = MagicMock(tenant_id=1)
        with (
            patch("routes.warehouse.StockService.transfer_stock", return_value=(out_m, in_m)),
            patch("routes.warehouse.StockService.get_pws_row") as gpw,
        ):
            gpw.side_effect = [MagicMock(quantity=10), None]
            resp = self._post(
                wh_admin_client,
                {"product_id": 1, "source_id": 2, "destination_id": 3, "quantity": 5},
            )
        assert resp.status_code == 200

    def test_transfer_value_error(self, wh_admin_client):
        with patch("routes.warehouse.StockService.transfer_stock", side_effect=ValueError("bad qty")):
            resp = self._post(
                wh_admin_client,
                {"product_id": 1, "source_id": 2, "destination_id": 3, "quantity": 5},
            )
        assert resp.status_code == 400

    def test_transfer_generic_error(self, wh_admin_client):
        with patch("routes.warehouse.StockService.transfer_stock", side_effect=RuntimeError("boom")):
            resp = self._post(
                wh_admin_client,
                {"product_id": 1, "source_id": 2, "destination_id": 3, "quantity": 5},
            )
        assert resp.status_code == 500


class TestApiExchange:
    def _post(self, client, payload=None, as_json=True):
        if as_json:
            return client.post("/warehouse/exchange", json=payload or {})
        return client.post("/warehouse/exchange", data="x", content_type="text/plain")

    def test_exchange_not_json(self, wh_admin_client):
        assert self._post(wh_admin_client, as_json=False).status_code == 415

    def test_exchange_missing_fields(self, wh_admin_client):
        assert self._post(wh_admin_client, {"warehouse_id": 1}).status_code == 400

    def test_exchange_bad_direction(self, wh_admin_client):
        resp = self._post(
            wh_admin_client,
            {"warehouse_id": 1, "product_id": 2, "quantity": 3, "direction": "SIDEWAYS"},
        )
        assert resp.status_code == 400

    def test_exchange_out_success(self, wh_admin_client):
        movement = MagicMock(tenant_id=1)
        with (
            patch("routes.warehouse.StockService.adjust_stock", return_value=movement),
            patch("routes.warehouse.StockService.get_pws_row", return_value=MagicMock(quantity=7)),
        ):
            resp = self._post(
                wh_admin_client,
                {"warehouse_id": 1, "product_id": 2, "quantity": 3, "direction": "OUT"},
            )
        assert resp.status_code == 200

    def test_exchange_value_error(self, wh_admin_client):
        with patch("routes.warehouse.StockService.adjust_stock", side_effect=ValueError("bad")):
            resp = self._post(wh_admin_client, {"warehouse_id": 1, "product_id": 2, "quantity": 3})
        assert resp.status_code == 400

    def test_exchange_generic_error(self, wh_admin_client):
        with patch("routes.warehouse.StockService.adjust_stock", side_effect=RuntimeError("x")):
            resp = self._post(wh_admin_client, {"warehouse_id": 1, "product_id": 2, "quantity": 3})
        assert resp.status_code == 500


class TestRemainingArcs:
    def test_view_product_none_with_qty(self, wh_admin_client):
        wh = MagicMock(spec=Warehouse)
        wh.branch_id = None
        wh.tenant_id = 1
        with (
            patch("routes.warehouse.tenant_get_or_404", return_value=wh),
            patch("routes.warehouse.branch_scope_id", return_value=None),
            patch(
                "routes.warehouse.StockService.get_warehouse_stock_totals",
                return_value=[(10, 5)],
            ),
            patch("routes.warehouse.StockService.get_tenant_product", return_value=None),
            patch("routes.warehouse.render_template", return_value="ok") as rt,
        ):
            resp = wh_admin_client.get("/warehouse/99")
        assert resp.status_code == 200
        assert rt.call_args[1]["stock"] == []

    def test_create_online_no_tenant(self, wh_admin_client):
        from services.store_service import StoreService

        with (
            patch("routes.warehouse.StockService.list_parent_warehouses", return_value=[]),
            patch("routes.warehouse.scoped_user_query") as sq,
            patch("routes.warehouse.get_accessible_branches_query") as bq,
            patch("routes.warehouse.get_active_tenant_id", return_value=None),
            patch("routes.warehouse.db.session"),
            patch("utils.tenant_limits.check_warehouses_limit", return_value=None),
        ):
            sq.return_value.all.return_value = []
            bq.return_value.order_by.return_value.all.return_value = []
            with patch.object(StoreService, "assert_single_online_warehouse", return_value=None):
                resp = wh_admin_client.post(
                    "/warehouse/create",
                    data={"name": "Online WH", "location": "", "warehouse_type": "online"},
                )
        assert resp.status_code in (200, 302, 303)

    def test_create_online_with_location(self, wh_admin_client):
        from services.store_service import StoreService

        with (
            patch("routes.warehouse.StockService.list_parent_warehouses", return_value=[]),
            patch("routes.warehouse.scoped_user_query") as sq,
            patch("routes.warehouse.get_accessible_branches_query") as bq,
            patch("routes.warehouse.get_active_tenant_id", return_value=1),
            patch("routes.warehouse.db.session"),
            patch("utils.tenant_limits.check_warehouses_limit", return_value=None),
            patch.object(StoreService, "assert_single_online_warehouse", return_value=None),
            patch.object(StoreService, "get_tenant_store", return_value=None),
        ):
            sq.return_value.all.return_value = []
            bq.return_value.order_by.return_value.all.return_value = []
            resp = wh_admin_client.post(
                "/warehouse/create",
                data={"name": "Online WH", "location": "Web", "warehouse_type": "online"},
            )
        assert resp.status_code in (302, 303)

    def test_create_with_code_no_duplicate(self, wh_admin_client):
        with (
            patch("routes.warehouse.StockService.list_parent_warehouses", return_value=[]),
            patch("routes.warehouse.scoped_user_query") as sq,
            patch("routes.warehouse.get_accessible_branches_query") as bq,
            patch("routes.warehouse.StockService.find_warehouse_by_code", return_value=None),
            patch("routes.warehouse.get_active_tenant_id", return_value=1),
            patch("routes.warehouse.db.session"),
            patch("utils.tenant_limits.check_warehouses_limit", return_value=None),
        ):
            sq.return_value.all.return_value = []
            bq.return_value.order_by.return_value.all.return_value = []
            resp = wh_admin_client.post(
                "/warehouse/create",
                data={"name": "WH", "location": "Dubai", "code": "UNIQUE1"},
            )
        assert resp.status_code in (302, 303)

    def test_create_valid_active_parent(self, wh_admin_client):
        parent = MagicMock(is_active=True)
        with (
            patch("routes.warehouse.StockService.list_parent_warehouses", return_value=[]),
            patch("routes.warehouse.scoped_user_query") as sq,
            patch("routes.warehouse.get_accessible_branches_query") as bq,
            patch("routes.warehouse.StockService.get_tenant_warehouse", return_value=parent),
            patch("routes.warehouse.get_active_tenant_id", return_value=1),
            patch("routes.warehouse.db.session"),
            patch("utils.tenant_limits.check_warehouses_limit", return_value=None),
        ):
            sq.return_value.all.return_value = []
            bq.return_value.order_by.return_value.all.return_value = []
            resp = wh_admin_client.post(
                "/warehouse/create",
                data={"name": "WH", "location": "Dubai", "parent_id": "5"},
            )
        assert resp.status_code in (302, 303)

    def test_create_online_store_already_linked(self, wh_admin_client):
        from services.store_service import StoreService

        with (
            patch("routes.warehouse.StockService.list_parent_warehouses", return_value=[]),
            patch("routes.warehouse.scoped_user_query") as sq,
            patch("routes.warehouse.get_accessible_branches_query") as bq,
            patch("routes.warehouse.get_active_tenant_id", return_value=1),
            patch("routes.warehouse.db.session"),
            patch("utils.tenant_limits.check_warehouses_limit", return_value=None),
            patch.object(StoreService, "assert_single_online_warehouse", return_value=None),
            patch.object(StoreService, "get_tenant_store") as gs,
        ):
            sq.return_value.all.return_value = []
            bq.return_value.order_by.return_value.all.return_value = []
            gs.return_value = MagicMock(warehouse_id=None)
            resp = wh_admin_client.post(
                "/warehouse/create",
                data={"name": "Online WH", "location": "", "warehouse_type": "online"},
            )
        assert resp.status_code in (302, 303)
