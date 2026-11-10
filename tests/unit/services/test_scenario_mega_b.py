"""Scenario mega-grid B — statutory payroll and levies.

Social insurance grids across gross values, GOSI/GPSSA variants, and
import-levy cartesian grids. Expectations from the published tables.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from services.purchase_service import compute_import_levy_defaults
from utils.country_tax import social_insurance_amount

GROSSES = [
    str(v)
    for v in (
        500,
        1000,
        1500,
        1880,
        3000,
        5000,
        7522,
        10000,
        15000,
        18800,
        25000,
        30000,
        40000,
        45000,
        50695,
        60000,
        70000,
        80000,
        150000,
        200000,
    )
]


class TestSocialMega:
    @pytest.mark.parametrize("gross", GROSSES)
    def test_ps(self, gross):
        r = social_insurance_amount(Decimal(gross), "PS")
        capped = min(Decimal(gross), Decimal("18800"))
        assert r["employee"] == (capped * Decimal("7") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("9") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("gross", GROSSES)
    def test_ae_nat(self, gross):
        r = social_insurance_amount(Decimal(gross), "AE", is_national=True)
        capped = min(Decimal(gross), Decimal("70000"))
        assert r["employee"] == (capped * Decimal("11") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("15") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("gross", GROSSES)
    def test_ae_non_nat(self, gross):
        r = social_insurance_amount(Decimal(gross), "AE", is_national=False)
        assert r["employee"] == Decimal("0.000")
        assert r["employer"] == Decimal("0.000")

    @pytest.mark.parametrize("gross", GROSSES)
    def test_sa_post(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=True, joined_2024_07_03_or_later=True)
        capped = min(Decimal(gross), Decimal("45000"))
        assert r["employee"] == (capped * Decimal("10.25") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("12.25") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("gross", GROSSES)
    def test_sa_pre(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=True, joined_2024_07_03_or_later=False)
        capped = min(Decimal(gross), Decimal("45000"))
        assert r["employee"] == (capped * Decimal("9.75") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("11.75") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("gross", GROSSES)
    def test_sa_non_nat(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=False)
        assert r["employee"] == Decimal("0.000")
        assert r["employer"] == (min(Decimal(gross), Decimal("45000")) * Decimal("2") / 100).quantize(Decimal("0.001"))


class TestLevyMega:
    @pytest.mark.parametrize(
        "qty,cost,cat,country",
        [
            (str(q), str(c), k, co)
            for q in (1, 3, 10)
            for c in (50, 200)
            for k in ("tobacco", "soft_drinks")
            for co in ("AE", "SA")
        ],
    )
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
        excise_rate = Decimal("100") if cat == "tobacco" else Decimal("50")
        base = goods + goods * customs_rate / 100
        assert excise == (base * excise_rate / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
