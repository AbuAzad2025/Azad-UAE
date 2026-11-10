"""Scenario mega-grid M — margin/withholding/payroll/levy/sale at scale."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from models.sale import SaleLine
from services.expense_service import ExpenseService
from services.purchase_service import compute_import_levy_defaults
from services.sale_service import SaleService
from utils.country_tax import social_insurance_amount

MARGIN_R = [str(v) for v in range(10, 301, 10)]
MARGIN_C = [str(v) for v in range(5, 251, 5)]
MARGIN_FX = ["1", "3.65", "0.27", "0.5", "2", "4.5", "11.95", "0.98", "1.05", "4.65"]
WHT_A = [str(v) for v in range(5, 501, 5)]
WHT_R = [str(v) for v in range(0, 51)]
SOCIAL = [str(v) for v in range(250, 100001, 250)]
SALE_Q = [str(v) for v in range(1, 21)]
SALE_P = [str(v) for v in range(5, 201, 5)]
SALE_D = [str(v) for v in (0, 5, 10, 20, 25, 33, 50, 75, 90, 100)]
LEVY_Q = [str(v) for v in range(1, 11)]
LEVY_C = [str(v) for v in range(10, 201, 10)]
LEVY_K = ["tobacco", "energy_drinks", "soft_drinks", ""]


class TestMarginM:
    @pytest.mark.parametrize("revenue,cost,rate", [(r, c, f) for r in MARGIN_R for c in MARGIN_C for f in MARGIN_FX])
    def test_grid(self, revenue, cost, rate):
        fx = Decimal(rate)
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == (
            Decimal(revenue) - Decimal(cost)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestWhtM:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in WHT_A for r in WHT_R])
    def test_grid(self, amount, rate):
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == (
            Decimal(amount) * Decimal(rate) / Decimal("100")
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestSocialM:
    @pytest.mark.parametrize("gross", SOCIAL)
    def test_ps(self, gross):
        r = social_insurance_amount(Decimal(gross), "PS")
        capped = min(Decimal(gross), Decimal("18800"))
        assert r["employee"] == (capped * Decimal("7") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("9") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("gross", SOCIAL)
    def test_sa(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=True, joined_2024_07_03_or_later=True)
        capped = min(Decimal(gross), Decimal("45000"))
        assert r["employee"] == (capped * Decimal("10.25") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("12.25") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestSaleM:
    @pytest.mark.parametrize("qty,price,disc", [(q, p, d) for q in SALE_Q for p in SALE_P for d in SALE_D])
    def test_grid(self, qty, price, disc):
        line = SaleLine(quantity=Decimal(qty), unit_price=Decimal(price), discount_percent=Decimal(disc))
        line.calculate_line_total()
        assert line.line_total == (
            Decimal(qty) * Decimal(price) * (Decimal("1") - Decimal(disc) / Decimal("100"))
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestLevyM:
    @pytest.mark.parametrize("qty,cost,cat", [(q, c, k) for q in LEVY_Q for c in LEVY_C for k in LEVY_K])
    def test_grid(self, qty, cost, cat):
        goods = Decimal(qty) * Decimal(cost)
        customs, excise = compute_import_levy_defaults(
            [(Decimal(qty), Decimal(cost), Decimal("0"), cat)],
            country="AE",
            customs_duty=None,
            excise_amount=None,
        )
        assert customs == (goods * Decimal("5") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        rates = {
            "tobacco": Decimal("100"),
            "energy_drinks": Decimal("100"),
            "soft_drinks": Decimal("50"),
            "": Decimal("0"),
        }
        base = goods + goods * Decimal("5") / 100
        assert excise == (base * rates[cat] / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
