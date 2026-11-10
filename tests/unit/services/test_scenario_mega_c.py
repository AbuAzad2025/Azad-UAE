"""Scenario mega-grid C — sale totals, tax strategies, MWAC, progressive tax."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from models.sale import SaleLine
from services.stock_service import _MWACHelper
from services.tax_service import TaxService
from utils.country_tax import compute_progressive_tax


class TestSaleTotalsMega:
    @pytest.mark.parametrize(
        "qty,price,disc",
        [
            (str(q), str(p), str(d))
            for q in (1, 2, 3, 5, 10, 25, 100, 7, 12, 50, 4, 20)
            for p in (5, 9.99, 25, 50, 100, 333.33, 1000, 15, 75, 250, 8, 60)
            for d in (0, 10, 25, 50, 90, 100)
        ],
    )
    def test_grid(self, qty, price, disc):
        line = SaleLine(quantity=Decimal(qty), unit_price=Decimal(price), discount_percent=Decimal(disc))
        line.calculate_line_total()
        expected = (Decimal(qty) * Decimal(price) * (Decimal("1") - Decimal(disc) / Decimal("100"))).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
        assert line.line_total == expected


class TestTaxStrategyMega:
    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (100, 500, 1000, 2500, 10000) for r in (5, 15, 16, 18, 0)],
    )
    def test_grid(self, amount, rate):
        strategy = TaxService._get_strategy(tenant_id=None)
        result = strategy.calculate_tax(Decimal(amount), Decimal(rate))
        assert Decimal(str(result["tax_amount"])) == (Decimal(amount) * Decimal(rate) / Decimal("100")).quantize(
            Decimal("0.01")
        )


class TestMwacMega:
    @pytest.mark.parametrize(
        "change,unit",
        [(str(c), str(u)) for c in (5, 25, 50, 100, 500, 1000, -10, -50, -100, 7) for u in (5, 20, 50, 60, 100, 250, 80, 15, 33, 99)],
    )
    def test_grid(self, change, unit):
        qty, value, avg = _MWACHelper.calc(Decimal("200"), Decimal("10000"), Decimal(change), Decimal(unit))
        assert qty == Decimal("200") + Decimal(change)
        assert value == Decimal("10000") + Decimal(change) * Decimal(unit)
        assert avg == (value / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class TestProgressiveMega:
    @pytest.mark.parametrize("income", [str(v) for v in range(0, 400001, 25000)])
    def test_grid(self, income):
        brackets = [(50000, Decimal("0")), (150000, Decimal("10")), (None, Decimal("20"))]
        tax = compute_progressive_tax(Decimal(income), brackets)
        t = Decimal(income)
        expected = Decimal("0")
        lower = Decimal("0")
        for upper, rate in brackets:
            if t <= lower:
                break
            top = t if upper is None else min(t, Decimal(str(upper)))
            expected += (top - lower) * rate / Decimal("100")
            if upper is None:
                break
            lower = Decimal(str(upper))
        assert tax == expected.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
