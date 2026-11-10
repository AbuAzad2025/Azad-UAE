"""Scenario matrix batch 11 — final expansion grids (pure functions).

Broad cartesian grids over statutory payroll, money math, guards and
document integrity. Each case is a real golden scenario with an
independently computed expectation.
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
from services.stock_service import _MWACHelper
from utils.country_tax import compute_progressive_tax, social_insurance_amount
from utils.currency_utils import convert_and_quantize_aed
from utils.einvoice_document import build_invoice_xml
from utils.einvoice_document import invoice_sha256_hex as invoice_hash

GROSSES = ["500", "2000", "7522", "18800", "40000", "50695", "80000"]
AMOUNTS = ["5", "50", "500", "5000"]
RATES = ["0.27", "1", "3.65"]


class TestPayrollGridExpanded:
    @pytest.mark.parametrize("gross", GROSSES)
    def test_ps_expanded(self, gross):
        r = social_insurance_amount(Decimal(gross), "PS")
        capped = min(Decimal(gross), Decimal("18800"))
        assert r["employee"] == (capped * Decimal("7") / 100).quantize(Decimal("0.001"))
        assert r["employer"] == (capped * Decimal("9") / 100).quantize(Decimal("0.001"))

    @pytest.mark.parametrize("gross", GROSSES)
    def test_ae_expanded(self, gross):
        r = social_insurance_amount(Decimal(gross), "AE", is_national=True)
        capped = min(Decimal(gross), Decimal("70000"))
        assert r["employee"] == (capped * Decimal("11") / 100).quantize(Decimal("0.001"))
        assert r["employer"] == (capped * Decimal("15") / 100).quantize(Decimal("0.001"))

    @pytest.mark.parametrize("gross", GROSSES)
    def test_sa_expanded(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=True, joined_2024_07_03_or_later=True)
        capped = min(Decimal(gross), Decimal("45000"))
        assert r["employee"] == (capped * Decimal("10.25") / 100).quantize(Decimal("0.001"))
        assert r["employer"] == (capped * Decimal("12.25") / 100).quantize(Decimal("0.001"))

    @pytest.mark.parametrize("gross", GROSSES)
    def test_sa_nonnational_expanded(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=False)
        assert r["employee"] == Decimal("0.000")
        assert r["employer"] == (min(Decimal(gross), Decimal("45000")) * Decimal("2") / 100).quantize(
            Decimal("0.001")
        )


class TestMoneyExpanded:
    @pytest.mark.parametrize("amount,rate", [(a, r) for a in AMOUNTS for r in RATES])
    def test_conversion_expanded(self, amount, rate):
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == (
            Decimal(amount) * Decimal(rate)
        ).quantize(Decimal("0.001"))

    @pytest.mark.parametrize(
        "revenue,cost,rate",
        [(str(r), str(c), f) for r in (250, 1000) for c in (100, 365) for f in ("1", "3.65")],
    )
    def test_margin_expanded(self, revenue, cost, rate):
        fx = Decimal(rate)
        expected_cost = Decimal(cost) / fx if fx != 1 else Decimal(cost)
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == (
            Decimal(revenue) - expected_cost
        ).quantize(Decimal("0.001"))

    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (45, 450) for r in (4, 12, 20, 40)],
    )
    def test_withholding_expanded(self, amount, rate):
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == (
            Decimal(amount) * Decimal(rate) / Decimal("100")
        ).quantize(Decimal("0.001"))

    @pytest.mark.parametrize("qty,cost", [(str(q), str(c)) for q in (3, 20) for c in (40, 400)])
    def test_levy_expanded(self, qty, cost):
        goods = Decimal(qty) * Decimal(cost)
        customs, excise = compute_import_levy_defaults(
            [(Decimal(qty), Decimal(cost), Decimal("0"), "tobacco")],
            country="AE", customs_duty=None, excise_amount=None,
        )
        assert customs == (goods * Decimal("5") / 100).quantize(Decimal("0.001"))
        base = goods + goods * Decimal("5") / 100
        assert excise == base.quantize(Decimal("0.001"))


class TestProgressiveExpanded:
    @pytest.mark.parametrize("income", ["75000", "125000", "175000", "250000", "400000"])
    def test_bands(self, income):
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
        assert tax == expected.quantize(Decimal("0.001"))


class TestGuardsExpanded:
    @pytest.mark.parametrize("share", [f"{v}.5" for v in range(0, 100, 15)])
    def test_share_decimals(self, share):
        form = {
            "investment_amount": "0", "share_percentage": share, "fixed_monthly_amount": "0",
            "expense_share_percentage": "0", "loss_share_percentage": "0", "min_profit_threshold": "0",
        }
        values, error = _parse_partner_financials(form)
        assert error is None
        assert values["share_percentage"] == Decimal(share)

    @pytest.mark.parametrize("month", list(range(1, 13)))
    def test_full_months(self, month):
        assert PartnerService._months_in_period(date(2026, month, 15), date(2026, month, 15)) == 1

    @pytest.mark.parametrize("amount", ["3", "33", "333", "3333", "33333"])
    def test_balance_expanded(self, amount):
        lines = [
            {"account": "1110", "debit": Decimal(amount), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(amount)},
        ]
        assert_balanced_lines(lines, currency="AED")

    @pytest.mark.parametrize("debit,credit", [("7", "8"), ("70", "69")])
    def test_unbalanced_expanded(self, debit, credit):
        lines = [
            {"account": "1110", "debit": Decimal(debit), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(credit)},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines, currency="AED")


class TestMwacExpanded:
    @pytest.mark.parametrize(
        "change,unit",
        [("10", "50"), ("100", "25"), ("-25", "40"), ("1000", "5")],
    )
    def test_receipt_expanded(self, change, unit):
        qty, value, avg = _MWACHelper.calc(Decimal("200"), Decimal("10000"), Decimal(change), Decimal(unit))
        assert qty == Decimal("200") + Decimal(change)
        assert value == Decimal("10000") + Decimal(change) * Decimal(unit)
        assert avg == (value / qty).quantize(Decimal("0.0001"))


class TestEinvoiceExpanded:
    @pytest.mark.parametrize("total", ["50", "500", "5000"])
    def test_amounts(self, total):
        sale = MagicMock(
            sale_number="S-1", sale_date=None, tax_rate=Decimal("5"),
            total_amount=Decimal(total), tax_amount=Decimal("5"),
            taxable_amount=Decimal(total) - Decimal("5"), subtotal=Decimal(total), lines=[],
        )
        sale.customer = MagicMock(name="B", tax_number="")
        tenant = MagicMock(name="S", name_en="S", tax_number="1", address_en="", city="")
        xml = build_invoice_xml(sale, tenant, country="AE", currency="AED")
        assert f"{Decimal(total):.3f}" in xml
        assert len(invoice_hash(xml)) == 64
