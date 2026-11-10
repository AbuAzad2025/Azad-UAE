"""Scenario mega-grid J — margins, withholding, payroll (pure functions)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from services.expense_service import ExpenseService
from services.sale_service import SaleService
from utils.country_tax import social_insurance_amount

MARGIN_R = [
    str(v)
    for v in (
        10,
        25,
        40,
        60,
        80,
        100,
        125,
        150,
        175,
        200,
        225,
        250,
        275,
        300,
        350,
        400,
        450,
        500,
        600,
        700,
        800,
        900,
        1000,
        1250,
        1500,
        2000,
        2500,
        3000,
        5000,
        10000,
    )
]
MARGIN_C = [
    str(v)
    for v in (
        5,
        10,
        20,
        25,
        30,
        40,
        50,
        60,
        75,
        100,
        125,
        150,
        200,
        250,
        300,
        365,
        400,
        500,
        600,
        730,
        800,
        900,
        1000,
        1500,
        2000,
    )
]
MARGIN_FX = ["1", "3.65", "0.27", "0.5", "2", "4.5", "11.95", "0.98"]
WHT_A = [
    str(v)
    for v in (
        5,
        10,
        15,
        20,
        25,
        30,
        40,
        50,
        60,
        75,
        90,
        100,
        125,
        150,
        175,
        200,
        225,
        250,
        300,
        350,
        400,
        450,
        500,
        600,
        750,
        900,
        1000,
        1250,
        1500,
        2000,
    )
]
WHT_R = [
    str(v)
    for v in (
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "7.5",
        "8",
        "9",
        "10",
        "12",
        "15",
        "18",
        "20",
        "22",
        "25",
        "30",
        "33",
        "40",
        "45",
        "50",
        "60",
        "75",
        "90",
        "100",
    )
]
SOCIAL = [
    str(v)
    for v in (
        100,
        400,
        800,
        1200,
        1600,
        1880,
        2200,
        2800,
        3200,
        3800,
        4200,
        4800,
        5500,
        6200,
        6800,
        7200,
        7800,
        8500,
        9500,
        10500,
        11500,
        12500,
        13500,
        14500,
        15500,
        16500,
        17500,
        18500,
        19500,
        21000,
        23000,
        26000,
        29000,
        33000,
        37000,
        41000,
        43000,
        44000,
        46000,
        47000,
        49000,
        51000,
        54000,
        57000,
        59000,
        61000,
        63000,
        66000,
        69000,
        71000,
        76000,
        85000,
        95000,
        110000,
        130000,
        160000,
        190000,
        220000,
        280000,
        350000,
        450000,
        600000,
        800000,
        1000000,
        1500000,
        2000000,
        3000000,
        5000000,
        10000000,
        20000000,
        50000000,
        100000000,
        999999999,
        123456789,
        987654321,
        555555555,
        333333333,
        777777777,
        111111111,
        222222222,
        444444444,
        666666666,
        888888888,
        1000000000,
        2000000000,
        9999999999,
        12345678901,
        99999999999,
        88888888888,
        77777777777,
        66666666666,
        55555555555,
        44444444444,
        33333333333,
    )
]


class TestMarginJ:
    @pytest.mark.parametrize("revenue,cost,rate", [(r, c, f) for r in MARGIN_R for c in MARGIN_C for f in MARGIN_FX])
    def test_grid(self, revenue, cost, rate):
        fx = Decimal(rate)
        expected_cost = (Decimal(cost) / fx).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == (
            Decimal(revenue) - expected_cost
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestWhtJ:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in WHT_A for r in WHT_R])
    def test_grid(self, amount, rate):
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == (
            Decimal(amount) * Decimal(rate) / Decimal("100")
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestSocialJ:
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
