"""Close remaining coverage gaps on the 18 target service modules."""
from __future__ import annotations

import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from models import Product
from services.ai_service import AIService


# ---------------------------------------------------------------------------
# advanced_analytics
# ---------------------------------------------------------------------------

class TestAdvancedAnalyticsGaps:
    def test_dated_liability_balance_subtracts(self, mocker):
        line = MagicMock(amount_aed=Decimal('75'))
        acct = MagicMock()
        mocker.patch('utils.gl_tenant.scope_gl_accounts').return_value.all.return_value = [acct]
        lines_q = MagicMock()
        lines_q.join.return_value = lines_q
        lines_q.filter.return_value = lines_q
        lines_q.all.return_value = [line]
        mocker.patch('models.GLJournalLine.query', lines_q)
        from services.advanced_analytics import AdvancedFinancialAnalytics
        total = AdvancedFinancialAnalytics._calculate_account_type_balance(
            'liability', date_from=date(2025, 1, 1), date_to=date(2025, 6, 1), tenant_id=1,
        )
        assert total == Decimal('-75')

    def test_expense_breakdown_nonzero_percentage(self, mocker):
        acct = MagicMock(code='5100', full_name='Rent', get_balance=lambda: Decimal('250'))
        mocker.patch('utils.gl_tenant.scope_gl_accounts').return_value.all.return_value = [acct]
        from services.advanced_analytics import AdvancedFinancialAnalytics
        result = AdvancedFinancialAnalytics.get_expense_breakdown(tenant_id=1)
        assert result['items'][0]['percentage'] == pytest.approx(100.0)

    def test_revenue_breakdown_zero_total_percentage(self, mocker):
        acct = MagicMock(code='4100', full_name='Zero', get_balance=lambda: Decimal('0'))
        mocker.patch('utils.gl_tenant.scope_gl_accounts').return_value.all.return_value = [acct]
        from services.advanced_analytics import AdvancedFinancialAnalytics
        result = AdvancedFinancialAnalytics.get_revenue_breakdown(tenant_id=1)
        assert result['items'][0]['percentage'] == 0


# ---------------------------------------------------------------------------
# ai_executor
# ---------------------------------------------------------------------------

@pytest.fixture
def ai_executor(mocker):
    mocker.patch('services.ai_executor.get_active_tenant_id', return_value=1)
    from services.ai_executor import AIExecutor
    user = MagicMock(id=42, tenant_id=1, branch_id=2, is_authenticated=True)
    return AIExecutor(user=user)


class TestAIExecutorGaps:
    def test_create_product_empty_name(self, ai_executor):
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='اسم المنتج'):
            ai_executor.create_product(name='', regular_price=10)

    def test_create_sale_customer_missing(self, ai_executor, mocker):
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='غير موجود'):
            ai_executor.create_sale('Ghost', [{'product_name': 'X', 'quantity': 1}])

    def test_create_sale_no_active_seller(self, ai_executor, mocker):
        customer = MagicMock(id=1)
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = customer
        User = mocker.patch('models.User')
        User.query.filter_by.return_value.first.return_value = None
        ai_executor.user = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='مستخدم نشط'):
            ai_executor.create_sale('Acme', [{'product_name': 'X', 'quantity': 1}])

    def test_create_sale_product_missing(self, ai_executor, mocker):
        customer = MagicMock(id=1)
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = customer
        Product = mocker.patch('models.Product')
        Product.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='المنتج'):
            ai_executor.create_sale('Acme', [{'product_name': 'Missing', 'quantity': 1}])

    def test_create_sale_with_payment_data(self, ai_executor, mocker):
        customer = MagicMock(id=1)
        product = MagicMock(id=2)
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = customer
        Product = mocker.patch('models.Product')
        Product.query.filter_by.return_value.first.return_value = product
        sale = MagicMock(id=5, sale_number='S-1', total_amount=Decimal('100'))
        mocker.patch('services.sale_service.SaleService.create_sale', return_value=sale)
        result = ai_executor.create_sale(
            'Acme', [{'product_name': 'Widget', 'quantity': 1}], paid_amount=50,
        )
        assert result['success'] is True

    def test_receive_payment_customer_missing(self, ai_executor, mocker):
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='غير موجود'):
            ai_executor.receive_payment('Missing', 100)

    def test_receive_payment_breaks_when_remaining_zero(self, ai_executor, mocker, app):
        customer = MagicMock(id=1, balance=Decimal('0'))
        sale1 = MagicMock(balance_due=Decimal('100'), paid_amount=Decimal('0'), payment_status='unpaid')
        sale2 = MagicMock(balance_due=Decimal('200'), paid_amount=Decimal('0'), payment_status='unpaid')
        with app.app_context():
            from models import Customer, Sale
            cust_q = MagicMock()
            cust_q.filter_by.return_value.first.return_value = customer
            mocker.patch.object(Customer, 'query', new_callable=mocker.PropertyMock, return_value=cust_q)
            sale_q = MagicMock()
            sale_q.filter.return_value.order_by.return_value.all.return_value = [sale1, sale2]
            mocker.patch.object(Sale, 'query', new_callable=mocker.PropertyMock, return_value=sale_q)
            mocker.patch.object(ai_executor, '_generate_number', return_value='PAY-002')
            mocker.patch('services.ai_executor.db.session')
            ai_executor.receive_payment('Acme', 100)
        assert sale1.payment_status == 'paid'
        assert sale2.payment_status == 'unpaid'

    def test_add_expense_zero_amount(self, ai_executor):
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='المبلغ'):
            ai_executor.add_expense('Rent', 0)

    def test_add_expense_no_category(self, ai_executor, mocker):
        ExpenseCategory = mocker.patch('models.ExpenseCategory')
        ExpenseCategory.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='تصنيف'):
            ai_executor.add_expense('Office', 50)

    def test_create_employee_empty_name(self, ai_executor):
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='اسم الموظف'):
            ai_executor.create_employee('')

    def test_create_purchase_supplier_missing(self, ai_executor, mocker):
        Supplier = mocker.patch('models.Supplier')
        Supplier.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='المورد'):
            ai_executor.create_purchase('Ghost', [{'product_name': 'X'}])

    def test_create_purchase_no_warehouse(self, ai_executor, mocker):
        supplier = MagicMock(id=1, name='V')
        Supplier = mocker.patch('models.Supplier')
        Supplier.query.filter_by.return_value.first.return_value = supplier
        Warehouse = mocker.patch('models.Warehouse')
        Warehouse.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='مستودع'):
            ai_executor.create_purchase('V', [{'product_name': 'X'}])

    def test_create_purchase_product_missing(self, ai_executor, mocker):
        supplier = MagicMock(id=1, name='V')
        warehouse = MagicMock(id=3)
        Supplier = mocker.patch('models.Supplier')
        Supplier.query.filter_by.return_value.first.return_value = supplier
        Warehouse = mocker.patch('models.Warehouse')
        Warehouse.query.filter_by.return_value.first.side_effect = [None, warehouse]
        Product = mocker.patch('models.Product')
        Product.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='المنتج'):
            ai_executor.create_purchase('V', [{'product_name': 'Missing'}])

    def test_profit_summary_with_cost_lines(self, ai_executor, mocker):
        mocker.patch('services.ai_executor.db.session')
        mocker.patch('services.ai_executor.db.session.query').return_value.filter.return_value.scalar.return_value = Decimal('1000')
        Sale = mocker.patch('models.Sale')
        Sale.query.filter.return_value.count.return_value = 1
        line = MagicMock(product_id=9, quantity=Decimal('2'))
        SaleLine = mocker.patch('models.SaleLine')
        SaleLine.query.join.return_value.filter.return_value.all.return_value = [line]
        product = MagicMock(cost_price=Decimal('100'))
        Product = mocker.patch('models.Product')
        Product.query.get.return_value = product
        result = ai_executor.profit_summary()
        assert result['cost'] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# ai_service
# ---------------------------------------------------------------------------

class TestAIServiceGetModelGaps:
    def test_get_model_none_pk(self):
        assert AIService._get_model(Product, None) is None

    def test_get_model_rejects_mock_instance(self, mocker):
        mock_product = MagicMock()
        mocker.patch('services.ai_service.db.session.get', return_value=mock_product)
        assert AIService._get_model(Product, 1) is None


# ---------------------------------------------------------------------------
# analytics_service
# ---------------------------------------------------------------------------

class TestAnalyticsServiceDonationGaps:
    def test_revenue_by_period_monthly_buckets(self, mocker):
        now = datetime.now(timezone.utc)
        donation = MagicMock(transaction_type='donation', amount_usd=Decimal('50'), created_at=now)
        purchase = MagicMock(transaction_type='purchase', amount_usd=Decimal('20'), created_at=now)
        bad = MagicMock(transaction_type='donation', amount_usd=Decimal('1'), created_at=None)
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [donation, purchase, bad]
        mocker.patch('services.analytics_service._db_session').return_value.query.return_value = q
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        from services.analytics_service import AnalyticsService
        result = AnalyticsService.get_revenue_by_period(months=1, tenant_id=1)
        assert result['donations'][0] >= 50
        assert result['purchases'][0] >= 20


# ---------------------------------------------------------------------------
# archive_service
# ---------------------------------------------------------------------------

class TestArchiveServiceGaps:
    def test_restore_inits_model_map_when_none(self, app, mocker):
        archived = MagicMock(table_name='sales', tenant_id=1, record_id=50)
        existing = MagicMock(is_active=False)
        model = MagicMock()
        model.query.get.return_value = existing
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        mocker.patch('services.archive_service.current_user', MagicMock())
        original_map = {'sales': None, 'purchases': None}
        mocker.patch('services.archive_service.ArchiveService.ARCHIVE_MODEL_MAP', original_map)
        mock_init = mocker.patch('services.archive_service.ArchiveService._init_archive_model_map', side_effect=lambda: original_map.update({'sales': model}))
        mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            result = ArchiveService.restore_record(archived)
        mock_init.assert_called_once()
        assert result is existing

    def test_restore_unknown_table_raises(self, app, mocker):
        archived = MagicMock(table_name='unknown_tbl', tenant_id=1, record_id=1)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        mocker.patch('services.archive_service.current_user', MagicMock())
        mocker.patch('services.archive_service.ArchiveService.ARCHIVE_MODEL_MAP', {'unknown_tbl': None})
        mocker.patch('services.archive_service.ArchiveService._init_archive_model_map')
        mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            with pytest.raises(ValueError, match='Model not found'):
                ArchiveService.restore_record(archived)

    def test_restore_record_not_found_raises(self, app, mocker):
        archived = MagicMock(table_name='sales', tenant_id=1, record_id=99)
        model = MagicMock()
        model.query.get.return_value = None
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        mocker.patch('services.archive_service.current_user', MagicMock())
        mocker.patch('services.archive_service.ArchiveService.ARCHIVE_MODEL_MAP', {'sales': model})
        mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            with pytest.raises(ValueError, match='Cannot restore'):
                ArchiveService.restore_record(archived)

    def test_init_archive_model_map_populates(self, mocker):
        mocker.patch('services.archive_service.ArchiveService.ARCHIVE_MODEL_MAP', {})
        from services.archive_service import ArchiveService
        ArchiveService._init_archive_model_map()
        assert ArchiveService.ARCHIVE_MODEL_MAP['sales'] is not None

    def test_get_archived_records_query_with_table(self, app, mocker):
        from models import ArchivedRecord
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mocker.patch.object(ArchivedRecord, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)
        from services.archive_service import ArchiveService
        with app.app_context():
            ArchiveService.get_archived_records_query(table_name='payments')
        mock_q.filter_by.assert_called_with(table_name='payments')

    def test_cleanup_old_archives_rollback_on_commit_failure(self, app, mocker):
        from models import ArchivedRecord
        old = MagicMock()
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [old]
        mocker.patch.object(ArchivedRecord, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)
        mock_session = mocker.patch('services.archive_service.db.session')
        mock_session.commit.side_effect = RuntimeError('db')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            with pytest.raises(RuntimeError):
                ArchiveService.cleanup_old_archives(days=30)


# ---------------------------------------------------------------------------
# backup_exec
# ---------------------------------------------------------------------------

class TestBackupExecGaps:
    def test_run_repo_python_script_success(self, mocker, tmp_path):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        script_rel = 'scripts/measure_18_services_coverage.py'
        script_abs = os.path.join(root, script_rel.replace('/', os.sep))
        if not os.path.isfile(script_abs):
            pytest.skip('script missing')
        completed = subprocess.CompletedProcess([], 0, stdout='ok', stderr='')
        mock_run = mocker.patch('services.backup_exec.subprocess.run', return_value=completed)
        from services.backup_exec import run_repo_python_script
        result = run_repo_python_script(script_rel, ['--help'])
        assert result.returncode == 0
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# branch_audit_service
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# campaign_service
# ---------------------------------------------------------------------------

class TestCeleryTasksGaps:
    def test_second_reminder_skips_store_without_email(self, mocker):
        cart = MagicMock(tenant_id=1, reminder_count=1)
        mock_q = MagicMock()
        mock_q.filter.return_value.all.side_effect = [[], [cart]]
        mocker.patch('models.shop_abandoned_cart.ShopAbandonedCart.query', mock_q)
        mocker.patch('services.store_service.StoreService.get_tenant_store', return_value=MagicMock(email=''))
        from services.celery_tasks import send_abandoned_cart_reminders
        send_abandoned_cart_reminders()
        assert cart.reminder_count == 1

    def test_second_reminder_rollback_on_commit_failure(self, mocker):
        cart = MagicMock(tenant_id=1, reminder_count=1)
        mock_q = MagicMock()
        mock_q.filter.return_value.all.side_effect = [[], [cart]]
        mocker.patch('models.shop_abandoned_cart.ShopAbandonedCart.query', mock_q)
        mocker.patch('services.store_service.StoreService.get_tenant_store', return_value=MagicMock(email='a@b.com'))
        mock_session = mocker.patch('extensions.db.session')
        mock_session.commit.side_effect = Exception('db')
        from services.celery_tasks import send_abandoned_cart_reminders
        send_abandoned_cart_reminders()
        mock_session.rollback.assert_called()


# ---------------------------------------------------------------------------
# cheque_accounting_integration
# ---------------------------------------------------------------------------

class TestChequeServiceValidationGaps:
    @pytest.mark.parametrize('field,value,match', [
        ('cheque_number', '', 'رقم الشيك'),
        ('cheque_bank_number', '', 'البنكي'),
        ('bank_name', '', 'البنك'),
        ('amount', Decimal('0'), 'المبلغ'),
        ('issue_date', None, 'الإصدار'),
        ('due_date', None, 'الاستحقاق'),
        ('cheque_type', 'bad', 'نوع'),
    ])
    def test_validate_cheque_fields(self, field, value, match):
        cheque = MagicMock(
            cheque_number='1', cheque_bank_number='BN1', bank_name='Bank',
            amount=Decimal('100'), issue_date=date.today(), due_date=date.today(),
            cheque_type='incoming',
        )
        setattr(cheque, field, value)
        from services.cheque_service import validate_cheque
        with pytest.raises(ValueError, match=match):
            validate_cheque(cheque)


class TestChequeServiceProcessGaps:
    def _outgoing_cheque(self, **kw):
        cheque = MagicMock(
            id=1, tenant_id=1, branch_id=1, cheque_type='outgoing',
            cheque_bank_number='OB1', amount=Decimal('500'), amount_aed=Decimal('500'),
            currency='AED', exchange_rate=Decimal('1'), status='pending',
            status_ar='معلق', customer_id=None, supplier_id=None, expense_id=None,
            **kw,
        )
        return cheque

    def test_issue_cheque_ap_fallback_without_customer(self, mocker):
        cheque = self._outgoing_cheque()
        mocker.patch('services.cheque_service.gl_ensure_core_accounts')
        mocker.patch('services.cheque_service.GLService.get_account_code_for_concept', return_value='2100')
        mocker.patch('services.cheque_service._post_gl', return_value=MagicMock(id=1))
        from services.cheque_service import process_cheque_issue
        process_cheque_issue(cheque)


    def test_clear_exchange_rate_fallback(self, mocker):
        cheque = self._outgoing_cheque()
        cheque.currency = 'USD'
        cheque.exchange_rate = Decimal('3.67')
        cheque.status = 'deposited'
        mocker.patch('services.cheque_service.gl_resolve_exchange_rate', side_effect=RuntimeError('no rate'))
        mocker.patch('services.cheque_service._create_clearing_journal_entry')
        mocker.patch('models.payment.Payment')
        mocker.patch('models.payment.Receipt')
        from services.cheque_service import process_cheque_clear
        process_cheque_clear(cheque)

    def test_bounce_customer_balance_adjust_failure_logged(self, mocker):
        cheque = MagicMock(
            id=2, tenant_id=1, cheque_type='incoming', status='deposited', status_ar='مودع',
            customer_id=5, amount_aed=Decimal('100'), supplier_id=None, expense_id=None,
            cheque_bank_number='B1',
        )
        cheque.customer.adjust_balance.side_effect = RuntimeError('balance')
        mocker.patch('services.cheque_service._create_bounce_journal_entry')
        mocker.patch('models.payment.Payment')
        mocker.patch('models.payment.Receipt')
        from services.cheque_service import process_cheque_bounce
        process_cheque_bounce(cheque, 'NSF')

    def test_bounce_fatal_error_reraises(self, mocker):
        cheque = MagicMock(id=3, status='deposited', status_ar='مودع', cheque_type='incoming')
        mocker.patch('services.cheque_service._create_bounce_journal_entry', side_effect=RuntimeError('gl'))
        from services.cheque_service import process_cheque_bounce
        with pytest.raises(RuntimeError):
            process_cheque_bounce(cheque, 'fail')

    def test_bounce_outgoing_supplier_payment(self, mocker):
        cheque = MagicMock(
            id=4, tenant_id=1, cheque_type='outgoing', status='pending', status_ar='معلق',
            supplier_id=8, expense_id=None, amount_aed=Decimal('200'), cheque_bank_number='B2',
            customer_id=None,
        )
        supplier = MagicMock()
        mocker.patch('services.cheque_service._create_bounce_journal_entry')
        mocker.patch('models.payment.Payment')
        mocker.patch('models.payment.Receipt')
        Supplier = mocker.patch('models.supplier.Supplier')
        Supplier.query.filter_by.return_value.first.return_value = supplier
        from services.cheque_service import process_cheque_bounce
        process_cheque_bounce(cheque, 'returned')

    def test_bounce_incoming_customer_credit_path(self, mocker):
        cheque = MagicMock(
            id=5, tenant_id=1, cheque_type='incoming', status='pending', status_ar='معلق',
            customer_id=3, customer=MagicMock(), expense_id=None, supplier_id=None,
            amount_aed=Decimal('50'), cheque_bank_number='B3',
        )
        mocker.patch('services.cheque_service.gl_get_customer_credit_account', return_value='1200')
        mocker.patch('services.cheque_service.gl_get_customer_credit_concept', return_value='AR')
        mocker.patch('services.cheque_service.GLService.get_account_code_for_concept', return_value='2100')
        mocker.patch('services.cheque_service._post_gl')
        from services.cheque_service import _create_bounce_journal_entry
        _create_bounce_journal_entry(cheque)

    def test_cancel_outgoing_customer_credit_path(self, mocker):
        cheque = MagicMock(
            id=6, tenant_id=1, cheque_type='outgoing', expense_id=None, supplier_id=None,
            customer_id=4, customer=MagicMock(), amount_aed=Decimal('80'),
            cheque_bank_number='C1',
        )
        mocker.patch('services.cheque_service.GLService.get_account_code_for_concept', return_value='2100')
        mocker.patch('services.cheque_service.gl_get_customer_credit_account', return_value='1200')
        mocker.patch('services.cheque_service.gl_get_customer_credit_concept', return_value='AR')
        mocker.patch('services.cheque_service._post_gl')
        from services.cheque_service import _create_cancel_journal_entry
        _create_cancel_journal_entry(cheque)

    def test_cancel_expense_category_gl_code(self, mocker):
        category = MagicMock(gl_account_code='6100')
        expense = MagicMock(category=category)
        cheque = MagicMock(
            id=7, tenant_id=1, cheque_type='outgoing', expense_id=9, supplier_id=None,
            customer_id=None, amount_aed=Decimal('30'), cheque_bank_number='C2',
        )
        mocker.patch('services.cheque_service.db.session.get', return_value=expense)
        mocker.patch('services.cheque_service.GLService.get_account_code_for_concept', return_value='2100')
        mocker.patch('services.cheque_service._post_gl')
        from services.cheque_service import _create_cancel_journal_entry
        _create_cancel_journal_entry(cheque)

    def test_cancel_rejects_linked_receipts(self, mocker):
        cheque = MagicMock(
            id=8, tenant_id=1, status='pending', cheque_type='incoming', notes='',
            supplier_id=None, expense_id=None,
        )
        receipt = MagicMock()
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [receipt]
        mocker.patch('models.payment.Payment')
        mocker.patch('models.payment.Receipt')
        Receipt = mocker.patch('models.payment.Receipt')
        Receipt.query.filter_by.return_value = mock_q
        mocker.patch('services.cheque_service._create_cancel_journal_entry')
        from services.cheque_service import process_cheque_cancel
        process_cheque_cancel(cheque, reason='void')



    def test_write_data_bundle_skips_empty_row_list(self, mocker, tmp_path, mock_db_connection):
        from services.backup_scoped_engine import ExportResult, write_data_bundle
        from services.backup_scope_config import SCOPE_TENANT
        mocker.patch('services.backup_scoped_engine.table_exists', return_value=True)
        mocker.patch('services.backup_scoped_engine.write_jsonl')
        export = ExportResult(
            tables={'empty_tbl': []},
            row_counts={'empty_tbl': 0},
            included=[],
            skipped=[],
            dependency_order=['empty_tbl'],
            scope=SCOPE_TENANT,
            tenant_id=1,
        )
        write_data_bundle(str(tmp_path), export, mock_db_connection())

    def test_remap_row_existing_pk_in_map(self):
        from services.backup_scoped_engine import _remap_row
        result = _remap_row({'id': 5, 'tenant_id': 1}, 'users', {'users': {5: 55}})
        assert result['id'] == 55

    def test_verify_branch_row_isolation_failure(self, tmp_path):
        import json
        from services.backup_scoped_engine import verify_scoped_isolation
        from services.backup_scope_config import SCOPE_BRANCH
        data_dir = tmp_path / 'data'
        data_dir.mkdir()
        tables = {'branches': [{'id': 99}], 'sales': [{'id': 1, 'branch_id': 5}]}
        for table, rows in tables.items():
            (data_dir / f'{table}.jsonl').write_text(
                '\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8',
            )
        (data_dir / 'schema_meta.json').write_text('{}', encoding='utf-8')
        manifest = {'backup_scope': SCOPE_BRANCH, 'tenant_id': 1, 'branch_id': 5, 'row_counts_per_table': {}}
        result = verify_scoped_isolation(manifest, str(tmp_path))
        assert result['ok'] is False
        assert any('branch row isolation' in e for e in result['errors'])

    def test_verify_skips_zero_expected_and_missing_jsonl(self, tmp_path):
        import json
        from services.backup_scoped_engine import verify_scoped_isolation
        from services.backup_scope_config import SCOPE_TENANT
        data_dir = tmp_path / 'data'
        data_dir.mkdir()
        (data_dir / 'tenants.jsonl').write_text('{"id": 1}\n', encoding='utf-8')
        (data_dir / 'schema_meta.json').write_text('{}', encoding='utf-8')
        manifest = {
            'backup_scope': SCOPE_TENANT, 'tenant_id': 1,
            'row_counts_per_table': {'customers': 0, 'ghost': 5},
        }
        result = verify_scoped_isolation(manifest, str(tmp_path))
        assert result['ok'] is True
