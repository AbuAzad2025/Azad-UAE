"""Commission basis — FX-consistent margins and VAT-inclusive discounts.

Golden values, independently computed:
- Foreign invoice: revenue 100 USD, base cost 365 AED at rate 3.65
  → cost in invoice currency = 100 USD → margin 0 (old code: 100 − 365).
- VAT-inclusive discount share is stripped of VAT before reducing margin.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from services.sale_service import SaleService


class TestCommissionMarginFx:
    def test_foreign_invoice_cost_converted_to_invoice_currency(self):
        margin = SaleService._commission_margin(Decimal("100"), Decimal("365"), Decimal("3.65"))
        assert margin == Decimal("0.000")

    def test_foreign_invoice_positive_margin(self):
        margin = SaleService._commission_margin(Decimal("120"), Decimal("365"), Decimal("3.65"))
        assert margin == Decimal("20.000")

    def test_domestic_invoice_unchanged(self):
        margin = SaleService._commission_margin(Decimal("100"), Decimal("60"), Decimal("1"))
        assert margin == Decimal("40.000")

    def test_negative_margin_stays_negative(self):
        margin = SaleService._commission_margin(Decimal("50"), Decimal("365"), Decimal("3.65"))
        assert margin == Decimal("-50.000")


class TestInclusiveDiscountStrip:
    def test_discount_share_stripped_of_vat(self, mocker):
        entry = MagicMock()
        entry.base_amount_aed = Decimal("100.000")
        entry.profit_margin = Decimal("100.000")
        entry.commission_amount_aed = Decimal("10.000")
        mocker.patch.object(SaleService, "_commission_base_aed", side_effect=lambda amount, *a, **k: amount)
        SaleService._apply_invoice_discount_to_commissions(
            [(entry, Decimal("100"), Decimal("100"), Decimal("10"), Decimal("100"))],
            subtotal=Decimal("100"),
            total_discount=Decimal("11"),
            exchange_rate=Decimal("1"),
            prices_include_vat=True,
            tax_rate=Decimal("10"),
        )
        # Share 11 gross → 10 net of 10% VAT → base 90, commission 9.
        assert entry.base_amount_aed == Decimal("90.000")
        assert entry.commission_amount_aed == Decimal("9.000")

    def test_non_inclusive_discount_unchanged(self, mocker):
        entry = MagicMock()
        entry.base_amount_aed = Decimal("100.000")
        entry.profit_margin = Decimal("100.000")
        entry.commission_amount_aed = Decimal("10.000")
        mocker.patch.object(SaleService, "_commission_base_aed", side_effect=lambda amount, *a, **k: amount)
        SaleService._apply_invoice_discount_to_commissions(
            [(entry, Decimal("100"), Decimal("100"), Decimal("10"), Decimal("100"))],
            subtotal=Decimal("100"),
            total_discount=Decimal("11"),
            exchange_rate=Decimal("1"),
            prices_include_vat=False,
            tax_rate=Decimal("10"),
        )
        assert entry.base_amount_aed == Decimal("89.000")
        assert entry.commission_amount_aed == Decimal("8.900")


class TestRecomputeHistoricalBasis:
    def test_foreign_entry_rebased_to_zero_margin(self, mocker):
        # Historical row: revenue 100 USD, base cost 365 AED stored as
        # cost_basis; old code booked margin 100 - 365 = -265 (floored to 0
        # commission via base 0). New basis: cost 100 USD → margin 0.
        entry = MagicMock(cost_basis=Decimal("365"), percentage=Decimal("20"), tenant_id=1, currency="USD")
        sale = MagicMock(tax_rate=Decimal("0"), prices_include_vat=False, exchange_rate=Decimal("3.65"))
        line = MagicMock(line_total=Decimal("100"), tax_category="standard")
        mocker.patch.object(SaleService, "_commission_base_aed", side_effect=lambda margin, *a, **k: margin)
        margin, base, commission = SaleService.recompute_commission_basis(entry, sale, line)
        assert margin == Decimal("0.000")
        assert base == Decimal("0.000")
        assert commission == Decimal("0.000")

    def test_foreign_entry_positive_margin(self, mocker):
        entry = MagicMock(cost_basis=Decimal("365"), percentage=Decimal("25"), tenant_id=1, currency="USD")
        sale = MagicMock(tax_rate=Decimal("0"), prices_include_vat=False, exchange_rate=Decimal("3.65"))
        line = MagicMock(line_total=Decimal("120"), tax_category="standard")
        mocker.patch.object(SaleService, "_commission_base_aed", side_effect=lambda margin, *a, **k: margin)
        margin, base, commission = SaleService.recompute_commission_basis(entry, sale, line)
        assert margin == Decimal("20.000")
        assert commission == Decimal("5.000")
