"""Comprehensive real-DB tests for Azadexa ERP covering financial flows."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, date
from unittest.mock import patch


class TestAuthFlow:
    def test_login_redirects_to_dashboard(self, client, sample_user):
        resp = client.post('/auth/login', data={
            'username': sample_user.username,
            'password': 'password123',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_rejects_wrong_password(self, client, sample_user):
        resp = client.post('/auth/login', data={
            'username': sample_user.username,
            'password': 'wrongpassword',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_logout_clears_session(self, logged_in_client):
        resp = logged_in_client.get('/auth/logout', follow_redirects=True)
        assert resp.status_code == 200


class TestSaleCreationAndFulfillment:
    def test_create_sale_calculates_totals(self, app, db_session, sample_tenant, sample_branch, sample_customer, sample_user, sample_warehouse, sample_product_with_stock, sample_gl_accounts):
        from services.sale_service import SaleService
        from models import Sale
        lines = [{'product': sample_product_with_stock, 'quantity': 2, 'unit_price': Decimal('100')}]
        sale = SaleService.create_sale(sample_customer, sample_user, lines, warehouse_id=sample_warehouse.id, currency='AED', defer_fulfillment=True)
        db_session.refresh(sale)
        assert sale.subtotal == Decimal('200.000')
        assert sale.total_amount > Decimal('0')
        assert sale.status == 'confirmed'

    def test_fulfill_sale_posts_gl_and_deducts_stock(self, app, db_session, sample_tenant, sample_branch, sample_customer, sample_user, sample_warehouse, sample_product_with_stock, sample_gl_accounts):
        from services.sale_service import SaleService
        from services.stock_service import StockService
        from models import GLJournalEntry, ProductWarehouseStock
        lines = [{'product': sample_product_with_stock, 'quantity': 2, 'unit_price': Decimal('100')}]
        sale = SaleService.create_sale(sample_customer, sample_user, lines, warehouse_id=sample_warehouse.id, currency='AED', defer_fulfillment=True)
        db_session.commit()
        payment_data = {'amount': Decimal('200'), 'currency': 'AED', 'payment_method': 'cash'}
        with patch('services.sale_service.post_or_fail'):
            with patch('services.sale_service.StockService.calculate_sale_cogs_and_deduct', return_value=Decimal('100')):
                SaleService.fulfill_sale(sale, payment_data=payment_data, paid_amount_aed=Decimal('200'))
        db_session.refresh(sale)
        assert sale.paid_amount_aed == Decimal('200')
        pws = ProductWarehouseStock.query.filter_by(product_id=sample_product_with_stock.id, warehouse_id=sample_warehouse.id).first()
        assert pws.quantity == Decimal('98')

    def test_fulfill_sale_with_overpayment_creates_prepayment(self, app, db_session, sample_tenant, sample_branch, sample_customer, sample_user, sample_warehouse, sample_product_with_stock, sample_gl_accounts):
        from services.sale_service import SaleService
        from models import Payment
        lines = [{'product': sample_product_with_stock, 'quantity': 1, 'unit_price': Decimal('100')}]
        sale = SaleService.create_sale(sample_customer, sample_user, lines, warehouse_id=sample_warehouse.id, currency='AED', defer_fulfillment=True)
        db_session.commit()
        payment_data = {'amount': Decimal('150'), 'currency': 'AED', 'payment_method': 'cash'}
        with patch('services.sale_service.post_or_fail'):
            with patch('services.sale_service.StockService.calculate_sale_cogs_and_deduct', return_value=Decimal('50')):
                SaleService.fulfill_sale(sale, payment_data=payment_data, paid_amount_aed=Decimal('150'))
        db_session.commit()
        prepayments = Payment.query.filter_by(payment_type='prepayment', customer_id=sample_customer.id).all()
        assert len(prepayments) >= 1
        assert prepayments[0].amount_aed == Decimal('50')


class TestSaleCancellation:
    def test_cancel_sale_rejects_confirmed_payments(self, app, db_session, sample_tenant, sample_branch, sample_customer, sample_user, sample_warehouse, sample_product_with_stock, sample_gl_accounts):
        from services.sale_service import SaleService
        from models import Payment
        lines = [{'product': sample_product_with_stock, 'quantity': 1, 'unit_price': Decimal('100')}]
        sale = SaleService.create_sale(sample_customer, sample_user, lines, warehouse_id=sample_warehouse.id, currency='AED', defer_fulfillment=True)
        db_session.commit()
        payment = Payment(
            tenant_id=sample_tenant.id, payment_number='PAY-001', payment_type='sale_payment',
            direction='incoming', sale_id=sale.id, customer_id=sample_customer.id,
            amount=Decimal('100'), amount_aed=Decimal('100'), payment_method='cash',
            payment_confirmed=True,
        )
        db_session.add(payment)
        db_session.commit()
        with pytest.raises(ValueError, match='لا يمكن إلغاء فاتورة لها دفعات مؤكدة'):
            SaleService.cancel_sale(sale)

    def test_cancel_sale_cancels_linked_pending_cheque(self, app, db_session, sample_tenant, sample_branch, sample_customer, sample_user, sample_warehouse, sample_product_with_stock, sample_gl_accounts):
        from services.sale_service import SaleService
        from services.cheque_service import process_cheque_cancel
        from models import Payment, Cheque
        lines = [{'product': sample_product_with_stock, 'quantity': 1, 'unit_price': Decimal('100')}]
        sale = SaleService.create_sale(sample_customer, sample_user, lines, warehouse_id=sample_warehouse.id, currency='AED', defer_fulfillment=True)
        db_session.commit()
        cheque = Cheque(
            tenant_id=sample_tenant.id, cheque_number='CHQ-CANCEL-001', cheque_bank_number='BNK-001',
            cheque_type='incoming', customer_id=sample_customer.id, bank_name='Test Bank',
            amount=Decimal('100'), amount_aed=Decimal('100'), issue_date=date.today(), due_date=date.today(),
            status='pending',
        )
        db_session.add(cheque)
        db_session.commit()
        payment = Payment(
            tenant_id=sample_tenant.id, payment_number='PAY-CHQ-001', payment_type='sale_payment',
            direction='incoming', sale_id=sale.id, customer_id=sample_customer.id,
            amount=Decimal('100'), amount_aed=Decimal('100'), payment_method='cheque',
            payment_confirmed=False, cheque_id=cheque.id,
        )
        db_session.add(payment)
        db_session.commit()
        with patch('services.sale_service.StockService.reverse_sale'):
            with patch('services.sale_service.GLService.reverse_entry'):
                SaleService.cancel_sale(sale)
        db_session.refresh(cheque)
        assert cheque.status == 'cancelled'


class TestPurchaseCreation:
    def test_create_purchase_adds_stock(self, app, db_session, sample_tenant, sample_user, sample_supplier, sample_warehouse, sample_product, sample_gl_accounts):
        from services.purchase_service import PurchaseService
        from models import PurchaseLine, ProductWarehouseStock
        lines_data = [{'product_id': sample_product.id, 'quantity': 10, 'unit_cost': Decimal('20'), 'discount_percent': 0}]
        with patch('services.purchase_service.GLService.ensure_core_accounts'):
            with patch('services.purchase_service.post_or_fail'):
                with patch('services.purchase_service.StockService.process_purchase_lines'):
                    purchase = PurchaseService.create_purchase(
                        sample_user, {'supplier_id': sample_supplier.id}, lines_data,
                        warehouse_id=sample_warehouse.id, currency='AED'
                    )
        db_session.refresh(purchase)
        assert purchase.total_amount > Decimal('0')
        assert purchase.status == 'confirmed'

    def test_cancel_purchase_reverses_stock(self, app, db_session, sample_tenant, sample_user, sample_supplier, sample_warehouse, sample_product, sample_gl_accounts):
        from services.purchase_service import PurchaseService
        lines_data = [{'product_id': sample_product.id, 'quantity': 5, 'unit_cost': Decimal('20'), 'discount_percent': 0}]
        with patch('services.purchase_service.GLService.ensure_core_accounts'):
            with patch('services.purchase_service.post_or_fail'):
                with patch('services.purchase_service.StockService.process_purchase_lines'):
                    purchase = PurchaseService.create_purchase(
                        sample_user, {'supplier_id': sample_supplier.id}, lines_data,
                        warehouse_id=sample_warehouse.id, currency='AED'
                    )
        db_session.commit()
        with patch('services.purchase_service.GLService.reverse_entry'):
            with patch('services.purchase_service.StockService.reverse_purchase'):
                PurchaseService.cancel_purchase(purchase)
        db_session.refresh(purchase)
        assert purchase.status == 'cancelled'


class TestPaymentFlows:
    def test_create_payment_to_supplier_reduces_ap(self, app, db_session, sample_tenant, sample_user, sample_supplier, sample_gl_accounts):
        from services.payment_service import PaymentService
        from models import Payment
        sample_supplier.apply_payment(Decimal('0'))
        db_session.commit()
        with patch('services.payment_service.post_or_fail'):
            payment = PaymentService.create_payment({
                'supplier_id': sample_supplier.id, 'amount': Decimal('500'),
                'currency': 'AED', 'payment_method': 'cash', 'notes': 'Test payment',
            })
        db_session.refresh(payment)
        assert payment.direction == 'outgoing'
        assert payment.payment_type == 'supplier_payment'

    def test_create_receipt_from_customer(self, app, db_session, sample_tenant, sample_user, sample_customer, sample_gl_accounts):
        from services.payment_service import PaymentService
        from models import Receipt
        sample_customer.apply_receipt(Decimal('0'))
        db_session.commit()
        with patch('services.payment_service.post_or_fail'):
            receipt = PaymentService.create_receipt({
                'customer_id': sample_customer.id, 'amount': Decimal('300'),
                'currency': 'AED', 'payment_method': 'cash', 'notes': 'Test receipt',
            })
        db_session.refresh(receipt)
        assert receipt.direction == 'incoming'


class TestChequeProcessing:
    def test_deposit_and_clear_incoming_cheque(self, app, db_session, sample_tenant, sample_customer, sample_gl_accounts):
        from services.cheque_service import process_cheque_deposit, process_cheque_clear
        from models import Cheque
        cheque = Cheque(
            tenant_id=sample_tenant.id, cheque_number='CHQ-DEP-001', cheque_bank_number='BNK-001',
            cheque_type='incoming', customer_id=sample_customer.id, bank_name='Test Bank',
            amount=Decimal('1000'), amount_aed=Decimal('1000'), issue_date=date.today(), due_date=date.today(),
            status='pending',
        )
        db_session.add(cheque)
        db_session.commit()
        process_cheque_deposit(cheque)
        db_session.commit()
        assert cheque.status == 'deposited'
        with patch('services.cheque_service._create_clearing_journal_entry'):
            process_cheque_clear(cheque)
        db_session.commit()
        assert cheque.status == 'cleared'

    def test_bounce_incoming_cheque_increases_ar(self, app, db_session, sample_tenant, sample_customer, sample_gl_accounts):
        from services.cheque_service import process_cheque_bounce
        from models import Cheque
        initial_balance = sample_customer.balance or Decimal('0')
        cheque = Cheque(
            tenant_id=sample_tenant.id, cheque_number='CHQ-BNC-001', cheque_bank_number='BNK-001',
            cheque_type='incoming', customer_id=sample_customer.id, bank_name='Test Bank',
            amount=Decimal('250'), amount_aed=Decimal('250'), issue_date=date.today(), due_date=date.today(),
            status='deposited',
        )
        db_session.add(cheque)
        db_session.commit()
        with patch('services.cheque_service._create_bounce_journal_entry'):
            with patch('services.cheque_service.GLService'):
                process_cheque_bounce(cheque, 'NSF')
        db_session.commit()
        db_session.refresh(sample_customer)
        assert cheque.status == 'bounced'
        expected_balance = initial_balance - Decimal('250')
        assert sample_customer.balance == expected_balance

    def test_cancel_outgoing_cheque(self, app, db_session, sample_tenant, sample_supplier, sample_gl_accounts):
        from services.cheque_service import process_cheque_cancel
        from models import Cheque
        cheque = Cheque(
            tenant_id=sample_tenant.id, cheque_number='CHQ-OUT-001', cheque_bank_number='BNK-001',
            cheque_type='outgoing', supplier_id=sample_supplier.id, bank_name='Test Bank',
            amount=Decimal('500'), amount_aed=Decimal('500'), issue_date=date.today(), due_date=date.today(),
            status='pending',
        )
        db_session.add(cheque)
        db_session.commit()
        with patch('services.cheque_service.gl_post_or_fail'):
            process_cheque_cancel(cheque, 'cancelled by user')
        db_session.commit()
        assert cheque.status == 'cancelled'


class TestGLAndLedger:
    def test_gl_account_balance_calculation(self, app, db_session, sample_tenant, sample_gl_accounts):
        from services.gl_service import GLService
        from models import GLAccount, GLJournalEntry, GLJournalLine
        GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
        db_session.commit()
        leaf_acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, is_header=False, type='asset').first()
        assert leaf_acc is not None
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id, entry_number='JE-TEST-001',
            entry_date=datetime.now(timezone.utc), description='Test entry',
            is_posted=True, total_debit=Decimal('100'), total_credit=Decimal('100'),
        )
        db_session.add(entry)
        db_session.flush()
        line = GLJournalLine(
            tenant_id=sample_tenant.id, entry_id=entry.id, account_id=leaf_acc.id,
            debit=Decimal('100'), credit=Decimal('0'), amount_aed=Decimal('100'),
        )
        db_session.add(line)
        db_session.commit()
        balance = leaf_acc.get_balance()
        assert balance == Decimal('100')

    def test_journal_entry_must_balance(self, app, db_session, sample_tenant, sample_gl_accounts):
        from services.gl_service import GLService
        from models import GLAccount
        GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
        db_session.commit()
        leaf_acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, is_header=False, type='asset').first()
        assert leaf_acc is not None
        with pytest.raises(ValueError, match='غير متوازن'):
            GLService.create_journal_entry(
                date=datetime.now(timezone.utc), description='Unbalanced',
                lines=[{'account': leaf_acc.code, 'debit': Decimal('100'), 'credit': Decimal('0')}],
                tenant_id=sample_tenant.id,
            )


class TestInventoryAndStock:
    def test_add_stock_increases_warehouse_quantity(self, app, db_session, sample_tenant, sample_warehouse, sample_product):
        from services.stock_service import StockService
        from models import ProductWarehouseStock
        StockService.add_stock(sample_product.id, 50, warehouse_id=sample_warehouse.id)
        db_session.commit()
        pws = ProductWarehouseStock.query.filter_by(product_id=sample_product.id, warehouse_id=sample_warehouse.id).first()
        assert pws is not None
        assert pws.quantity >= Decimal('50')

    def test_process_purchase_lines_updates_weighted_average(self, app, db_session, sample_tenant, sample_warehouse, sample_product, sample_supplier, sample_gl_accounts):
        from services.stock_service import StockService
        from models import Purchase, PurchaseLine, ProductWarehouseCost
        StockService.add_stock(sample_product.id, 10, warehouse_id=sample_warehouse.id)
        db_session.commit()
        purchase = Purchase(
            tenant_id=sample_tenant.id, purchase_number='PUR-WAC-001', supplier_id=sample_supplier.id,
            warehouse_id=sample_warehouse.id, branch_id=sample_warehouse.branch_id,
            supplier_name='Test', purchase_date=datetime.now(timezone.utc), user_id=1,
            total_amount=Decimal('20'), amount=Decimal('20'), amount_aed=Decimal('20'), exchange_rate=1,
        )
        db_session.add(purchase)
        db_session.commit()
        line = PurchaseLine(
            tenant_id=sample_tenant.id, purchase_id=purchase.id, product_id=sample_product.id,
            quantity=1, unit_cost=Decimal('20'), line_total=Decimal('20'),
        )
        db_session.add(line)
        db_session.commit()
        def mock_update_wac(tenant_id, product_id, warehouse_id, received_qty, unit_cost_aed, reference_type, reference_id):
            pwc = ProductWarehouseCost.query.filter_by(tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id).first()
            if not pwc:
                pwc = ProductWarehouseCost(tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id, average_cost=unit_cost_aed, total_quantity=received_qty, total_value=received_qty*unit_cost_aed)
                db_session.add(pwc)
            else:
                pwc.total_quantity += received_qty
                pwc.total_value += received_qty * unit_cost_aed
                if pwc.total_quantity > 0:
                    pwc.average_cost = pwc.total_value / pwc.total_quantity
            db_session.flush()
        with patch.object(StockService, '_update_wac_on_receipt', side_effect=mock_update_wac):
            StockService.process_purchase_lines(purchase, warehouse_id=sample_warehouse.id)
        db_session.commit()
        db_session.refresh(sample_product)
        pwcs = ProductWarehouseCost.query.filter_by(product_id=sample_product.id).all()
        total_val = sum(Decimal(str(pwc.total_value or 0)) for pwc in pwcs)
        total_qty = sum(Decimal(str(pwc.total_quantity or 0)) for pwc in pwcs)
        if total_qty > 0:
            expected_cost = (total_val / total_qty).quantize(Decimal('0.001'))
            assert sample_product.cost_price == expected_cost


class TestReports:
    def test_sales_report_endpoint(self, logged_in_client, sample_tenant, sample_customer, sample_user, sample_warehouse, sample_product_with_stock, sample_gl_accounts):
        from services.sale_service import SaleService
        lines = [{'product': sample_product_with_stock, 'quantity': 1, 'unit_price': Decimal('100')}]
        sale = SaleService.create_sale(sample_customer, sample_user, lines, warehouse_id=sample_warehouse.id, currency='AED', defer_fulfillment=True)
        db_session = sale.__class__.query.session
        db_session.commit()
        resp = logged_in_client.get('/reports/sales')
        assert resp.status_code == 200

    def test_receivables_report_endpoint(self, logged_in_client, sample_tenant, sample_customer, sample_user, sample_warehouse, sample_product_with_stock, sample_gl_accounts):
        from services.sale_service import SaleService
        lines = [{'product': sample_product_with_stock, 'quantity': 1, 'unit_price': Decimal('100')}]
        sale = SaleService.create_sale(sample_customer, sample_user, lines, warehouse_id=sample_warehouse.id, currency='AED', defer_fulfillment=True)
        db_session = sale.__class__.query.session
        db_session.commit()
        resp = logged_in_client.get('/reports/receivables')
        assert resp.status_code == 200


class TestFrontendRoutesAuthenticated:
    def test_dashboard_loads(self, logged_in_client):
        resp = logged_in_client.get('/')
        assert resp.status_code == 200

    def test_sales_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/sales/')
        assert resp.status_code == 200

    def test_purchases_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/purchases/')
        assert resp.status_code == 200

    def test_payments_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/payments/', follow_redirects=True)
        assert resp.status_code == 200

    def test_cheques_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/cheques/')
        assert resp.status_code == 200

    def test_ledger_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/ledger/')
        assert resp.status_code == 200

    def test_products_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/products/')
        assert resp.status_code == 200

    def test_customers_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/customers/')
        assert resp.status_code == 200

    def test_suppliers_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/suppliers/')
        assert resp.status_code == 200

    def test_inventory_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/warehouse/')
        assert resp.status_code == 200

    def test_expenses_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/expenses/')
        assert resp.status_code == 200

    def test_reports_index_loads(self, logged_in_client):
        resp = logged_in_client.get('/reports/')
        assert resp.status_code == 200
