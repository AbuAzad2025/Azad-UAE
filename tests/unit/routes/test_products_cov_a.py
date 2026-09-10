"""Coverage boost A for routes/products.py — helpers, create validation, import."""

import tempfile
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

import routes.products as products_mod
from routes.products import (
    _category_name_conflict,
    _category_to_json,
    _parse_category_payload,
)
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
        stack.enter_context(
            patch(
                "routes.products.ProductService.find_duplicate_product",
                side_effect=lambda sku, barcode, tid=None: product_query_mock.filter.return_value.first.return_value,
            )
        )
        stack.enter_context(
            patch(
                "routes.products.ProductService.find_category_by_name",
                side_effect=lambda tid, name: (
                    category_query.filter_by.return_value.filter.return_value.first.return_value
                ),
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


def _import_dataframe(data):
    import importlib
    import sys

    for mod in ("pandas", "numpy"):
        if isinstance(sys.modules.get(mod), MagicMock):
            sys.modules.pop(mod, None)
    pd = importlib.import_module("pandas")
    return pd.DataFrame(data)


class TestTenantBusinessTypeDefault:
    def test_no_tenant_returns_general(self, cov_products_client):
        """Line 48: _tenant_business_type_default with no active tenant."""
        form = _mock_product_form(validate=False)
        with (
            _products_patches(),
            patch("forms.product.ProductForm", return_value=form),
            patch("routes.products.get_active_tenant_id", return_value=None),
            patch("routes.products.render_template", return_value="ok") as render,
        ):
            resp = cov_products_client.get("/products/create")
        assert resp.status_code == 200
        assert render.call_args[1]["default_industry"] == "general"


class TestTenantCategoryOr404Arcs:
    def test_no_tenant_aborts_404(self, cov_products_client):
        """Arc 53-59: _tenant_category_or_404 with no tenant -> 404."""
        with (
            _products_patches(),
            patch("routes.products.get_active_tenant_id", return_value=None),
        ):
            resp = cov_products_client.get("/products/categories/9")
        assert resp.status_code == 404

    def test_missing_category_aborts_404(self, cov_products_client):
        """Arc 53-59: tenant set but category lookup returns None -> 404."""
        with (
            _products_patches(),
            patch("routes.products.ProductService.get_active_category", return_value=None),
        ):
            resp = cov_products_client.get("/products/categories/9")
        assert resp.status_code == 404


class TestCategoryPayloadHelpers:
    def test_category_payload_empty(self, cov_products_client):
        """Line 64: _category_payload with empty form data -> flash + redirect."""
        with _products_patches():
            resp = cov_products_client.post("/products/categories/create", data={})
        assert resp.status_code == 302

    def test_category_name_conflict_delegates(self):
        """Line 89: _category_name_conflict delegates to ProductService."""
        sentinel = MagicMock()
        with patch("routes.products.ProductService.find_category_name_conflict", return_value=sentinel) as finder:
            assert _category_name_conflict(1, "Cat", exclude_id=2) is sentinel
        finder.assert_called_once_with(1, "Cat", exclude_id=2)

    def test_category_to_json(self):
        """Line 93: _category_to_json serialises fields."""
        cat = _category(4, name="Tools")
        cat.name_ar = "عدد"
        cat.description = "desc"
        with patch("routes.products.ProductService.count_products_in_category", return_value=7):
            from routes.products import _category_json

            body = _category_json(cat)
        assert body["id"] == 4
        assert body["product_count"] == 7
        payload = _category_to_json(cat)
        assert payload == {"id": 4, "name": "Tools", "name_ar": "عدد", "description": "desc"}

    def test_parse_category_payload_empty(self):
        """Arc 102-109: empty payload -> error."""
        name, _ar, _desc, err = _parse_category_payload(None)
        assert name is None
        assert err is not None

    def test_parse_category_payload_missing_name(self):
        """Arc 102-109: blank name -> error."""
        _n, _ar, _d, err = _parse_category_payload({"name": "   "})
        assert err is not None

    def test_parse_category_payload_valid(self):
        """Arc 102-109: valid payload parses."""
        name, name_ar, desc, err = _parse_category_payload({"name": "Cat", "name_ar": "فئة"})
        assert err is None
        assert name == "Cat"
        assert name_ar == "فئة"
        assert desc is None


class TestValidateCreatePayloadLines:
    def _post_create(self, client, form, data):
        with (
            _products_patches(),
            patch("forms.product.ProductForm", return_value=form),
            patch("routes.products.render_template", return_value="ok"),
        ):
            return client.post("/products/create", data=data)

    def test_missing_name_line_116(self, cov_products_client):
        """Line 116: empty product name -> validation error, re-render."""
        form = _mock_product_form(validate=True)
        resp = self._post_create(
            cov_products_client,
            form,
            {"name": "", "regular_price": "10", "warehouse_id": "1"},
        )
        assert resp.status_code == 200

    def test_missing_price_line_118(self, cov_products_client):
        """Line 118: regular_price None -> validation error, re-render."""
        form = _mock_product_form(validate=True, price=None)
        resp = self._post_create(
            cov_products_client,
            form,
            {"name": "X", "regular_price": "10", "warehouse_id": "1"},
        )
        assert resp.status_code == 200

    def test_negative_price_line_120(self, cov_products_client):
        """Line 120: negative sale price -> validation error, re-render."""
        form = _mock_product_form(validate=True, price=-3.0)
        resp = self._post_create(
            cov_products_client,
            form,
            {"name": "X", "regular_price": "-3", "warehouse_id": "1"},
        )
        assert resp.status_code == 200

    def test_negative_stock_line_124(self, cov_products_client):
        """Line 124: negative opening stock -> validation error, re-render."""
        form = _mock_product_form(validate=True)
        resp = self._post_create(
            cov_products_client,
            form,
            {"name": "X", "regular_price": "10", "warehouse_id": "1", "current_stock": "-2"},
        )
        assert resp.status_code == 200

    def test_stock_without_cost_line_128(self, cov_products_client):
        """Line 128: positive opening stock with zero cost -> validation error."""
        form = _mock_product_form(validate=True)
        resp = self._post_create(
            cov_products_client,
            form,
            {
                "name": "X",
                "regular_price": "10",
                "warehouse_id": "1",
                "current_stock": "5",
                "cost_price": "",
            },
        )
        assert resp.status_code == 200


class TestImportBranches:
    def test_import_get_renders_arc_308_482(self, cov_products_client):
        """Arc 308->482: GET /products/import skips POST body, renders."""
        with _products_patches():
            resp = cov_products_client.get("/products/import")
        assert resp.status_code == 200

    def test_import_row_nan_warranty_autosku_barcode_new_category(self, cov_products_client):
        """Arcs 379->385, 386->389, 390->393, 424-429 via one import row."""
        df = _import_dataframe(
            {
                "name": ["Gadget"],
                "price": [12.0],
                "cost": [5.0],
                "stock": [2.0],
                "warranty": [None],
                "sku": [""],
                "barcode": [""],
                "category": ["BrandNewCat"],
            }
        )
        new_cat = MagicMock()
        new_cat.id = 77
        new_product = MagicMock()
        new_product.id = 55
        with (
            _products_patches(),
            patch("routes.products._read_import_dataframe", return_value=df),
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.ProductService.find_duplicate_product", return_value=None),
            patch("routes.products.ProductService.find_category_by_name", return_value=None),
            patch("routes.products.ProductService.create_category", return_value=new_cat),
            patch("routes.products.ProductService.create_product", return_value=new_product),
        ):
            resp = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "products.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_import_update_existing_zero_stock_arc_402_411(self, cov_products_client):
        """Arc 402->411: existing product updated with zero stock skips adjust."""
        df = _import_dataframe({"name": ["Known"], "price": [9.0], "stock": [0.0]})
        existing = _product(31, name="Known", current_stock=4)
        with (
            _products_patches(),
            patch("routes.products._read_import_dataframe", return_value=df),
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.ProductService.find_duplicate_product", return_value=existing),
        ):
            resp = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "products.xlsx"), "update_existing": "1"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_import_dataframe_failure_renders_arc_476_482(self, cov_products_client):
        """Arc 476->482: processing exception -> finally cleanup -> re-render."""
        with (
            _products_patches(),
            patch(
                "routes.products._read_import_dataframe",
                side_effect=RuntimeError("unreadable"),
            ),
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
        ):
            resp = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "products.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200

    def test_import_grid_autosku_and_barcode(self, cov_products_client):
        """Arcs 514->517, 518->521: empty sku/barcode auto-generated."""
        new_product = MagicMock()
        new_product.id = 66
        with (
            _products_patches(),
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.ProductService.create_product", return_value=new_product),
        ):
            resp = cov_products_client.post(
                "/products/import-grid",
                data={"name[]": ["Grid Item"], "price[]": ["7"], "stock[]": ["0"]},
            )
        assert resp.status_code == 302


class TestUpdateCategoryNullJson:
    def test_null_json_body_line_1342(self, cov_products_client):
        """Line 1342: JSON null body on update -> 400 error response."""
        cat = _category(5, name="Old")
        with (
            _products_patches(),
            patch("routes.products._tenant_category_or_404", return_value=cat),
        ):
            resp = cov_products_client.post(
                "/products/categories/5/update",
                data="null",
                content_type="application/json",
            )
        assert resp.status_code == 400
