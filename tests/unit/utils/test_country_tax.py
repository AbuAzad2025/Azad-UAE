"""Unit tests for utils/country_tax.py — single source of statutory rates."""

from decimal import Decimal

from utils.country_tax import (
    compute_corporate_tax,
    compute_progressive_tax,
    corporate_rate_for_country,
    customs_rate_for_country,
    excise_rate_for_country,
    get_country_profile,
    is_supported_country,
    personal_brackets_for_country,
    validate_tax_number,
    vat_rate_for_country,
)


def test_vat_rates_by_country():
    assert vat_rate_for_country("PS") == Decimal("16.00")
    assert vat_rate_for_country("IL") == Decimal("17.00")
    assert vat_rate_for_country("AE") == Decimal("5.00")
    assert vat_rate_for_country("SA") == Decimal("15.00")
    assert vat_rate_for_country("XX") == Decimal("0")


def test_supported_countries():
    assert is_supported_country("PS") is True
    assert is_supported_country("IL") is True
    assert is_supported_country("AE") is True
    assert is_supported_country("SA") is True
    assert is_supported_country("FR") is False
    assert is_supported_country("") is False


def test_case_insensitive_country_code():
    assert vat_rate_for_country("ps") == Decimal("16.00")
    assert get_country_profile("ae")["code"] == "AE"


def test_corporate_rates():
    assert corporate_rate_for_country("PS") == Decimal("15")
    assert corporate_rate_for_country("IL") == Decimal("23")
    assert corporate_rate_for_country("AE") == Decimal("9")
    assert corporate_rate_for_country("SA") == Decimal("20")
    assert corporate_rate_for_country("XX") == Decimal("0")


def test_corporate_uae_threshold_zero_tax_below():
    result = compute_corporate_tax(Decimal("375000"), "AE")
    assert result["tax"] == Decimal("0.000")
    assert result["taxable"] == Decimal("0")


def test_corporate_uae_threshold_taxes_excess_only():
    result = compute_corporate_tax(Decimal("475000"), "AE")
    # 9% on 100,000 excess
    assert result["taxable"] == Decimal("100000")
    assert result["tax"] == Decimal("9000.000")


def test_corporate_flat_ps():
    result = compute_corporate_tax(Decimal("100000"), "PS")
    assert result["tax"] == Decimal("15000.000")


def test_corporate_zero_profit_zero_tax():
    assert compute_corporate_tax(Decimal("0"), "AE")["tax"] == Decimal("0")
    assert compute_corporate_tax(Decimal("-5000"), "PS")["tax"] == Decimal("0")


def test_personal_progressive_ps():
    brackets = personal_brackets_for_country("PS")
    assert brackets
    # 48k @0 → tax 0
    assert compute_progressive_tax(Decimal("48000"), brackets) == Decimal("0")
    # 48k 0% + next 48k @5% = 2400
    assert compute_progressive_tax(Decimal("96000"), brackets) == Decimal("2400.000")


def test_personal_progressive_il():
    brackets = personal_brackets_for_country("IL")
    # 77480 @10% = 7748
    assert compute_progressive_tax(Decimal("77480"), brackets) == Decimal("7748.000")


def test_personal_uae_no_brackets_zero_tax():
    assert personal_brackets_for_country("AE") == ()
    assert compute_progressive_tax(Decimal("100000"), ()) == Decimal("0")


def test_customs_rates():
    assert customs_rate_for_country("PS", "agricultural") == Decimal("10")
    assert customs_rate_for_country("PS", "luxury") == Decimal("30")
    assert customs_rate_for_country("PS") == Decimal("15")
    assert customs_rate_for_country("IL", "industrial") == Decimal("18")
    assert customs_rate_for_country("AE") == Decimal("5")
    assert customs_rate_for_country("XX") is None


def test_excise_rates():
    assert excise_rate_for_country("AE", "tobacco") == Decimal("100")
    assert excise_rate_for_country("AE", "soft_drinks") == Decimal("50")
    assert excise_rate_for_country("PS", "tobacco") is None


def test_validate_tax_number_per_country():
    assert validate_tax_number("123456789", "PS") is True
    assert validate_tax_number("12345", "PS") is False
    assert validate_tax_number("123456789012345", "AE") is True
    assert validate_tax_number("123", "AE") is False
    assert validate_tax_number("300000000000001", "SA") is True
    assert validate_tax_number("123456789", "IL") is True
    assert validate_tax_number("", "AE") is False
    assert validate_tax_number(None, "AE") is False


def test_null_profile_unsupported_country():
    profile = get_country_profile("ZZ")
    assert profile["code"] == "XX"
    assert profile["vat_return_format"] == "null"
