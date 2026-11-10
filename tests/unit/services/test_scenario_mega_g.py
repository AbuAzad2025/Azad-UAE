"""Scenario mega-grid G — final large generated grids (pure functions).

All expectations are independent hand formulas. Combined with batches 1-6
and the earlier session scenarios, this exceeds 5000 real scenario cases.
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
from utils.country_tax import compute_corporate_tax, compute_progressive_tax, social_insurance_amount
from utils.currency_utils import convert_and_quantize_aed
from utils.einvoice_document import build_invoice_xml
from utils.einvoice_document import invoice_sha256_hex as invoice_hash

CONV = [
    (str(a), str(r))
    for a in (3, 11, 23, 47, 91, 123, 456, 789, 1011, 2222, 33333, 88888, 100001, 6, 19, 71, 999, 4321, 65535, 2)
    for r in (
        "0.0027",
        "0.036",
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
        "7",
        "12.5",
        "0.0037",
    )
]
MARGIN = [
    (str(r), str(c), f)
    for r in (125, 375, 625, 875, 1125, 1375, 1625, 1875, 2125, 2375, 2625, 2875, 3125, 3375, 3625)
    for c in (75, 150, 275, 365, 450, 600, 800, 950)
    for f in ("1", "3.65", "2", "0.5", "4.5", "0.27")
]
WHT = [
    (str(a), str(r))
    for a in (18, 36, 54, 72, 90, 108, 126, 144, 162, 180, 198, 216, 234, 252, 270, 288, 306, 324, 342, 360)
    for r in ("3", "6", "9", "12", "18", "24", "33", "45", "60", "90")
]
SOCIAL = [
    str(v)
    for v in (
        250,
        750,
        1250,
        2000,
        3500,
        4500,
        6000,
        7000,
        8000,
        9000,
        11000,
        13000,
        16000,
        17000,
        19000,
        22000,
        28000,
        32000,
        42000,
        46000,
        48000,
        52000,
        58000,
        62000,
        68000,
        72000,
        90000,
        110000,
        150000,
        250000,
    )
]
LEVY = [
    (str(q), str(c), k)
    for q in (2, 4, 6, 8)
    for c in (25, 75, 150, 300)
    for k in ("tobacco", "energy_drinks", "soft_drinks", "")
]
SALE = [
    (str(q), str(p), str(d))
    for q in (2, 3, 4, 6, 8, 9, 11, 15, 20, 30)
    for p in (7, 12, 18, 24, 36, 48, 66, 88, 120, 240)
    for d in (0, 5, 15, 30, 60, 75)
]
FIN = [
    (str(s), str(e), str(lo))
    for s in (0, 5, 15, 20, 35, 40, 45, 55, 60, 65, 70, 80, 85, 90, 95, 100)
    for e in (0, 25, 50, 75, 100)
    for lo in (0, 25, 50, 75, 100)
]
WIN = [(date(2026, m, d), date(2026, m, d)) for m in range(1, 13) for d in (1, 5, 10, 15, 20, 25, 28)]
BAL = [
    str(v)
    for v in (1, 11, 111, 1111, 11111, 111111, 3, 33, 333, 3333, 33333, 9, 99, 999, 9999, 99999, 7, 70, 700, 7000)
]
STRAT = [(str(a), str(r)) for a in (50, 250, 750, 1500, 5000, 15000, 50000, 125000) for r in (5, 15, 16, 18, 0)]
MWAC = [
    (str(c), str(u))
    for c in (1, 11, 33, 77, 111, 222, 333, 500, 750, 999, -5, -25, -100, -250, -500)
    for u in (3, 9, 27, 45, 60, 120, 300, 777)
]
PROG = [str(v) for v in range(0, 500001, 50000)]
CORP = [
    (c, str(p))
    for c in ("AE",)
    for p in (300000, 375000, 400000, 500000, 750000, 1000000, 1500000, 2000000, 3000000, 5000000)
]
EINV = [
    (co, str(t)) for co in ("AE", "PS", "IL", "SA") for t in (50, 100, 250, 500, 1000, 2500, 5000, 10000, 50000, 99999)
]


class TestConvG:
    @pytest.mark.parametrize("amount,rate", CONV)
    def test_grid(self, amount, rate):
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == (
            Decimal(amount) * Decimal(rate)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestMarginG:
    @pytest.mark.parametrize("revenue,cost,rate", MARGIN)
    def test_grid(self, revenue, cost, rate):
        fx = Decimal(rate)
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == (
            Decimal(revenue) - Decimal(cost)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestWhtG:
    @pytest.mark.parametrize("amount,rate", WHT)
    def test_grid(self, amount, rate):
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == (
            Decimal(amount) * Decimal(rate) / Decimal("100")
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestSocialG:
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


class TestLevyG:
    @pytest.mark.parametrize("qty,cost,cat", LEVY)
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


class TestSaleG:
    @pytest.mark.parametrize("qty,price,disc", SALE)
    def test_grid(self, qty, price, disc):
        line = SaleLine(quantity=Decimal(qty), unit_price=Decimal(price), discount_percent=Decimal(disc))
        line.calculate_line_total()
        assert line.line_total == (
            Decimal(qty) * Decimal(price) * (Decimal("1") - Decimal(disc) / Decimal("100"))
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestFinancialsG:
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


class TestWindowsG:
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

    @pytest.mark.parametrize("debit,credit", [(str(d), str(c)) for d, c in [(5, 4), (500, 499), (5000, 5001)]])
    def test_unbalanced(self, debit, credit):
        lines = [
            {"account": "1110", "debit": Decimal(debit), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(credit)},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines, currency="AED")


class TestTaxG:
    @pytest.mark.parametrize("amount,rate", STRAT)
    def test_strategy(self, amount, rate):
        strategy = TaxService._get_strategy(tenant_id=None)
        result = strategy.calculate_tax(Decimal(amount), Decimal(rate))
        assert Decimal(str(result["tax_amount"])) == (Decimal(amount) * Decimal(rate) / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @pytest.mark.parametrize("income", PROG)
    def test_progressive(self, income):
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

    @pytest.mark.parametrize("country,profit", CORP)
    def test_corporate(self, country, profit):
        result = compute_corporate_tax(Decimal(profit), country)
        p = Decimal(profit)
        expected_tax = (
            Decimal("0.000")
            if p <= Decimal("375000")
            else ((p - Decimal("375000")) * Decimal("9") / 100).quantize(Decimal("0.001"))
        )
        assert result["tax"] == expected_tax


class TestMwacG:
    @pytest.mark.parametrize("change,unit", MWAC)
    def test_grid(self, change, unit):
        qty, value, avg = _MWACHelper.calc(Decimal("400"), Decimal("20000"), Decimal(change), Decimal(unit))
        assert qty == Decimal("400") + Decimal(change)
        assert value == Decimal("20000") + Decimal(change) * Decimal(unit)
        assert avg == (value / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class TestEinvoiceG:
    @pytest.mark.parametrize("country,total", EINV)
    def test_grid(self, country, total):
        sale = MagicMock(
            sale_number="S-1",
            sale_date=None,
            tax_rate=Decimal("5"),
            total_amount=Decimal(total),
            tax_amount=Decimal("5"),
            taxable_amount=Decimal(total) - Decimal("5"),
            subtotal=Decimal(total),
            lines=[],
        )
        sale.customer = MagicMock(name="B", tax_number="")
        tenant = MagicMock(name="S", name_en="S", tax_number="1", address_en="", city="")
        xml = build_invoice_xml(sale, tenant, country=country, currency="AED")
        assert f"{Decimal(total):.3f}" in xml
        assert len(invoice_hash(xml)) == 64
