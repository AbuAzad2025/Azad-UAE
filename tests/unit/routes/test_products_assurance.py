"""Assurance tests for routes/products.py — gap coverage beyond chunk/route suites."""
from __future__ import annotations

import tempfile
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.test_products_routes import (
    _category,
    _mock_product_form,
    _product,
    _products_patches,
    _warehouse,
    _warehouse_query_mock,
)


pytest_plugins = ["tests.unit.conftest"]


@pytest.fixture
def upload_dir():
    path = tempfile.mkdtemp()
    yield path


@pytest.fixture
def product_client_upload(app_factory, bypass_product_auth, upload_dir):
    from routes.products import products_bp

    app = app_factory(
        products_bp,
        config_overrides={"UPLOAD_FOLDER": upload_dir},
    )
    return app.test_client()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestSafeFloatRequireFloat:
    @pytest.mark.parametrize(
        "value,default,expected",
        [
            ("  -3.14  ", 0.0, -3.14),
            (42, 0.0, 42.0),
            (None, 99.9, 99.9),
            ("12,5", 0.0, 0.0),
        ],
    )
    def test_safe_float_edges(self, value, default, expected):
        from routes.products import safe_float

        assert safe_float(value, default=default) == expected

    @pytest.mark.parametrize("value", ["abc", "12,5", "   "])
    def test_require_float_raises(self, value):
        from routes.products import require_float

        with pytest.raises(ValueError):
            require_float(value)


class TestParseProductPartners:
    def test_invalid_percentage_text(self):
        from routes.products import _parse_product_partners

        form = MagicMock()
        form.getlist.side_effect = lambda key: {
            "partner_customer_id[]": ["1"],
            "partner_percentage[]": ["abc"],
        }.get(key, [])
        partners, err = _parse_product_partners(form)
        assert partners is None
        assert "نسبة" in err

    def test_percentage_zero_or_over_100(self):
        from routes.products import _parse_product_partners

        partner = MagicMock()
        partner.id = 3
        form = MagicMock()
        form.getlist.side_effect = lambda key: {
            "partner_customer_id[]": ["3"],
            "partner_percentage[]": ["0"],
        }.get(key, [])
        with _products_patches() as ctx:
            ctx["customer_query"].filter.return_value.first.return_value = partner
            partners, err = _parse_product_partners(form)
        assert partners is None
        assert "بين 0 و 100" in err

        form.getlist.side_effect = lambda key: {
            "partner_customer_id[]": ["3"],
            "partner_percentage[]": ["101"],
        }.get(key, [])
        with _products_patches() as ctx:
            ctx["customer_query"].filter.return_value.first.return_value = partner
            partners, err = _parse_product_partners(form)
        assert partners is None

    def test_happy_path_single_partner(self):
        from routes.products import _parse_product_partners

        partner = MagicMock()
        partner.id = 4
        form = MagicMock()
        form.getlist.side_effect = lambda key: {
            "partner_customer_id[]": ["4"],
            "partner_percentage[]": ["25"],
        }.get(key, [])
        with _products_patches() as ctx:
            ctx["customer_query"].filter.return_value.first.return_value = partner
            partners, err = _parse_product_partners(form)
        assert err is None
        assert partners == [{"partner_customer_id": 4, "percentage": 25.0}]


class TestAnnotateStockAndBranch:
    def test_annotate_visible_stock_with_warehouses(self, app_factory, bypass_product_auth):
        from routes.products import _annotate_visible_stock, products_bp

        app = app_factory(products_bp)
        items = [_product(1, current_stock=5), _product(2, current_stock=8)]
        with app.app_context(), patch(
            "routes.products.get_accessible_warehouse_ids", return_value=[1, 2]
        ), patch(
            "routes.products.get_branch_stock_map", return_value={1: 11.0, 2: 22.0}
        ):
            result = _annotate_visible_stock(items)
        assert result[0].visible_stock == 11.0
        assert result[1].visible_stock == 22.0

    def test_annotate_branch_info_no_warehouse_ids(self):
        from routes.products import _annotate_branch_and_warehouse_info

        product = _product()
        result = _annotate_branch_and_warehouse_info([product], [])
        assert result[0].visible_warehouse_names == []
        assert result[0].visible_branch_names == []

    def test_annotate_branch_info_populates_names(self, app_factory, bypass_product_auth):
        from routes.products import _annotate_branch_and_warehouse_info, products_bp

        app = app_factory(products_bp)
        product = _product(7)
        session_query = MagicMock()
        session_query.join.return_value.outerjoin.return_value.filter.return_value.filter.return_value.all.return_value = [
            (7, "WH EN", "WH AR", "Branch A", "B1"),
            (7, "WH2", None, "Branch B", None),
        ]
        with app.app_context(), patch("routes.products.db.session.query", return_value=session_query):
            result = _annotate_branch_and_warehouse_info([product], [1, 2])
        assert "WH AR" in result[0].visible_warehouse_names
        assert "Branch A (B1)" in result[0].visible_branch_names
        assert "Branch B" in result[0].visible_branch_names


class TestWantsJson:
    def test_is_json_content_type(self, app_factory, bypass_product_auth):
        from routes.products import _wants_json, products_bp

        app = app_factory(products_bp)
        with app.test_request_context("/", json={"x": 1}):
            assert _wants_json() is True

    def test_xhr_header(self, app_factory, bypass_product_auth):
        from routes.products import _wants_json, products_bp

        app = app_factory(products_bp)
        with app.test_request_context("/", headers={"X-Requested-With": "XMLHttpRequest"}):
            assert _wants_json() is True

    def test_plain_form_false(self, app_factory, bypass_product_auth):
        from routes.products import _wants_json, products_bp

        app = app_factory(products_bp)
        with app.test_request_context("/", method="POST", data={"a": "1"}):
            assert _wants_json() is False


class TestGetAlternativeWarehouses:
    def test_excludes_current_warehouse(self, app_factory, bypass_product_auth):
        from routes.products import _get_alternative_warehouses, products_bp

        app = app_factory(products_bp)
        wh_main = _warehouse(1, "Main")
        wh_alt = _warehouse(2, "Alt")
        with app.app_context(), patch(
            "routes.products.get_accessible_warehouses", return_value=[wh_main, wh_alt]
        ), patch("routes.products.StockService.get_product_stock", side_effect=lambda pid, warehouse_id=None, user=None: 5.0 if warehouse_id == 2 else 0):
            result = _get_alternative_warehouses(1, exclude_warehouse_id=1)
        assert len(result) == 1
        assert result[0]["warehouse_id"] == 2

    def test_skips_zero_stock_warehouses(self, app_factory, bypass_product_auth):
        from routes.products import _get_alternative_warehouses, products_bp

        app = app_factory(products_bp)
        wh = _warehouse(2, "Empty")
        with app.app_context(), patch(
            "routes.products.get_accessible_warehouses", return_value=[wh]
        ), patch("routes.products.StockService.get_product_stock", return_value=0):
            assert _get_alternative_warehouses(1, 99) == []


class TestScopedCustomersQuery:
    def test_without_branch_scope(self, app_factory, bypass_product_auth):
        from routes.products import _scoped_customers_query, products_bp

        app = app_factory(products_bp)
        query = MagicMock()
        query.filter.return_value = query
        with app.app_context(), patch("routes.products.tenant_query", return_value=query), patch(
            "routes.products.branch_scope_id", return_value=None
        ):
            _scoped_customers_query("merchant")
        assert query.filter.call_count >= 1


# ---------------------------------------------------------------------------
# Import template & import_products
# ---------------------------------------------------------------------------


class TestImportTemplate:
    def test_download_failure_redirects(self, product_client):
        with patch("pandas.DataFrame", side_effect=RuntimeError("boom")):
            resp = product_client.get("/products/import-template")
        assert resp.status_code == 302
        assert resp.location.endswith("/products/import")


class TestImportProducts:
    def test_import_xls_and_skip_blank_rows(self, product_client_upload):
        import pandas as pd

        df = pd.DataFrame(
            {
                "name": ["", float("nan"), "Valid XLS"],
                "price": [1.0, 2.0, 15.0],
                "stock": [0.0, 0.0, 3.0],
            }
        )
        new_product = MagicMock()
        new_product.id = 50
        with _products_patches() as ctx, patch("models.Warehouse.query", _warehouse_query_mock()), patch(
            "pandas.read_excel", return_value=df
        ), patch("routes.products.Product", return_value=new_product):
            ctx["product_query"].filter.return_value.first.return_value = None
            resp = product_client_upload.post(
                "/products/import",
                data={"file": (BytesIO(b"xls"), "products.xls")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/")

    def test_import_existing_category_reuse(self, product_client_upload):
        import pandas as pd

        existing_cat = _category(9, name="Tools")
        df = pd.DataFrame({"name": ["CatProd"], "price": [20.0], "category": ["Tools"]})
        with _products_patches() as ctx, patch("models.Warehouse.query", _warehouse_query_mock()), patch(
            "pandas.read_excel", return_value=df
        ), patch("routes.products.ProductCategory") as pc_cls:
            ctx["product_query"].filter.return_value.first.return_value = None
            pc_cls.query.filter_by.return_value.filter.return_value.first.return_value = existing_cat
            resp = product_client_upload.post(
                "/products/import",
                data={"file": (BytesIO(b"x"), "products.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_import_update_existing_same_stock_skips_adjust(self, product_client_upload):
        import pandas as pd

        existing = _product(name="SameStock")
        existing.current_stock = 10.0
        df = pd.DataFrame({"name": ["SameStock"], "price": [12.0], "stock": [10.0]})
        with _products_patches() as ctx, patch("models.Warehouse.query", _warehouse_query_mock()), patch(
            "pandas.read_excel", return_value=df
        ), patch("routes.products.StockService.adjust_stock") as adjust:
            q = ctx["product_query"].filter.return_value
            q.filter.return_value.first.return_value = existing
            q.first.return_value = existing
            resp = product_client_upload.post(
                "/products/import",
                data={
                    "file": (BytesIO(b"x"), "products.xlsx"),
                    "update_existing": "1",
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        adjust.assert_not_called()

    def test_import_outer_exception_and_cleanup(self, product_client_upload, upload_dir, mocker):
        import os

        mocker.patch("pandas.read_excel", side_effect=RuntimeError("parse fail"))
        filepath_holder = {}

        original_join = os.path.join

        def join_and_track(*args):
            path = original_join(*args)
            if args and str(args[-1]).startswith("import_"):
                filepath_holder["path"] = path
            return path

        with _products_patches(), patch("models.Warehouse.query", _warehouse_query_mock()), patch(
            "os.path.join", side_effect=join_and_track
        ), patch("os.path.exists", return_value=True), patch("os.remove") as remove:
            resp = product_client_upload.post(
                "/products/import",
                data={"file": (BytesIO(b"data"), "products.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        remove.assert_called()


class TestImportGrid:
    def test_import_grid_no_warehouse_still_commits(self, product_client):
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = None
        wh_query.filter_by.return_value.filter.return_value.first.return_value = None
        with _products_patches() as ctx, patch("models.Warehouse.query", wh_query):
            resp = product_client.post(
                "/products/import-grid",
                data={"name[]": ["No WH"], "price[]": ["5"], "stock[]": ["0"]},
            )
        assert resp.status_code == 302
        ctx["session"].commit.assert_called()


# ---------------------------------------------------------------------------
# Index branch-scoped filters & branch columns
# ---------------------------------------------------------------------------


class TestIndexAssurance:
    def test_branch_scoped_empty_page(self, product_client):
        items = [_product(1)]
        query = MagicMock()
        query.order_by.return_value.all.return_value = items
        with _products_patches(products=items, visible_query=query, branch_scope=3), patch(
            "routes.products.get_branch_stock_map", return_value={1: 0.0}
        ), patch("routes.products.render_template", return_value="idx") as render:
            resp = product_client.get("/products/?stock=out&page=5&per_page=10")
        assert resp.status_code == 200
        assert render.call_args[1]["products"] == []

    def test_index_annotates_branch_columns(self, product_client):
        items = [_product(3)]
        query = MagicMock()
        query.order_by.return_value.paginate.return_value = MagicMock(items=items, page=1, per_page=20, total=1, pages=1, has_prev=False, has_next=False, prev_num=None, next_num=None)
        session_query = MagicMock()
        session_query.join.return_value.outerjoin.return_value.filter.return_value.filter.return_value.all.return_value = [
            (3, "W", "و", "Br", "C"),
        ]
        with _products_patches(products=items, visible_query=query, branch_scope=None), patch(
            "routes.products.should_show_all_branch_columns", return_value=True
        ), patch("routes.products.db.session.query", return_value=session_query), patch(
            "routes.products.render_template", return_value="idx"
        ) as render:
            resp = product_client.get("/products/")
        assert resp.status_code == 200
        assert render.call_args[1]["show_branch_columns"] is True


# ---------------------------------------------------------------------------
# Create / edit validation branches
# ---------------------------------------------------------------------------


class TestCreateAssurance:
    def test_create_get_preselected_warehouse(self, product_client):
        form = _mock_product_form()
        with _products_patches(), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products.render_template", return_value="create"
        ) as render:
            resp = product_client.get("/products/create?warehouse_id=5")
        assert resp.status_code == 200
        assert render.call_args[1]["preselected_warehouse_id"] == 5

    def test_create_partner_parse_error(self, product_client):
        form = _mock_product_form(validate=True)
        with _products_patches(), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products._parse_product_partners", return_value=(None, "partner bad")
        ), patch("routes.products.render_template", return_value="create") as render:
            resp = product_client.post(
                "/products/create",
                data={"name": "X", "regular_price": "10", "warehouse_id": "1"},
            )
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/create.html"

    def test_create_form_validation_flashes(self, product_client):
        form = _mock_product_form(validate=False)
        form.errors = {"sku": ["duplicate"], "name": ["required"]}
        with _products_patches(), patch("forms.product.ProductForm", return_value=form):
            resp = product_client.post("/products/create", data={"name": ""})
        assert resp.status_code == 200

    def test_create_without_initial_stock(self, product_client):
        form = _mock_product_form(validate=True)
        added = _product(77, name="NoStock")
        added.partner_shares = MagicMock()
        added.partner_shares.append = MagicMock()
        session = MagicMock()
        with _products_patches(), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products.Product", return_value=added
        ), patch("routes.products.db.session", session), patch(
            "routes.products.StockService.add_opening_stock"
        ) as opening:
            resp = product_client.post(
                "/products/create",
                data={"name": "NoStock", "regular_price": "10", "warehouse_id": "1", "current_stock": "0"},
            )
        assert resp.status_code == 302
        opening.assert_not_called()

    def test_create_image_save_returns_none(self, product_client):
        form = _mock_product_form(validate=True)
        added = _product(78)
        added.tenant_id = 1
        added.partner_shares = MagicMock()
        added.partner_shares.append = MagicMock()
        session = MagicMock()
        with _products_patches(), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products.Product", return_value=added
        ), patch("routes.products.db.session", session), patch(
            "routes.products.save_uploaded_file", return_value=None
        ):
            resp = product_client.post(
                "/products/create",
                data={
                    "name": "ImgFail",
                    "regular_price": "10",
                    "warehouse_id": "1",
                    "image": (BytesIO(b"x"), "x.png"),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert added.image_url is None


class TestEditAssurance:
    def test_edit_cost_json_blocked_with_stock(self, product_client, bypass_product_auth):
        bypass_product_auth.can_see_costs = MagicMock(return_value=True)
        form = _mock_product_form(validate=True)
        product = _product()
        product.cost_price = Decimal("10")
        with _products_patches(product=product), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products.StockService.get_product_stock", return_value=5.0
        ), patch("models.ProductPriceTier") as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = product_client.post(
                "/products/1/edit",
                data={"name": "X", "regular_price": "10", "cost_price": "99", "current_stock": "5"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_edit_cost_allowed_when_stock_zero(self, product_client, bypass_product_auth):
        bypass_product_auth.can_see_costs = MagicMock(return_value=True)
        form = _mock_product_form(validate=True)
        product = _product()
        product.cost_price = Decimal("10")
        with _products_patches(product=product), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products.StockService.get_product_stock", return_value=0.0
        ), patch("models.ProductPriceTier") as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = product_client.post(
                "/products/1/edit",
                data={"name": "X", "regular_price": "10", "cost_price": "99", "current_stock": "0", "warehouse_id": "1"},
            )
        assert resp.status_code == 302

    def test_edit_partner_no_tenant(self, product_client):
        form = _mock_product_form(validate=True)
        product = _product()
        product.tenant_id = None
        with _products_patches(product=product), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products._parse_product_partners",
            return_value=([{"partner_customer_id": 1, "percentage": 10}], None),
        ), patch("routes.products.render_template", return_value="edit") as render, patch(
            "models.ProductPriceTier"
        ) as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = product_client.post(
                "/products/1/edit",
                data={"name": "X", "regular_price": "10", "current_stock": "5"},
            )
        assert resp.status_code == 200

    def test_edit_partner_customer_missing(self, product_client):
        form = _mock_product_form(validate=True)
        product = _product()
        product.tenant_id = 1
        customer_query = MagicMock()
        customer_query.filter_by.return_value.first.return_value = None
        with _products_patches(product=product), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products._parse_product_partners",
            return_value=([{"partner_customer_id": 99, "percentage": 10}], None),
        ), patch("routes.products.Customer") as cust_cls, patch(
            "routes.products.render_template", return_value="edit"
        ), patch("models.ProductPriceTier") as tier_model:
            cust_cls.query.filter_by.return_value.first.return_value = None
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = product_client.post(
                "/products/1/edit",
                data={"name": "X", "regular_price": "10", "current_stock": "5"},
            )
        assert resp.status_code == 200

    def test_edit_partner_wrong_tenant(self, product_client):
        form = _mock_product_form(validate=True)
        product = _product()
        product.tenant_id = 1
        wrong_partner = MagicMock()
        wrong_partner.tenant_id = 2
        with _products_patches(product=product), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products._parse_product_partners",
            return_value=([{"partner_customer_id": 8, "percentage": 10}], None),
        ), patch("routes.products.Customer") as cust_cls, patch(
            "routes.products.render_template", return_value="edit"
        ), patch("models.ProductPriceTier") as tier_model:
            cust_cls.query.filter_by.return_value.first.return_value = wrong_partner
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = product_client.post(
                "/products/1/edit",
                data={"name": "X", "regular_price": "10", "current_stock": "5"},
            )
        assert resp.status_code == 200

    def test_edit_deactivates_empty_tier(self, product_client, bypass_product_auth):
        bypass_product_auth.can_see_costs = MagicMock(return_value=False)
        form = _mock_product_form(validate=True)
        product = _product()
        existing_tier = MagicMock()
        existing_tier.is_active = True
        with _products_patches(product=product), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products.StockService.get_product_stock", return_value=10.0
        ), patch("models.ProductPriceTier") as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = existing_tier
            resp = product_client.post(
                "/products/1/edit",
                data={
                    "name": "X",
                    "regular_price": "10",
                    "current_stock": "10",
                    "warehouse_id": "1",
                    "tier_wholesale_price": "",
                },
            )
        assert resp.status_code == 302
        assert existing_tier.is_active is False

    def test_edit_exception_rollback(self, product_client):
        form = _mock_product_form(validate=True)
        product = _product()
        session = MagicMock()
        session.commit.side_effect = RuntimeError("fail")
        with _products_patches(product=product), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products.db.session", session
        ), patch("routes.products.StockService.get_product_stock", return_value=10.0), patch(
            "models.ProductPriceTier"
        ) as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = product_client.post(
                "/products/1/edit",
                data={"name": "X", "regular_price": "10", "current_stock": "10", "warehouse_id": "1"},
            )
        assert resp.status_code == 200

    def test_edit_merchant_missing(self, product_client):
        form = _mock_product_form(validate=True)
        product = _product()
        customer_query = MagicMock()
        customer_query.filter.return_value.first.return_value = None
        with _products_patches(product=product), patch("forms.product.ProductForm", return_value=form), patch(
            "routes.products.tenant_query", return_value=customer_query
        ), patch("routes.products.render_template", return_value="edit"), patch(
            "models.ProductPriceTier"
        ) as tier_model:
            tier_model.query.filter_by.return_value.first.return_value = None
            resp = product_client.post(
                "/products/1/edit",
                data={
                    "name": "X",
                    "regular_price": "10",
                    "current_stock": "5",
                    "merchant_customer_id": "999",
                },
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Delete (soft/hard/html vs json)
# ---------------------------------------------------------------------------


class TestDeleteAssurance:
    def test_delete_scope_403_html(self, product_client):
        product = _product()
        with _products_patches(product=product), patch(
            "routes.products._ensure_product_scope", return_value=False
        ), patch("routes.products.render_template", return_value="denied") as render:
            resp = product_client.post("/products/1/delete")
        assert resp.status_code == 403
        assert render.call_args[0][0] == "errors/403.html"

    def test_delete_soft_flash_html(self, product_client):
        product = _product()
        sl = MagicMock()
        pl = MagicMock()
        sl.query.filter_by.return_value.filter.return_value.count.return_value = 1
        pl.query.filter_by.return_value.filter.return_value.count.return_value = 0
        with _products_patches(product=product), patch(
            "routes.products.StockService.get_product_stock", return_value=0.0
        ), patch("models.SaleLine", sl), patch("models.PurchaseLine", pl):
            resp = product_client.post("/products/1/delete")
        assert resp.status_code == 302
        assert product.is_active is False

    def test_delete_hard_flash_html(self, product_client):
        product = _product()
        sl = MagicMock()
        pl = MagicMock()
        sl.query.filter_by.return_value.filter.return_value.count.return_value = 0
        pl.query.filter_by.return_value.filter.return_value.count.return_value = 0
        with _products_patches(product=product) as ctx, patch(
            "routes.products.StockService.get_product_stock", return_value=0.0
        ), patch("models.SaleLine", sl), patch("models.PurchaseLine", pl):
            resp = product_client.post("/products/1/delete")
        assert resp.status_code == 302
        ctx["session"].delete.assert_called_with(product)


# ---------------------------------------------------------------------------
# adjust_stock extras
# ---------------------------------------------------------------------------


class TestAdjustStockAssurance:
    def test_adjust_with_notes_and_reason(self, product_client):
        with _products_patches(), patch("routes.products.StockService.adjust_stock") as adjust:
            resp = product_client.post(
                "/products/1/adjust-stock",
                data={
                    "adjustment_type": "add",
                    "quantity": "2",
                    "warehouse_id": "1",
                    "reason": "count",
                    "notes": "cycle count",
                },
            )
        assert resp.status_code == 200
        assert adjust.call_args[1]["notes"] == "cycle count"

    def test_adjust_invalid_type(self, product_client):
        with _products_patches():
            resp = product_client.post(
                "/products/1/adjust-stock",
                data={"adjustment_type": "bogus", "quantity": "1", "warehouse_id": "1"},
            )
        assert resp.status_code == 400

    def test_adjust_server_error_500(self, product_client, mocker):
        mocker.patch("routes.products.tenant_get_or_404", return_value=_product())
        mocker.patch("routes.products.StockService.get_product_stock", return_value=10.0)
        mocker.patch(
            "routes.products.StockService.adjust_stock",
            side_effect=RuntimeError("db"),
        )
        mocker.patch("routes.products.LoggingCore.log_audit")
        mocker.patch(
            "routes.products.ensure_warehouse_access",
            return_value=_warehouse(),
        )
        mocker.patch("routes.products.db.session")
        resp = product_client.post(
            "/products/1/adjust-stock",
            data={"adjustment_type": "add", "quantity": "1", "warehouse_id": "1"},
        )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# api_search
# ---------------------------------------------------------------------------


class TestApiSearchAssurance:
    def test_api_search_no_warehouse_ids_uses_current_stock(self, product_client):
        p = _product(1, current_stock=33)
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value.limit.return_value.all.return_value = [p]
        with _products_patches(visible_query=query), patch(
            "routes.products.get_accessible_warehouse_ids", return_value=[]
        ):
            resp = product_client.get("/products/api/search?q=a")
        assert resp.status_code == 200
        assert resp.get_json()[0]["stock"] == 33.0

    def test_api_search_short_query_returns_all(self, product_client):
        items = [_product(1), _product(2, name="B")]
        query = MagicMock()
        query.order_by.return_value.limit.return_value.all.return_value = items
        with _products_patches(visible_query=query):
            resp = product_client.get("/products/api/search?q=")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2


# ---------------------------------------------------------------------------
# Categories form paths
# ---------------------------------------------------------------------------


class TestCategoriesAssurance:
    def test_create_category_form_duplicate(self, product_client):
        with _products_patches() as ctx:
            ctx["category_query"].filter.return_value.first.return_value = _category()
            resp = product_client.post(
                "/products/categories/create",
                data={"name": "Dup"},
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/categories")

    def test_create_category_form_missing_name(self, product_client):
        with _products_patches():
            resp = product_client.post(
                "/products/categories/create",
                data={"name": "  "},
            )
        assert resp.status_code == 302

    def test_create_category_form_success(self, product_client):
        new_cat = _category(20, name="FormCat")
        pc_class = MagicMock()
        pc_class.query.filter.return_value.first.return_value = None
        pc_class.return_value = new_cat
        with _products_patches(), patch("routes.products.ProductCategory", pc_class):
            resp = product_client.post(
                "/products/categories/create",
                data={"name": "FormCat", "description": "desc"},
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/categories")


# ---------------------------------------------------------------------------
# Print labels
# ---------------------------------------------------------------------------


class TestPrintLabelsAssurance:
    def test_print_label_branch_scope_exception(self, product_client, mocker):
        product = _product()
        mocker.patch("routes.products.tenant_get_or_404", return_value=product)
        mocker.patch(
            "services.label_print_service.get_single_label_html",
            return_value="<html/>",
        )
        with patch(
            "utils.branching.report_branch_scope_id",
            side_effect=RuntimeError("no branch"),
            create=True,
        ):
            resp = product_client.get("/products/1/print-label")
        assert resp.status_code == 200

    def test_print_labels_json_invalid_ids_redirect(self, product_client):
        with _products_patches():
            resp = product_client.post(
                "/products/print-labels",
                json={"product_ids": ["bad", ""]},
            )
        assert resp.status_code == 302

    def test_print_labels_json_success(self, product_client, mocker):
        mocker.patch(
            "services.label_print_service.get_product_labels_html",
            return_value="<batch/>",
        )
        resp = product_client.post(
            "/products/print-labels",
            json={"product_ids": [1, 2]},
        )
        assert resp.status_code == 200
