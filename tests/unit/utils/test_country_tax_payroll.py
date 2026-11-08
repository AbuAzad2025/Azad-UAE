"""Pin the statutory payroll rates — the exact 2025 statutory figures.

These tests fail if anyone edits a rate, ceiling or floor in
``utils/country_tax.py`` without deliberately bumping the legal constants.
Each block cites the instrument the rate comes from.
"""

from decimal import Decimal

from utils.country_tax import (
    payroll_income_tax_amount,
    social_insurance_amount,
)


def _si(gross, country, **kw):
    return social_insurance_amount(gross, country, **kw)


# Palestinian NSSF — law 6/2016 social security law.
def test_ps_nssf_rates_and_ceiling():
    result = _si(Decimal("5000"), "PS")
    assert result["employee"] == Decimal("350.000")  # 7%
    assert result["employer"] == Decimal("450.000")  # 9%
    assert result["ceiling"] == Decimal("18800")
    assert result["eligible"] is True


def test_ps_nssf_cap_applies():
    result = _si(Decimal("30000"), "PS")
    assert result["employee"] == Decimal("1316.000")  # 18800 * 7%
    assert result["employer"] == Decimal("1692.000")  # 18800 * 9%


# IL — Bituach Leumi + Mas Briut, two tiers. 2025: reduced-rate threshold
# 7,522 NIS, max insurable salary 50,695 NIS.
def test_il_two_tier_rates_low_band():
    result = _si(Decimal("7000"), "IL")
    assert result["employee"] == Decimal("245.000")  # 7000 * 3.5%
    assert result["employer"] == Decimal("315.700")  # 7000 * 4.51%


def test_il_two_tier_rates_across_threshold():
    result = _si(Decimal("8000"), "IL")
    expected_emp = Decimal("7522") * Decimal("0.035") + Decimal("478") * Decimal("0.12")
    expected_er = Decimal("7522") * Decimal("0.0451") + Decimal("478") * Decimal("0.076")
    assert result["employee"] == expected_emp.quantize(Decimal("0.001"))
    assert result["employer"] == expected_er.quantize(Decimal("0.001"))


def test_il_above_max_insurable_salary_is_capped():
    result = _si(Decimal("80000"), "IL")
    # Above the 50,695 ceiling, no additional contributions on the excess.
    assert result["ceiling"] == Decimal("50695")
    capped = _si(Decimal("50695"), "IL")
    assert result["employee"] == capped["employee"]
    assert result["employer"] == capped["employer"]


# KSA — GOSI (2025). New social insurance law applies from 2024-07-03.
def test_sa_gosi_new_law_member():
    result = _si(Decimal("5000"), "SA", is_national=True, joined_2024_07_03_or_later=True)
    assert result["employee"] == Decimal("512.500")  # 10.25%
    assert result["employer"] == Decimal("612.500")  # 12.25%


def test_sa_gosi_pre_july_2024_member():
    result = _si(Decimal("5000"), "SA", is_national=True, joined_2024_07_03_or_later=False)
    assert result["employee"] == Decimal("487.500")  # 9.75%
    assert result["employer"] == Decimal("587.500")  # 11.75%


def test_sa_gosi_non_national_pays_hazards_only():
    result = _si(Decimal("5000"), "SA", is_national=False)
    assert result["employee"] == Decimal("0")
    assert result["employer"] == Decimal("100.000")  # 2% occupational hazards


def test_sa_gosi_ceiling():
    result = _si(Decimal("100000"), "SA", is_national=True, joined_2024_07_03_or_later=True)
    assert result["employee"] == Decimal("4612.500")  # 45000 * 10.25%


# UAE — GPSSA (Federal Decree Law No. 57 of 2023), nationals only.
def test_ae_gpssa_nationals_only():
    result = _si(Decimal("10000"), "AE", is_national=False)
    assert result["employee"] == Decimal("0")
    assert result["employer"] == Decimal("0")
    assert result["eligible"] is False


def test_ae_gpssa_national_rates():
    result = _si(Decimal("10000"), "AE", is_national=True)
    assert result["employee"] == Decimal("1100.000")  # 11%
    assert result["employer"] == Decimal("1500.000")  # 15%
    assert result["ceiling"] == Decimal("70000")


def test_ae_gpssa_ceiling():
    result = _si(Decimal("90000"), "AE", is_national=True)
    assert result["employee"] == Decimal("7700.000")  # 70000 * 11%
    assert result["employer"] == Decimal("10500.000")  # 70000 * 15%


# Personal income tax — progressive brackets in utils/country_tax.py.
def test_ae_sa_have_no_personal_income_tax():
    assert payroll_income_tax_amount(Decimal("360000"), "AE")["tax"] == Decimal("0")
    assert payroll_income_tax_amount(Decimal("360000"), "SA")["tax"] == Decimal("0")


def test_ps_income_tax_below_exempt_band():
    assert payroll_income_tax_amount(Decimal("40000"), "PS")["tax"] == Decimal("0.000")


def test_ps_income_tax_brackets():
    # 25000 above the 48k exempt band at 5%, nothing more.
    assert payroll_income_tax_amount(Decimal("73000"), "PS")["tax"] == Decimal("1250.000")


def test_il_income_tax_uses_credit_points():
    gross_tax = payroll_income_tax_amount(Decimal("77480"), "IL", credit_points=Decimal("0"))["tax"]
    with_credit = payroll_income_tax_amount(Decimal("77480"), "IL")["tax"]
    assert gross_tax == Decimal("7748.000")  # 77480 * 10%
    assert with_credit == Decimal("1214.000")  # 7748 - 2.25 * 2904


def test_il_income_tax_credit_points_cannot_go_negative():
    # Below the point where credit points fully offset the bill.
    assert payroll_income_tax_amount(Decimal("10000"), "IL")["tax"] == Decimal("0")


def test_unknown_country_returns_zero():
    result = _si(Decimal("5000"), "XX")
    assert result["employee"] == Decimal("0")
    assert result["employer"] == Decimal("0")
    assert payroll_income_tax_amount(Decimal("60000"), "XX")["tax"] == Decimal("0")
