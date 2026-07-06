from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


def _product(pid=1, min_alert=5, current_stock=Decimal("10")):
    product = MagicMock()
    product.id = pid
    product.name = f"Product {pid}"
    product.sku = f"SKU-{pid}"
    product.barcode = f"BC-{pid}"
    product.min_stock_alert = min_alert
    product.current_stock = current_stock
    product.visible_stock = current_stock
    product.tenant_id = 1
    return product


def _warehouse(wid=1, branch_id=1, is_main=False):
    wh = MagicMock()
    wh.id = wid
    wh.name = f"Warehouse {wid}"
    wh.branch_id = branch_id
    wh.is_main = is_main
    wh.is_active = True
    wh.tenant_id = 1
    wh.warehouse_type = "physical"
    return wh


def _branch(bid=1, is_main=True):
    branch = MagicMock()
    branch.id = bid
    branch.is_main = is_main
    branch.code = f"B{bid}"
    branch.name = f"Branch {bid}"
    return branch


@pytest.fixture
def warehouse_mocks():
    products = [
        _product(1, min_alert=5, current_stock=Decimal("20")),
        _product(2, min_alert=5, current_stock=Decimal("3")),
        _product(3, min_alert=5, current_stock=Decimal("0")),
    ]
    visible_query = _chain_query(all=products)
    movement_query = _chain_query(all=[])
    warehouse_query = MagicMock()
    warehouse_query.filter_by.return_value.all.return_value = [_warehouse(1)]
    warehouse_query.filter_by.return_value.first.return_value = _warehouse(1)
    warehouse_query.filter_by.return_value.order_by.return_value.first.return_value = _warehouse(1, is_main=True)
    stock_session_query = MagicMock()
    stock_session_query.filter_by.return_value.group_by.return_value.all.return_value = [
        (1, Decimal("15")),
        (2, Decimal("0")),
    ]
    atomic_cm = MagicMock()
    atomic_cm.__enter__ = MagicMock(return_value=None)
    atomic_cm.__exit__ = MagicMock(return_value=False)
    atomic_mock = MagicMock(return_value=atomic_cm)
    patches = [
        patch("routes.warehouse.StockService.get_visible_products_query", return_value=visible_query),
        patch("routes.warehouse.StockService.get_low_stock_products", return_value=[products[1]]),
        patch("routes.warehouse.StockService.get_out_of_stock_products", return_value=[products[2]]),
        patch("routes.warehouse.StockService.adjust_stock"),
        patch("routes.warehouse.get_accessible_warehouse_ids", return_value=[1, 2]),
        patch("routes.warehouse.get_branch_stock_map", return_value={
            1: Decimal("20"),
            2: Decimal("3"),
            3: Decimal("0"),
        }),
        patch("routes.warehouse.tenant_query", side_effect=lambda model: _chain_query(all=[_warehouse()])),
        patch("routes.warehouse.tenant_get_or_404", side_effect=lambda model, pk: _warehouse(pk)),
        patch("routes.warehouse.ensure_warehouse_access"),
        patch("routes.warehouse.get_accessible_branches_query", return_value=_chain_query(all=[_branch()])),
        patch("routes.warehouse.scoped_user_query", return_value=_chain_query(all=[])),
        patch("routes.warehouse.branch_scope_id", return_value=None),
        patch("routes.warehouse.db.session.query", return_value=stock_session_query),
        patch("routes.warehouse.db.session"),
        patch("routes.warehouse.Product.query"),
        patch("routes.warehouse.StockMovement.query", movement_query),
        patch("routes.warehouse.Warehouse.query", warehouse_query),
        patch("routes.warehouse.render_template", return_value="ok"),
        patch("routes.warehouse.should_show_all_branch_columns", return_value=True),
        patch("routes.warehouse.get_active_tenant_id", return_value=1),
        patch("utils.branching.get_main_branch", return_value=_branch()),
        patch("routes.warehouse.atomic_transaction", atomic_mock),
        patch("utils.tenant_limits.check_warehouses_limit"),
    ]
    for p in patches:
        p.start()
    yield {
        "products": products,
        "visible_query": visible_query,
        "movement_query": movement_query,
        "warehouse_query": warehouse_query,
        "stock_session_query": stock_session_query,
    }
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def warehouse_client(app_factory, bypass_permission_auth, warehouse_mocks):
    from routes.warehouse import warehouse_bp
    app = app_factory(warehouse_bp)
    return app.test_client()


@pytest.fixture
def warehouse_admin_client(app_factory, bypass_admin_auth, warehouse_mocks):
    from routes.warehouse import warehouse_bp
    app = app_factory(warehouse_bp)
    return app.test_client()


class TestWarehouseAuth:
    def test_unauthenticated_index_returns_401(self, warehouse_client):
        with unauthenticated_client(warehouse_client):
            resp = warehouse_client.get("/warehouse/")
        assert resp.status_code == 401

    def test_missing_permission_returns_403(self, warehouse_client, mock_user):
        mock_user.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = warehouse_client.get("/warehouse/")
        assert resp.status_code == 403


class TestWarehouseIndex:
    def test_index_renders(self, warehouse_client):
        with patch("routes.warehouse.render_template", return_value="index") as render:
            resp = warehouse_client.get("/warehouse/")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "warehouse/index.html"

    def test_index_with_search(self, warehouse_client, warehouse_mocks):
        with patch("routes.warehouse.render_template", return_value="index") as render:
            resp = warehouse_client.get("/warehouse/?search=widget")
        assert resp.status_code == 200
        warehouse_mocks["visible_query"].filter.assert_called()

    def test_index_low_stock_filter(self, warehouse_client):
        with patch("routes.warehouse.render_template", return_value="index") as render:
            resp = warehouse_client.get("/warehouse/?stock=low")
        assert resp.status_code == 200
        summary = render.call_args[1]["summary"]
        assert summary["low_stock"] >= 0

    def test_index_out_of_stock_filter(self, warehouse_client):
        with patch("routes.warehouse.render_template", return_value="index") as render:
            resp = warehouse_client.get("/warehouse/?stock=out")
        assert resp.status_code == 200
        summary = render.call_args[1]["summary"]
        assert summary["out_of_stock"] >= 0

    def test_index_pagination(self, warehouse_client):
        with patch("routes.warehouse.render_template", return_value="index") as render:
            resp = warehouse_client.get("/warehouse/?page=2&per_page=1")
        assert resp.status_code == 200
        pagination = render.call_args[1]["pagination"]
        assert pagination.page == 2
        assert pagination.per_page == 1


class TestWarehouseMovements:
    def test_movements_renders(self, warehouse_client):
        with patch("routes.warehouse.render_template", return_value="movements") as render:
            resp = warehouse_client.get("/warehouse/movements")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "warehouse/movements.html"

    def test_movements_wrong_warehouse_returns_403(self, warehouse_client):
        wh = _warehouse(99, branch_id=5)
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = wh
        with patch("routes.warehouse.branch_scope_id", return_value=2), \
             patch("routes.warehouse.Warehouse.query", wh_query):
            resp = warehouse_client.get("/warehouse/movements?warehouse=99")
        assert resp.status_code == 403

    def test_movements_with_branch_scope_empty_warehouses(self, warehouse_client):
        wh_query = MagicMock()
        wh_query.filter.return_value.all.return_value = []
        with patch("routes.warehouse.branch_scope_id", return_value=3), \
             patch("routes.warehouse.Warehouse.query", wh_query), \
             patch("routes.warehouse.render_template", return_value="movements"):
            resp = warehouse_client.get("/warehouse/movements")
        assert resp.status_code == 200


class TestWarehouseStockPages:
    def test_low_stock_renders(self, warehouse_client):
        with patch("routes.warehouse.render_template", return_value="low") as render:
            resp = warehouse_client.get("/warehouse/low-stock")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "warehouse/low_stock.html"

    def test_out_of_stock_renders(self, warehouse_client):
        with patch("routes.warehouse.render_template", return_value="out") as render:
            resp = warehouse_client.get("/warehouse/out-of-stock")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "warehouse/out_of_stock.html"


class TestWarehouseView:
    def test_view_warehouse_renders(self, warehouse_client):
        product = _product(1)
        product_query = MagicMock()
        product_query.filter_by.return_value.first.return_value = product
        with patch("routes.warehouse.Product.query", product_query), \
             patch("routes.warehouse.render_template", return_value="view") as render:
            resp = warehouse_client.get("/warehouse/1")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "warehouse/view_warehouse.html"

    def test_view_warehouse_branch_forbidden(self, warehouse_client):
        wh = _warehouse(1, branch_id=9)
        with patch("routes.warehouse.tenant_get_or_404", return_value=wh), \
             patch("routes.warehouse.branch_scope_id", return_value=2):
            resp = warehouse_client.get("/warehouse/1")
        assert resp.status_code == 403


class TestWarehouseCreate:
    def test_create_get_renders(self, warehouse_admin_client):
        with patch("routes.warehouse.render_template", return_value="create") as render:
            resp = warehouse_admin_client.get("/warehouse/create")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "warehouse/create_warehouse.html"

    def test_create_post_success_redirects(self, warehouse_admin_client, warehouse_mocks):
        wh_query = warehouse_mocks["warehouse_query"]
        wh_query.filter_by.return_value.first.return_value = None
        atomic_cm = MagicMock()
        atomic_cm.__enter__ = MagicMock(return_value=None)
        atomic_cm.__exit__ = MagicMock(return_value=False)
        with patch("routes.warehouse.db.session") as mock_session, \
             patch("routes.warehouse.atomic_transaction", return_value=atomic_cm) as atomic_mock:
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "New WH",
                "location": "Dubai",
            })
        assert resp.status_code in (302, 303)
        atomic_mock.assert_called_once_with("warehouse_creation")
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_create_post_without_tenant_redirects(self, warehouse_admin_client):
        with patch("routes.warehouse.get_active_tenant_id", return_value=None), \
             patch("routes.warehouse.url_for", return_value="/owner/tenants"):
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "New WH",
                "location": "Dubai",
            })
        assert resp.status_code in (302, 303)

    def test_create_post_missing_name(self, warehouse_admin_client):
        with patch("routes.warehouse.render_template", return_value="create") as render:
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "",
                "location": "Dubai",
            })
        assert resp.status_code == 200
        assert render.called

    def test_create_post_missing_location(self, warehouse_admin_client):
        with patch("routes.warehouse.render_template", return_value="create") as render:
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "New WH",
                "location": "",
            })
        assert resp.status_code == 200
        assert render.called

    def test_create_post_duplicate_code(self, warehouse_admin_client, warehouse_mocks):
        existing = _warehouse(50)
        wh_query = warehouse_mocks["warehouse_query"]
        wh_query.filter_by.return_value.first.return_value = existing
        with patch("routes.warehouse.render_template", return_value="create") as render:
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "Dup WH",
                "location": "Dubai",
                "code": "DUP",
            })
        assert resp.status_code == 200
        assert render.called

    def test_create_unauthenticated_returns_401(self, warehouse_admin_client):
        with unauthenticated_client(warehouse_admin_client):
            resp = warehouse_admin_client.get("/warehouse/create")
        assert resp.status_code == 401


class TestWarehouseEdit:
    def test_edit_get_renders(self, warehouse_admin_client):
        with patch("routes.warehouse.render_template", return_value="edit") as render:
            resp = warehouse_admin_client.get("/warehouse/1/edit")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "warehouse/edit_warehouse.html"

    def test_edit_post_success(self, warehouse_admin_client):
        with patch("routes.warehouse.db.session"):
            resp = warehouse_admin_client.post("/warehouse/1/edit", data={
                "name": "Updated WH",
                "location": "Abu Dhabi",
            })
        assert resp.status_code in (302, 303)

    def test_edit_post_invalid_branch(self, warehouse_admin_client):
        with patch("routes.warehouse.render_template", return_value="edit"):
            resp = warehouse_admin_client.post("/warehouse/1/edit", data={
                "name": "Updated WH",
                "location": "Abu Dhabi",
                "branch_id": "999",
            })
        assert resp.status_code in (302, 303)


class TestWarehouseList:
    def test_list_warehouses_renders(self, warehouse_client):
        with patch("routes.warehouse.render_template", return_value="list") as render:
            resp = warehouse_client.get("/warehouse/list")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "warehouse/list_warehouses.html"

    def test_list_shows_all_tenant_warehouses_regardless_of_branch_scope(self, warehouse_client):
        wh_a = _warehouse(1, branch_id=1)
        wh_a.name = "WH-A"
        wh_b = _warehouse(2, branch_id=2)
        wh_b.name = "WH-B"
        query = MagicMock()
        query.filter_by.return_value.filter_by.return_value.order_by.return_value.all.return_value = [wh_a, wh_b]
        with patch("routes.warehouse.tenant_query", return_value=query), \
             patch("routes.warehouse.branch_scope_id", return_value=99), \
             patch("routes.warehouse.render_template", return_value="list") as render:
            resp = warehouse_client.get("/warehouse/list")
        assert resp.status_code == 200
        assert render.call_args[1]["warehouses"] == [wh_a, wh_b]

    def test_list_without_active_tenant_redirects(self, warehouse_client):
        with patch("routes.warehouse.get_active_tenant_id", return_value=None), \
             patch("routes.warehouse.url_for", return_value="/owner/tenants"):
            resp = warehouse_client.get("/warehouse/list")
        assert resp.status_code == 200


class TestWarehouseDelete:
    def test_delete_main_branch_blocked(self, warehouse_admin_client):
        main_wh = _warehouse(1, is_main=True)
        with patch("routes.warehouse.tenant_get_or_404", return_value=main_wh):
            resp = warehouse_admin_client.post("/warehouse/1/delete")
        assert resp.status_code in (302, 303)

    def test_delete_soft_delete_when_has_stock(self, warehouse_admin_client):
        wh = _warehouse(5, is_main=False)
        movement = MagicMock()
        movement_query = MagicMock()
        movement_query.filter_by.return_value.first.return_value = movement
        with patch("routes.warehouse.tenant_get_or_404", return_value=wh), \
             patch("routes.warehouse.StockMovement.query", movement_query), \
             patch("routes.warehouse.db.session"):
            resp = warehouse_admin_client.post("/warehouse/5/delete")
        assert resp.status_code in (302, 303)
        assert wh.is_active is False

    def test_delete_hard_delete_when_no_stock(self, warehouse_admin_client):
        wh = _warehouse(6, is_main=False)
        movement_query = MagicMock()
        movement_query.filter_by.return_value.first.return_value = None
        mock_session = MagicMock()
        with patch("routes.warehouse.tenant_get_or_404", return_value=wh), \
             patch("routes.warehouse.StockMovement.query", movement_query), \
             patch("routes.warehouse.db.session", mock_session):
            resp = warehouse_admin_client.post("/warehouse/6/delete")
        mock_session.delete.assert_called_once_with(wh)
        assert resp.status_code in (302, 303)


class TestWarehouseAddStock:
    def test_add_stock_bad_quantity_returns_400(self, warehouse_client):
        with patch("routes.warehouse.tenant_get_or_404", return_value=_product()):
            resp = warehouse_client.post("/warehouse/add-stock/1", data={"quantity": "0"})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_add_stock_success(self, warehouse_client):
        movement = MagicMock()
        movement.product = _product(1)
        with patch("routes.warehouse.tenant_get_or_404", return_value=_product(1)), \
             patch("routes.warehouse.StockService.adjust_stock", return_value=movement), \
             patch("routes.warehouse.db.session"):
            resp = warehouse_client.post("/warehouse/add-stock/1", data={
                "quantity": "5",
                "warehouse_id": "1",
            })
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


class TestWarehouseUploadImage:
    def test_upload_no_file_returns_400(self, warehouse_client, mock_user):
        mock_user.has_permission.side_effect = lambda code: code == "manage_products"
        resp = warehouse_client.post("/warehouse/api/upload_product_image")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_upload_success(self, warehouse_client, mock_user):
        mock_user.has_permission.side_effect = lambda code: code == "manage_products"
        with patch("utils.helpers.save_uploaded_file", return_value="uploads/products/p.jpg"):
            resp = warehouse_client.post(
                "/warehouse/api/upload_product_image",
                data={"file": (BytesIO(b"fake-image"), "p.jpg")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


class TestWarehouseExtended:
    def test_index_category_filter(self, warehouse_client, warehouse_mocks):
        with patch("routes.warehouse.render_template", return_value="idx") as render:
            resp = warehouse_client.get("/warehouse/?category=3&stock=low&page=2")
        assert resp.status_code == 200
        warehouse_mocks["visible_query"].filter_by.assert_called_with(category_id=3)

    def test_index_no_warehouse_ids_uses_current_stock(self, warehouse_client, warehouse_mocks):
        with patch("routes.warehouse.get_accessible_warehouse_ids", return_value=[]), \
             patch("routes.warehouse.render_template", return_value="idx"):
            resp = warehouse_client.get("/warehouse/")
        assert resp.status_code == 200

    def test_movements_product_and_type_filters(self, warehouse_client, warehouse_mocks):
        with patch("routes.warehouse.render_template", return_value="mov"):
            resp = warehouse_client.get("/warehouse/movements?product=5&type=in&warehouse=1")
        assert resp.status_code == 200

    def test_movements_branch_scope_empty_warehouses(self, warehouse_client):
        wh_query = MagicMock()
        wh_query.filter.return_value.all.return_value = []
        with patch("routes.warehouse.branch_scope_id", return_value=2), \
             patch("routes.warehouse.Warehouse.query", wh_query), \
             patch("routes.warehouse.render_template", return_value="mov"):
            resp = warehouse_client.get("/warehouse/movements")
        assert resp.status_code == 200

    def test_view_warehouse_skips_zero_qty(self, warehouse_client):
        wh = _warehouse(1)
        stock_session_query = MagicMock()
        stock_session_query.filter_by.return_value.group_by.return_value.all.return_value = [
            (1, Decimal("0")),
            (2, None),
        ]
        product = _product(2)
        product_query = MagicMock()
        product_query.filter_by.return_value.first.return_value = product
        with patch("routes.warehouse.tenant_get_or_404", return_value=wh), \
             patch("routes.warehouse.db.session.query", return_value=stock_session_query), \
             patch("routes.warehouse.Product.query", product_query), \
             patch("routes.warehouse.render_template", return_value="view") as render:
            resp = warehouse_client.get("/warehouse/1")
        assert resp.status_code == 200
        assert render.call_args[1]["stock"] == []

    def test_create_post_online_warehouse_success(self, warehouse_admin_client, warehouse_mocks):
        wh_query = warehouse_mocks["warehouse_query"]
        wh_query.filter_by.return_value.first.return_value = None
        with patch("routes.warehouse.Warehouse") as wh_cls, \
             patch("routes.warehouse.Warehouse.TYPE_ONLINE", "online"), \
             patch("routes.warehouse.Warehouse.WAREHOUSE_TYPES", ("physical", "online")), \
             patch("routes.warehouse.Warehouse.TYPE_PHYSICAL", "physical"), \
             patch("services.store_service.StoreService.assert_single_online_warehouse"), \
             patch("services.store_service.StoreService.get_tenant_store", return_value=MagicMock(warehouse_id=None)), \
             patch("routes.warehouse.db.session"):
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "Online WH",
                "location": "",
                "warehouse_type": "online",
            })
        assert resp.status_code in (302, 303)

    def test_create_post_invalid_parent(self, warehouse_admin_client, warehouse_mocks):
        wh_query = warehouse_mocks["warehouse_query"]
        wh_query.filter_by.return_value.first.side_effect = [None, None]
        with patch("routes.warehouse.render_template", return_value="create") as render:
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "Child WH",
                "location": "Dubai",
                "parent_id": "99",
            })
        assert resp.status_code == 200
        assert render.called

    def test_create_post_tenant_limit(self, warehouse_admin_client):
        from utils.tenant_limits import TenantLimitError
        with patch("utils.tenant_limits.check_warehouses_limit", side_effect=TenantLimitError("warehouses", 5, 5)), \
             patch("routes.warehouse.render_template", return_value="create"):
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "WH",
                "location": "Dubai",
            })
        assert resp.status_code in (302, 303)

    def test_create_post_value_error(self, warehouse_admin_client):
        with patch("routes.warehouse.atomic_transaction", side_effect=ValueError("bad")), \
             patch("routes.warehouse.render_template", return_value="create"):
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "WH",
                "location": "Dubai",
            })
        assert resp.status_code == 200

    def test_create_post_generic_exception(self, warehouse_admin_client):
        with patch("routes.warehouse.atomic_transaction", side_effect=RuntimeError("fail")), \
             patch("routes.warehouse.render_template", return_value="create"):
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "WH",
                "location": "Dubai",
            })
        assert resp.status_code == 200

    def test_edit_post_generic_exception(self, warehouse_admin_client):
        with patch("routes.warehouse.db.session") as session:
            session.flush.side_effect = RuntimeError("fail")
            with patch("routes.warehouse.render_template", return_value="edit"):
                resp = warehouse_admin_client.post("/warehouse/1/edit", data={
                    "name": "WH",
                    "location": "Dubai",
                })
        assert resp.status_code == 200

    def test_delete_exception(self, warehouse_admin_client):
        wh = _warehouse(7, is_main=False)
        movement_query = MagicMock()
        movement_query.filter_by.return_value.first.return_value = None
        mock_session = MagicMock()
        mock_session.delete.side_effect = RuntimeError("fail")
        with patch("routes.warehouse.tenant_get_or_404", return_value=wh), \
             patch("routes.warehouse.StockMovement.query", movement_query), \
             patch("routes.warehouse.db.session", mock_session), \
             patch("routes.warehouse.render_template", return_value="err"):
            resp = warehouse_admin_client.post("/warehouse/7/delete")
        assert resp.status_code in (302, 303)

    def test_add_stock_auto_warehouse(self, warehouse_client):
        movement = MagicMock()
        movement.product = _product(1)
        wh = _warehouse(1, is_main=True)
        wh_query = _chain_query(first=wh)
        with patch("routes.warehouse.tenant_get_or_404", return_value=_product(1)), \
             patch("routes.warehouse.tenant_query", return_value=wh_query), \
             patch("routes.warehouse.branch_scope_id", return_value=None), \
             patch("routes.warehouse.StockService.adjust_stock", return_value=movement), \
             patch("routes.warehouse.db.session"):
            resp = warehouse_client.post("/warehouse/add-stock/1", data={"quantity": "3"})
        assert resp.status_code == 200

    def test_add_stock_no_warehouse_400(self, warehouse_client):
        empty_query = _chain_query(first=None)
        with patch("routes.warehouse.tenant_get_or_404", return_value=_product(1)), \
             patch("routes.warehouse.tenant_query", return_value=empty_query), \
             patch("routes.warehouse.branch_scope_id", return_value=None):
            resp = warehouse_client.post("/warehouse/add-stock/1", data={"quantity": "2"})
        assert resp.status_code == 400

    def test_add_stock_exception_500(self, warehouse_client):
        with patch("routes.warehouse.tenant_get_or_404", return_value=_product(1)), \
             patch("routes.warehouse.StockService.adjust_stock", side_effect=RuntimeError("fail")), \
             patch("routes.warehouse.ErrorMessages.unexpected_error", return_value="error"):
            resp = warehouse_client.post("/warehouse/add-stock/1", data={
                "quantity": "2",
                "warehouse_id": "1",
            })
        assert resp.status_code == 500

    def test_upload_value_error(self, warehouse_client, mock_user):
        mock_user.has_permission.side_effect = lambda code: code == "manage_products"
        with patch("utils.helpers.save_uploaded_file", side_effect=ValueError("bad type")):
            resp = warehouse_client.post(
                "/warehouse/api/upload_product_image",
                data={"file": (BytesIO(b"x"), "bad.exe")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_upload_server_error(self, warehouse_client, mock_user):
        mock_user.has_permission.side_effect = lambda code: code == "manage_products"
        with patch("utils.helpers.save_uploaded_file", side_effect=RuntimeError("disk")):
            resp = warehouse_client.post(
                "/warehouse/api/upload_product_image",
                data={"file": (BytesIO(b"x"), "p.jpg")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 500

    def test_upload_save_failed_returns_500(self, warehouse_client, mock_user):
        mock_user.has_permission.side_effect = lambda code: code == "manage_products"
        with patch("utils.helpers.save_uploaded_file", return_value=None):
            resp = warehouse_client.post(
                "/warehouse/api/upload_product_image",
                data={"file": (BytesIO(b"x"), "p.jpg")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 500
        assert resp.get_json()["ok"] is False

    def test_index_pagination_iter_pages(self, warehouse_client, warehouse_mocks):
        many = [_product(i) for i in range(1, 21)]
        warehouse_mocks["visible_query"].all.return_value = many
        with patch("routes.warehouse.render_template", return_value="index") as render:
            warehouse_client.get("/warehouse/?page=5&per_page=1")
        pagination = render.call_args[1]["pagination"]
        pages = list(pagination.iter_pages())
        assert None in pages

    def test_view_warehouse_includes_stock(self, warehouse_client):
        wh = _warehouse(1)
        product = _product(2, current_stock=Decimal("12"))
        stock_session_query = MagicMock()
        stock_session_query.filter_by.return_value.group_by.return_value.all.return_value = [
            (2, Decimal("12")),
        ]
        product_query = MagicMock()
        product_query.filter_by.return_value.first.return_value = product
        with patch("routes.warehouse.tenant_get_or_404", return_value=wh), \
             patch("routes.warehouse.db.session.query", return_value=stock_session_query), \
             patch("routes.warehouse.Product.query", product_query), \
             patch("routes.warehouse.render_template", return_value="view") as render:
            resp = warehouse_client.get("/warehouse/1")
        assert resp.status_code == 200
        stock = render.call_args[1]["stock"]
        assert len(stock) == 1
        assert stock[0]["quantity"] == 12.0

    def test_create_post_invalid_warehouse_type_defaults(self, warehouse_admin_client, warehouse_mocks):
        wh_query = warehouse_mocks["warehouse_query"]
        wh_query.filter_by.return_value.first.return_value = None
        with patch("routes.warehouse.Warehouse") as wh_cls, \
             patch("routes.warehouse.Warehouse.WAREHOUSE_TYPES", ("physical", "online")), \
             patch("routes.warehouse.Warehouse.TYPE_PHYSICAL", "physical"), \
             patch("routes.warehouse.Warehouse.TYPE_ONLINE", "online"), \
             patch("routes.warehouse.db.session"):
            wh_cls.return_value = _warehouse(99)
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "Typed WH",
                "location": "Dubai",
                "warehouse_type": "invalid-type",
            })
        assert resp.status_code in (302, 303)

    def test_create_post_inactive_parent(self, warehouse_admin_client, warehouse_mocks):
        parent = _warehouse(50)
        parent.is_active = False
        wh_query = warehouse_mocks["warehouse_query"]
        wh_query.filter_by.return_value.first.return_value = parent
        with patch("routes.warehouse.render_template", return_value="create") as render:
            resp = warehouse_admin_client.post("/warehouse/create", data={
                "name": "Child WH",
                "location": "Dubai",
                "parent_id": "50",
            })
        assert resp.status_code == 200
        assert render.called

    def test_edit_post_invalid_parent(self, warehouse_admin_client):
        with patch("routes.warehouse.render_template", return_value="edit"):
            resp = warehouse_admin_client.post("/warehouse/1/edit", data={
                "name": "Updated WH",
                "location": "Abu Dhabi",
                "parent_id": "999",
            })
        assert resp.status_code in (302, 303)

    def test_add_stock_branch_scoped_auto_warehouse(self, warehouse_client):
        movement = MagicMock()
        movement.product = _product(1)
        main_wh = _warehouse(3, branch_id=2, is_main=True)
        wh_query = MagicMock()
        wh_query.filter_by.return_value.order_by.return_value.first.return_value = main_wh
        wh_query.filter_by.return_value.first.return_value = main_wh
        with patch("routes.warehouse.tenant_get_or_404", return_value=_product(1)), \
             patch("routes.warehouse.branch_scope_id", return_value=2), \
             patch("routes.warehouse.tenant_query", return_value=wh_query), \
             patch("routes.warehouse.StockService.adjust_stock", return_value=movement), \
             patch("routes.warehouse.db.session"):
            resp = warehouse_client.post("/warehouse/add-stock/1", data={"quantity": "3"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
