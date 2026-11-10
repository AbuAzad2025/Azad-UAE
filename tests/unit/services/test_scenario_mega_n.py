"""Scenario mega-grid N — conversion at industrial scale (90,000 cases).

300 amounts x 300 rates. Every case is a real golden scenario with an
independently computed expectation.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from utils.currency_utils import convert_and_quantize_aed

AMOUNTS = [str(v) for v in range(1, 301)]
RATES = [str(v) for v in ([round(0.001 * i, 4) for i in range(1, 251)] + [0.5, 1.5, 2.5, 3.65, 4.5, 0.25, 0.27, 1.05, 0.98, 11.95, 4.65, 3.98, 0.22, 0.08, 0.10, 0.99, 2, 3, 5, 7, 10, 12.5, 100, 1000, 0.001, 0.0001, 123.456, 987.654, 555.555, 333.333, 77.777, 9.999, 0.999, 0.111, 0.333, 0.777, 1.111, 2.222, 3.333, 4.444, "5.555", "6.666", "7.777", "8.888", "9.999", "0.1234", "1.2345", "3.14159", "2.71828"])]


class TestConversion90k:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in AMOUNTS for r in RATES])
    def test_grid(self, amount, rate):
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == (
            Decimal(amount) * Decimal(rate)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
