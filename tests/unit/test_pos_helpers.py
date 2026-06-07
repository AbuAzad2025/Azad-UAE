import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from utils.pos_helpers import (
    POS_WALKIN_MARKER,
    POS_QA_MARKER,
    get_pos_walkin_customer,
    merge_checkout_lines,
    serialize_pos_product,
    _warehouse_ids_for_stock,
)

class TestMergeCheckoutLines:
    def test_merge_duplicate_products(self):
        lines = [
            {"product_id": 1, "quantity": 2, "discount_percent": 0, "unit_price": 100},
            {"product_id": 1, "quantity": 3, "discount_percent": 0, "unit_price": 100},
        ]
        result = merge_checkout_lines(lines)
        assert len(result) == 1
        assert result[0]["quantity"] == Decimal("5")
        assert result[0]["product_id"] == 1
    def test_keeps_last_discount(self):
        lines = [
            {"product_id": 1, "quantity": 1, "discount_percent": 5, "unit_price": 100},
            {"product_id": 1, "quantity": 2, "discount_percent": 10, "unit_price": 100},
        ]
        result = merge_checkout_lines(lines)
        assert result[0]["discount_percent"] == Decimal("10")
    def test_preserves_unit_price(self):
        lines = [
            {"product_id": 1, "quantity": 1, "discount_percent": 0, "unit_price": 100},
            {"product_id": 1, "quantity": 2, "discount_percent": 0, "unit_price": None},
        ]
        result = merge_checkout_lines(lines)
        assert result[0]["unit_price"] == Decimal("100")
    def test_rejects_invalid_quantity(self):
        with pytest.raises(ValueError):
            merge_checkout_lines([{"product_id": 1, "quantity": 0, "discount_percent": 0}])
    def test_rejects_negative_discount(self):
        with pytest.raises(ValueError):
            merge_checkout_lines([{"product_id": 1, "quantity": 1, "discount_percent": -5}])
    def test_rejects_discount_over_100(self):
        with pytest.raises(ValueError):
            merge_checkout_lines([{"product_id": 1, "quantity": 1, "discount_percent": 101}])
    def test_rejects_non_dict_row(self):
        with pytest.raises(ValueError):
            merge_checkout_lines(["invalid"])
    def test_maintains_order(self):
        lines = [
            {"product_id": 1, "quantity": 1, "discount_percent": 0},
            {"product_id": 2, "quantity": 1, "discount_percent": 0},
            {"product_id": 1, "quantity": 1, "discount_percent": 0},
        ]
        result = merge_checkout_lines(lines)
        assert [r["product_id"] for r in result] == [1, 2]

class TestSerializePosProduct:
    def test_basic_serialization(self):
        product = MagicMock()
        product.id = 1
        product.name = "Test Product"
        product.name_ar = "منتج تجريبي"
        product.sku = "SKU123"
        product.barcode = "123456"
        product.regular_price = Decimal("99.99")
        product.unit = "piece"
        product.is_active = True
        result = serialize_pos_product(product, {1: 10})
        assert result["id"] == 1
        assert result["name"] == "Test Product"
        assert result["sku"] == "SKU123"
        assert result["barcode"] == "123456"
        assert result["price"] == 99.99
        assert result["stock"] == 10.0
        assert result["is_out_of_stock"] is False
    def test_out_of_stock(self):
        product = MagicMock()
        product.id = 1
        product.name = "Empty"
        product.name_ar = ""
        product.sku = ""
        product.barcode = ""
        product.regular_price = None
        product.unit = ""
        product.is_active = True
        product.current_stock = 0
        result = serialize_pos_product(product, {})
        assert result["is_out_of_stock"] is True
        assert result["price"] == 0.0
    def test_inactive_product(self):
        product = MagicMock()
        product.id = 1
        product.name = "Inactive"
        product.name_ar = ""
        product.sku = ""
        product.barcode = ""
        product.regular_price = None
        product.unit = ""
        product.is_active = False
        result = serialize_pos_product(product, {})
        assert result["is_inactive"] is True
    def test_label_with_sku(self):
        product = MagicMock()
        product.id = 1
        product.name = "Item"
        product.sku = "ABC"
        product.name_ar = ""
        product.barcode = ""
        product.regular_price = None
        product.unit = ""
        product.is_active = True
        result = serialize_pos_product(product, {})
        assert result["text"] == "Item (ABC)"
    def test_label_without_sku(self):
        product = MagicMock()
        product.id = 1
        product.name = "Item"
        product.sku = ""
        product.name_ar = ""
        product.barcode = ""
        product.regular_price = None
        product.unit = ""
        product.is_active = True
        result = serialize_pos_product(product, {})
        assert result["text"] == "Item"

class TestWarehouseIdsForStock:
    def test_specific_warehouse(self):
        result = _warehouse_ids_for_stock(5)
        assert result == [5]
    def test_none_uses_user_warehouses(self):
        with patch("utils.pos_helpers.get_accessible_warehouse_ids") as mock:
            mock.return_value = [1, 2]
            result = _warehouse_ids_for_stock(None, user="dummy")
            assert result == [1, 2]

class TestConstants:
    def test_walkin_marker(self):
        assert POS_WALKIN_MARKER == "[POS-WALKIN]"
    def test_qa_marker(self):
        assert POS_QA_MARKER == "[POS-QA]"
