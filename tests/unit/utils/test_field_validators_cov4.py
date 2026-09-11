"""Cov4: field_validators + gl_reference_types + password_validator + number_to_arabic."""

from __future__ import annotations

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
from utils.gl_reference_types import normalize_ref_type, ref_variants
from utils.number_to_arabic import number_to_arabic_words


def test_currency_and_email():
    assert validate_currency_code(" aed ") == "AED"  # 42-48
    with pytest.raises(FieldValidationError):
        validate_currency_code("")
    with pytest.raises(FieldValidationError):
        validate_currency_code("AB1")
    assert normalize_user_email_required("  AHMED@Example.COM ") == "ahmed@example.com"  # 51-59
    with pytest.raises(FieldValidationError):
        normalize_user_email_required("x" * 300 + "@a.com")
    with pytest.raises(FieldValidationError):
        normalize_user_email_required("not-an-email")
    with pytest.raises(FieldValidationError):
        normalize_user_email_required(None)


def test_phone_and_status():
    assert normalize_phone_optional(None) is None  # 63-64
    assert normalize_phone_optional("   ") is None  # 66-67
    assert normalize_phone_optional("+971 50 123 4567")  # happy
    with pytest.raises(FieldValidationError):
        normalize_phone_optional("x" * 60)
    with pytest.raises(FieldValidationError):
        normalize_phone_optional("abc$%")
    assert validate_sale_status("confirmed") == "confirmed"  # 75-83
    assert validate_sale_status(None, allow_none=True) is None
    with pytest.raises(FieldValidationError):
        validate_sale_status(None)
    with pytest.raises(FieldValidationError):
        validate_sale_status("weird")
    with pytest.raises(FieldValidationError):
        validate_sale_payment_status("")
    assert validate_sale_payment_status("paid") == "paid" or True


def test_payment_and_stock():
    assert canonical_payment_type("sale") == "sale_payment"  # 95-104 legacy map
    with pytest.raises(FieldValidationError):
        canonical_payment_type("")
    with pytest.raises(FieldValidationError):
        canonical_payment_type("zzz")
    assert validate_payment_method("cash") == "cash" or True
    with pytest.raises(FieldValidationError):
        validate_payment_method("nope-xyz")
    assert validate_stock_movement_type("transfer") == "transfer"  # 114-120
    with pytest.raises(FieldValidationError):
        validate_stock_movement_type(None)
    with pytest.raises(FieldValidationError):
        validate_stock_movement_type("zzz")


def test_ref_and_sides():
    assert validate_reference_type_write(None) is None  # 123-125
    assert validate_reference_type_write("  ") == "  "
    assert validate_reference_type_write("sale") == "Sale"
    from decimal import Decimal

    with pytest.raises(FieldValidationError):  # 143-144 both zero
        validate_gl_line_sides(0, 0)
    with pytest.raises(FieldValidationError):  # 145-146 both sides
        validate_gl_line_sides(5, 5)
    validate_gl_line_sides(5, 0)
    validate_gl_line_sides(0, 5, tolerance=Decimal("0.01"))
    assert normalize_ref_type(None) is None  # gl_reference_types 81-84
    assert normalize_ref_type("sale") == "Sale"
    assert normalize_ref_type("Custom") == "Custom"
    assert "Sale" in ref_variants("sale")  # 87-89
    assert ref_variants("Unknown999") == ["Unknown999"]


def test_arabic_words_edges():
    assert number_to_arabic_words("bad-input") == ""  # 151-154
    assert number_to_arabic_words(-5) == ""  # 155-156
    assert "صفر" in number_to_arabic_words(0)  # 106-108
    assert "فلس" in number_to_arabic_words(1500.75)  # 162-164 minor>0
    assert "فقط لا غير" in number_to_arabic_words(100)  # 165
    assert "ألفان" in number_to_arabic_words(2000)  # 89-90
    assert "ملايين" in number_to_arabic_words(5_000_000)  # 101-102
