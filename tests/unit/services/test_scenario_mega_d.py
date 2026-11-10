"""Scenario mega-grid D — financial ranges, windows, balance, documents."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from routes.partners import _parse_partner_financials
from services.gl_posting import GlPostingError, assert_balanced_lines
from services.partner_service import PartnerService
from utils.einvoice_document import build_invoice_xml
from utils.einvoice_document import invoice_sha256_hex as invoice_hash


class TestFinancialsMega:
    @pytest.mark.parametrize(
        "share,expense,loss",
        [
            (str(s), str(e), str(lo))
            for s in (0, 10, 25, 50, 75, 100, 33.33)
            for e in (0, 50, 100)
            for lo in (0, 50, 100)
        ],
    )
    def test_grid(self, share, expense, loss):
        form = {
            "investment_amount": "0", "share_percentage": share, "fixed_monthly_amount": "0",
            "expense_share_percentage": expense, "loss_share_percentage": loss, "min_profit_threshold": "0",
        }
        values, error = _parse_partner_financials(form)
        assert error is None
        assert values["share_percentage"] == Decimal(share)
        assert values["expense_share_percentage"] == Decimal(expense)
        assert values["loss_share_percentage"] == Decimal(loss)

    @pytest.mark.parametrize("field", ["share_percentage", "expense_share_percentage", "loss_share_percentage"])
    @pytest.mark.parametrize("bad", ["-1", "101", "150", "abc", ""])
    def test_bad_grid(self, field, bad):
        form = {
            "investment_amount": "0", "share_percentage": "10", "fixed_monthly_amount": "0",
            "expense_share_percentage": "0", "loss_share_percentage": "0", "min_profit_threshold": "0",
        }
        form[field] = bad
        values, error = _parse_partner_financials(form)
        # An empty string falls back to "0" (valid); others refuse.
        if bad == "":
            assert error is None
        else:
            assert values is None
            assert error


class TestWindowsMega:
    @pytest.mark.parametrize(
        "start,end",
        [
            (date(2026, m, d), date(2026, m, d))
            for m in range(1, 13)
            for d in (1, 7, 15, 21, 28)
        ],
    )
    def test_single_days(self, start, end):
        partner = MagicMock(start_date=start, end_date=end)
        window = PartnerService._active_window(partner, date(2026, 1, 1), date(2026, 12, 31))
        assert window is not None
        assert window[0] == start
        assert window[1] == end

    @pytest.mark.parametrize("amount", [str(v) for v in (2, 20, 200, 2000, 20000, 200000)])
    def test_balance_mega(self, amount):
        lines = [
            {"account": "1110", "debit": Decimal(amount), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(amount)},
        ]
        assert_balanced_lines(lines, currency="AED")

    @pytest.mark.parametrize("debit,credit", [(str(d), str(c)) for d, c in [(5, 6), (50, 49), (500, 505), (5000, 4999)]])
    def test_unbalanced_mega(self, debit, credit):
        lines = [
            {"account": "1110", "debit": Decimal(debit), "credit": Decimal("0")},
            {"account": "4100", "debit": Decimal("0"), "credit": Decimal(credit)},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines, currency="AED")


class TestEinvoiceMega:
    @pytest.mark.parametrize("country", ["AE", "PS", "IL", "SA"])
    @pytest.mark.parametrize("total", ["100", "250", "1000", "9999"])
    def test_grid(self, country, total):
        sale = MagicMock(
            sale_number="S-1", sale_date=None, tax_rate=Decimal("5"),
            total_amount=Decimal(total), tax_amount=Decimal("5"),
            taxable_amount=Decimal(total) - Decimal("5"), subtotal=Decimal(total), lines=[],
        )
        sale.customer = MagicMock(name="B", tax_number="")
        tenant = MagicMock(name="S", name_en="S", tax_number="1", address_en="", city="")
        xml = build_invoice_xml(sale, tenant, country=country, currency="AED")
        assert f"{Decimal(total):.3f}" in xml
        assert len(invoice_hash(xml)) == 64
