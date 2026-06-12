"""
Tests for critical financial fixes identified in the comprehensive financial audit.
These tests verify the correctness of accounting, inventory, and payment logic.
"""
import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch


class TestChequeBounceBalanceFix:
    """
    Fix: cheque_service.py process_cheque_bounce was calling
    adjust_balance(+amount) which INCREASED customer credit (reduced AR).
    Bounce should INCREASE debt (reduce credit balance), so we pass -amount.
    """

    def test_bounce_incoming_cheque_increases_customer_debt(self, app, db_session, sample_customer, sample_tenant):
        from services.cheque_service import process_cheque_bounce
        from models import Cheque

        # Set customer with some credit balance (positive = credit, negative = debt)
        sample_customer.balance = Decimal('100')
        db_session.commit()

        cheque = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number="CHQ-BOUNCE-001",
            cheque_bank_number="BNK-001",
            cheque_type="incoming",
            customer_id=sample_customer.id,
            bank_name="Test Bank",
            amount=Decimal("500.00"),
            amount_aed=Decimal("500.00"),
            issue_date=date.today(),
            due_date=date.today(),
            status="deposited",
        )
        db_session.add(cheque)
        db_session.commit()

        with patch('services.cheque_service._create_bounce_journal_entry'):
            with patch('services.cheque_service.GLService'):
                process_cheque_bounce(cheque, "NSF")

        # Bounce of 500 AED should INCREASE debt by 500 (balance goes from +100 to -400)
        assert sample_customer.balance == Decimal('-400')

    def test_bounce_incoming_cheque_from_zero_balance(self, app, db_session, sample_customer, sample_tenant):
        from services.cheque_service import process_cheque_bounce
        from models import Cheque

        sample_customer.balance = Decimal('0')
        db_session.commit()

        cheque = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number="CHQ-BOUNCE-002",
            cheque_bank_number="BNK-002",
            cheque_type="incoming",
            customer_id=sample_customer.id,
            bank_name="Test Bank",
            amount=Decimal("250.00"),
            amount_aed=Decimal("250.00"),
            issue_date=date.today(),
            due_date=date.today(),
            status="deposited",
        )
        db_session.add(cheque)
        db_session.commit()

        with patch('services.cheque_service._create_bounce_journal_entry'):
            with patch('services.cheque_service.GLService'):
                process_cheque_bounce(cheque, "NSF")

        assert sample_customer.balance == Decimal('-250')


class TestReceiptAllocationFlushFix:
    """
    Fix: payment_service.py create_receipt was adding sale_payment to session
    but not flushing before calling recalculate_payment_status().
    The new payment was invisible to the relationship query.
    """

    def test_receipt_allocation_updates_sale_payment_status(self, app, db_session, sample_tenant, sample_customer, sample_user, sample_branch):
        from services.payment_service import PaymentService
        from models import Sale, Payment, Receipt

        # Create a sale with balance due
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="S-ALLOC-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            branch_id=sample_branch.id,
            total_amount=Decimal("100.000"),
            amount=Decimal("100.000"),
            amount_aed=Decimal("100.000"),
            paid_amount=Decimal("0"),
            paid_amount_aed=Decimal("0"),
            balance_due=Decimal("100.000"),
            payment_status='unpaid',
        )
        db_session.add(sale)
        db_session.commit()

        payment_data = {
            'customer_id': sample_customer.id,
            'amount': Decimal('100'),
            'currency': 'AED',
            'payment_method': 'cash',
            'branch_id': sample_branch.id,
            'allocate_to_sales': {str(sale.id): Decimal('100')},
        }

        with patch('services.payment_service.GLService') as mock_gl:
            mock_gl.ensure_core_accounts = MagicMock()
            mock_gl.get_payment_debit_account.return_value = '1110'
            mock_gl.get_payment_debit_concept.return_value = 'CASH'
            mock_gl.get_customer_credit_account.return_value = '1130'
            mock_gl.get_customer_credit_concept.return_value = 'AR'
            with patch('services.payment_service.post_or_fail'):
                receipt = PaymentService.create_receipt(payment_data)

        db_session.refresh(sale)
        assert sale.payment_status == 'paid'
        assert sale.balance_due == Decimal('0')


class TestProductCostPriceWeightedAverageFix:
    """
    Fix: stock_service.py process_purchase_lines was setting product.cost_price
    to the last line's warehouse-specific cost, corrupting the global cost.
    Now it recalculates a weighted average across all ProductWarehouseCost records.
    """

    def test_process_purchase_lines_weighted_average_cost(self, app, db_session, sample_tenant, sample_product, sample_warehouse):
        from services.stock_service import StockService
        from models import Purchase, PurchaseLine, Warehouse, ProductWarehouseCost
        from utils.gl_reference_types import GLRef

        # Create a second warehouse
        wh2 = Warehouse(
            tenant_id=sample_tenant.id,
            name="Secondary Warehouse",
            name_ar="مستودع ثانوي",
        )
        db_session.add(wh2)
        db_session.commit()

        # Pre-populate PWC for warehouse 1 with existing stock at cost 10
        pwc1 = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            average_cost=Decimal('10.000'),
            total_quantity=Decimal('10.000'),
            total_value=Decimal('100.000'),
        )
        db_session.add(pwc1)
        db_session.commit()

        # Create a purchase into warehouse 2 with cost 20 (double the first warehouse)
        purchase = Purchase(
            tenant_id=sample_tenant.id,
            purchase_number="PUR-COST-001",
            supplier_id=1,
            supplier_name="Test Supplier",
            purchase_date=datetime.now(timezone.utc),
            user_id=1,
            total_amount=Decimal("20.000"),
            amount=Decimal("20.000"),
            amount_aed=Decimal("20.000"),
            exchange_rate=Decimal('1'),
        )
        db_session.add(purchase)
        db_session.commit()

        line = PurchaseLine(
            tenant_id=sample_tenant.id,
            purchase_id=purchase.id,
            product_id=sample_product.id,
            quantity=Decimal('1.000'),
            unit_cost=Decimal('20.000'),
            line_total=Decimal('20.000'),
        )
        db_session.add(line)
        db_session.commit()

        # Mock _update_wac_on_receipt to simulate warehouse 2 getting cost 20
        def mock_update_wac(tenant_id, product_id, warehouse_id, received_qty, unit_cost_aed, reference_type, reference_id):
            pwc = ProductWarehouseCost.query.filter_by(
                tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id
            ).first()
            if not pwc:
                pwc = ProductWarehouseCost(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    average_cost=unit_cost_aed,
                    total_quantity=received_qty,
                    total_value=received_qty * unit_cost_aed,
                )
                db_session.add(pwc)
            else:
                pwc.total_quantity += received_qty
                pwc.total_value += received_qty * unit_cost_aed
                if pwc.total_quantity > 0:
                    pwc.average_cost = pwc.total_value / pwc.total_quantity

        with patch.object(StockService, '_update_wac_on_receipt', side_effect=mock_update_wac):
            StockService.process_purchase_lines(purchase, warehouse_id=wh2.id)

        db_session.refresh(sample_product)
        # Weighted average: (10*10 + 1*20) / 11 = 120/11 ≈ 10.909
        pwcs = ProductWarehouseCost.query.filter_by(product_id=sample_product.id).all()
        pwc_info = ', '.join([f"wh={p.warehouse_id} qty={p.total_quantity} val={p.total_value}" for p in pwcs])
        expected = Decimal('10.909')
        assert sample_product.cost_price == expected, f"Expected {expected}, got {sample_product.cost_price}. PWCs: [{pwc_info}]"


class TestOverpaymentPrepaymentFix:
    """
    Fix: sale_service.py fulfill_sale was recording overpayment only as a note.
    Now it creates a separate prepayment Payment record and updates customer balance.
    """

    def test_overpayment_creates_prepayment(self, app, db_session, sample_tenant, sample_customer, sample_user, sample_branch, sample_product, sample_warehouse):
        from services.sale_service import SaleService
        from models import Sale, Payment

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="S-OVER-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            branch_id=sample_branch.id,
            warehouse_id=sample_warehouse.id,
            total_amount=Decimal("100.000"),
            amount=Decimal("100.000"),
            amount_aed=Decimal("100.000"),
            paid_amount=Decimal("0"),
            balance_due=Decimal("100.000"),
            payment_status='unpaid',
            exchange_rate=Decimal('1'),
        )
        db_session.add(sale)
        db_session.commit()

        # Create a sale line so fulfill_sale can process inventory
        from models import SaleLine
        line = SaleLine(
            tenant_id=sample_tenant.id,
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=Decimal('1'),
            unit_price=Decimal('100'),
            line_total=Decimal('100'),
            cost_price=Decimal('50'),
        )
        db_session.add(line)
        db_session.commit()

        # Add stock so fulfillment doesn't fail
        from services.stock_service import StockService
        StockService.add_stock(
            product_id=sample_product.id,
            quantity=Decimal('10'),
            reference_type='test',
            reference_id=1,
            warehouse_id=sample_warehouse.id,
        )
        db_session.commit()

        payment_data = {
            'amount': Decimal('150'),
            'currency': 'AED',
            'payment_method': 'cash',
            'exchange_rate': 1.0,
        }

        with patch('services.sale_service.GLService') as mock_gl:
            mock_gl.ensure_core_accounts = MagicMock()
            mock_gl.get_customer_credit_account.return_value = '1130'
            mock_gl.get_customer_credit_concept.return_value = 'AR'
            mock_gl.get_payment_debit_account.return_value = '1110'
            mock_gl.get_payment_debit_concept.return_value = 'CASH'
            with patch('services.sale_service.post_or_fail'):
                with patch('services.sale_service.StockService.calculate_sale_cogs_and_deduct', return_value=Decimal('50')):
                    SaleService.fulfill_sale(sale, payment_data=payment_data, paid_amount_aed=Decimal('150'))

        db_session.commit()

        # Should have sale_payment for 100 and prepayment for 50
        payments = Payment.query.filter_by(customer_id=sample_customer.id).all()
        sale_payments = [p for p in payments if p.payment_type == 'sale_payment']
        prepayments = [p for p in payments if p.payment_type == 'prepayment']

        assert len(sale_payments) >= 1
        assert len(prepayments) == 1
        assert prepayments[0].amount_aed == Decimal('50.000')

        # Customer balance should reflect the prepayment credit
        # Customer started at 0, sale made them -100 (debt), payment of 100 cancels that,
        # prepayment of 50 makes them +50 (credit)
        db_session.refresh(sample_customer)
        assert sample_customer.balance == Decimal('50')


class TestCancelSaleOrphanChequeFix:
    """
    Fix: sale_service.py cancel_sale was leaving pending payments/cheques orphaned.
    Now it rejects pending payments and cancels their linked cheques.
    """

    def test_cancel_sale_rejects_pending_cheque_payment(self, app, db_session, sample_tenant, sample_customer, sample_user, sample_branch, sample_product, sample_warehouse):
        from services.sale_service import SaleService
        from models import Sale, Payment, Cheque

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="S-CANCEL-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            branch_id=sample_branch.id,
            warehouse_id=sample_warehouse.id,
            total_amount=Decimal("100.000"),
            amount=Decimal("100.000"),
            amount_aed=Decimal("100.000"),
            paid_amount=Decimal("0"),
            balance_due=Decimal("100.000"),
            payment_status='unpaid',
            exchange_rate=Decimal('1'),
        )
        db_session.add(sale)
        db_session.commit()

        # Add a pending cheque payment
        cheque = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number="CHQ-PEND-001",
            cheque_bank_number="BNK-001",
            cheque_type="incoming",
            customer_id=sample_customer.id,
            bank_name="Test Bank",
            amount=Decimal("100.00"),
            amount_aed=Decimal("100.00"),
            issue_date=date.today(),
            due_date=date.today(),
            status="pending",
        )
        db_session.add(cheque)
        db_session.commit()

        payment = Payment(
            tenant_id=sample_tenant.id,
            payment_number="PAY-PEND-001",
            payment_type='sale_payment',
            direction='incoming',
            sale_id=sale.id,
            customer_id=sample_customer.id,
            amount=Decimal("100.000"),
            amount_aed=Decimal("100.000"),
            currency='AED',
            exchange_rate=Decimal('1'),
            payment_method='cheque',
            payment_confirmed=False,
            cheque_id=cheque.id,
        )
        db_session.add(payment)
        db_session.commit()

        # Cancel should reject the payment and cancel the cheque
        with patch('services.sale_service.StockService'):
            with patch('services.sale_service.GLService'):
                SaleService.cancel_sale(sale)

        db_session.refresh(payment)
        db_session.refresh(cheque)

        assert payment.rejection_reason is not None
        assert 'إلغاء فاتورة' in payment.rejection_reason
        assert cheque.status == 'cancelled'

    def test_cancel_sale_blocked_if_confirmed_payment_exists(self, app, db_session, sample_tenant, sample_customer, sample_user, sample_branch, sample_product, sample_warehouse):
        from services.sale_service import SaleService
        from models import Sale, Payment

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="S-CANCEL-002",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            branch_id=sample_branch.id,
            warehouse_id=sample_warehouse.id,
            total_amount=Decimal("100.000"),
            amount=Decimal("100.000"),
            amount_aed=Decimal("100.000"),
            paid_amount=Decimal("100.000"),
            balance_due=Decimal("0"),
            payment_status='paid',
            exchange_rate=Decimal('1'),
        )
        db_session.add(sale)
        db_session.commit()

        payment = Payment(
            tenant_id=sample_tenant.id,
            payment_number="PAY-CONF-001",
            payment_type='sale_payment',
            direction='incoming',
            sale_id=sale.id,
            customer_id=sample_customer.id,
            amount=Decimal("100.000"),
            amount_aed=Decimal("100.000"),
            currency='AED',
            exchange_rate=Decimal('1'),
            payment_method='cash',
            payment_confirmed=True,
        )
        db_session.add(payment)
        db_session.commit()

        with pytest.raises(ValueError, match='لا يمكن إلغاء فاتورة لها دفعات مؤكدة'):
            SaleService.cancel_sale(sale)


class TestRollbackLoggingFix:
    """
    Fix: All db.session.rollback() calls in critical services now have
    current_app.logger.exception() or warning() before them.
    This is a code-quality test ensuring the pattern is present.
    """

    def test_sale_service_rollbacks_have_logging(self, app):
        import inspect
        from services import sale_service
        source = inspect.getsource(sale_service)
        # Simple heuristic: every 'db.session.rollback()' should be preceded by
        # a logger call in the same function block (within ~3 lines above).
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if 'db.session.rollback()' in line:
                preceding = '\n'.join(lines[max(0, i-5):i])
                assert ('logger.exception' in preceding or 'logger.warning' in preceding or 'logger.error' in preceding), (
                    f"Rollback at line {i+1} lacks preceding logging"
                )

    def test_payment_service_rollbacks_have_logging(self, app):
        import inspect
        from services import payment_service
        source = inspect.getsource(payment_service)
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if 'db.session.rollback()' in line:
                preceding = '\n'.join(lines[max(0, i-5):i])
                assert ('logger.exception' in preceding or 'logger.warning' in preceding or 'logger.error' in preceding), (
                    f"Rollback at line {i+1} lacks preceding logging"
                )

    def test_purchase_service_rollbacks_have_logging(self, app):
        import inspect
        from services import purchase_service
        source = inspect.getsource(purchase_service)
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if 'db.session.rollback()' in line:
                preceding = '\n'.join(lines[max(0, i-5):i])
                assert ('logger.exception' in preceding or 'logger.warning' in preceding or 'logger.error' in preceding), (
                    f"Rollback at line {i+1} lacks preceding logging"
                )
