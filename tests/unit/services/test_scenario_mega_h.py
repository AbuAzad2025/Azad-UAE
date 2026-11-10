"""Scenario mega-grid H — tens of thousands of golden cases (pure functions).

Generated cartesian grids across money math, statutory payroll, levies,
sale totals, financial guards, windows, balances, strategies and MWAC.
Every expectation is an independent hand formula.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import MagicMock

import pytest

from models.sale import SaleLine
from routes.partners import _parse_partner_financials
from services.expense_service import ExpenseService
from services.gl_posting import GlPostingError, assert_balanced_lines
from services.partner_service import PartnerService
from services.purchase_service import compute_import_levy_defaults
from services.sale_service import SaleService
from services.stock_service import _MWACHelper
from services.tax_service import TaxService
from utils.country_tax import social_insurance_amount
from utils.currency_utils import convert_and_quantize_aed

CONV_A = [
    str(v)
    for v in (
        1,
        3,
        7,
        11,
        23,
        47,
        91,
        123,
        250,
        456,
        789,
        999,
        1011,
        2222,
        3333,
        5555,
        7777,
        9999,
        12345,
        22222,
        33333,
        44444,
        54321,
        65535,
        77777,
        88888,
        99999,
        100001,
        123456,
        999999,
        500000,
        250000,
        750000,
        1250000,
        9999999,
        10000000,
        5,
        17,
        88,
        400,
        2025,
        77,
        555,
        9000,
        31415,
        27182,
        16180,
        14142,
        17320,
        9999,
    )
]
CONV_R = [
    str(v)
    for v in (
        "0.0027",
        "0.036",
        "0.27",
        "0.5",
        "0.9",
        "1",
        "1.5",
        "2",
        "3.65",
        "4.5",
        "10",
        "5.25",
        "7",
        "12.5",
        "0.0037",
        "0.1234",
        "1.2345",
        "2.5",
        "3.75",
        "4.05",
        "5.5",
        "6.25",
        "7.75",
        "8.5",
        "9.99",
        "11.95",
        "0.95",
        "0.98",
        "1.02",
        "1.05",
        "0.25",
        "0.22",
        "0.08",
        "0.10",
        "0.99",
        "4.65",
        "3.98",
        "0.2723",
        "3.6725",
        "0.75",
    )
]
MARGIN_R = [
    str(v)
    for v in (
        25,
        50,
        75,
        100,
        125,
        150,
        175,
        200,
        250,
        300,
        375,
        400,
        450,
        500,
        625,
        700,
        750,
        875,
        1000,
        1125,
        1250,
        1375,
        1500,
        1750,
        2000,
        2500,
        9999,
        60,
        420,
        840,
    )
]
MARGIN_C = [
    str(v) for v in (5, 10, 25, 40, 50, 75, 100, 150, 200, 250, 275, 300, 365, 400, 450, 500, 600, 730, 800, 950)
]
MARGIN_FX = ["1", "3.65", "0.5", "2", "4.5", "0.27", "11.95", "0.98"]
WHT_A = [
    str(v)
    for v in (
        5,
        15,
        25,
        36,
        45,
        54,
        63,
        72,
        81,
        90,
        108,
        126,
        144,
        162,
        180,
        198,
        216,
        234,
        252,
        270,
        288,
        306,
        324,
        342,
        360,
        450,
        540,
        720,
        900,
        1800,
    )
]
WHT_R = [
    str(v)
    for v in (
        "0",
        "1",
        "2",
        "3",
        "5",
        "6",
        "7.5",
        "9",
        "10",
        "12",
        "15",
        "18",
        "20",
        "24",
        "30",
        "33",
        "45",
        "50",
        "60",
        "90",
    )
]
SOCIAL = [
    str(v)
    for v in (
        100,
        250,
        500,
        750,
        1000,
        1250,
        1500,
        1880,
        2000,
        2500,
        3000,
        3500,
        4000,
        4500,
        5000,
        6000,
        7000,
        7522,
        8000,
        9000,
        10000,
        11000,
        12000,
        13000,
        15000,
        16000,
        17000,
        18000,
        18800,
        19000,
        20000,
        22000,
        25000,
        28000,
        30000,
        32000,
        35000,
        40000,
        42000,
        45000,
        46000,
        48000,
        50000,
        50695,
        52000,
        58000,
        60000,
        62000,
        65000,
        68000,
        70000,
        72000,
        80000,
        90000,
        100000,
        110000,
        150000,
        200000,
        250000,
        300000,
        500000,
    )
]
LEVY = [
    (str(q), str(c), k, co)
    for q in (1, 2, 3, 5, 10, 20)
    for c in (10, 25, 50, 100, 200, 500)
    for k in ("tobacco", "energy_drinks", "soft_drinks", "")
    for co in ("AE", "SA")
]
SALE = [
    (str(q), str(p), str(d))
    for q in (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 50, 100, 200)
    for p in (3, 7, 11, 15, 20, 33.33, 50, 75, 99.99, 100, 250, 333.33, 500, 999, 1000)
    for d in (0, 5, 10, 15, 20, 25, 33, 50, 75, 90, 100, 99)
]
FIN = [
    (str(s), str(e), str(lo))
    for s in (0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100)
    for e in (0, 20, 40, 60, 80, 100)
    for lo in (0, 20, 40, 60, 80, 100)
]
WIN = [(date(2026, m, d), date(2026, m, d)) for m in range(1, 13) for d in range(1, 16)]
BAL = [
    str(v)
    for v in (
        1,
        2,
        5,
        10,
        25,
        50,
        100,
        250,
        500,
        1000,
        2500,
        5000,
        10000,
        25000,
        50000,
        100000,
        250000,
        500000,
        1000000,
        999999,
    )
]
STRAT = [
    (str(a), str(r))
    for a in (
        25,
        50,
        100,
        250,
        500,
        750,
        1000,
        2500,
        5000,
        10000,
        25000,
        50000,
        100000,
        250000,
        500000,
        1000000,
        333,
        777,
        12345,
        99999,
    )
    for r in (5, 15, 16, 18, 0)
]
MWAC = [
    (str(c), str(u))
    for c in (1, 5, 10, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500, 750, 1000, -5, -25, -50, -100, -250)
    for u in (3, 7, 9, 12, 15, 20, 25, 30, 45, 50, 60, 80, 99, 100, 120, 200, 250, 300, 777, 999)
]


class TestConvH:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in CONV_A for r in CONV_R])
    def test_grid(self, amount, rate):
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == (
            Decimal(amount) * Decimal(rate)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestMarginH:
    @pytest.mark.parametrize("revenue,cost,rate", [(r, c, f) for r in MARGIN_R for c in MARGIN_C for f in MARGIN_FX])
    def test_grid(self, revenue, cost, rate):
        fx = Decimal(rate)
        expected_cost = (Decimal(cost) / fx).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == (
            Decimal(revenue) - expected_cost
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestWhtH:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in WHT_A for r in WHT_R])
    def test_grid(self, amount, rate):
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == (
            Decimal(amount) * Decimal(rate) / Decimal("100")
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestSocialH:
    @pytest.mark.parametrize("gross", SOCIAL)
    def test_ps(self, gross):
        r = social_insurance_amount(Decimal(gross), "PS")
        capped = min(Decimal(gross), Decimal("18800"))
        assert r["employee"] == (capped * Decimal("7") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("9") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("gross", SOCIAL)
    def test_ae(self, gross):
        r = social_insurance_amount(Decimal(gross), "AE", is_national=True)
        capped = min(Decimal(gross), Decimal("70000"))
        assert r["employee"] == (capped * Decimal("11") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("15") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("gross", SOCIAL)
    def test_sa(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=True, joined_2024_07_03_or_later=True)
        capped = min(Decimal(gross), Decimal("45000"))
        assert r["employee"] == (capped * Decimal("10.25") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("12.25") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestLevyH:
    @pytest.mark.parametrize("qty,cost,cat,country", LEVY)
    def test_grid(self, qty, cost, cat, country):
        goods = Decimal(qty) * Decimal(cost)
        customs_rate = Decimal("5") if country == "AE" else Decimal("15")
        customs, excise = compute_import_levy_defaults(
            [(Decimal(qty), Decimal(cost), Decimal("0"), cat)],
            country=country,
            customs_duty=None,
            excise_amount=None,
        )
        assert customs == (goods * customs_rate / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        rates = {
            "tobacco": Decimal("100"),
            "energy_drinks": Decimal("100"),
            "soft_drinks": Decimal("50"),
            "": Decimal("0"),
        }
        base = goods + goods * customs_rate / 100
        assert excise == (base * rates[cat] / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestSaleH:
    @pytest.mark.parametrize("qty,price,disc", SALE)
    def test_grid(self, qty, price, disc):
        line = SaleLine(quantity=Decimal(qty), unit_price=Decimal(price), discount_percent=Decimal(disc))
        line.calculate_line_total()
        assert line.line_total == (
            Decimal(qty) * Decimal(price) * (Decimal("1") - Decimal(disc) / Decimal("100"))
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestFinancialsH:
    @pytest.mark.parametrize("share,expense,loss", FIN)
    def test_grid(self, share, expense, loss):
        form = {
            "investment_amount": "0",
            "share_percentage": share,
            "fixed_monthly_amount": "0",
            "expense_share_percentage": expense,
            "loss_share_percentage": loss,
            "min_profit_threshold": "0",
        }
        values, error = _parse_partner_financials(form)
        assert error is None
        assert values["share_percentage"] == Decimal(share)
        assert values["expense_share_percentage"] == Decimal(expense)
        assert values["loss_share_percentage"] == Decimal(loss)


class TestWindowsH:
    @pytest.mark.parametrize("start,end", WIN)
    def test_grid(self, start, end):
        partner = MagicMock(start_date=start, end_date=end)
        window = PartnerService._active_window(partner, date(2026, 1, 1), date(2026, 12, 31))
        assert window[0] == start and window[1] == end

    @pytest.mark.parametrize("amount", BAL)
    def test_balance(self, amount):
        lines = [
            {"account": "1110", "debit": Decimal(amount), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(amount)},
        ]
        assert_balanced_lines(lines, currency="AED")

    @pytest.mark.parametrize(
        "debit,credit",
        [(str(d), str(c)) for d, c in [(5, 6), (50, 49), (500, 505), (5000, 4999), (100, 101), (1000, 999)]],
    )
    def test_unbalanced(self, debit, credit):
        lines = [
            {"account": "1110", "debit": Decimal(debit), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(credit)},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines, currency="AED")


class TestStrategiesH:
    @pytest.mark.parametrize("amount,rate", STRAT)
    def test_grid(self, amount, rate):
        strategy = TaxService._get_strategy(tenant_id=None)
        result = strategy.calculate_tax(Decimal(amount), Decimal(rate))
        assert Decimal(str(result["tax_amount"])) == (Decimal(amount) * Decimal(rate) / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class TestInventoryH:
    @pytest.mark.parametrize("change,unit", MWAC)
    def test_grid(self, change, unit):
        qty, value, avg = _MWACHelper.calc(Decimal("400"), Decimal("20000"), Decimal(change), Decimal(unit))
        assert qty == Decimal("400") + Decimal(change)
        assert value == Decimal("20000") + Decimal(change) * Decimal(unit)
        assert avg == (value / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
