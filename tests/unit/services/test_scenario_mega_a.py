"""Scenario mega-grid A — money math (conversion, margins, withholding).

Cartesian grids; every expectation is an independent hand formula.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from services.expense_service import ExpenseService
from services.sale_service import SaleService
from utils.currency_utils import convert_and_quantize_aed

CONV_AMOUNTS = [
    str(v) for v in (1, 7, 33, 99, 250, 999, 5000, 12345, 100000, 3, 17, 88, 400, 2025, 77, 555, 9000, 12, 600, 31415)
]
CONV_RATES = [
    str(v)
    for v in (
        "0.0027",
        "0.27",
        "0.5",
        "1",
        "1.5",
        "2",
        "3.65",
        "4.5",
        "10",
        "0.9",
        "5.25",
        "0.0037",
        "7",
        "0.036",
        "12.5",
    )
]
MARGIN_REVENUE = [str(v) for v in (50, 100, 150, 200, 300, 500, 750, 1000, 2500, 9999, 60, 420)]
MARGIN_COST = [str(v) for v in (10, 40, 50, 100, 200, 365, 500, 730)]
MARGIN_RATES = ["1", "3.65", "0.5", "2"]
WH_AMOUNTS = [str(v) for v in (10, 25, 100, 250, 500, 999, 1000, 5000, 10000, 7, 33, 333, 750, 1250, 99999)]
WH_RATES = [str(v) for v in ("0", "1", "2", "3", "5", "7.5", "10", "15", "20", "30", "50", "7.25")]


class TestConversionMega:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in CONV_AMOUNTS for r in CONV_RATES])
    def test_grid(self, amount, rate):
        expected = (Decimal(amount) * Decimal(rate)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == expected


class TestMarginMega:
    @pytest.mark.parametrize(
        "revenue,cost,rate",
        [(r, c, f) for r in MARGIN_REVENUE for c in MARGIN_COST for f in MARGIN_RATES],
    )
    def test_grid(self, revenue, cost, rate):
        fx = Decimal(rate)
        expected = (Decimal(revenue) - Decimal(cost)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == expected


class TestWithholdingMega:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in WH_AMOUNTS for r in WH_RATES])
    def test_grid(self, amount, rate):
        expected = (Decimal(amount) * Decimal(rate) / Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == expected
