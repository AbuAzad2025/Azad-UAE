"""Celery async tasks — worker execution, retries, failure isolation."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_app_context(mocker):
    app = MagicMock()
    app.extensions = {'mail': MagicMock(default_sender='noreply@test.com')}
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=None)
    ctx.__exit__ = MagicMock(return_value=False)
    app.app_context.return_value = ctx
    mocker.patch('app.create_app', return_value=app)
    return app


class TestInventoryReconciliationTask:
    """run_inventory_reconciliation — single vs all tenants, mismatch logging."""

    def _matched_report(self):
        return {
            'summary': {
                'all_matched_qty': True,
                'all_matched_value': True,
                'all_matched': True,
                'record_count': 10,
                'total_pwc_qty': 100,
                'total_movement_qty': 100,
                'total_gl_value': 5000,
                'overall_value_diff': 0,
            },
            'rows': [{'matched_qty': True, 'product_id': 1, 'warehouse_id': 1,
                      'pwc_qty': 1, 'movement_qty': 1, 'qty_diff': 0}],
            'warehouse_summary': [{'matched_value': True, 'warehouse_id': 1,
                                   'pwc_value': 100, 'gl_value': 100, 'value_diff': 0}],
        }

    def test_single_tenant_all_matched(self, mocker, mock_app_context):
        mocker.patch(
            'services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary',
            return_value=self._matched_report(),
        )
        from services.celery_tasks import run_inventory_reconciliation
        result = run_inventory_reconciliation(tenant_id=1)
        assert result['tenant_id'] == 1
        assert result['all_matched'] is True
        assert result['record_count'] == 10

    def test_all_tenants_aggregate(self, mocker, mock_app_context):
        mock_db = mocker.patch('extensions.db')
        mock_db.session.query.return_value.distinct.return_value.order_by.return_value.all.return_value = [
            (1,), (2,),
        ]
        mocker.patch(
            'services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary',
            return_value=self._matched_report(),
        )
        from services.celery_tasks import run_inventory_reconciliation
        result = run_inventory_reconciliation(tenant_id=None)
        assert result['tenant_count'] == 2
        assert result['all_matched'] is True

    def test_mismatch_logs_warnings(self, mocker, mock_app_context, caplog):
        report = self._matched_report()
        report['summary']['all_matched_qty'] = False
        report['rows'] = [{
            'matched_qty': False, 'product_id': 5, 'warehouse_id': 2,
            'pwc_qty': 10, 'movement_qty': 8, 'qty_diff': 2,
        }]
        report['warehouse_summary'] = [{
            'matched_value': False, 'warehouse_id': 2,
            'pwc_value': 1000, 'gl_value': 900, 'value_diff': 100,
        }]
        mocker.patch(
            'services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary',
            return_value=report,
        )
        mock_db = mocker.patch('extensions.db')
        mock_db.session.query.return_value.distinct.return_value.order_by.return_value.all.return_value = [(1,)]

        from services.celery_tasks import run_inventory_reconciliation
        import logging
        with caplog.at_level(logging.WARNING):
            result = run_inventory_reconciliation()
        assert result['results'][0]['all_matched'] is False

    def test_legacy_all_matched_summary_key(self, mocker, mock_app_context):
        report = self._matched_report()
        del report['summary']['all_matched_qty']
        report['summary']['all_matched'] = True
        mocker.patch(
            'services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary',
            return_value=report,
        )
        from services.celery_tasks import run_inventory_reconciliation
        result = run_inventory_reconciliation(tenant_id=3)
        assert result['all_matched'] is True


class TestCeleryReportAndMailTasks:
    """generate_monthly_report, send_invoice_email — success/failure paths."""

    def test_generate_monthly_report(self, mocker, mock_app_context):
        from services.celery_tasks import generate_monthly_report
        result = generate_monthly_report(6, 2026)
        assert result['success'] is False
        assert 'Disabled' in result['error']

    def test_send_invoice_email_success(self, mocker, mock_app_context):
        sale = MagicMock()
        sale.sale_number = 'INV-001'
        sale.customer.email = 'buyer@test.com'
        Sale = mocker.patch('models.Sale')
        Sale.query.get.return_value = sale
        mocker.patch('flask_mail.Message', return_value=MagicMock())
        mail = mocker.patch('extensions.mail')
        from services.celery_tasks import send_invoice_email
        result = send_invoice_email(1)
        assert result['success'] is True
        mail.send.assert_called_once()

    def test_send_invoice_email_missing_customer(self, mocker, mock_app_context):
        Sale = mocker.patch('models.Sale')
        Sale.query.get.return_value = None
        from services.celery_tasks import send_invoice_email
        assert send_invoice_email(999) == {'success': False}


class TestCeleryMaintenanceTasks:
    """Backup, exchange rates, neural training, reminders, cache cleanup."""

    def test_auto_backup_database(self, mocker, mock_app_context):
        mocker.patch('services.backup_service.BackupService.auto_backup_daily', return_value={'id': 1})
        from services.celery_tasks import auto_backup_database
        result = auto_backup_database()
        assert result['success'] is True

    def test_update_exchange_rates(self, mocker, mock_app_context):
        fake_cs = MagicMock()
        fake_cs.update_all_rates.return_value = {'updated': 3}
        mocker.patch.dict('sys.modules', {'services.currency_service': MagicMock(CurrencyService=fake_cs)})
        from services.celery_tasks import update_exchange_rates
        assert update_exchange_rates() == {'updated': 3}

    def test_train_neural_models(self, mocker, mock_app_context):
        mock_neural = MagicMock()
        mock_neural.train_all_models.return_value = {'models': 2}
        fake_module = MagicMock(get_neural_engine=MagicMock(return_value=mock_neural))
        mocker.patch.dict('sys.modules', {'ai_knowledge.neural_engine': fake_module})
        from services.celery_tasks import train_neural_models
        assert train_neural_models() == {'models': 2}

    def test_send_payment_reminders_counts_sent(self, mocker, mock_app_context):
        c1 = MagicMock(phone='0501111111', name='A')
        c1.get_balance_aed.return_value = Decimal('2000')
        c2 = MagicMock(phone=None, name='B')
        c2.get_balance_aed.return_value = Decimal('5000')
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.all.return_value = [c1, c2]
        mocker.patch(
            'services.whatsapp_service.WhatsAppService.send_payment_reminder',
            return_value={'success': True},
        )
        from services.celery_tasks import send_payment_reminders
        result = send_payment_reminders()
        assert result['sent'] == 1
        assert result['total_checked'] == 2


class TestAbandonedCartReminders:
    """send_abandoned_cart_reminders — first/second pass, rollback on failure."""

    def test_first_reminder_updates_cart(self, mocker):
        now = datetime.now(timezone.utc)
        cart = MagicMock(tenant_id=1, reminder_count=0)
        mock_q = MagicMock()
        mock_q.filter.return_value.all.side_effect = [[cart], []]
        mocker.patch('models.shop_abandoned_cart.ShopAbandonedCart.query', mock_q)
        store = MagicMock(email='store@test.com')
        mocker.patch('services.store_service.StoreService.get_tenant_store', return_value=store)
        mocker.patch('extensions.db.session')

        from services.celery_tasks import send_abandoned_cart_reminders
        send_abandoned_cart_reminders()
        assert cart.reminder_sent_at is not None
        assert cart.reminder_count == 1

    def test_skips_cart_without_store_email(self, mocker):
        cart = MagicMock(tenant_id=1, reminder_count=0)
        cart.reminder_sent_at = None
        mock_q = MagicMock()
        mock_q.filter.return_value.all.side_effect = [[cart], []]
        mocker.patch('models.shop_abandoned_cart.ShopAbandonedCart.query', mock_q)
        mocker.patch('services.store_service.StoreService.get_tenant_store', return_value=None)

        from services.celery_tasks import send_abandoned_cart_reminders
        send_abandoned_cart_reminders()
        assert cart.reminder_sent_at is None

    def test_second_reminder_increments_count(self, mocker):
        cart = MagicMock(tenant_id=1, reminder_count=1)
        mock_q = MagicMock()
        mock_q.filter.return_value.all.side_effect = [[], [cart]]
        mocker.patch('models.shop_abandoned_cart.ShopAbandonedCart.query', mock_q)
        mocker.patch('services.store_service.StoreService.get_tenant_store', return_value=MagicMock(email='s@t.com'))
        mocker.patch('extensions.db.session')

        from services.celery_tasks import send_abandoned_cart_reminders
        send_abandoned_cart_reminders()
        assert cart.reminder_count == 2

    def test_failed_commit_rolls_back(self, mocker):
        cart = MagicMock(tenant_id=1, reminder_count=0)
        mock_q = MagicMock()
        mock_q.filter.return_value.all.side_effect = [[cart], []]
        mocker.patch('models.shop_abandoned_cart.ShopAbandonedCart.query', mock_q)
        mocker.patch('services.store_service.StoreService.get_tenant_store', return_value=MagicMock(email='x@y.com'))
        mock_session = mocker.patch('extensions.db.session')
        mock_session.commit.side_effect = Exception('db error')

        from services.celery_tasks import send_abandoned_cart_reminders
        send_abandoned_cart_reminders()
        mock_session.rollback.assert_called()

    def test_second_reminder_skips_store_without_email(self, mocker):
        cart = MagicMock(tenant_id=1, reminder_count=1)
        mock_q = MagicMock()
        mock_q.filter.return_value.all.side_effect = [[], [cart]]
        mocker.patch('models.shop_abandoned_cart.ShopAbandonedCart.query', mock_q)
        mocker.patch('services.store_service.StoreService.get_tenant_store', return_value=MagicMock(email=None))
        mocker.patch('extensions.db.session')
        from services.celery_tasks import send_abandoned_cart_reminders
        send_abandoned_cart_reminders()
        assert cart.reminder_count == 1

    def test_second_reminder_commit_failure_rolls_back(self, mocker):
        cart = MagicMock(tenant_id=1, reminder_count=1)
        mock_q = MagicMock()
        mock_q.filter.return_value.all.side_effect = [[], [cart]]
        mocker.patch('models.shop_abandoned_cart.ShopAbandonedCart.query', mock_q)
        mocker.patch('services.store_service.StoreService.get_tenant_store', return_value=MagicMock(email='s@t.com'))
        mock_session = mocker.patch('extensions.db.session')
        mock_session.commit.side_effect = Exception('second fail')
        from services.celery_tasks import send_abandoned_cart_reminders
        send_abandoned_cart_reminders()
        mock_session.rollback.assert_called()


class TestCacheCleanupTask:
    """cleanup_old_cache — success and dead-letter style error capture."""

    def test_cache_clear_success(self, mocker):
        cache = mocker.patch('extensions.cache')
        from services.celery_tasks import cleanup_old_cache
        result = cleanup_old_cache()
        assert result == {'success': True, 'message': 'Cache cleared'}

    def test_cache_clear_failure_isolated(self, mocker):
        cache = mocker.patch('extensions.cache')
        cache.clear.side_effect = RuntimeError('redis down')
        from services.celery_tasks import cleanup_old_cache
        result = cleanup_old_cache()
        assert result['success'] is False
        assert 'redis down' in result['error']


class TestCeleryConfiguration:
    """Worker configuration — beat schedule and serialization."""

    def test_celery_beat_schedule_registered(self):
        from services.celery_tasks import celery
        assert 'daily-inventory-reconciliation' in celery.conf.beat_schedule
        assert 'check-abandoned-carts' in celery.conf.beat_schedule

    def test_task_serializer_json(self):
        from services.celery_tasks import celery
        assert celery.conf.task_serializer == 'json'
