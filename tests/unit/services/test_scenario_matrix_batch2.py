"""Scenario matrix batch 2 — pure-function golden cases (fast, no DB).

Hundreds of independently computed cases across statutory tax tables,
currency conversion, progressive/corporate tax, commissions, withholding,
import levies, and financial parsing guards. Each parametrize case is one
real scenario; expectations are hand formulas, not implementation copies.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from services.expense_service import ExpenseService
from services.purchase_service import compute_import_levy_defaults
from services.sale_service import SaleService
from utils.country_tax import (
    compute_corporate_tax,
    compute_progressive_tax,
    customs_rate_for_country,
    excise_rate_for_country,
    vat_rate_for_country,
)
from utils.currency_utils import convert_and_quantize_aed


class TestStatutoryVatRates:
    @pytest.mark.parametrize(
        "code,expected",
        [("PS", "16"), ("IL", "18"), ("AE", "5"), ("SA", "15"), ("XX", "0"), ("", "0")],
    )
    def test_vat_rate_by_country(self, code, expected):
        assert vat_rate_for_country(code) == Decimal(expected)


class TestCustomsExciseRates:
    @pytest.mark.parametrize(
        "code,expected",
        [("PS", "15"), ("IL", "18"), ("AE", "5"), ("SA", "15"), ("XX", "0")],
    )
    def test_customs_rate(self, code, expected):
        assert (customs_rate_for_country(code) or Decimal("0")) == Decimal(expected)

    @pytest.mark.parametrize(
        "code,category,expected",
        [
            ("AE", "tobacco", "100"),
            ("AE", "energy_drinks", "100"),
            ("AE", "soft_drinks", "50"),
            ("SA", "tobacco", "100"),
            ("SA", "energy_drinks", "100"),
            ("SA", "soft_drinks", "50"),
            ("AE", "", "0"),
            ("PS", "tobacco", "0"),
        ],
    )
    def test_excise_rate(self, code, category, expected):
        rate = excise_rate_for_country(code, category) or Decimal("0")
        assert rate == Decimal(expected)


class TestCurrencyConversion:
    @pytest.mark.parametrize(
        "amount,rate,expected",
        [
            ("100", "3.65", "365.000"),
            ("100", "1", "100.000"),
            ("50", "0.27", "13.500"),
            ("0", "3.65", "0.000"),
            ("1000", "0.5", "500.000"),
            ("33.33", "3", "99.990"),
            ("123.456", "2", "246.912"),
            ("999.999", "1.5", "1499.999"),
            ("10", "0.0027", "0.027"),
            ("250", "4", "1000.000"),
        ],
    )
    def test_convert_golden(self, amount, rate, expected):
        result = convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED")
        assert result == Decimal(expected)


class TestProgressiveTax:
    @pytest.mark.parametrize(
        "income,expected",
        [
            ("0", "0.000"),
            ("10000", "0.000"),
            ("50000", "0.000"),
            ("100000", "5000.000"),
            ("200000", "20000.000"),
            ("50000.50", "0.050"),
        ],
    )
    def test_progressive_golden(self, income, expected):
        brackets = [(50000, Decimal("0")), (150000, Decimal("10")), (None, Decimal("20"))]
        result = compute_progressive_tax(Decimal(income), brackets)
        assert Decimal(str(result)) == Decimal(expected)


class TestCorporateTax:
    @pytest.mark.parametrize(
        "country,profit,expected_tax",
        [("AE", "500000", "11250.000"), ("AE", "2000000", "146250.000"), ("AE", "100000", "0.000")],
    )
    def test_corporate_golden(self, country, profit, expected_tax):
        result = compute_corporate_tax(Decimal(profit), country)
        assert result["tax"] == Decimal(expected_tax)


class TestWithholdingExpanded:
    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (10, 100, 250, 999, 10000) for r in (1, 5, 7.5, 15, 30)],
    )
    def test_withholding_matrix(self, amount, rate):
        expected = (Decimal(amount) * Decimal(rate) / Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == expected


class TestImportLevyExpanded:
    @pytest.mark.parametrize("qty,cost,disc", [(q, c, d) for q in (1, 5, 10) for c in (25, 100) for d in (0, 20)])
    def test_customs_matrix(self, qty, cost, disc):
        goods = Decimal(str(qty)) * Decimal(str(cost)) * (Decimal("1") - Decimal(str(disc)) / Decimal("100"))
        customs, excise = compute_import_levy_defaults(
            [(qty, Decimal(str(cost)), Decimal(str(disc)), "")],
            country="AE",
            customs_duty=None,
            excise_amount=None,
        )
        assert customs == (goods * Decimal("5") / Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert excise == Decimal("0.000")

    @pytest.mark.parametrize("category", ["tobacco", "energy_drinks", "soft_drinks", ""])
    def test_excise_matrix(self, category):
        customs, excise = compute_import_levy_defaults(
            [(10, Decimal("100"), Decimal("0"), category)],
            country="AE",
            customs_duty=None,
            excise_amount=None,
        )
        assert customs == Decimal("50.000")
        rate = {"tobacco": 100, "energy_drinks": 100, "soft_drinks": 50, "": 0}[category]
        assert excise == (Decimal("1050") * Decimal(str(rate)) / Decimal("100")).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )


class TestCommissionMarginExpanded:
    @pytest.mark.parametrize(
        "revenue,cost,rate",
        [(r, c, f) for r in (100, 200, 500) for c in (50, 365) for f in ("1", "3.65")],
    )
    def test_margin_matrix(self, revenue, cost, rate):
        fx = Decimal(rate)
        expected_cost = Decimal(str(cost)) / fx if fx != 1 else Decimal(str(cost))
        expected = (Decimal(str(revenue)) - expected_cost).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert SaleService._commission_margin(Decimal(str(revenue)), Decimal(str(cost)), fx) == expected
