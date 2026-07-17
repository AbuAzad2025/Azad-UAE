from __future__ import annotations

import pytest

from models.store_payment_method import StorePaymentMethod


class TestStorePaymentMethodHelpers:
    def test_get_config_empty(self):
        pm = StorePaymentMethod(code="cod", name_ar="نقد", name_en="COD")
        assert pm.get_config() == {}

    def test_get_config_valid_json(self):
        pm = StorePaymentMethod(code="bank", name_ar="بنك", name_en="Bank")
        pm.config_json = '{"key": "value"}'
        assert pm.get_config() == {"key": "value"}

    def test_get_config_invalid_json(self):
        pm = StorePaymentMethod(code="bad", name_ar="x", name_en="x")
        pm.config_json = "not-json"
        assert pm.get_config() == {}

    def test_get_config_non_dict_json(self):
        pm = StorePaymentMethod(code="list", name_ar="x", name_en="x")
        pm.config_json = "[1, 2]"
        assert pm.get_config() == {}

    def test_set_config_round_trip(self):
        pm = StorePaymentMethod(code="cfg", name_ar="x", name_en="x")
        pm.set_config({"a": 1})
        assert pm.get_config() == {"a": 1}

    def test_display_name_en(self):
        pm = StorePaymentMethod(code="cod", name_ar="نقد", name_en="Cash on Delivery")
        assert pm.display_name("en") == "Cash on Delivery"

    def test_display_name_ar_fallback(self):
        pm = StorePaymentMethod(code="cod", name_ar="نقد", name_en="")
        assert pm.display_name("ar") == "نقد"

    def test_display_description_en(self):
        pm = StorePaymentMethod(
            code="cod",
            name_ar="نقد",
            name_en="COD",
            description_ar="وصف",
            description_en="Pay on delivery",
        )
        assert pm.display_description("en") == "Pay on delivery"

    def test_display_description_ar_fallback(self):
        pm = StorePaymentMethod(
            code="cod",
            name_ar="نقد",
            name_en="COD",
            description_ar="ادفع عند الاستلام",
            description_en="",
        )
        assert pm.display_description("ar") == "ادفع عند الاستلام"

    def test_normalize_code_valid(self):
        assert StorePaymentMethod.normalize_code("Bank-Transfer") == "bank_transfer"

    def test_normalize_code_invalid(self):
        with pytest.raises(ValueError, match="رمز"):
            StorePaymentMethod.normalize_code("123bad")

    def test_repr(self):
        pm = StorePaymentMethod(
            code="cod", name_ar="نقد", name_en="COD", is_enabled=True
        )
        assert "cod" in repr(pm)
