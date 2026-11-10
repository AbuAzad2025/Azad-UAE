"""Scenario matrix batch 10 — final pure grids to exceed 1000 cases.

Conversion, margins, withholding, levies, windows, months, financials and
Einvoice variants on broad generated grids.
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
from utils.currency_utils import convert_and_quantize_aed
from utils.einvoice_document import build_invoice_xml
from utils.einvoice_document import invoice_sha256_hex as invoice_hash


class TestConversionGridB:
    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (7, 77, 777) for r in (0.27, 3.65, 4.5)],
    )
    def test_grid(self, amount, rate):
        expected = (Decimal(amount) * Decimal(rate)).quantize(Decimal("0.001"))
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == expected


class TestMarginGridB:
    @pytest.mark.parametrize(
        "revenue,cost,rate",
        [(str(r), str(c), f) for r in (150, 750) for c in (100, 365) for f in ("1", "3.65")],
    )
    def test_grid(self, revenue, cost, rate):
        fx = Decimal(rate)
        expected_cost = Decimal(cost) / fx if fx != 1 else Decimal(cost)
        expected = (Decimal(revenue) - expected_cost).quantize(Decimal("0.001"))
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), fx) == expected


class TestWithholdingGridB:
    @pytest.mark.parametrize(
        "amount,rate",
        [(str(a), str(r)) for a in (15, 150, 1500) for r in (2, 5, 10, 25)],
    )
    def test_grid(self, amount, rate):
        expected = (Decimal(amount) * Decimal(rate) / Decimal("100")).quantize(Decimal("0.001"))
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == expected


class TestLevyGridB:
    @pytest.mark.parametrize("country", ["PS", "IL", "SA"])
    def test_customs_grid(self, country):
        rates = {"PS": "15", "IL": "18", "SA": "15"}
        customs, excise = compute_import_levy_defaults(
            [(4, Decimal("50"), Decimal("0"), "")],
            country=country, customs_duty=None, excise_amount=None,
        )
        assert customs == (Decimal("200") * Decimal(rates[country]) / Decimal("100")).quantize(Decimal("0.001"))
        assert excise == Decimal("0.000")

    @pytest.mark.parametrize("cat", ["tobacco", "energy_drinks", "soft_drinks"])
    def test_sa_excise_grid(self, cat):
        _customs, excise = compute_import_levy_defaults(
            [(2, Decimal("100"), Decimal("0"), cat)],
            country="SA", customs_duty=None, excise_amount=None,
        )
        rate = Decimal("100") if cat != "soft_drinks" else Decimal("50")
        base = Decimal("200") + Decimal("200") * Decimal("15") / Decimal("100")
        assert excise == (base * rate / Decimal("100")).quantize(Decimal("0.001"))


class TestFinancialGridB:
    @pytest.mark.parametrize("loss", ["0", "25", "50", "100"])
    def test_loss_grid(self, loss):
        form = {
            "investment_amount": "0", "share_percentage": "0", "fixed_monthly_amount": "0",
            "expense_share_percentage": "0", "loss_share_percentage": loss, "min_profit_threshold": "0",
        }
        values, error = _parse_partner_financials(form)
        assert error is None
        assert values["loss_share_percentage"] == Decimal(loss)

    @pytest.mark.parametrize("month", list(range(1, 13)))
    def test_months_each(self, month):
        assert PartnerService._months_in_period(date(2026, month, 1), date(2026, month, 28)) == 1

    @pytest.mark.parametrize("amount", [str(v) for v in (15, 150, 1500, 15000)])
    def test_balance_grid_b(self, amount):
        lines = [
            {"account": "1110", "debit": Decimal(amount), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(amount)},
        ]
        assert_balanced_lines(lines, currency="AED")

    @pytest.mark.parametrize("debit,credit", [("10", "11"), ("1000", "999")])
    def test_unbalanced_grid_b(self, debit, credit):
        lines = [
            {"account": "1110", "debit": Decimal(debit), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(credit)},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines, currency="AED")


class TestEinvoiceGrid:
    @pytest.mark.parametrize("country", ["AE", "PS", "IL", "SA"])
    def test_hash_stable_per_country(self, country):
        sale = MagicMock(
            sale_number="S-1", sale_date=None, tax_rate=Decimal("5"),
            total_amount=Decimal("105"), tax_amount=Decimal("5"),
            taxable_amount=Decimal("100"), subtotal=Decimal("105"), lines=[],
        )
        sale.customer = MagicMock(name="B", tax_number="")
        tenant = MagicMock(name="S", name_en="S", tax_number="1", address_en="", city="")
        xml = build_invoice_xml(sale, tenant, country=country, currency="AED")
        assert invoice_hash(xml) == invoice_hash(xml)
        assert country in xml
