"""Scenario mega-grid F — mixed expansion grids (pure functions).

Extra cartesian coverage: payroll, money, levies, MWAC, documents, windows,
and tax-strategy variants. Expectations are independent hand formulas.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import MagicMock

import pytest

from services.expense_service import ExpenseService
from services.gl_posting import assert_balanced_lines
from services.partner_service import PartnerService
from services.purchase_service import compute_import_levy_defaults
from services.sale_service import SaleService
from services.stock_service import _MWACHelper
from services.tax_service import TaxService
from utils.country_tax import payroll_income_tax_amount, social_insurance_amount
from utils.currency_utils import convert_and_quantize_aed
from utils.einvoice_document import build_invoice_xml
from utils.einvoice_document import invoice_sha256_hex as invoice_hash

GROSSES = [str(v) for v in (800, 2500, 6000, 12000, 18000, 22000, 35000, 50000, 55000, 65000, 90000, 120000)]


class TestPayrollMega:
    @pytest.mark.parametrize("gross", GROSSES)
    def test_ps(self, gross):
        r = social_insurance_amount(Decimal(gross), "PS")
        capped = min(Decimal(gross), Decimal("18800"))
        assert r["employee"] == (capped * Decimal("7") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("9") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("gross", GROSSES)
    def test_sa(self, gross):
        r = social_insurance_amount(Decimal(gross), "SA", is_national=True, joined_2024_07_03_or_later=True)
        capped = min(Decimal(gross), Decimal("45000"))
        assert r["employee"] == (capped * Decimal("10.25") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert r["employer"] == (capped * Decimal("12.25") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("income", ["80000", "150000", "250000", "400000", "700000", "1500000"])
    def test_il_payroll(self, income):
        r = payroll_income_tax_amount(Decimal(income), "IL")
        assert r["tax"] > Decimal("0")
        assert r["tax"] < Decimal(income)

    @pytest.mark.parametrize("income", ["60000", "90000", "120000", "180000"])
    def test_ps_payroll(self, income):
        r = payroll_income_tax_amount(Decimal(income), "PS")
        assert r["tax"] >= Decimal("0")


class TestMoneyMegaF:
    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (13, 131, 1313) for r in ("0.27", "1.5", "3.65", "4.5", "0.9", "0.0037")],
    )
    def test_conversion(self, amount, rate):
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == (
            Decimal(amount) * Decimal(rate)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize(
        "revenue,cost,rate",
        [(str(r), str(c), f) for r in (175, 875) for c in (75, 365) for f in ("1", "3.65", "2")],
    )
    def test_margin(self, revenue, cost, rate):
        fx = Decimal(rate)
        expected_cost = (Decimal(cost) / fx).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == (
            Decimal(revenue) - expected_cost
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (35, 350, 3500) for r in (6, 9, 18, 22)],
    )
    def test_withholding(self, amount, rate):
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == (
            Decimal(amount) * Decimal(rate) / Decimal("100")
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestLevyMegaF:
    @pytest.mark.parametrize("qty,cost", [(str(q), str(c)) for q in (2, 5, 20) for c in (30, 150, 600)])
    def test_ae(self, qty, cost):
        goods = Decimal(qty) * Decimal(cost)
        customs, excise = compute_import_levy_defaults(
            [(Decimal(qty), Decimal(cost), Decimal("0"), "tobacco")],
            country="AE",
            customs_duty=None,
            excise_amount=None,
        )
        assert customs == (goods * Decimal("5") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        assert excise == (goods + goods * Decimal("5") / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @pytest.mark.parametrize("country,rate", [("PS", "15"), ("IL", "18"), ("SA", "15")])
    def test_customs_countries(self, country, rate):
        customs, _ = compute_import_levy_defaults(
            [(10, Decimal("10"), Decimal("0"), "")],
            country=country,
            customs_duty=None,
            excise_amount=None,
        )
        assert customs == (Decimal("100") * Decimal(rate) / 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class TestInventoryMegaF:
    @pytest.mark.parametrize(
        "change,unit",
        [(str(c), str(u)) for c in (15, 75, 150, -30, -75, 250) for u in (12, 45, 90, 200)],
    )
    def test_mwac(self, change, unit):
        qty, value, avg = _MWACHelper.calc(Decimal("300"), Decimal("15000"), Decimal(change), Decimal(unit))
        assert qty == Decimal("300") + Decimal(change)
        assert value == Decimal("15000") + Decimal(change) * Decimal(unit)
        assert avg == (value / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class TestStrategyMegaF:
    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (200, 2000, 20000) for r in (5, 16, 18, 15, 0)],
    )
    def test_grid(self, amount, rate):
        strategy = TaxService._get_strategy(tenant_id=None)
        result = strategy.calculate_tax(Decimal(amount), Decimal(rate))
        assert Decimal(str(result["tax_amount"])) == (Decimal(amount) * Decimal(rate) / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class TestWindowsMegaF:
    @pytest.mark.parametrize(
        "start,end",
        [(date(2026, m, d), date(2026, m, d)) for m in (1, 2, 3, 4, 5, 6, 7, 8) for d in (2, 9, 16, 23, 28)],
    )
    def test_days(self, start, end):
        partner = MagicMock(start_date=start, end_date=end)
        window = PartnerService._active_window(partner, date(2026, 1, 1), date(2026, 12, 31))
        assert window[0] == start and window[1] == end

    @pytest.mark.parametrize("amount", ["25", "250", "2500", "25000", "250000"])
    def test_balance(self, amount):
        lines = [
            {"account": "1110", "debit": Decimal(amount), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(amount)},
        ]
        assert_balanced_lines(lines, currency="AED")


class TestEinvoiceMegaF:
    @pytest.mark.parametrize(
        "country,total", [("AE", "75"), ("PS", "232"), ("IL", "236"), ("SA", "230"), ("AE", "1050")]
    )
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
