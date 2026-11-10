"""Scenario mega-grid K — levies, totals, guards, documents (pure functions)."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import MagicMock

import pytest

from models.sale import SaleLine
from routes.partners import _parse_partner_financials
from services.gl_posting import GlPostingError, assert_balanced_lines
from services.partner_service import PartnerService
from services.purchase_service import compute_import_levy_defaults
from services.stock_service import _MWACHelper
from services.tax_service import TaxService
from utils.country_tax import compute_corporate_tax, compute_progressive_tax
from utils.einvoice_document import build_invoice_xml
from utils.einvoice_document import invoice_sha256_hex as invoice_hash

LEVY = [
    (str(q), str(c), k, co)
    for q in (1, 2, 4, 5, 10, 25, 50)
    for c in (10, 30, 75, 120, 250, 400, 800, 1000)
    for k in ("tobacco", "energy_drinks", "soft_drinks", "")
    for co in ("AE", "SA", "PS")
]
SALE = [
    (str(q), str(p), str(d))
    for q in (1, 3, 7, 9, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in (2, 6, 9, 14, 22, 33, 49, 66, 77, 99, 111, 222)
    for d in (0, 15, 35, 55, 85, 95, 100)
]
FIN = [
    (str(s), str(e), str(lo))
    for s in (0, 7, 13, 21, 33, 47, 58, 66, 72, 83, 91, 97, 100)
    for e in (0, 15, 30, 45, 60, 75, 90, 100)
    for lo in (0, 15, 30, 45, 60, 75, 90, 100)
]
WIN = [(date(2026, m, d), date(2026, m, d)) for m in range(1, 13) for d in (1, 3, 6, 9, 12, 15, 18, 21, 24, 27, 28)]
BAL = [
    str(v)
    for v in (
        4,
        8,
        16,
        32,
        64,
        128,
        256,
        512,
        1024,
        2048,
        4096,
        8192,
        16384,
        32768,
        65536,
        131072,
        262144,
        524288,
        6,
        66,
        666,
        6666,
        66666,
        666666,
        9999,
        8888,
        7777,
        12321,
        54321,
        98765,
    )
]
STRAT = [
    (str(a), str(r))
    for a in (10, 25, 50, 75, 100, 125, 200, 300, 400, 600, 800, 900, 1100, 1300, 1700, 2100, 3000, 4000, 6000, 8000)
    for r in (5, 15, 16, 18, 0)
]
MWAC = [
    (str(c), str(u))
    for c in (3, 9, 15, 27, 45, 60, 90, 120, 180, 240, 300, 360, 450, 600, 900, -7, -45, -90, -180, -450)
    for u in (4, 8, 11, 16, 22, 30, 44, 55, 66, 77, 88, 99, 111, 150, 222, 333, 444, 555, 666, 777)
]
PROG = [str(v) for v in range(0, 1000001, 20000)]
CORP = [
    ("AE", str(p))
    for p in (
        0,
        100000,
        200000,
        300000,
        374999,
        375000,
        375001,
        400000,
        600000,
        800000,
        1000000,
        1250000,
        1500000,
        1750000,
        2000000,
        2500000,
        3000000,
        4000000,
        5000000,
        7500000,
    )
]
EINV = [
    (co, str(t))
    for co in ("AE", "PS", "IL", "SA")
    for t in (25, 75, 150, 300, 750, 1500, 3000, 7500, 15000, 30000, 75000, 150000, 300000, 750000, 1500000)
]


class TestLevyK:
    @pytest.mark.parametrize("qty,cost,cat,country", LEVY)
    def test_grid(self, qty, cost, cat, country):
        goods = Decimal(qty) * Decimal(cost)
        rates = {"AE": Decimal("5"), "SA": Decimal("15"), "PS": Decimal("15")}
        customs_rate = rates[country]
        customs, excise = compute_import_levy_defaults(
            [(Decimal(qty), Decimal(cost), Decimal("0"), cat)],
            country=country,
            customs_duty=None,
            excise_amount=None,
        )
        assert customs == (goods * customs_rate / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        exc = {
            "AE": {"tobacco": "100", "energy_drinks": "100", "soft_drinks": "50", "": "0"},
            "SA": {"tobacco": "100", "energy_drinks": "100", "soft_drinks": "50", "": "0"},
            "PS": {"tobacco": "0", "energy_drinks": "0", "soft_drinks": "0", "": "0"},
        }[country][cat]
        base = goods + goods * customs_rate / 100
        assert excise == (base * Decimal(exc) / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestSaleK:
    @pytest.mark.parametrize("qty,price,disc", SALE)
    def test_grid(self, qty, price, disc):
        line = SaleLine(quantity=Decimal(qty), unit_price=Decimal(price), discount_percent=Decimal(disc))
        line.calculate_line_total()
        assert line.line_total == (
            Decimal(qty) * Decimal(price) * (Decimal("1") - Decimal(disc) / Decimal("100"))
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestFinancialsK:
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

    @pytest.mark.parametrize("start,end", WIN)
    def test_windows(self, start, end):
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
        [(str(d), str(c)) for d, c in [(2, 3), (25, 24), (250, 251), (2500, 2499), (25000, 25001), (250000, 249999)]],
    )
    def test_unbalanced(self, debit, credit):
        lines = [
            {"account": "1110", "debit": Decimal(debit), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(credit)},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines, currency="AED")


class TestTaxK:
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
            else ((p - Decimal("375000")) * Decimal("9") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        )
        assert result["tax"] == expected_tax


class TestInventoryK:
    @pytest.mark.parametrize("change,unit", MWAC)
    def test_grid(self, change, unit):
        qty, value, avg = _MWACHelper.calc(Decimal("500"), Decimal("25000"), Decimal(change), Decimal(unit))
        assert qty == Decimal("500") + Decimal(change)
        assert value == Decimal("25000") + Decimal(change) * Decimal(unit)
        assert avg == (value / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class TestEinvoiceK:
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
