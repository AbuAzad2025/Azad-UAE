"""Field validators — currency, phone, sale/payment/stock/GL line guards."""

from __future__ import annotations

from decimal import Decimal

import pytest

from utils.field_validators import (
    FieldValidationError,
    canonical_payment_type,
    normalize_phone_optional,
    normalize_user_email_required,
    validate_currency_code,
    validate_gl_line_sides,
    validate_payment_method,
    validate_reference_type_write,
    validate_sale_payment_status,
    validate_sale_status,
    validate_stock_movement_type,
)


class TestCurrencyAndPhone:
    def test_validate_currency_code_ok(self):
        assert validate_currency_code("aed") == "AED"

    def test_validate_currency_code_empty(self):
        with pytest.raises(FieldValidationError, match="العملة"):
            validate_currency_code("")

    def test_validate_currency_code_bad_format(self):
        with pytest.raises(FieldValidationError, match="ISO"):
            validate_currency_code("US")

    def test_normalize_phone_optional_none(self):
        assert normalize_phone_optional(None) is None
        assert normalize_phone_optional("  ") is None

    def test_normalize_phone_optional_ok(self):
        assert normalize_phone_optional("+971 50 123-4567") == "+971 50 123-4567"

    def test_normalize_user_email_required_ok(self):
        assert (
            normalize_user_email_required("  User@Example.COM  ") == "user@example.com"
        )

    def test_normalize_user_email_required_missing(self):
        with pytest.raises(FieldValidationError, match="Email is required"):
            normalize_user_email_required("")
        with pytest.raises(FieldValidationError, match="Email is required"):
            normalize_user_email_required(None)

    def test_normalize_user_email_required_invalid(self):
        with pytest.raises(FieldValidationError, match="Invalid email"):
            normalize_user_email_required("not-an-email")

    def test_normalize_phone_too_long(self):
        with pytest.raises(FieldValidationError, match="الطول"):
            normalize_phone_optional("1" * 51)

    def test_normalize_phone_bad_chars(self):
        with pytest.raises(FieldValidationError, match="أحرف"):
            normalize_phone_optional("abc")


class TestSaleAndPaymentStatus:
    def test_validate_sale_status_ok(self):
        assert validate_sale_status("confirmed") == "confirmed"

    def test_validate_sale_status_allow_none(self):
        assert validate_sale_status(None, allow_none=True) is None

    def test_validate_sale_status_invalid(self):
        with pytest.raises(FieldValidationError, match="غير مدعومة"):
            validate_sale_status("draft")

    def test_validate_sale_payment_status_ok(self):
        assert validate_sale_payment_status("paid") == "paid"

    def test_validate_sale_payment_status_invalid(self):
        with pytest.raises(FieldValidationError):
            validate_sale_payment_status("unknown")


class TestPaymentTypeAndMethod:
    def test_canonical_payment_type_legacy_sale(self):
        assert canonical_payment_type("sale", for_new=True) == "sale_payment"

    def test_canonical_payment_type_empty(self):
        with pytest.raises(FieldValidationError, match="نوع الدفعة"):
            canonical_payment_type("")

    def test_canonical_payment_type_unknown(self):
        with pytest.raises(FieldValidationError, match="غير مدعوم"):
            canonical_payment_type("crypto")

    def test_validate_payment_method_ok(self):
        assert validate_payment_method("cash") == "cash"

    def test_validate_payment_method_invalid(self):
        with pytest.raises(FieldValidationError, match="طريقة الدفع"):
            validate_payment_method("bitcoin")


class TestStockAndGl:
    def test_validate_stock_movement_type_ok(self):
        assert validate_stock_movement_type("transfer") == "transfer"

    def test_validate_stock_movement_type_missing(self):
        with pytest.raises(FieldValidationError, match="نوع حركة"):
            validate_stock_movement_type(None)

    def test_validate_stock_movement_type_unknown(self):
        with pytest.raises(FieldValidationError, match="غير مدعوم"):
            validate_stock_movement_type("magic")

    def test_validate_sale_status_empty_raises(self):
        with pytest.raises(FieldValidationError):
            validate_sale_status("   ")

    def test_validate_sale_payment_status_empty_raises(self):
        with pytest.raises(FieldValidationError):
            validate_sale_payment_status("  ")

    def test_validate_reference_type_write_whitespace_passthrough(self):
        assert validate_reference_type_write("   ") == "   "

    def test_validate_reference_type_write_legacy_value(self, mocker):
        mocker.patch("utils.field_validators.normalize_ref_type", return_value="Sale")
        mocker.patch("utils.field_validators.LEGACY_REF_MAP", {"sale": "Sale"})
        assert validate_reference_type_write("sale") == "Sale"

    def test_validate_reference_type_write_non_legacy(self, mocker):
        mocker.patch(
            "utils.field_validators.normalize_ref_type", return_value="CustomRef"
        )
        mocker.patch("utils.field_validators.LEGACY_REF_MAP", {"sale": "Sale"})
        assert validate_reference_type_write("CustomRef") == "CustomRef"

    def test_validate_gl_line_sides_debit_only(self):
        validate_gl_line_sides(100, 0)

    def test_validate_gl_line_sides_both_zero(self):
        with pytest.raises(FieldValidationError, match="مدين أو دائن"):
            validate_gl_line_sides(0, 0)

    def test_validate_gl_line_sides_both_nonzero(self):
        with pytest.raises(FieldValidationError, match="لا يجوز"):
            validate_gl_line_sides(100, 50)

    def test_validate_gl_line_sides_custom_tolerance(self):
        validate_gl_line_sides(
            Decimal("0.005"), Decimal("0.005"), tolerance=Decimal("0.01")
        )
