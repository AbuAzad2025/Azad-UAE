"""Scenario mega-grid O — commission margins at industrial scale (100,000 cases)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from services.sale_service import SaleService

REVENUE = [str(v) for v in range(10, 1001, 10)]
COST = [str(v) for v in range(5, 501, 5)]
FX = ["1", "3.65", "0.27", "0.5", "2", "4.5", "11.95", "0.98", "1.05", "4.65"]


class TestMargin100k:
    @pytest.mark.parametrize("revenue,cost,rate", [(r, c, f) for r in REVENUE for c in COST for f in FX])
    def test_grid(self, revenue, cost, rate):
        fx = Decimal(rate)
        fx_rate = Decimal(str(fx))
        expected_cost = Decimal(cost) / fx_rate if fx_rate != 1 else Decimal(cost)
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == (
            Decimal(revenue) - expected_cost
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
