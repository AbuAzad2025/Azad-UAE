"""Split tenders (Phase 2) — SaleService.prepare_split_payments /
_create_split_payments / fulfill_sale wiring.

Per conventions, heavy collaborators (GL, stock, numbering) are mocked at
the SaleService boundary; conversion math stays real (Decimal-exact).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.sale_service import SaleService


def _sale(amount_aed="100"):
    sale = MagicMock()
    sale.amount_aed = Decimal(amount_aed)
    sale.total_amount = Decimal(amount_aed)
    sale.subtotal = Decimal(amount_aed)
    sale.discount_amount = Decimal("0")
    sale.shipping_cost = Decimal("0")
    sale.tax_rate = Decimal("0")
    sale.tax_amount = Decimal("0")
    sale.prices_include_vat = False
    sale.exchange_rate = Decimal("1")
    sale.warehouse_id = 1
    sale.sale_number = "S-1"
    sale.tenant_id = 1
    sale.branch_id = 1
    sale.customer_id = 1
    sale.seller_id = 2
    sale.notes = ""
    return sale


def _chunks(*rows):
    """rows: (amount, method, currency, rate)"""
    return [
        {"amount": amount, "payment_method": method, "currency": currency, "exchange_rate": rate}
        for amount, method, currency, rate in rows
    ]


@pytest.fixture
def payment_mocks():
    with (
        patch.object(SaleService, "create_payment_for_sale") as create_payment,
        patch("services.sale_service.db") as mock_db,
        patch("utils.helpers.generate_number", return_value="PRE-1"),
        patch("models.Payment") as mock_payment_cls,
    ):
        mock_payment_cls.return_value = MagicMock(id=55)
        yield type(
            "Mocks",
            (),
            {
                "create_payment": create_payment,
                "db": mock_db,
                "payment_cls": mock_payment_cls,
            },
        )


class TestPrepareSplitPayments:
    def test_prepares_chunks_with_exact_aed(self):
        prepared = SaleService.prepare_split_payments(_chunks(("30", "cash", "AED", "1"), ("70", "card", "AED", "1")))
        assert [p["amount_aed"] for p in prepared] == [Decimal("30.000"), Decimal("70.000")]
        assert prepared[0]["amount"] == Decimal("30")
        assert prepared[1]["payment_method"] == "card"

    def test_mixed_currency_exact_conversion(self):
        prepared = SaleService.prepare_split_payments(
            _chunks(("10", "cash", "USD", "3.673"), ("50", "card", "AED", "1"))
        )
        assert prepared[0]["amount_aed"] == Decimal("36.730")
        assert prepared[1]["amount_aed"] == Decimal("50.000")

    def test_empty_list_rejected(self):
        with pytest.raises(ValueError, match="فارغة"):
            SaleService.prepare_split_payments([])

    def test_non_dict_chunk_rejected(self):
        with pytest.raises(ValueError, match="غير صالحة"):
            SaleService.prepare_split_payments(["cash"])

    def test_zero_amount_rejected(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            SaleService.prepare_split_payments(_chunks(("0", "cash", "AED", "1")))

    def test_negative_amount_rejected(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            SaleService.prepare_split_payments(_chunks(("-5", "cash", "AED", "1")))

    def test_missing_method_rejected(self):
        with pytest.raises(ValueError):
            SaleService.prepare_split_payments([{"amount": "10", "currency": "AED", "exchange_rate": "1"}])

    def test_invalid_method_rejected(self):
        with pytest.raises(ValueError, match="غير مدعومة"):
            SaleService.prepare_split_payments(_chunks(("10", "bitcoin", "AED", "1")))

    def test_invalid_rate_rejected(self):
        with pytest.raises(ValueError, match="سعر الصرف"):
            SaleService.prepare_split_payments(_chunks(("10", "cash", "AED", "0")))

    def test_bank_alias_normalized(self):
        prepared = SaleService.prepare_split_payments(_chunks(("10", "bank", "AED", "1")))
        assert prepared[0]["payment_method"] == "bank_transfer"


class TestCreateSplitPayments:
    def test_two_methods_summing_exactly(self, payment_mocks):
        sale = _sale("100")
        prepared = SaleService.prepare_split_payments(_chunks(("30", "cash", "AED", "1"), ("70", "card", "AED", "1")))
        SaleService._create_split_payments(sale, prepared)
        assert payment_mocks.create_payment.call_count == 2
        amounts = [c.kwargs["amount"] for c in payment_mocks.create_payment.call_args_list]
        assert amounts == [Decimal("30"), Decimal("70")]
        methods = [c.kwargs["payment_method"] for c in payment_mocks.create_payment.call_args_list]
        assert methods == ["cash", "card"]
        # No prepayment on exact settlement
        payment_mocks.db.session.add.assert_not_called()
        sale.customer.apply_receipt.assert_not_called()

    def test_three_methods_summing_exactly(self, payment_mocks):
        sale = _sale("100")
        prepared = SaleService.prepare_split_payments(
            _chunks(("25", "cash", "AED", "1"), ("25", "card", "AED", "1"), ("50", "e_wallet", "AED", "1"))
        )
        SaleService._create_split_payments(sale, prepared)
        assert payment_mocks.create_payment.call_count == 3
        payment_mocks.db.session.add.assert_not_called()

    def test_partial_payment_leaves_balance_on_account(self, payment_mocks):
        sale = _sale("100")
        prepared = SaleService.prepare_split_payments(_chunks(("40", "cash", "AED", "1")))
        SaleService._create_split_payments(sale, prepared)
        assert payment_mocks.create_payment.call_count == 1
        assert payment_mocks.create_payment.call_args.kwargs["amount"] == Decimal("40")
        # Partial ≠ overpayment — no prepayment booked.
        payment_mocks.db.session.add.assert_not_called()

    def test_overpayment_caps_crossing_chunk_and_prepays_once(self, payment_mocks):
        sale = _sale("100")
        prepared = SaleService.prepare_split_payments(_chunks(("60", "cash", "AED", "1"), ("80", "card", "AED", "1")))
        SaleService._create_split_payments(sale, prepared)
        # First chunk booked in full, crossing chunk capped at remaining 40.
        amounts = [c.kwargs["amount"] for c in payment_mocks.create_payment.call_args_list]
        assert amounts == [Decimal("60"), Decimal("40.000")]
        # Exactly ONE aggregate prepayment for the 40 excess (last tender's terms).
        payment_mocks.db.session.add.assert_called_once()
        prepayment_kwargs = payment_mocks.payment_cls.call_args.kwargs
        assert prepayment_kwargs["payment_type"] == "prepayment"
        assert prepayment_kwargs["amount_aed"] == Decimal("40")
        assert prepayment_kwargs["amount"] == Decimal("40.000")
        assert prepayment_kwargs["payment_method"] == "card"
        sale.customer.apply_receipt.assert_called_once_with(Decimal("40"))
        assert "[دفع زائد]" in sale.notes

    def test_overpayment_beyond_last_chunk_pools_into_single_prepayment(self, payment_mocks):
        sale = _sale("50")
        prepared = SaleService.prepare_split_payments(_chunks(("40", "cash", "AED", "1"), ("60", "card", "AED", "1")))
        SaleService._create_split_payments(sale, prepared)
        # Chunk 1 fully applied (40), chunk 2 partially applied (10) — excess 50 pooled once.
        amounts = [c.kwargs["amount"] for c in payment_mocks.create_payment.call_args_list]
        assert amounts == [Decimal("40"), Decimal("10.000")]
        payment_mocks.db.session.add.assert_called_once()
        assert payment_mocks.payment_cls.call_args.kwargs["amount_aed"] == Decimal("50")

    def test_chunk_fully_beyond_balance_creates_no_payment_row(self, payment_mocks):
        sale = _sale("50")
        prepared = SaleService.prepare_split_payments(_chunks(("50", "cash", "AED", "1"), ("20", "card", "AED", "1")))
        SaleService._create_split_payments(sale, prepared)
        # Only the first chunk pays the invoice; the second is entirely excess.
        assert payment_mocks.create_payment.call_count == 1
        assert payment_mocks.create_payment.call_args.kwargs["amount"] == Decimal("50")
        payment_mocks.db.session.add.assert_called_once()
        assert payment_mocks.payment_cls.call_args.kwargs["amount_aed"] == Decimal("20")

    def test_mixed_currency_split_exact(self, payment_mocks):
        sale = _sale("86.730")
        prepared = SaleService.prepare_split_payments(
            _chunks(("10", "cash", "USD", "3.673"), ("50", "card", "AED", "1"))
        )
        SaleService._create_split_payments(sale, prepared)
        assert payment_mocks.create_payment.call_count == 2
        first = payment_mocks.create_payment.call_args_list[0].kwargs
        assert first["amount"] == Decimal("10")
        assert first["currency"] == "USD"
        payment_mocks.db.session.add.assert_not_called()

    def test_zero_total_sum_rejected(self, payment_mocks):
        sale = _sale("100")
        with pytest.raises(ValueError, match="أكبر من صفر"):
            SaleService._create_split_payments(sale, [])

    def test_cheque_overpayment_prepayment_unconfirmed(self, payment_mocks):
        sale = _sale("50")
        prepared = SaleService.prepare_split_payments(
            _chunks(
                ("70", "cheque", "AED", "1"),
            )
        )
        prepared[0].update({"cheque_number": "CH1", "cheque_date": "2026-08-01", "bank_name": "ENBD"})
        SaleService._create_split_payments(sale, prepared)
        assert payment_mocks.payment_cls.call_args.kwargs["payment_confirmed"] is False


class TestFulfillSaleSplitWiring:
    def test_fulfill_prepares_raw_chunks(self):
        sale = _sale("100")
        sale.lines = []
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch("services.sale_service.StockService") as stock,
            patch("services.sale_service.GLService"),
            patch("services.sale_service.post_or_fail"),
            patch("services.sale_service.post_sale_commissions"),
            patch.object(SaleService, "create_payment_for_sale") as create_payment,
            patch("services.sale_service.db"),
        ):
            stock.check_availability_in_warehouse.return_value = (True, "")
            stock.calculate_sale_cogs_and_deduct.return_value = Decimal("0")
            SaleService.fulfill_sale(
                sale,
                payments_data=_chunks(("30", "cash", "AED", "1"), ("70", "card", "AED", "1")),
            )
        assert create_payment.call_count == 2
        assert [c.kwargs["amount"] for c in create_payment.call_args_list] == [Decimal("30"), Decimal("70")]

    def test_fulfill_single_payment_data_backward_compatible(self):
        sale = _sale("100")
        sale.lines = []
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch("services.sale_service.StockService") as stock,
            patch("services.sale_service.GLService"),
            patch("services.sale_service.post_or_fail"),
            patch("services.sale_service.post_sale_commissions"),
            patch.object(SaleService, "create_payment_for_sale") as create_payment,
            patch("services.sale_service.db"),
        ):
            stock.check_availability_in_warehouse.return_value = (True, "")
            stock.calculate_sale_cogs_and_deduct.return_value = Decimal("0")
            SaleService.fulfill_sale(
                sale,
                payment_data={
                    "amount": 100,
                    "payment_method": "cash",
                    "currency": "AED",
                    "exchange_rate": 1.0,
                },
                paid_amount_aed=Decimal("100"),
            )
        create_payment.assert_called_once()
        assert create_payment.call_args.kwargs["amount"] == 100

    def test_fulfill_rejects_invalid_split_sum(self):
        sale = _sale("100")
        sale.lines = []
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch("services.sale_service.StockService") as stock,
            patch("services.sale_service.GLService"),
            patch("services.sale_service.post_or_fail"),
            patch("services.sale_service.post_sale_commissions"),
            patch("services.sale_service.db"),
        ):
            stock.check_availability_in_warehouse.return_value = (True, "")
            with pytest.raises(ValueError, match="أكبر من صفر"):
                SaleService.fulfill_sale(sale, payments_data=_chunks(("0", "cash", "AED", "1")))
