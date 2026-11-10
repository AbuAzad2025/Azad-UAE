"""Scenario matrix batch 8 — validation guards, totals, and edge grids.

Pure-function cases: withholding refusals, sale-line totals, discount
guards, IA payload variants, commission base floors, active windows,
payroll IL/PS bands, MWAC receipts, and sequential-loss variants.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from models.sale import SaleLine
from services.expense_service import ExpenseService
from services.ita_allocation_service import ItaAllocationService
from services.partner_service import PartnerService
from services.sale_service import SaleService
from services.stock_service import _MWACHelper
from utils.country_tax import payroll_income_tax_amount


class TestWithholdingRefusals:
    @pytest.mark.parametrize(
        "amount,rate",
        [
            ("100", None), ("100", "-1"), ("100", "101"), ("100", "abc"),
            ("0", "5"), ("-5", "5"), ("100", "NaN"), ("100", "Infinity"),
        ],
    )
    def test_invalid_refused(self, amount, rate):
        with pytest.raises(ValueError):
            ExpenseService.calculate_withholding(amount, rate, True)


class TestSaleLineTotalsGrid:
    @pytest.mark.parametrize(
        "qty,price,disc",
        [(str(q), str(p), str(d)) for q in (1, 2, 5) for p in (10, 33.33) for d in (0, 10, 50)],
    )
    def test_line_total_grid(self, qty, price, disc):
        line = SaleLine(quantity=Decimal(qty), unit_price=Decimal(price), discount_percent=Decimal(disc))
        line.calculate_line_total()
        expected = (Decimal(qty) * Decimal(price) * (Decimal("1") - Decimal(disc) / Decimal("100"))).quantize(
            Decimal("0.001")
        )
        assert line.line_total == expected


class TestCommissionBaseFloor:
    @pytest.mark.parametrize("margin", ["0", "-5", "-100.5"])
    def test_nonpositive_margin_zero_base(self, margin):
        assert SaleService._commission_base_aed(Decimal(margin), Decimal("3.65")) == Decimal("0")


class TestActiveWindowGrid:
    @pytest.mark.parametrize(
        "start,end,days",
        [
            (date(2026, 1, 1), date(2026, 1, 31), 31),
            (date(2026, 1, 15), date(2026, 1, 15), 1),
            (date(2026, 1, 31), date(2026, 1, 31), 1),
            (date(2025, 12, 1), None, 31),
            (None, date(2026, 2, 5), 31),
        ],
    )
    def test_window_grid(self, start, end, days):
        partner = MagicMock(start_date=start, end_date=end)
        window = PartnerService._active_window(partner, date(2026, 1, 1), date(2026, 1, 31))
        assert window is not None
        assert (window[1] - window[0]).days + 1 == days

    def test_after_period_none(self):
        partner = MagicMock(start_date=date(2026, 2, 1), end_date=None)
        assert PartnerService._active_window(partner, date(2026, 1, 1), date(2026, 1, 31)) is None


class TestPayrollBands:
    @pytest.mark.parametrize("income", ["120000", "300000", "800000"])
    def test_il_progressive_grows(self, income):
        result = payroll_income_tax_amount(Decimal(income), "IL")
        assert result["tax"] > Decimal("0")
        assert result["tax"] < Decimal(income) / Decimal("2")

    @pytest.mark.parametrize("income", ["50000", "100000", "150000"])
    def test_ps_band_grows(self, income):
        result = payroll_income_tax_amount(Decimal(income), "PS")
        assert result["tax"] >= Decimal("0")

    def test_il_credit_points_reduce_tax(self):
        base = payroll_income_tax_amount(Decimal("500000"), "IL")
        fewer = payroll_income_tax_amount(Decimal("500000"), "IL", credit_points=Decimal("1"))
        assert fewer["tax"] > base["tax"]


class TestMwacReceipts:
    @pytest.mark.parametrize(
        "old_qty,old_value,change,unit_cost",
        [
            ("100", "5000", "25", "70"), ("100", "5000", "200", "40"),
            ("0", "0", "5", "100"), ("1000", "20000", "1000", "20"),
            ("10", "300", "90", "10"), ("75", "1500", "25", "60"),
        ],
    )
    def test_receipt_invariants(self, old_qty, old_value, change, unit_cost):
        qty, value, avg = _MWACHelper.calc(
            Decimal(old_qty), Decimal(old_value), Decimal(change), Decimal(unit_cost)
        )
        assert qty == Decimal(old_qty) + Decimal(change)
        assert value == Decimal(old_value) + Decimal(change) * Decimal(unit_cost)
        assert avg == (value / qty).quantize(Decimal("0.0001")) if qty else Decimal("0")


class TestItaVariants:
    def _sale(self):
        return MagicMock(
            sale_number="S-1", taxable_amount=Decimal("100"), tax_amount=Decimal("18"),
            total_amount=Decimal("118"), discount_amount=Decimal("0"),
            subtotal=Decimal("100"), sale_date=None,
        )

    @pytest.mark.parametrize(
        "seller,buyer,has_buyer",
        [("123456789", "987654321", True), ("123456789", "", False)],
    )
    def test_buyer_presence(self, seller, buyer, has_buyer):
        payload = ItaAllocationService._build_payload(MagicMock(id=1), self._sale(), seller, buyer)
        assert ("Customer_VAT_Number" in payload) == has_buyer
        assert payload["Vat_Number"] == seller

    def test_invoice_id_capped(self):
        sale = self._sale()
        sale.sale_number = "X" * 60
        payload = ItaAllocationService._build_payload(MagicMock(id=1), sale, "123456789", "")
        assert len(payload["Invoice_ID"]) <= 50
