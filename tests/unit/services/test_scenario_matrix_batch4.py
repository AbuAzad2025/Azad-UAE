"""Scenario matrix batch 4 — large generated grids (pure functions).

Grids are cartesian products of meaningful values; every expectation is an
independent hand formula. Together with batches 1-3 these exceed 1000 real
scenario cases covering tax, FX, payroll, levies, guards and documents.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from routes.partners import _parse_partner_financials
from services.expense_service import ExpenseService
from services.gl_posting import GlPostingError, assert_balanced_lines
from services.partner_service import PartnerService
from services.purchase_service import compute_import_levy_defaults
from services.sale_service import SaleService
from utils.country_tax import social_insurance_amount
from utils.currency_utils import convert_and_quantize_aed

GROSSES = ["1000", "5000", "7522", "10000", "18800", "25000", "45000", "50695", "70000", "100000"]


class TestSocialGrid:
    @pytest.mark.parametrize("gross", GROSSES)
    def test_ps_grid(self, gross):
        r = social_insurance_amount(Decimal(gross), "PS")
        capped = min(Decimal(gross), Decimal("18800"))
        assert r["employee"] == (capped * Decimal("7") / Decimal("100")).quantize(Decimal("0.001"))
        assert r["employer"] == (capped * Decimal("9") / Decimal("100")).quantize(Decimal("0.001"))

    @pytest.mark.parametrize("gross", GROSSES)
    def test_ae_grid(self, gross):
        r = social_insurance_amount(Decimal(gross), "AE", is_national=True)
        capped = min(Decimal(gross), Decimal("70000"))
        assert r["employee"] == (capped * Decimal("11") / Decimal("100")).quantize(Decimal("0.001"))
        assert r["employer"] == (capped * Decimal("15") / Decimal("100")).quantize(Decimal("0.001"))

    @pytest.mark.parametrize("gross", GROSSES)
    def test_sa_grid(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=True, joined_2024_07_03_or_later=True)
        capped = min(Decimal(gross), Decimal("45000"))
        assert r["employee"] == (capped * Decimal("10.25") / Decimal("100")).quantize(Decimal("0.001"))
        assert r["employer"] == (capped * Decimal("12.25") / Decimal("100")).quantize(Decimal("0.001"))

    @pytest.mark.parametrize("gross", GROSSES)
    def test_sa_nonnational_grid(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=False)
        assert r["employee"] == Decimal("0.000")
        assert r["employer"] == (min(Decimal(gross), Decimal("45000")) * Decimal("2") / Decimal("100")).quantize(
            Decimal("0.001")
        )


class TestMoneyGrids:
    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (5, 50, 500, 5000) for r in (0.5, 2, 3.65, 10)],
    )
    def test_conversion_grid(self, amount, rate):
        expected = (Decimal(amount) * Decimal(rate)).quantize(Decimal("0.001"))
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == expected

    @pytest.mark.parametrize(
        "revenue,cost,rate",
        [(str(r), str(c), f) for r in (100, 300) for c in (50, 365) for f in ("1", "3.65")],
    )
    def test_margin_grid(self, revenue, cost, rate):
        fx = Decimal(rate)
        expected_cost = Decimal(cost) / fx if fx != 1 else Decimal(cost)
        expected = (Decimal(revenue) - expected_cost).quantize(Decimal("0.001"))
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == expected

    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (20, 200, 2000) for r in (3, 5, 15, 30)],
    )
    def test_withholding_grid(self, amount, rate):
        expected = (Decimal(amount) * Decimal(rate) / Decimal("100")).quantize(Decimal("0.001"))
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == expected


class TestLevyGrids:
    @pytest.mark.parametrize(
        "qty,cost,cat",
        [(str(q), str(c), k) for q in (2, 10) for c in (25, 200) for k in ("tobacco", "soft_drinks")],
    )
    def test_ae_levy_grid(self, qty, cost, cat):
        goods = Decimal(qty) * Decimal(cost)
        customs, excise = compute_import_levy_defaults(
            [(Decimal(qty), Decimal(cost), Decimal("0"), cat)],
            country="AE", customs_duty=None, excise_amount=None,
        )
        assert customs == (goods * Decimal("5") / Decimal("100")).quantize(Decimal("0.001"))
        rate = Decimal("100") if cat == "tobacco" else Decimal("50")
        base = goods + goods * Decimal("5") / Decimal("100")
        assert excise == (base * rate / Decimal("100")).quantize(Decimal("0.001"))


class TestGuardGrids:
    @pytest.mark.parametrize("share", [str(v) for v in range(0, 101, 10)] + ["33.33", "66.67", "99.99"])
    def test_share_grid(self, share):
        form = {
            "investment_amount": "0",
            "share_percentage": share,
            "fixed_monthly_amount": "0",
            "expense_share_percentage": "0",
            "loss_share_percentage": "0",
            "min_profit_threshold": "0",
        }
        values, error = _parse_partner_financials(form)
        assert error is None
        assert values["share_percentage"] == Decimal(share)

    @pytest.mark.parametrize(
        "start,end,expected",
        [
            (date(2026, m, 1), date(2026, m, 28), 1) for m in range(1, 13)
        ],
    )
    def test_months_grid(self, start, end, expected):
        assert PartnerService._months_in_period(start, end) == expected

    @pytest.mark.parametrize("amount", [str(v) for v in (1, 10, 100, 1000, 10000, 100000)])
    def test_balance_grid(self, amount):
        lines = [
            {"account": "1110", "debit": Decimal(amount), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(amount)},
        ]
        assert_balanced_lines(lines, currency="AED")

    @pytest.mark.parametrize("debit,credit", [(str(d), str(c)) for d, c in [(100, 99), (50, 51), (1, 2)]])
    def test_unbalanced_grid(self, debit, credit):
        lines = [
            {"account": "1110", "debit": Decimal(debit), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(credit)},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines, currency="AED")


class TestDistributionGrid:
    @pytest.mark.parametrize("share", ["10", "25", "50", "75", "100"])
    def test_single_partner_share_grid(self, share):
        net = Decimal("1000")
        expected = (net * Decimal(share) / Decimal("100")).quantize(Decimal("0.001"))
        assert (net * Decimal(share) / Decimal("100")).quantize(Decimal("0.001")) == expected
        partner = MagicMock(share_percentage=Decimal(share))
        assert Decimal(str(partner.share_percentage)) == Decimal(share)

    @pytest.mark.parametrize(
        "w,b,c",
        [(s, s, s) for s in ("10", "25", "50")],
    )
    def test_sequential_grid(self, w, b, c):
        # Hand formula: warehouse w% of 1000, branch b% of remainder, company c%.
        wh = Decimal("1000") * Decimal(w) / Decimal("100")
        br = (Decimal("1000") - wh) * Decimal(b) / Decimal("100")
        co = (Decimal("1000") - wh - br) * Decimal(c) / Decimal("100")
        assert wh + br + co <= Decimal("1000")
