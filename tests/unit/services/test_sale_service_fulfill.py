from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


def _sale(**overrides):
    customer = MagicMock()
    customer.apply_sale = MagicMock()
    customer.apply_receipt = MagicMock()
    line = MagicMock()
    line.product_id = 1
    line.quantity = 1
    line.product = MagicMock(name="Widget")
    line.product.name = "Widget"
    sale = MagicMock(
        id=1,
        sale_number="S-001",
        customer=customer,
        customer_id=1,
        warehouse_id=1,
        tenant_id=1,
        branch_id=1,
        seller_id=2,
        exchange_rate=Decimal("1"),
        currency="AED",
        amount_aed=Decimal("100"),
        total_amount=Decimal("100"),
        subtotal=Decimal("100"),
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        tax_rate=Decimal("5"),
        tax_amount=Decimal("0"),
        taxable_amount=Decimal("100"),
        prices_include_vat=False,
        notes="",
        paid_amount=Decimal("0"),
        paid_amount_aed=Decimal("0"),
        lines=[line],
        sale_date=MagicMock(date=lambda: MagicMock()),
    )
    sale.__dict__.update(overrides)
    return sale


class TestFulfillSale:
    def test_fulfill_no_customer(self, app):
        from services.sale_service import SaleService

        sale = _sale(customer=None)
        with pytest.raises(ValueError, match="العميل غير موجود"):
            SaleService.fulfill_sale(sale)

    def test_fulfill_inventory_already_posted(self, app):
        from services.sale_service import SaleService

        sale = _sale()
        with patch.object(SaleService, "has_inventory_posted", return_value=True):
            with pytest.raises(ValueError, match="تم تنفيذ المخزون"):
                SaleService.fulfill_sale(sale)

    def test_fulfill_stock_unavailable(self, app):
        from services.sale_service import SaleService

        sale = _sale()
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch("services.sale_service.StockService") as stock,
        ):
            stock.check_availability_in_warehouse.return_value = (False, "نفد")
            with pytest.raises(ValueError, match="نفد"):
                SaleService.fulfill_sale(sale)

    def test_fulfill_basic_no_payment(self, app):
        from services.sale_service import SaleService

        sale = _sale()
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch("services.sale_service.StockService") as stock,
            patch("services.sale_service.GLService") as gl,
            patch("services.sale_service.post_or_fail"),
            patch("services.sale_service.post_sale_commissions"),
            patch("services.sale_service.should_post_vat_gl", return_value=False),
        ):
            stock.check_availability_in_warehouse.return_value = (True, "")
            stock.process_sale_lines.return_value = None
            stock.calculate_sale_cogs_and_deduct.return_value = Decimal("0")
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4000"
            SaleService.fulfill_sale(sale)
            sale.calculate_totals.assert_called_once()
            sale.customer.apply_sale.assert_called_once()

    def test_fulfill_with_cash_payment(self, app):
        from services.sale_service import SaleService

        sale = _sale()
        payment_data = {
            "amount": 100,
            "currency": "AED",
            "exchange_rate": 1.0,
            "payment_method": "cash",
        }
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch.object(SaleService, "create_payment_for_sale") as mk_pay,
            patch("services.sale_service.StockService") as stock,
            patch("services.sale_service.GLService") as gl,
            patch("services.sale_service.post_or_fail"),
            patch("services.sale_service.post_sale_commissions"),
            patch("services.sale_service.should_post_vat_gl", return_value=False),
        ):
            stock.check_availability_in_warehouse.return_value = (True, "")
            stock.calculate_sale_cogs_and_deduct.return_value = Decimal("50")
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4000"
            SaleService.fulfill_sale(sale, payment_data=payment_data)
            mk_pay.assert_called_once()

    def test_fulfill_overpayment_creates_prepayment(self, app):
        from services.sale_service import SaleService

        sale = _sale(amount_aed=Decimal("100"))
        payment_data = {
            "amount": 150,
            "currency": "AED",
            "exchange_rate": 1.0,
            "payment_method": "cash",
        }
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch.object(SaleService, "create_payment_for_sale"),
            patch("services.sale_service.StockService") as stock,
            patch("services.sale_service.GLService") as gl,
            patch("services.sale_service.post_or_fail"),
            patch("services.sale_service.post_sale_commissions"),
            patch("services.sale_service.should_post_vat_gl", return_value=False),
            patch("services.sale_service.generate_number", return_value="PRE-1"),
            patch("services.sale_service.db.session") as mock_db,
        ):
            stock.check_availability_in_warehouse.return_value = (True, "")
            stock.calculate_sale_cogs_and_deduct.return_value = Decimal("0")
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4000"
            SaleService.fulfill_sale(sale, payment_data=payment_data)
            mock_db.add.assert_called()
            sale.customer.apply_receipt.assert_called()

    def test_fulfill_negative_payment_raises(self, app):
        from services.sale_service import SaleService

        sale = _sale()
        payment_data = {
            "amount": 10,
            "currency": "AED",
            "exchange_rate": -1.0,
            "payment_method": "cash",
        }
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch("services.sale_service.StockService") as stock,
        ):
            stock.check_availability_in_warehouse.return_value = (True, "")
            with pytest.raises(ValueError, match="مبلغ الدفع"):
                SaleService.fulfill_sale(sale, payment_data=payment_data)

    def test_fulfill_vat_inclusive_gl(self, app):
        from services.sale_service import SaleService

        sale = _sale(prices_include_vat=True, tax_rate=Decimal("5"))
        with (
            patch.object(SaleService, "has_inventory_posted", return_value=False),
            patch("services.sale_service.StockService") as stock,
            patch("services.sale_service.GLService") as gl,
            patch("services.sale_service.post_or_fail") as post,
            patch("services.sale_service.post_sale_commissions"),
            patch("services.sale_service.should_post_vat_gl", return_value=True),
        ):
            stock.check_availability_in_warehouse.return_value = (True, "")
            stock.calculate_sale_cogs_and_deduct.return_value = Decimal("0")
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4000"
            SaleService.fulfill_sale(sale)
            assert post.called


class TestCreatePaymentForSale:
    def test_zero_amount_raises(self, app):
        from services.sale_service import SaleService

        with pytest.raises(ValueError, match="مبلغ الدفع"):
            SaleService.create_payment_for_sale(_sale(), 0, "cash")

    def test_cheque_missing_fields(self, app):
        from services.sale_service import SaleService

        with pytest.raises(ValueError, match="رقم الشيك"):
            SaleService.create_payment_for_sale(_sale(), 100, "cheque")

    def test_cheque_invalid_date(self, app):
        from services.sale_service import SaleService

        with pytest.raises(ValueError, match="تاريخ الشيك"):
            SaleService.create_payment_for_sale(
                _sale(),
                100,
                "cheque",
                cheque_number="123",
                cheque_date="bad",
                bank_name="Bank",
            )

    def test_cash_payment_success(self, app):
        from services.sale_service import SaleService

        sale = _sale()
        with (
            patch("services.sale_service.generate_number", return_value="PAY-1"),
            patch("services.sale_service.GLService") as gl,
            patch("services.sale_service.post_or_fail"),
            patch("services.sale_service.db.session") as mock_db,
        ):
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            SaleService.create_payment_for_sale(sale, 100, "cash", currency="AED", exchange_rate=1.0)
            mock_db.add.assert_called()
            sale.recalculate_payment_status.assert_called()

    def test_cheque_payment_success(self, app):
        from services.sale_service import SaleService

        sale = _sale()
        with (
            patch("services.sale_service.generate_number", return_value="PAY-2"),
            patch("services.sale_service.GLService") as gl,
            patch("services.sale_service.post_or_fail"),
            patch("services.sale_service.db.session") as mock_db,
            patch("models.Cheque"),
        ):
            gl.get_account_code_for_concept.return_value = "1150"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            SaleService.create_payment_for_sale(
                sale,
                100,
                "cheque",
                currency="AED",
                exchange_rate=1.0,
                cheque_number="CHQ1",
                cheque_date="2026-06-30",
                bank_name="ENBD",
            )
            assert mock_db.add.call_count >= 1

    def test_fx_gain_on_payment(self, app):
        from services.sale_service import SaleService

        sale = _sale(exchange_rate=Decimal("3.67"), currency="USD")
        with (
            patch("services.sale_service.generate_number", return_value="PAY-3"),
            patch("services.sale_service.GLService") as gl,
            patch("services.sale_service.post_or_fail") as post,
            patch("services.sale_service.db.session"),
        ):
            gl.get_payment_debit_account.return_value = "1100"
            gl.get_payment_debit_concept.return_value = "CASH"
            gl.get_customer_credit_account.return_value = "1200"
            gl.get_customer_credit_concept.return_value = "AR"
            gl.get_account_code_for_concept.return_value = "4900"
            SaleService.create_payment_for_sale(sale, 100, "cash", currency="USD", exchange_rate=3.8)
            assert post.call_count >= 2
