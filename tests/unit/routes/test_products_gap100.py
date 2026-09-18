"""Gap coverage for routes/products.py — hits missing branches/lines.

Missing per report: 59, 308->482, 386->389, 390->393, 476->482, 514->517, 518->521, 959->976
"""

import tempfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest


def _warehouse(wid=1):
    wh = MagicMock()
    wh.id = wid
    wh.name = "Main WH"
    wh.name_ar = "مستودع"
    wh.is_main = True
    wh.is_active = True
    wh.tenant_id = 1
    return wh


def _product(pid=1):
    p = MagicMock()
    p.id = pid
    p.name = "Widget"
    p.sku = "SKU-1"
    p.barcode = "BC-1"
    p.regular_price = 100
    p.cost_price = 50
    p.current_stock = 10
    p.min_stock_alert = 5
    p.partner_shares = []
    p.extra_fields = {}
    p.industry = "general"
    p.unit = "pcs"
    p.is_active = True
    p.tenant_id = 1
    return p


def _category(cid=1, name="Cat"):
    c = MagicMock()
    c.id = cid
    c.name = name
    c.name_ar = None
    c.description = None
    c.is_active = True
    c.tenant_id = 1
    return c


@pytest.fixture
def upload_dir():
    d = tempfile.mkdtemp()
    yield d


@pytest.fixture
def cov_products_client(app_factory, bypass_permission_auth, upload_dir):
    from routes.products import products_bp

    app = app_factory(products_bp, config_overrides={"UPLOAD_FOLDER": upload_dir})
    return app.test_client()


class TestLine59TenantCategoryOr404:
    """Line 59: abort when category lookup returns None (tenant present)."""

    def test_category_missing_aborts_404(self, cov_products_client):
        with (
            patch("routes.products.get_active_tenant_id", return_value=1),
            patch("routes.products.ProductService.get_active_category", return_value=None),
        ):
            resp = cov_products_client.get("/products/categories/999")
        assert resp.status_code == 404

    def test_no_tenant_aborts_404(self, cov_products_client):
        with patch("routes.products.get_active_tenant_id", return_value=None):
            resp = cov_products_client.get("/products/categories/1")
        assert resp.status_code == 404

    def test_category_found_returns_json(self, cov_products_client):
        cat = _category(5, name="Found")
        with (
            patch("routes.products.get_active_tenant_id", return_value=1),
            patch("routes.products.ProductService.get_active_category", return_value=cat),
            patch("routes.products.ProductService.count_products_in_category", return_value=2),
        ):
            resp = cov_products_client.get("/products/categories/5")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["category"]["id"] == 5


class TestImportBranches308_482:
    """Arcs 308->482, 386->389, 390->393, 476->482 via /products/import."""

    def test_get_renders_without_post(self, cov_products_client):
        with (
            patch("routes.products.ProductService.list_active_categories", return_value=[]),
            patch("routes.products.render_template", return_value="ok"),
        ):
            resp = cov_products_client.get("/products/import")
        assert resp.status_code == 200

    def test_missing_file_field_redirects(self, cov_products_client):
        resp = cov_products_client.post("/products/import", data={})
        assert resp.status_code == 302

    def test_empty_filename_redirects(self, cov_products_client):
        # empty filename triggers 302 before reaching `if file:` block
        with patch("routes.products.render_template", return_value="ok"):
            resp = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_unsupported_extension_early_return_covers_cleanup_false_branch(self, cov_products_client):
        # ext not in allowed -> return redirect, filepath stays None -> finally if false
        with patch("routes.products.render_template", return_value="ok"):
            resp = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "bad.txt")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_falsy_file_covers_308_to_482(self, cov_products_client):
        """Arc 308->482: `if file:` false -> render import page."""
        from routes.products import import_products

        falsy = MagicMock()
        falsy.__bool__ = MagicMock(return_value=False)
        falsy.__nonzero__ = falsy.__bool__
        falsy.filename = "keep.xlsx"
        with cov_products_client.application.test_request_context("/products/import", method="POST"):
            with patch("routes.products.request") as mock_req:
                mock_req.method = "POST"
                mock_req.files = {"file": falsy}
                mock_req.form = {}
                # need is_json etc? import_products checks request.method and request.files only
                with patch("routes.products.render_template", return_value="ok") as render:
                    resp = import_products()
                    assert resp == "ok"
                    render.assert_called_with("products/import.html")

    def test_import_with_existing_sku_barcode_covers_false_branches_386_390(self, cov_products_client):
        """When sku/barcode present, 386->389 and 390->393 false branches (no auto)."""
        import pandas as pd

        df = pd.DataFrame(
            {
                "name": ["Gadget"],
                "price": [15.0],
                "cost": [5.0],
                "stock": [0.0],
                "warranty": [365],
                "sku": ["KEEP-SKU"],
                "barcode": ["KEEP-BC"],
                "category": [""],
            }
        )
        new_product = _product(55)
        with (
            patch("routes.products._read_import_dataframe", return_value=df),
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.ProductService.find_duplicate_product", return_value=None),
            patch("routes.products.ProductService.create_product", return_value=new_product),
            patch("routes.products.ProductService.find_category_by_name", return_value=None),
            patch("routes.products.get_active_tenant_id", return_value=1),
            patch("routes.products.generate_sku", return_value="AUTO-SKU") as gen_sku,
            patch("routes.products.generate_barcode", return_value="AUTO-BC") as gen_bc,
            patch("routes.products.db.session"),
            patch("routes.products.StockService.add_opening_stock"),
        ):
            resp = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "products.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        gen_sku.assert_not_called()
        gen_bc.assert_not_called()

    def test_import_with_empty_sku_barcode_covers_true_branches(self, cov_products_client):
        """When sku/barcode empty, true branches generate."""
        import pandas as pd

        df = pd.DataFrame(
            {
                "name": ["Gadget2"],
                "price": [12.0],
                "cost": [5.0],
                "stock": [0.0],
                "warranty": [None],
                "sku": [""],
                "barcode": [""],
                "category": [""],
            }
        )
        new_product = _product(56)
        with (
            patch("routes.products._read_import_dataframe", return_value=df),
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.ProductService.find_duplicate_product", return_value=None),
            patch("routes.products.ProductService.create_product", return_value=new_product),
            patch("routes.products.generate_sku", return_value="AUTO-SKU"),
            patch("routes.products.generate_barcode", return_value="AUTO-BC"),
            patch("routes.products.get_active_tenant_id", return_value=1),
            patch("routes.products.db.session"),
            patch("routes.products.StockService.add_opening_stock"),
        ):
            resp = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "products.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_import_exception_covers_476_cleanup_true_then_false(self, cov_products_client, upload_dir):
        # force exception after filepath creation to hit cleanup true branch (file exists)
        import pandas as pd

        pd.DataFrame({"name": ["X"], "price": [1.0]})
        # make _read_import_dataframe raise after file is saved (filepath exists)
        with (
            patch("routes.products._read_import_dataframe", side_effect=RuntimeError("boom")),
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.current_app"),
            patch("routes.products.render_template", return_value="ok"),
        ):
            # need UPLOAD_FOLDER to be upload_dir already via fixture
            # ensure file is written to disk so cleanup true branch executes
            resp = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "products.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        # also test cleanup when file does not exist (os.path.exists false)
        with (
            patch("routes.products._read_import_dataframe", side_effect=RuntimeError("boom")),
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("os.path.exists", return_value=False),
            patch("routes.products.render_template", return_value="ok"),
        ):
            resp2 = cov_products_client.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "products.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp2.status_code == 200


class TestImportGridBranches514_521:
    """Arcs 514->517 and 518->521 in /products/import-grid."""

    def test_grid_empty_sku_barcode_auto(self, cov_products_client):
        new_product = _product(66)
        with (
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.ProductService.create_product", return_value=new_product),
            patch("routes.products.generate_sku", return_value="AUTO-SKU"),
            patch("routes.products.generate_barcode", return_value="AUTO-BC"),
            patch("routes.products.db.session"),
            patch("routes.products.StockService.add_opening_stock"),
            patch("routes.products.get_active_tenant_id", return_value=1),
        ):
            resp = cov_products_client.post(
                "/products/import-grid",
                data={"name[]": ["Grid1"], "price[]": ["10"], "stock[]": ["0"], "sku[]": [""], "barcode[]": [""]},
            )
        assert resp.status_code == 302

    def test_grid_with_sku_barcode_no_auto(self, cov_products_client):
        new_product = _product(67)
        with (
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.ProductService.create_product", return_value=new_product),
            patch("routes.products.generate_sku", return_value="SHOULD-NOT-BE-CALLED") as gen_sku,
            patch("routes.products.generate_barcode", return_value="SHOULD-NOT-BE-CALLED") as gen_bc,
            patch("routes.products.db.session"),
            patch("routes.products.StockService.add_opening_stock"),
            patch("routes.products.get_active_tenant_id", return_value=1),
        ):
            resp = cov_products_client.post(
                "/products/import-grid",
                data={
                    "name[]": ["Grid2"],
                    "price[]": ["10"],
                    "stock[]": ["0"],
                    "sku[]": ["KEEP-SKU"],
                    "barcode[]": ["KEEP-BC"],
                },
            )
        assert resp.status_code == 302
        gen_sku.assert_not_called()
        gen_bc.assert_not_called()

    def test_grid_mixed_sku_barcode(self, cov_products_client):
        new_product = _product(68)
        with (
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.ProductService.create_product", return_value=new_product),
            patch("routes.products.generate_sku", return_value="AUTO-SKU"),
            patch("routes.products.generate_barcode", return_value="AUTO-BC"),
            patch("routes.products.db.session"),
            patch("routes.products.StockService.add_opening_stock"),
            patch("routes.products.get_active_tenant_id", return_value=1),
        ):
            resp = cov_products_client.post(
                "/products/import-grid",
                data={
                    "name[]": ["Grid3"],
                    "price[]": ["10"],
                    "stock[]": ["0"],
                    "sku[]": [""],
                    "barcode[]": ["KEEP-BC"],
                },
            )
        assert resp.status_code == 302


class TestEditBranch959_976:
    """Arc 959->976: merchant_customer_id present but found vs not found."""

    def _base_patches(self, product=None, merchant_found=None):
        prod = product or _product(10)
        prod.partner_shares = []
        from tests.unit.routes.conftest import _chain_query

        visible = _chain_query(all=[prod])
        return {
            "product": prod,
            "visible": visible,
            "merchant_found": merchant_found,
        }

    def test_edit_merchant_not_found_returns_render(self, cov_products_client):

        prod = _product(10)
        prod.partner_shares = []
        form = MagicMock()
        form.validate_on_submit.return_value = True
        form.category_id.data = 1
        form.errors = {}
        with (
            patch("routes.products.tenant_get_or_404", return_value=prod),
            patch("routes.products.ProductService.list_active_categories", return_value=[_category()]),
            patch("routes.products.get_accessible_warehouses", return_value=[_warehouse()]),
            patch("routes.products.ProductService.scoped_customers", return_value=[]),
            patch("routes.products.branch_scope_id", return_value=None),
            patch("routes.products.get_active_tenant_id", return_value=1),
            patch("routes.products.StockService.get_product_stock", return_value=10),
            patch("routes.products.ProductService.find_scoped_customer", return_value=None),
            patch("routes.products.render_template", return_value="ok") as render,
            patch("forms.product.ProductForm", return_value=form),
        ):
            resp = cov_products_client.post(
                "/products/10/edit",
                data={"name": "X", "regular_price": "10", "merchant_customer_id": "99", "current_stock": "10"},
            )
        assert resp.status_code == 200
        assert render.called

    def test_edit_merchant_found_falls_through_to_976(self, cov_products_client):
        prod = _product(10)
        prod.partner_shares = []
        form = MagicMock()
        form.validate_on_submit.return_value = True
        form.category_id.data = 1
        form.errors = {}
        merchant = MagicMock(id=99)
        with (
            patch("routes.products.tenant_get_or_404", return_value=prod),
            patch("routes.products.ProductService.list_active_categories", return_value=[_category()]),
            patch("routes.products.get_accessible_warehouses", return_value=[_warehouse()]),
            patch("routes.products.ProductService.scoped_customers", return_value=[merchant]),
            patch("routes.products.branch_scope_id", return_value=None),
            patch("routes.products.get_active_tenant_id", return_value=1),
            patch("routes.products.StockService.get_product_stock", return_value=10),
            patch("routes.products.ProductService.find_scoped_customer", return_value=merchant),
            patch("routes.products._parse_product_partners", return_value=([], None)),
            patch("routes.products.save_uploaded_file", return_value=None),
            patch("routes.products.assign_tenant_id"),
            patch("routes.products.LoggingCore.log_audit"),
            patch("routes.products.ProductService.get_price_tier", return_value=None),
            patch("routes.products.ProductService.create_price_tier"),
            patch("routes.products.StockService.adjust_stock"),
            patch("routes.products.db.session"),
            patch("routes.products.render_template", return_value="ok"),
            patch("forms.product.ProductForm", return_value=form),
        ):
            resp = cov_products_client.post(
                "/products/10/edit",
                data={"name": "X", "regular_price": "10", "merchant_customer_id": "99", "current_stock": "10"},
            )
        # should not early-return at 959, should proceed (redirect or render)
        assert resp.status_code in (200, 302)

    def test_edit_no_merchant_skips_branch(self, cov_products_client):
        prod = _product(10)
        prod.partner_shares = []
        form = MagicMock()
        form.validate_on_submit.return_value = True
        form.category_id.data = 1
        form.errors = {}
        with (
            patch("routes.products.tenant_get_or_404", return_value=prod),
            patch("routes.products.ProductService.list_active_categories", return_value=[_category()]),
            patch("routes.products.get_accessible_warehouses", return_value=[_warehouse()]),
            patch("routes.products.ProductService.scoped_customers", return_value=[]),
            patch("routes.products.branch_scope_id", return_value=None),
            patch("routes.products.get_active_tenant_id", return_value=1),
            patch("routes.products.StockService.get_product_stock", return_value=10),
            patch("routes.products._parse_product_partners", return_value=([], None)),
            patch("routes.products.save_uploaded_file", return_value=None),
            patch("routes.products.assign_tenant_id"),
            patch("routes.products.LoggingCore.log_audit"),
            patch("routes.products.ProductService.get_price_tier", return_value=None),
            patch("routes.products.ProductService.create_price_tier"),
            patch("routes.products.StockService.adjust_stock"),
            patch("routes.products.db.session"),
            patch("routes.products.render_template", return_value="ok"),
            patch("forms.product.ProductForm", return_value=form),
        ):
            resp = cov_products_client.post(
                "/products/10/edit",
                data={"name": "X", "regular_price": "10", "current_stock": "10"},
            )
        assert resp.status_code in (200, 302)
