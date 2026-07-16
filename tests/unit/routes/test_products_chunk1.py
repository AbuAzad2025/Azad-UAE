"""tests/unit/test_products_chunk1.py — Products JSON & batch operation endpoints."""

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_product(product_id, name, sku="SKU-001", price=100.0, stock=50.0,
                  unit="pcs", min_stock=5, barcode="BAR001"):
    p = MagicMock()
    p.id = product_id
    p.name = name
    p.sku = sku
    p.barcode = barcode
    p.regular_price = price
    p.current_stock = stock
    p.min_stock_alert = min_stock
    p.unit = unit
    return p


# =============================================================================
#  /api/search
# =============================================================================

class TestApiSearch:
    ENDPOINT = "/products/api/search"

    @pytest.fixture(autouse=True)
    def _patch_services(self, mocker):
        """Mock services used by api/search so no real DB is hit."""
        self.mock_query = MagicMock(name="products_query")
        self.mock_query.filter.return_value = self.mock_query
        self.mock_query.order_by.return_value = self.mock_query
        self.mock_query.limit.return_value = self.mock_query

        mocker.patch(
            "routes.products.StockService.get_visible_products_query",
            return_value=self.mock_query,
        )
        mocker.patch(
            "routes.products.get_branch_stock_map",
            return_value={},
        )
        mocker.patch(
            "routes.products.get_accessible_warehouse_ids",
            return_value=[],
        )

    def test_search_returns_filtered_products(self, product_client):
        products = [
            _make_product(1, "Test Product A", price=50.0, stock=10),
            _make_product(2, "Test Product B", price=75.0, stock=5),
        ]
        self.mock_query.all.return_value = products

        resp = product_client.get(f"{self.ENDPOINT}?q=test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["name"] == "Test Product A"
        assert data[0]["price"] == 50.0
        assert data[0]["stock"] == 10.0

    def test_empty_query_returns_all(self, product_client):
        products = [_make_product(1, "Prod")]
        self.mock_query.all.return_value = products

        resp = product_client.get(self.ENDPOINT)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1

    def test_empty_results(self, product_client):
        self.mock_query.all.return_value = []

        resp = product_client.get(f"{self.ENDPOINT}?q=zzzzz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []

    def test_with_warehouse_id(self, product_client, mocker):
        mocker.patch(
            "routes.products.get_branch_stock_map",
            return_value={1: 99.0},
        )
        products = [_make_product(1, "Prod", stock=50)]
        self.mock_query.all.return_value = products

        resp = product_client.get(f"{self.ENDPOINT}?q=prod&warehouse_id=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data[0]["stock"] == 99.0

    def test_run_out_product_low_stock_flag(self, product_client):
        products = [
            _make_product(1, "Low", stock=2, min_stock=10),
            _make_product(2, "Ok", stock=20, min_stock=10),
        ]
        self.mock_query.all.return_value = products

        resp = product_client.get(f"{self.ENDPOINT}?q=test")
        data = resp.get_json()
        assert data[0]["is_low_stock"] is True
        assert data[1]["is_low_stock"] is False


# =============================================================================
#  /categories/create
# =============================================================================

class TestCreateCategory:
    ENDPOINT = "/products/categories/create"

    @pytest.fixture(autouse=True)
    def _patch_category(self, mocker):
        pc = mocker.patch("routes.products.ProductCategory")
        pc.query.filter.return_value.first.return_value = None
        pc.return_value.id = 1
        pc.return_value.name = "Test Category"
        pc.return_value.name_ar = "تصنيف اختبار"
        pc.return_value.description = "A test"
        product = mocker.patch("routes.products.Product")
        product.query.filter_by.return_value.count.return_value = 0
        return pc

    def test_json_happy_path(self, product_client, mock_db):
        resp = product_client.post(
            self.ENDPOINT,
            json={"name": "New Category", "name_ar": "تصنيف جديد"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["category"]["name"] == "Test Category"

    def test_json_missing_name_returns_400(self, product_client):
        resp = product_client.post(self.ENDPOINT, json={"name_ar": "only ar"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False

    def test_json_duplicate_name_returns_400(self, product_client, mocker):
        pc = mocker.patch("routes.products.ProductCategory")
        pc.query.filter.return_value.first.return_value = MagicMock(name="existing")

        resp = product_client.post(
            self.ENDPOINT, json={"name": "Existing"}
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False

    def test_json_invalid_body_returns_400(self, product_client):
        resp = product_client.post(
            self.ENDPOINT,
            data=b"not json",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_exception_during_create_returns_400(self, product_client, mocker, mock_db):
        pc = mocker.patch("routes.products.ProductCategory")
        pc.query.filter.return_value.first.return_value = None
        pc.side_effect = Exception("DB fail")

        resp = product_client.post(
            self.ENDPOINT, json={"name": "Cat"}
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False


# =============================================================================
#  /<id>/adjust-stock
# =============================================================================

class TestAdjustStock:
    ENDPOINT = "/products"

    @pytest.fixture(autouse=True)
    def _patch_services(self, mocker):
        self.mock_product = _make_product(1, "Widget", stock=100)
        mocker.patch(
            "routes.products.tenant_get_or_404",
            return_value=self.mock_product,
        )
        mocker.patch(
            "routes.products.StockService.get_product_stock",
            return_value=100.0,
        )
        mocker.patch("routes.products.StockService.adjust_stock")
        mocker.patch("routes.products.LoggingCore.log_audit")
        mocker.patch(
            "routes.products.ensure_warehouse_access",
            return_value=MagicMock(id=1, name="Main WH"),
        )

    def test_add_quantity(self, product_client):
        resp = product_client.post(
            f"{self.ENDPOINT}/1/adjust-stock",
            data={"adjustment_type": "add", "quantity": "10", "warehouse_id": "1"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["new_stock"] == 110.0

    def test_subtract_quantity(self, product_client):
        resp = product_client.post(
            f"{self.ENDPOINT}/1/adjust-stock",
            data={"adjustment_type": "subtract", "quantity": "20", "warehouse_id": "1"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["new_stock"] == 80.0

    def test_set_quantity(self, product_client):
        resp = product_client.post(
            f"{self.ENDPOINT}/1/adjust-stock",
            data={"adjustment_type": "set", "quantity": "150", "warehouse_id": "1"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["new_stock"] == 150.0

    def test_invalid_quantity_returns_422(self, product_client):
        resp = product_client.post(
            f"{self.ENDPOINT}/1/adjust-stock",
            data={"adjustment_type": "add", "quantity": "not-a-number", "warehouse_id": "1"},
        )
        assert resp.status_code == 422

    def test_subtract_below_zero_returns_400(self, product_client):
        resp = product_client.post(
            f"{self.ENDPOINT}/1/adjust-stock",
            data={"adjustment_type": "subtract", "quantity": "999", "warehouse_id": "1"},
        )
        assert resp.status_code == 400

    def test_unknown_type_returns_400(self, product_client):
        resp = product_client.post(
            f"{self.ENDPOINT}/1/adjust-stock",
            data={"adjustment_type": "unknown", "quantity": "10", "warehouse_id": "1"},
        )
        assert resp.status_code == 400

    def test_rollback_on_exception(self, product_client, mocker):
        mocker.patch(
            "routes.products.StockService.adjust_stock",
            side_effect=Exception("Stock service down"),
        )
        resp = product_client.post(
            f"{self.ENDPOINT}/1/adjust-stock",
            data={"adjustment_type": "add", "quantity": "10", "warehouse_id": "1"},
        )
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["success"] is False
