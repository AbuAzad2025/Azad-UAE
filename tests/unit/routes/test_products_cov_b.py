"""Coverage boost B for routes/products.py — create/edit/category/delete/adjust."""

import tempfile
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

import routes.products as products_mod
from tests.unit.routes.conftest import _chain_query


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


def _mock_product_form(validate=True, category_id=1, price=10.0):
    form = MagicMock()
    form.validate_on_submit.return_value = validate
    form.category_id.data = category_id
    form.regular_price.data = price
    form.errors = {"name": ["required"]} if not validate else {}
    return form


def _orm_column():
    col = MagicMock()
    col.ilike = MagicMock(return_value=MagicMock())
    eq_expr = MagicMock()
    eq_expr.__or__ = MagicMock(return_value=MagicMock())
    col.__eq__ = MagicMock(return_value=eq_expr)
    col.__le__ = MagicMock(return_value=MagicMock())
    return col


def _product_class_mock(product_query_mock=None):
    if product_query_mock is None:
        product_query_mock = MagicMock()
    inner = MagicMock()
    inner.filter.return_value = inner
    inner.first.return_value = None
    product_query_mock.filter.return_value = inner
    product_query_mock.filter_by.return_value.count.return_value = 0
    cls = MagicMock()
    cls.query = product_query_mock
    for attr in ("name", "sku", "barcode", "current_stock", "min_stock_alert", "tenant_id"):
        setattr(cls, attr, _orm_column())

    def _construct(*_args, **kwargs):
        product = MagicMock()
        product.id = 99
        for key, value in kwargs.items():
            setattr(product, key, value)
        return product

    cls.side_effect = _construct
    return cls, product_query_mock


@contextmanager
def _products_patches(products=None, branch_scope=None, visible_query=None, product=None, categories=None):
    products = products if products is not None else [_product(1), _product(2, name="Other")]
    product = product or products[0]
    categories = categories if categories is not None else [_category()]
    visible_query = visible_query or _chain_query(all=products, count=len(products))

    category_query = MagicMock()
    category_query.filter_by.return_value.all.return_value = categories
    category_query.filter.return_value.first.return_value = None
    category_query.filter_by.return_value.order_by.return_value.all.return_value = categories
    session_query = _chain_query(all=[])
    find_scoped_customer = MagicMock(return_value=None)
    scoped_customers = MagicMock(return_value=[])

    with ExitStack() as stack:
        product_cls, product_query_mock = _product_class_mock()
        stack.enter_context(
            patch("routes.products.StockService.get_visible_products_query", return_value=visible_query)
        )
        stack.enter_context(patch("routes.products.StockService.get_product_stock", return_value=10.0))
        stack.enter_context(patch("routes.products.StockService.adjust_stock"))
        stack.enter_context(patch("routes.products.StockService.add_opening_stock"))
        stack.enter_context(patch("routes.products.ProductService.find_scoped_customer", find_scoped_customer))
        stack.enter_context(patch("routes.products.ProductService.scoped_customers", scoped_customers))
        stack.enter_context(patch("routes.products.ProductService.tenant_business_type", return_value="general"))
        stack.enter_context(patch("routes.products.ProductService.get_price_tier", return_value=None))
        stack.enter_context(patch("routes.products.tenant_get_or_404", return_value=product))
        stack.enter_context(patch("routes.products.render_template", return_value="ok"))
        session = stack.enter_context(patch("routes.products.db.session"))
        stack.enter_context(patch("routes.products.db.session.query", return_value=session_query))
        stack.enter_context(
            patch(
                "routes.products.ProductService.list_active_categories",
                side_effect=lambda tid, ordered=False: (
                    category_query.filter_by.return_value.order_by.return_value.all.return_value
                    if ordered
                    else category_query.filter_by.return_value.all.return_value
                ),
            )
        )
        stack.enter_context(
            patch(
                "routes.products.ProductService.category_name_taken",
                side_effect=lambda tid, name, exclude_id=None: (
                    category_query.filter.return_value.first.return_value is not None
                ),
            )
        )
        stack.enter_context(
            patch(
                "routes.products.ProductService.count_products_in_category",
                side_effect=lambda tid, cid: product_query_mock.filter_by.return_value.count.return_value,
            )
        )
        stack.enter_context(patch.object(products_mod, "Product", product_cls))
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
        stack.enter_context(patch("routes.products.db.or_", return_value=MagicMock(name="sql_or")))
        stack.enter_context(patch("utils.tenant_limits.check_products_limit"))
        yield {
            "visible_query": visible_query,
            "product": product,
            "products": products,
            "category_query": category_query,
            "session": session,
            "product_query": product_query_mock,
        }


@pytest.fixture
def upload_dir():
    path = tempfile.mkdtemp()
    yield path


@pytest.fixture
def cov_products_client(app_factory, bypass_permission_auth, upload_dir):
    from routes.products import products_bp

    app = app_factory(products_bp, config_overrides={"UPLOAD_FOLDER": upload_dir})
    return app.test_client()


class TestCreateExtraAndImageArcs:
    def test_empty_extra_value_arc_784_781(self, cov_products_client):
        """Arc 784->781: empty extra_ field value loops without storing."""
        form = _mock_product_form(validate=True)
        with (
            _products_patches(),
            patch("forms.product.ProductForm", return_value=form),
        ):
            resp = cov_products_client.post(
                "/products/create",
                data={
                    "name": "Extra Empty",
                    "regular_price": "10",
                    "warehouse_id": "1",
                    "extra_color": "",
                },
            )
        assert resp.status_code == 302

    def test_image_empty_filename_arc_793_798(self, cov_products_client):
        """Arc 793->798: uploaded image with empty filename skips saving."""
        form = _mock_product_form(validate=True)
        with (
            _products_patches(),
            patch("forms.product.ProductForm", return_value=form),
        ):
            resp = cov_products_client.post(
                "/products/create",
                data={
                    "name": "No Image Name",
                    "regular_price": "10",
                    "warehouse_id": "1",
                    "image": (BytesIO(b"img"), ""),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302


class TestEditArcs:
    def _base_edit_data(self):
        return {
            "name": "X",
            "regular_price": "10",
            "cost_price": "50",
            "current_stock": "10",
            "warehouse_id": "1",
        }

    def test_no_merchant_skips_to_partners_arc_959_976(self, cov_products_client, mock_user):
        """Arc 959->976: no merchant id skips merchant block, edit succeeds."""
        mock_user.can_see_costs.return_value = True
        form = _mock_product_form(validate=True)
        product = _product()
        with (
            _products_patches(product=product),
            patch("forms.product.ProductForm", return_value=form),
        ):
            resp = cov_products_client.post("/products/1/edit", data=self._base_edit_data())
        assert resp.status_code == 302

    def test_unchanged_cost_arc_1019_1042(self, cov_products_client, mock_user):
        """Arc 1019->1042: unchanged cost skips the stock-guarded cost block."""
        mock_user.can_see_costs.return_value = True
        form = _mock_product_form(validate=True)
        product = _product()
        with (
            _products_patches(product=product),
            patch("forms.product.ProductForm", return_value=form),
        ):
            resp = cov_products_client.post("/products/1/edit", data=self._base_edit_data())
        assert resp.status_code == 302
        assert float(product.cost_price) == 50.0

    def test_edit_image_empty_filename_arc_1113_1118(self, cov_products_client, mock_user):
        """Arc 1113->1118: edit image with empty filename skips saving."""
        mock_user.can_see_costs.return_value = False
        form = _mock_product_form(validate=True)
        product = _product()
        with (
            _products_patches(product=product),
            patch("forms.product.ProductForm", return_value=form),
        ):
            resp = cov_products_client.post(
                "/products/1/edit",
                data={**self._base_edit_data(), "image": (BytesIO(b"img"), "")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_edit_image_save_returns_none_arc_1115_1118(self, cov_products_client, mock_user):
        """Arc 1115->1118: failed image save keeps existing image_url."""
        mock_user.can_see_costs.return_value = False
        form = _mock_product_form(validate=True)
        product = _product()
        with (
            _products_patches(product=product),
            patch("forms.product.ProductForm", return_value=form),
            patch("routes.products.save_uploaded_file", return_value=None),
        ):
            resp = cov_products_client.post(
                "/products/1/edit",
                data={**self._base_edit_data(), "image": (BytesIO(b"img"), "pic.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert product.image_url is None


class TestGetCategory:
    def test_get_category_success_lines_1328_1330(self, cov_products_client):
        """Lines 1328-1330: fetch single category returns JSON payload."""
        cat = _category(9, name="Solo")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
        ):
            resp = cov_products_client.get("/products/categories/9")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["category"]["id"] == 9


class TestUpdateCategoryArcs:
    def test_invalid_payload_json_arc_1346_1349(self, cov_products_client):
        """Arc 1346-1349 (json): blank name -> 400 error response."""
        cat = _category(5, name="Old")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
        ):
            resp = cov_products_client.post("/products/categories/5/update", json={"name": "   "})
        assert resp.status_code == 400

    def test_invalid_payload_form_arc_1346_1349(self, cov_products_client):
        """Arc 1346-1349 (form): blank name -> flash + redirect."""
        cat = _category(5, name="Old")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
        ):
            resp = cov_products_client.post("/products/categories/5/update", data={"name": ""})
        assert resp.status_code == 302

    def test_name_taken_json_arc_1353_1357(self, cov_products_client):
        """Arc 1353-1357 (json): duplicate name -> 400 error response."""
        cat = _category(5, name="Old")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch("routes.products._category_name_taken", return_value=True),
        ):
            resp = cov_products_client.post("/products/categories/5/update", json={"name": "Taken"})
        assert resp.status_code == 400

    def test_name_taken_form_arc_1353_1357(self, cov_products_client):
        """Arc 1353-1357 (form): duplicate name -> flash + redirect."""
        cat = _category(5, name="Old")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch("routes.products._category_name_taken", return_value=True),
        ):
            resp = cov_products_client.post("/products/categories/5/update", data={"name": "Taken"})
        assert resp.status_code == 302

    def test_success_form_arc_1370_1371(self, cov_products_client):
        """Arc 1370-1376 (form success): rename via form -> redirect."""
        cat = _category(5, name="Old")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch("routes.products._category_name_taken", return_value=False),
        ):
            resp = cov_products_client.post("/products/categories/5/update", data={"name": "Fresh"})
        assert resp.status_code == 302
        assert cat.name == "Fresh"

    def test_exception_json_arc_1373_1374(self, cov_products_client):
        """Arc 1370-1376 (json exception): failure -> 400 error response."""
        cat = _category(5, name="Old")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch(
                "routes.products._category_name_taken",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = cov_products_client.post("/products/categories/5/update", json={"name": "Fresh"})
        assert resp.status_code == 400

    def test_exception_form_arc_1375_1376(self, cov_products_client):
        """Arc 1370-1376 (form exception): failure -> flash + redirect."""
        cat = _category(5, name="Old")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch(
                "routes.products._category_name_taken",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = cov_products_client.post("/products/categories/5/update", data={"name": "Fresh"})
        assert resp.status_code == 302


class TestDeleteCategoryArcs:
    def test_blocked_form_arc_1398_1399(self, cov_products_client):
        """Arc 1398-1399: linked products, form post -> flash + redirect."""
        cat = _category(6, name="Used")
        with (
            _products_patches() as ctx,
            patch("routes.products._tenant_category_or_404", return_value=cat),
        ):
            ctx["product_query"].filter_by.return_value.count.return_value = 3
            resp = cov_products_client.post("/products/categories/6/delete", data={})
        assert resp.status_code == 302

    def test_success_form_arc_1407_1408(self, cov_products_client):
        """Arc 1407-1413 (form success): empty category deactivated -> redirect."""
        cat = _category(7, name="Empty")
        with (
            _products_patches() as ctx,
            patch("routes.products._tenant_category_or_404", return_value=cat),
        ):
            ctx["product_query"].filter_by.return_value.count.return_value = 0
            resp = cov_products_client.post("/products/categories/7/delete", data={})
        assert resp.status_code == 302
        assert cat.is_active is False

    def test_exception_json_arc_1410_1411(self, cov_products_client):
        """Arc 1407-1413 (json exception): failure -> 400 error response."""
        cat = _category(7, name="Empty")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch(
                "routes.products.ProductService.count_products_in_category",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = cov_products_client.post("/products/categories/7/delete", json={})
        assert resp.status_code == 400

    def test_exception_form_arc_1412_1413(self, cov_products_client):
        """Arc 1407-1413 (form exception): failure -> flash + redirect."""
        cat = _category(7, name="Empty")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch(
                "routes.products.ProductService.count_products_in_category",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = cov_products_client.post("/products/categories/7/delete", data={})
        assert resp.status_code == 302


class TestAdjustStockNoWarehouse:
    def test_no_warehouse_no_branch_arc_1475_1485(self, cov_products_client):
        """Arc 1475->1485: global scope without warehouse uses master stock."""
        with _products_patches():
            resp = cov_products_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "add", "quantity": "5"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["new_stock"] == 15.0
