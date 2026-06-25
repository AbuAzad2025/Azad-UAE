import tempfile
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


def _product(pid=1, name="Widget", sku="SKU-1", barcode="BC-1", min_alert=5, current_stock=10):
    product = MagicMock()
    product.id = pid
    product.name = name
    product.sku = sku
    product.barcode = barcode
    product.regular_price = Decimal("100")
    product.cost_price = Decimal("50")
    product.min_stock_alert = min_alert
    product.current_stock = current_stock
    product.visible_stock = current_stock
    product.tenant_id = 1
    product.is_active = True
    product.partner_shares = MagicMock()
    product.partner_shares.clear = MagicMock()
    product.partner_shares.append = MagicMock()
    product.extra_fields = {}
    product.industry = "general"
    product.unit = "pcs"
    product.stock_movements = _chain_query(all=[])
    product.image_url = None
    return product


def _warehouse(wid=1, name="Main WH", name_ar="مستودع"):
    wh = MagicMock()
    wh.id = wid
    wh.name = name
    wh.name_ar = name_ar
    wh.is_main = True
    wh.is_active = True
    wh.tenant_id = 1
    return wh


def _category(cid=1, name="Cat"):
    cat = MagicMock()
    cat.id = cid
    cat.name = name
    cat.name_ar = None
    cat.description = None
    cat.is_active = True
    cat.tenant_id = 1
    return cat


def _mock_product_form(validate=True, category_id=1):
    form = MagicMock()
    form.validate_on_submit.return_value = validate
    form.category_id.data = category_id
    form.errors = {"name": ["required"]} if not validate else {}
    return form


def _warehouse_query_mock():
    warehouse_query = MagicMock()
    warehouse_query.filter_by.return_value.first.return_value = _warehouse()
    warehouse_query.filter_by.return_value.filter.return_value.first.return_value = None
    return warehouse_query


@contextmanager
def _products_patches(
    products=None,
    branch_scope=None,
    visible_query=None,
    product=None,
    categories=None,
):
    products = products if products is not None else [_product(1), _product(2, name="Other")]
    product = product or products[0]
    categories = categories if categories is not None else [_category()]
    visible_query = visible_query or _chain_query(all=products, count=len(products))

    category_query = MagicMock()
    category_query.filter_by.return_value.all.return_value = categories
    category_query.filter.return_value.first.return_value = None
    category_query.filter_by.return_value.order_by.return_value.all.return_value = categories

    warehouse_query = MagicMock()
    warehouse_query.filter_by.return_value.first.return_value = _warehouse()

    customer_query = _chain_query(all=[])
    session_query = _chain_query(all=[])

    with ExitStack() as stack:
        stack.enter_context(patch("routes.products.StockService.get_visible_products_query", return_value=visible_query))
        stack.enter_context(patch("routes.products.StockService.get_product_stock", return_value=10.0))
        stack.enter_context(patch("routes.products.StockService.adjust_stock"))
        stack.enter_context(patch("routes.products.StockService.add_opening_stock"))
        stack.enter_context(patch("routes.products.tenant_query", return_value=customer_query))
        stack.enter_context(patch("routes.products.tenant_get_or_404", return_value=product))
        stack.enter_context(patch("routes.products.render_template", return_value="ok"))
        session = stack.enter_context(patch("routes.products.db.session"))
        stack.enter_context(patch("routes.products.db.session.query", return_value=session_query))
        stack.enter_context(patch("routes.products.ProductCategory.query", category_query))
        stack.enter_context(patch("routes.products.branch_scope_id", return_value=branch_scope))
        stack.enter_context(patch("routes.products.get_accessible_warehouses", return_value=[_warehouse()]))
        stack.enter_context(patch("routes.products.get_accessible_warehouse_ids", return_value=[1]))
        stack.enter_context(patch("routes.products.ensure_warehouse_access", return_value=_warehouse()))
        stack.enter_context(patch("routes.products.assign_tenant_id"))
        stack.enter_context(patch("routes.products.LoggingCore.log_audit"))
        stack.enter_context(patch("routes.products.get_branch_stock_map", return_value={1: 10.0, 2: 3.0}))
        stack.enter_context(patch("routes.products.should_show_all_branch_columns", return_value=False))
        stack.enter_context(patch("routes.products.get_active_tenant_id", return_value=1))
        stack.enter_context(patch("utils.tenanting.get_active_tenant_id", return_value=1))
        stack.enter_context(patch("routes.products.generate_sku", return_value="AUTO-SKU"))
        stack.enter_context(patch("routes.products.generate_barcode", return_value="AUTO-BC"))
        stack.enter_context(patch("routes.products.save_uploaded_file", return_value="products/img.png"))
        product_query_patch = stack.enter_context(patch("routes.products.Product.query"))
        stack.enter_context(patch("utils.tenant_limits.check_products_limit"))
        yield {
            "visible_query": visible_query,
            "product": product,
            "products": products,
            "category_query": category_query,
            "session": session,
            "customer_query": customer_query,
            "product_query": product_query_patch,
            "warehouse_query": warehouse_query,
        }


@pytest.fixture
def upload_dir():
    path = tempfile.mkdtemp()
    yield path


@pytest.fixture
def products_client(app_factory, bypass_permission_auth, upload_dir):
    from routes.products import products_bp

    app = app_factory(products_bp, config_overrides={"UPLOAD_FOLDER": upload_dir})
    return app.test_client()


class TestProductsAuth:
    def test_unauthenticated_index_returns_401(self, products_client):
        with unauthenticated_client(products_client):
            resp = products_client.get("/products/")
        assert resp.status_code == 401

    def test_forbidden_without_manage_products(self, products_client, mock_user):
        mock_user.has_permission.return_value = False
        with patch("utils.auth_helpers.is_global_owner_user", return_value=False), \
             patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = products_client.get("/products/")
        assert resp.status_code == 403

    def test_view_scope_403_when_out_of_scope(self, products_client):
        with _products_patches() as ctx, \
             patch("routes.products._ensure_product_scope", return_value=False), \
             patch("routes.products.render_template", return_value="denied") as render:
            resp = products_client.get("/products/1")
        assert resp.status_code == 403
        assert render.call_args[0][0] == "errors/403.html"


class TestHelperFunctions:
    @pytest.mark.parametrize("value,expected", [
        ("10.5", 10.5),
        ("", 0.0),
        (None, 0.0),
        ("bad", 0.0),
    ])
    def test_safe_float(self, value, expected):
        from routes.products import safe_float
        assert safe_float(value) == expected

    def test_safe_float_custom_default(self):
        from routes.products import safe_float
        assert safe_float("", default=99.0) == 99.0

    @pytest.mark.parametrize("value,expected", [("5", 5.0), ("0", 0.0)])
    def test_require_float_valid(self, value, expected):
        from routes.products import require_float
        assert require_float(value) == expected

    @pytest.mark.parametrize("value", ["", None, "x"])
    def test_require_float_invalid(self, value):
        from routes.products import require_float
        with pytest.raises(ValueError):
            require_float(value)

    def test_parse_product_partners_empty(self):
        from routes.products import _parse_product_partners
        form = MagicMock()
        form.getlist.side_effect = lambda key: []
        partners, err = _parse_product_partners(form)
        assert partners == []
        assert err is None

    def test_parse_product_partners_incomplete_row(self):
        from routes.products import _parse_product_partners
        form = MagicMock()
        form.getlist.side_effect = lambda key: {
            "partner_customer_id[]": ["1"],
            "partner_percentage[]": [""],
        }.get(key, [])
        partners, err = _parse_product_partners(form)
        assert partners is None
        assert err is not None

    def test_parse_product_partners_duplicate(self, products_client):
        from routes.products import _parse_product_partners
        partner = MagicMock()
        partner.id = 5
        with _products_patches() as ctx:
            ctx["customer_query"].filter.return_value.first.return_value = partner
            form = MagicMock()
            form.getlist.side_effect = lambda key: {
                "partner_customer_id[]": ["5", "5"],
                "partner_percentage[]": ["10", "20"],
            }.get(key, [])
            partners, err = _parse_product_partners(form)
        assert partners is None
        assert "تكرار" in err

    def test_parse_product_partners_total_over_100(self, products_client):
        from routes.products import _parse_product_partners
        partner = MagicMock()
        partner.id = 5
        with _products_patches() as ctx:
            ctx["customer_query"].filter.return_value.first.return_value = partner
            form = MagicMock()
            form.getlist.side_effect = lambda key: {
                "partner_customer_id[]": ["5", "6"],
                "partner_percentage[]": ["60", "50"],
            }.get(key, [])
            partners, err = _parse_product_partners(form)
        assert partners is None
        assert "100" in err


class TestImportTemplate:
    def test_download_import_template_returns_excel(self, products_client):
        resp = products_client.get("/products/import-template")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.mimetype

    def test_download_import_template_failure_redirects(self, products_client):
        with patch("pandas.DataFrame", side_effect=RuntimeError("fail")):
            resp = products_client.get("/products/import-template")
        assert resp.status_code == 302
        assert resp.location.endswith("/products/import")


class TestImportProducts:
    def test_import_get_renders(self, products_client):
        with _products_patches(), patch("routes.products.render_template", return_value="import") as render:
            resp = products_client.get("/products/import")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/import.html"

    def test_import_post_no_file(self, products_client):
        with _products_patches():
            resp = products_client.post("/products/import", data={})
        assert resp.status_code == 302

    def test_import_post_empty_filename(self, products_client):
        with _products_patches():
            resp = products_client.post(
                "/products/import",
                data={"file": (BytesIO(b""), "")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_import_post_unsupported_extension(self, products_client, upload_dir):
        with _products_patches():
            resp = products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"data"), "bad.txt")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_import_post_missing_columns(self, products_client, upload_dir):
        import pandas as pd

        df = pd.DataFrame({"foo": [1]})
        with _products_patches(), patch("models.Warehouse.query", _warehouse_query_mock()):
            with patch("pandas.read_excel", return_value=df), \
                 patch("pandas.read_csv", return_value=df):
                resp = products_client.post(
                    "/products/import",
                    data={"file": (BytesIO(b"x"), "products.xlsx")},
                    content_type="multipart/form-data",
                )
        assert resp.status_code == 302

    def test_import_post_success_new_product(self, products_client, upload_dir):
        import pandas as pd

        df = pd.DataFrame({
            "name": ["New Product"],
            "price": [25.0],
            "stock": [5.0],
        })
        wh_query = _warehouse_query_mock()
        with _products_patches() as ctx:
            ctx["product_query"].filter.return_value.first.return_value = None
            with patch("models.Warehouse.query", wh_query), \
                 patch("pandas.read_excel", return_value=df):
                resp = products_client.post(
                    "/products/import",
                    data={"file": (BytesIO(b"x"), "products.xlsx")},
                    content_type="multipart/form-data",
                )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/")

    def test_import_post_duplicate_without_update(self, products_client, upload_dir):
        import pandas as pd

        df = pd.DataFrame({"name": ["Dup"], "price": [10.0]})
        existing = _product(name="Dup")
        with _products_patches() as ctx:
            ctx["product_query"].filter.return_value.first.return_value = existing
            with patch("models.Warehouse.query", _warehouse_query_mock()), \
                 patch("pandas.read_excel", return_value=df):
                resp = products_client.post(
                    "/products/import",
                    data={"file": (BytesIO(b"x"), "products.xlsx")},
                    content_type="multipart/form-data",
                )
        assert resp.status_code == 302

    def test_import_post_update_existing(self, products_client, upload_dir):
        import pandas as pd

        df = pd.DataFrame({"name": ["Existing"], "price": [15.0], "stock": [20.0]})
        existing = _product(name="Existing")
        existing.current_stock = 10
        with _products_patches() as ctx:
            ctx["product_query"].filter.return_value.first.return_value = existing
            with patch("models.Warehouse.query", _warehouse_query_mock()), \
                 patch("pandas.read_excel", return_value=df):
                resp = products_client.post(
                    "/products/import",
                    data={
                        "file": (BytesIO(b"x"), "products.xlsx"),
                        "update_existing": "1",
                    },
                    content_type="multipart/form-data",
                )
        assert resp.status_code == 302


class TestImportGrid:
    def test_import_grid_success(self, products_client):
        with _products_patches() as ctx, patch("models.Warehouse.query", _warehouse_query_mock()):
            resp = products_client.post(
                "/products/import-grid",
                data={
                    "name[]": ["Grid Item"],
                    "price[]": ["12"],
                    "cost[]": ["6"],
                    "stock[]": ["3"],
                    "sku[]": [""],
                    "barcode[]": [""],
                },
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/")
        ctx["session"].commit.assert_called()

    def test_import_grid_skips_empty_names(self, products_client):
        with _products_patches(), patch("models.Warehouse.query", _warehouse_query_mock()):
            resp = products_client.post(
                "/products/import-grid",
                data={"name[]": ["", "  "], "price[]": ["1", "2"]},
            )
        assert resp.status_code == 302


class TestProductsIndex:
    def test_index_non_scoped_paginate(self, products_client):
        items = [_product(1), _product(2)]
        query = _chain_query(all=items, count=2)
        with _products_patches(products=items, visible_query=query, branch_scope=None) as ctx, \
             patch("routes.products.render_template", return_value="index") as render:
            resp = products_client.get("/products/?page=1&per_page=10")
        assert resp.status_code == 200
        assert render.call_args[1]["products"] == items

    def test_index_branch_scoped_pagination(self, products_client):
        items = [_product(i, current_stock=i * 5) for i in range(1, 6)]
        query = _chain_query(all=items)
        with _products_patches(products=items, visible_query=query, branch_scope=2) as ctx, \
             patch("routes.products.render_template", return_value="index") as render, \
             patch("routes.products.get_branch_stock_map", return_value={i: float(i) for i in range(1, 6)}):
            resp = products_client.get("/products/?page=2&per_page=2")
        assert resp.status_code == 200
        pagination = render.call_args[1]["pagination"]
        assert pagination.page == 2
        assert pagination.per_page == 2
        assert len(render.call_args[1]["products"]) == 2

    def test_index_search_filter(self, products_client):
        query = _chain_query(all=[_product()])
        with _products_patches(visible_query=query) as ctx:
            resp = products_client.get("/products/?search=widget")
        assert resp.status_code == 200
        ctx["visible_query"].filter.assert_called()

    def test_index_category_filter(self, products_client):
        query = _chain_query(all=[_product()])
        with _products_patches(visible_query=query) as ctx:
            resp = products_client.get("/products/?category=3")
        assert resp.status_code == 200
        ctx["visible_query"].filter_by.assert_called_with(category_id=3)

    def test_index_low_stock_filter_non_scoped(self, products_client):
        query = _chain_query(all=[_product()])
        with _products_patches(visible_query=query, branch_scope=None):
            resp = products_client.get("/products/?stock=low")
        assert resp.status_code == 200
        query.filter.assert_called()

    def test_index_out_stock_filter_branch_scoped(self, products_client):
        items = [
            _product(1, current_stock=0),
            _product(2, current_stock=10),
        ]
        query = _chain_query(all=items)
        with _products_patches(products=items, visible_query=query, branch_scope=1), \
             patch("routes.products.get_branch_stock_map", return_value={1: 0.0, 2: 5.0}), \
             patch("routes.products.render_template", return_value="index") as render:
            resp = products_client.get("/products/?stock=out")
        assert resp.status_code == 200
        page_products = render.call_args[1]["products"]
        assert all((p.visible_stock or 0) <= 0 for p in page_products)

    def test_index_show_branch_columns(self, products_client):
        items = [_product()]
        query = _chain_query(all=items)
        session_rows = [(1, "WH", "مستودع", "Branch", "B1")]
        session_query = MagicMock()
        session_query.join.return_value.outerjoin.return_value.filter.return_value.filter.return_value.all.return_value = session_rows
        with _products_patches(products=items, visible_query=query), \
             patch("routes.products.should_show_all_branch_columns", return_value=True), \
             patch("routes.products.db.session.query", return_value=session_query), \
             patch("routes.products.render_template", return_value="index"):
            resp = products_client.get("/products/")
        assert resp.status_code == 200


class TestProductsCreate:
    def test_create_get(self, products_client):
        form = _mock_product_form()
        with _products_patches(), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.render_template", return_value="create") as render:
            resp = products_client.get("/products/create")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/create.html"

    def test_create_post_validation_failure(self, products_client):
        form = _mock_product_form(validate=False)
        with _products_patches(), patch("forms.product.ProductForm", return_value=form):
            resp = products_client.post("/products/create", data={"name": ""})
        assert resp.status_code == 200

    def test_create_post_missing_warehouse(self, products_client):
        form = _mock_product_form(validate=True)
        with _products_patches(), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.render_template", return_value="create") as render:
            resp = products_client.post(
                "/products/create",
                data={"name": "New", "regular_price": "10", "warehouse_id": ""},
            )
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/create.html"

    def test_create_post_invalid_warehouse(self, products_client):
        form = _mock_product_form(validate=True)
        with _products_patches(), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.ensure_warehouse_access", side_effect=ValueError("bad")), \
             patch("routes.products.render_template", return_value="create") as render:
            resp = products_client.post(
                "/products/create",
                data={"name": "New", "regular_price": "10", "warehouse_id": "99"},
            )
        assert resp.status_code == 200

    def test_create_post_tenant_limit(self, products_client):
        from utils.tenant_limits import TenantLimitError

        form = _mock_product_form(validate=True)
        with _products_patches(), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("utils.tenant_limits.check_products_limit", side_effect=TenantLimitError("products", 10, 10)):
            resp = products_client.post(
                "/products/create",
                data={"name": "New", "regular_price": "10", "warehouse_id": "1"},
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/create")

    def test_create_post_success(self, products_client):
        form = _mock_product_form(validate=True)
        added_product = MagicMock()
        added_product.id = 99
        added_product.name = "Created"
        added_product.tenant_id = 1
        added_product.partner_shares = MagicMock()
        added_product.partner_shares.append = MagicMock()

        session = MagicMock()
        session.flush.side_effect = lambda: setattr(added_product, "id", 99)

        with _products_patches() as ctx, \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.Product", return_value=added_product), \
             patch("routes.products.db.session", session), \
             patch("routes.products.LoggingCore.log_audit") as log_audit:
            resp = products_client.post(
                "/products/create",
                data={
                    "name": "Created",
                    "regular_price": "100",
                    "warehouse_id": "1",
                    "current_stock": "5",
                    "sku": "NEW-SKU",
                },
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/")
        log_audit.assert_called_with("create", "products", 99)
        session.commit.assert_called()


class TestProductsViewEditDelete:
    def test_view_success(self, products_client):
        product = _product()
        with _products_patches(product=product) as ctx, \
             patch("routes.products.render_template", return_value="view") as render:
            resp = products_client.get("/products/1")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/view.html"
        assert render.call_args[1]["product"] is product

    def test_view_branch_scoped_movements(self, products_client):
        product = _product()
        movements = _chain_query(all=[])
        product.stock_movements = movements
        with _products_patches(product=product, branch_scope=2):
            resp = products_client.get("/products/1")
        assert resp.status_code == 200
        movements.filter.assert_called()

    def test_edit_get(self, products_client):
        form = _mock_product_form()
        product = _product()
        with _products_patches(product=product), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.render_template", return_value="edit") as render:
            resp = products_client.get("/products/1/edit")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/edit.html"

    def test_edit_post_negative_stock(self, products_client):
        form = _mock_product_form(validate=True)
        product = _product()
        with _products_patches(product=product), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.render_template", return_value="edit") as render:
            resp = products_client.post(
                "/products/1/edit",
                data={"name": "X", "current_stock": "-1", "regular_price": "10"},
            )
        assert resp.status_code == 200

    def test_edit_post_success(self, products_client, mock_user):
        form = _mock_product_form(validate=True)
        product = _product()
        mock_user.can_see_costs.return_value = False
        with _products_patches(product=product) as ctx, \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.StockService.get_product_stock", return_value=10.0), \
             patch("routes.products.LoggingCore.log_audit") as log_audit, \
             patch("models.ProductPriceTier") as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = products_client.post(
                "/products/1/edit",
                data={
                    "name": "Updated",
                    "regular_price": "120",
                    "cost_price": "50",
                    "current_stock": "10",
                    "warehouse_id": "1",
                },
            )
        assert resp.status_code == 302
        assert "/products/1" in resp.location
        log_audit.assert_called_with("update", "products", 1)

    def test_delete_with_stock_blocked(self, products_client):
        product = _product()
        with _products_patches(product=product), \
             patch("routes.products.StockService.get_product_stock", return_value=5.0):
            resp = products_client.post("/products/1/delete")
        assert resp.status_code == 302
        assert resp.location.endswith("/products/1")

    def test_delete_soft_when_sales_exist(self, products_client):
        product = _product()
        sl = MagicMock()
        pl = MagicMock()
        sl.query.filter_by.return_value.filter.return_value.count.return_value = 2
        pl.query.filter_by.return_value.filter.return_value.count.return_value = 0
        with _products_patches(product=product) as ctx, \
             patch("routes.products.StockService.get_product_stock", return_value=0.0), \
             patch("models.SaleLine", sl), \
             patch("models.PurchaseLine", pl), \
             patch("routes.products.LoggingCore.log_audit") as log_audit:
            resp = products_client.post("/products/1/delete")
        assert resp.status_code == 302
        assert product.is_active is False
        log_audit.assert_called_with("deactivate", "products", 1)

    def test_delete_hard_when_no_links(self, products_client):
        product = _product()
        sl = MagicMock()
        pl = MagicMock()
        sl.query.filter_by.return_value.filter.return_value.count.return_value = 0
        pl.query.filter_by.return_value.filter.return_value.count.return_value = 0
        with _products_patches(product=product) as ctx, \
             patch("routes.products.StockService.get_product_stock", return_value=0.0), \
             patch("models.SaleLine", sl), \
             patch("models.PurchaseLine", pl), \
             patch("routes.products.LoggingCore.log_audit") as log_audit:
            resp = products_client.post("/products/1/delete")
        assert resp.status_code == 302
        ctx["session"].delete.assert_called_with(product)
        log_audit.assert_called_with("delete", "products", 1)


class TestApiSearch:
    def test_api_search_with_query(self, products_client):
        items = [_product(1, name="Alpha")]
        query = _chain_query(all=items)
        with _products_patches(products=items, visible_query=query):
            resp = products_client.get("/products/api/search?q=alp")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "Alpha"

    def test_api_search_empty_query(self, products_client):
        items = [_product()]
        query = _chain_query(all=items)
        with _products_patches(products=items, visible_query=query):
            resp = products_client.get("/products/api/search")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_api_search_with_warehouse_id(self, products_client):
        items = [_product()]
        query = _chain_query(all=items)
        with _products_patches(products=items, visible_query=query), \
             patch("routes.products.get_branch_stock_map", return_value={1: 42.0}):
            resp = products_client.get("/products/api/search?q=a&warehouse_id=1")
        assert resp.status_code == 200
        assert resp.get_json()[0]["stock"] == 42.0


class TestCategories:
    def test_categories_list(self, products_client):
        cats = [_category(1), _category(2, name="B")]
        category_query = MagicMock()
        category_query.filter_by.return_value.order_by.return_value.all.return_value = cats
        with _products_patches(categories=cats), \
             patch("routes.products.ProductCategory.query", category_query), \
             patch("routes.products.render_template", return_value="cats") as render:
            resp = products_client.get("/products/categories")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/categories.html"

    def test_create_category_form_success(self, products_client):
        new_cat = _category(10, name="Fresh")
        with _products_patches() as ctx:
            ctx["category_query"].filter.return_value.first.return_value = None
            ctx["session"].add = MagicMock()
            with patch("routes.products.ProductCategory", return_value=new_cat):
                resp = products_client.post(
                    "/products/categories/create",
                    data={"name": "Fresh", "name_ar": "جديد"},
                )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/categories")

    def test_create_category_json_missing_name(self, products_client):
        with _products_patches():
            resp = products_client.post(
                "/products/categories/create",
                json={"name_ar": "only"},
            )
        assert resp.status_code == 400

    def test_create_category_json_duplicate(self, products_client):
        with _products_patches() as ctx:
            ctx["category_query"].filter.return_value.first.return_value = _category()
            resp = products_client.post(
                "/products/categories/create",
                json={"name": "Dup"},
            )
        assert resp.status_code == 400

    def test_create_category_json_success(self, products_client):
        new_cat = _category(11, name="JSON Cat")
        pc_class = MagicMock()
        pc_class.query.filter.return_value.first.return_value = None
        pc_class.return_value = new_cat
        with _products_patches() as ctx, patch("routes.products.ProductCategory", pc_class):
            resp = products_client.post(
                "/products/categories/create",
                json={"name": "JSON Cat"},
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True


class TestAdjustStock:
    def test_adjust_stock_add(self, products_client):
        with _products_patches():
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "add", "quantity": "5", "warehouse_id": "1"},
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["new_stock"] == 15.0

    def test_adjust_stock_subtract(self, products_client):
        with _products_patches():
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "subtract", "quantity": "3", "warehouse_id": "1"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["new_stock"] == 7.0

    def test_adjust_stock_set(self, products_client):
        with _products_patches():
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "set", "quantity": "25", "warehouse_id": "1"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["new_stock"] == 25.0

    def test_adjust_stock_invalid_quantity(self, products_client):
        with _products_patches():
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "add", "quantity": "bad", "warehouse_id": "1"},
            )
        assert resp.status_code == 422

    def test_adjust_stock_subtract_insufficient(self, products_client):
        with _products_patches(), \
             patch("routes.products._get_alternative_warehouses", return_value=[]):
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "subtract", "quantity": "999", "warehouse_id": "1"},
            )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["insufficient"] is True

    def test_adjust_stock_branch_requires_warehouse(self, products_client):
        with _products_patches(branch_scope=2), \
             patch("routes.products.get_accessible_warehouses", return_value=[_warehouse(1), _warehouse(2)]):
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "add", "quantity": "1"},
            )
        assert resp.status_code == 400

    def test_adjust_stock_scope_403(self, products_client):
        with _products_patches(), patch("routes.products._ensure_product_scope", return_value=False):
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "add", "quantity": "1", "warehouse_id": "1"},
            )
        assert resp.status_code == 403


class TestPrintLabels:
    def test_print_label(self, app_factory, bypass_permission_auth):
        from routes.products import products_bp

        product = _product()
        app = app_factory(products_bp)
        client = app.test_client()
        with patch("routes.products.tenant_get_or_404", return_value=product), \
             patch("services.label_print_service.get_single_label_html", return_value="<html>label</html>") as label:
            resp = client.get("/products/1/print-label")
        assert resp.status_code == 200
        assert b"label" in resp.data
        label.assert_called_once()

    def test_print_labels_post_json(self, app_factory, bypass_permission_auth):
        from routes.products import products_bp

        app = app_factory(products_bp)
        client = app.test_client()
        with patch("services.label_print_service.get_product_labels_html", return_value="<html>labels</html>") as labels:
            resp = client.post("/products/print-labels", json={"product_ids": [1, 2]})
        assert resp.status_code == 200
        labels.assert_called_once()

    def test_print_labels_post_empty_redirects(self, products_client):
        with _products_patches():
            resp = products_client.post("/products/print-labels", data={})
        assert resp.status_code == 302
        assert resp.location.endswith("/products/")

    def test_print_labels_forbidden_without_view_products(self, products_client, mock_user):
        mock_user.has_permission.side_effect = lambda perm: perm != "view_products"
        with patch("utils.auth_helpers.is_global_owner_user", return_value=False), \
             patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = products_client.get("/products/1/print-label")
        assert resp.status_code == 403


class TestProductsExtendedCoverage:
    def test_index_branch_low_stock_filter(self, products_client):
        items = [
            _product(1, min_alert=10, current_stock=5),
            _product(2, min_alert=5, current_stock=20),
        ]
        query = _chain_query(all=items)
        with _products_patches(products=items, visible_query=query, branch_scope=1), \
             patch("routes.products.get_branch_stock_map", return_value={1: 3.0, 2: 20.0}), \
             patch("routes.products.render_template", return_value="index") as render:
            resp = products_client.get("/products/?stock=low")
        assert resp.status_code == 200
        page_products = render.call_args[1]["products"]
        assert len(page_products) == 1

    def test_import_csv_file(self, products_client, upload_dir):
        import pandas as pd

        df = pd.DataFrame({"name": ["Csv Product"], "price": [9.0], "warranty": ["30"], "category": ["Tools"]})
        new_cat = _category(5, name="Tools")
        pc_class = MagicMock()
        pc_class.query.filter_by.return_value.filter.return_value.first.return_value = None
        pc_class.return_value = new_cat
        new_product = MagicMock()
        new_product.id = 88
        with _products_patches() as ctx:
            ctx["product_query"].filter.return_value.first.return_value = None
            with patch("models.Warehouse.query", _warehouse_query_mock()), \
                 patch("pandas.read_csv", return_value=df), \
                 patch("routes.products.ProductCategory", pc_class), \
                 patch("routes.products.Product", return_value=new_product):
                resp = products_client.post(
                    "/products/import",
                    data={"file": (BytesIO(b"a,b\n1,2"), "products.csv")},
                    content_type="multipart/form-data",
                )
        assert resp.status_code == 302

    def test_import_row_exception_and_cleanup(self, products_client, upload_dir):
        import pandas as pd

        df = pd.DataFrame({"name": ["Bad Row"], "price": ["not-a-number"]})
        with _products_patches() as ctx:
            ctx["product_query"].filter.return_value.first.return_value = None
            with patch("models.Warehouse.query", _warehouse_query_mock()), \
                 patch("pandas.read_excel", return_value=df):
                resp = products_client.post(
                    "/products/import",
                    data={"file": (BytesIO(b"x"), "products.xlsx")},
                    content_type="multipart/form-data",
                )
        assert resp.status_code == 302

    def test_import_grid_row_error(self, products_client):
        with _products_patches(), \
             patch("models.Warehouse.query", _warehouse_query_mock()), \
             patch("routes.products.Product", side_effect=RuntimeError("boom")):
            resp = products_client.post(
                "/products/import-grid",
                data={"name[]": ["Broken"], "price[]": ["1"]},
            )
        assert resp.status_code == 302

    def test_create_post_with_partners_image_and_tiers(self, products_client):
        form = _mock_product_form(validate=True)
        added = _product(99, name="Rich")
        added.partner_shares = MagicMock()
        added.partner_shares.append = MagicMock()
        session = MagicMock()
        merchant = MagicMock()
        merchant.id = 7
        partner = MagicMock()
        partner.id = 8
        customer_query = _chain_query(all=[])
        customer_query.filter.return_value.first.side_effect = [merchant, partner]

        with _products_patches() as ctx, \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.Product", return_value=added), \
             patch("routes.products.db.session", session), \
             patch("routes.products.tenant_query", return_value=customer_query), \
             patch("routes.products.ProductPartner") as pp_cls, \
             patch("models.ProductPriceTier") as tier_cls:
            pp_cls.return_value = MagicMock()
            tier_cls.return_value = MagicMock()
            resp = products_client.post(
                "/products/create",
                data={
                    "name": "Rich",
                    "regular_price": "100",
                    "warehouse_id": "1",
                    "current_stock": "2",
                    "merchant_customer_id": "7",
                    "partner_customer_id[]": ["8"],
                    "partner_percentage[]": ["25"],
                    "tier_wholesale_price": "90",
                    "warranty_days": "365",
                    "has_serial_number": "on",
                    "extra_color": "red",
                    "image": (BytesIO(b"img"), "photo.png"),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        session.commit.assert_called()

    def test_create_post_invalid_merchant(self, products_client):
        form = _mock_product_form(validate=True)
        customer_query = _chain_query(all=[])
        customer_query.filter.return_value.first.return_value = None
        with _products_patches(), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.tenant_query", return_value=customer_query), \
             patch("routes.products.render_template", return_value="create") as render:
            resp = products_client.post(
                "/products/create",
                data={
                    "name": "X",
                    "regular_price": "10",
                    "warehouse_id": "1",
                    "merchant_customer_id": "999",
                },
            )
        assert resp.status_code == 200

    def test_create_post_exception_rollback(self, products_client):
        form = _mock_product_form(validate=True)
        session = MagicMock()
        session.commit.side_effect = RuntimeError("db fail")
        with _products_patches(), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.Product", return_value=_product()), \
             patch("routes.products.db.session", session), \
             patch("routes.products.render_template", return_value="create"):
            resp = products_client.post(
                "/products/create",
                data={"name": "X", "regular_price": "10", "warehouse_id": "1"},
            )
        assert resp.status_code == 200

    def test_edit_post_cost_change_blocked(self, products_client, mock_user):
        form = _mock_product_form(validate=True)
        product = _product()
        mock_user.can_see_costs.return_value = True
        with _products_patches(product=product), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.StockService.get_product_stock", return_value=5.0), \
             patch("routes.products.render_template", return_value="edit") as render, \
             patch("models.ProductPriceTier") as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = products_client.post(
                "/products/1/edit",
                data={"name": "X", "regular_price": "10", "cost_price": "99", "current_stock": "5"},
            )
        assert resp.status_code == 200

    def test_edit_post_branch_stock_without_warehouse(self, products_client):
        form = _mock_product_form(validate=True)
        product = _product()
        with _products_patches(product=product, branch_scope=2), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.StockService.get_product_stock", return_value=5.0), \
             patch("routes.products.render_template", return_value="edit") as render, \
             patch("models.ProductPriceTier") as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = products_client.post(
                "/products/1/edit",
                data={"name": "X", "regular_price": "10", "current_stock": "8"},
            )
        assert resp.status_code == 200

    def test_edit_post_with_image_and_existing_tier(self, products_client, mock_user):
        form = _mock_product_form(validate=True)
        product = _product()
        mock_user.can_see_costs.return_value = False
        existing_tier = MagicMock()
        existing_tier.price = 80
        existing_tier.is_active = True
        with _products_patches(product=product), \
             patch("forms.product.ProductForm", return_value=form), \
             patch("routes.products.StockService.get_product_stock", return_value=10.0), \
             patch("models.ProductPriceTier") as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = existing_tier
            resp = products_client.post(
                "/products/1/edit",
                data={
                    "name": "Img",
                    "regular_price": "10",
                    "current_stock": "10",
                    "warehouse_id": "1",
                    "tier_retail_price": "0",
                    "image": (BytesIO(b"img"), "pic.png"),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_delete_json_with_stock_error(self, products_client):
        product = _product()
        with _products_patches(product=product), \
             patch("routes.products.StockService.get_product_stock", return_value=3.0):
            resp = products_client.post(
                "/products/1/delete",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_delete_exception_json(self, products_client):
        product = _product()
        sl = MagicMock()
        pl = MagicMock()
        sl.query.filter_by.return_value.filter.return_value.count.return_value = 0
        pl.query.filter_by.return_value.filter.return_value.count.return_value = 0
        session = MagicMock()
        session.commit.side_effect = RuntimeError("fail")
        with _products_patches(product=product), \
             patch("routes.products.StockService.get_product_stock", return_value=0.0), \
             patch("routes.products.db.session", session), \
             patch("models.SaleLine", sl), \
             patch("models.PurchaseLine", pl):
            resp = products_client.post(
                "/products/1/delete",
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_create_category_form_exception(self, products_client):
        session = MagicMock()
        session.commit.side_effect = RuntimeError("db")
        pc_class = MagicMock()
        pc_class.query.filter.return_value.first.return_value = None
        with _products_patches(), \
             patch("routes.products.db.session", session), \
             patch("routes.products.ProductCategory", pc_class):
            resp = products_client.post(
                "/products/categories/create",
                data={"name": "Fail Cat"},
            )
        assert resp.status_code == 302

    def test_adjust_stock_branch_single_warehouse(self, products_client):
        wh = _warehouse(3)
        with _products_patches(branch_scope=2), \
             patch("routes.products.get_accessible_warehouses", return_value=[wh]), \
             patch("routes.products.StockService.get_product_stock", return_value=4.0):
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "add", "quantity": "1"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["new_stock"] == 5.0

    def test_adjust_stock_zero_quantity(self, products_client):
        with _products_patches():
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "add", "quantity": "0", "warehouse_id": "1"},
            )
        assert resp.status_code == 400

    def test_adjust_stock_subtract_alternatives_exception(self, products_client):
        with _products_patches(), \
             patch("routes.products._get_alternative_warehouses", side_effect=RuntimeError("alt fail")):
            resp = products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "subtract", "quantity": "999", "warehouse_id": "1"},
            )
        assert resp.status_code == 400
        assert resp.get_json()["alternative_locations"] == []

    def test_annotate_visible_stock_no_warehouses(self):
        from routes.products import _annotate_visible_stock

        product = _product(current_stock=7)
        with patch("routes.products.get_accessible_warehouse_ids", return_value=[]):
            result = _annotate_visible_stock([product])
        assert result[0].visible_stock == 7

    def test_annotate_branch_info_empty_products(self):
        from routes.products import _annotate_branch_and_warehouse_info

        assert _annotate_branch_and_warehouse_info([], [1]) == []

    def test_get_alternative_warehouses(self, app_factory, bypass_permission_auth):
        from routes.products import products_bp, _get_alternative_warehouses

        app = app_factory(products_bp)
        wh = _warehouse(2, name="Alt")
        with app.app_context(), \
             patch("routes.products.get_accessible_warehouses", return_value=[wh]), \
             patch("routes.products.StockService.get_product_stock", return_value=12.0):
            result = _get_alternative_warehouses(1, 1)
        assert result[0]["warehouse_id"] == 2
        assert result[0]["available_stock"] == 12.0

    def test_parse_product_partners_invalid_partner_id(self):
        from routes.products import _parse_product_partners

        form = MagicMock()
        form.getlist.side_effect = lambda key: {
            "partner_customer_id[]": ["bad"],
            "partner_percentage[]": ["10"],
        }.get(key, [])
        partners, err = _parse_product_partners(form)
        assert partners is None

    def test_parse_product_partners_missing_customer(self, products_client):
        from routes.products import _parse_product_partners

        with _products_patches() as ctx:
            ctx["customer_query"].filter.return_value.first.return_value = None
            form = MagicMock()
            form.getlist.side_effect = lambda key: {
                "partner_customer_id[]": ["9"],
                "partner_percentage[]": ["10"],
            }.get(key, [])
            partners, err = _parse_product_partners(form)
        assert partners is None
        assert "غير موجود" in err

    def test_print_label_with_branch_scope(self, app_factory, bypass_permission_auth):
        from routes.products import products_bp

        product = _product()
        app = app_factory(products_bp)
        client = app.test_client()
        with patch("routes.products.tenant_get_or_404", return_value=product), \
             patch("utils.branching.report_branch_scope_id", return_value=3, create=True), \
             patch("services.label_print_service.get_single_label_html", return_value="html") as label:
            resp = client.get("/products/1/print-label")
        assert resp.status_code == 200
        assert label.call_args[1]["branch_id"] == 3

    def test_print_labels_form_post(self, app_factory, bypass_permission_auth):
        from routes.products import products_bp

        app = app_factory(products_bp)
        client = app.test_client()
        with patch("services.label_print_service.get_product_labels_html", return_value="batch") as labels:
            resp = client.post("/products/print-labels", data={"product_ids": ["1", "2"]})
        assert resp.status_code == 200
        labels.assert_called_once()

    def test_scoped_customers_query_with_branch(self, app_factory, bypass_permission_auth):
        from routes.products import _scoped_customers_query, products_bp

        app = app_factory(products_bp)
        query = _chain_query(all=[])
        with app.app_context(), \
             patch("routes.products.branch_scope_id", return_value=5), \
             patch("routes.products.tenant_query", return_value=query):
            result = _scoped_customers_query("merchant")
        assert result is query
