from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _capture_handlers(mocker):
    handlers = {}

    def listens_for(model, event):
        def decorator(fn):
            handlers.setdefault(model.__name__ if hasattr(model, '__name__') else str(model), []).append(fn)
            return fn
        return decorator

    mocker.patch('sqlalchemy.event.listens_for', side_effect=listens_for)
    return handlers


class TestRegisterAllListeners:
    def test_register_all_skips_ai_by_default(self, mocker):
        mocker.patch('models.events.register_sale_listeners')
        mocker.patch('models.events.register_receipt_listeners')
        mocker.patch('models.events.register_purchase_listeners')
        mocker.patch('models.events.register_payment_listeners')
        mocker.patch('models.events.register_branch_listeners')
        mocker.patch('models.events.register_stock_movement_listeners')
        mocker.patch('models.events.register_cheque_listeners')
        mocker.patch('models.events.register_product_return_listeners')
        mocker.patch('models.events.register_expense_listeners')
        mocker.patch('models.events.register_gl_listeners')
        mocker.patch('models.events.register_validation_listeners')
        mocker.patch('models.events.register_audit_listeners')
        mocker.patch('models.events.register_automatic_gl_listeners')
        mocker.patch('models.events.ai_orm_listeners_enabled', return_value=False)
        ai = mocker.patch('models.events.register_ai_listeners')
        neural = mocker.patch('models.events.register_neural_training_listeners')
        log = mocker.patch('models.events.logger')

        from models.events import register_all_listeners

        register_all_listeners()
        ai.assert_not_called()
        neural.assert_not_called()
        log.info.assert_called()

    def test_register_all_enables_ai_when_flag_on(self, mocker):
        for name in (
            'register_sale_listeners', 'register_receipt_listeners', 'register_purchase_listeners',
            'register_payment_listeners', 'register_branch_listeners', 'register_stock_movement_listeners',
            'register_cheque_listeners', 'register_product_return_listeners', 'register_expense_listeners',
            'register_gl_listeners', 'register_validation_listeners', 'register_audit_listeners',
            'register_automatic_gl_listeners',
        ):
            mocker.patch(f'models.events.{name}')
        mocker.patch('models.events.ai_orm_listeners_enabled', return_value=True)
        ai = mocker.patch('models.events.register_ai_listeners')
        neural = mocker.patch('models.events.register_neural_training_listeners')

        from models.events import register_all_listeners

        with pytest.warns(RuntimeWarning, match='Experimental AI ORM listeners'):
            register_all_listeners()
        ai.assert_called_once()
        neural.assert_called_once()


class TestSaleListeners:
    def test_sale_after_insert_logs_active_sale(self, mocker):
        handlers = _capture_handlers(mocker)
        mocker.patch('models.events.logger')
        from models.events import register_sale_listeners

        register_sale_listeners()
        target = SimpleNamespace(
            sale_number='S-1', customer_id=1, is_active=True, status='confirmed',
        )
        for fn in handlers.get('Sale', []):
            fn(None, MagicMock(), target)

    def test_sale_debug_failure_is_swallowed(self, mocker):
        handlers = _capture_handlers(mocker)
        mocker.patch('models.events.logger.debug', side_effect=RuntimeError('log'))
        from models.events import register_sale_listeners

        register_sale_listeners()
        target = SimpleNamespace(
            sale_number='S-ERR', customer_id=1, is_active=True, status='confirmed',
        )
        for fn in handlers.get('Sale', []):
            if fn.__name__ == '_h':
                fn(None, MagicMock(), target)

    def test_sale_inactive_skips_debug(self, mocker):
        handlers = _capture_handlers(mocker)
        debug = mocker.patch('models.events.logger.debug')
        from models.events import register_sale_listeners

        register_sale_listeners()
        target = SimpleNamespace(
            sale_number='S-X', customer_id=1, is_active=False, status='confirmed',
        )
        for fn in handlers.get('Sale', []):
            if fn.__name__ == '_h':
                fn(None, MagicMock(), target)
        debug.assert_not_called()

    def test_sale_delete_logs_and_handles_error(self, mocker):
        handlers = _capture_handlers(mocker)
        info = mocker.patch('models.events.logger.info', side_effect=RuntimeError('log fail'))
        warn = mocker.patch('models.events.logger.warning')
        from models.events import register_sale_listeners

        register_sale_listeners()
        target = SimpleNamespace(sale_number='S-DEL')
        delete_handlers = [fn for fn in handlers.get('Sale', []) if fn.__name__ == '_h2']
        for fn in delete_handlers:
            fn(None, MagicMock(), target)
        warn.assert_called()


class TestReceiptListeners:
    def test_receipt_insert_failure(self, mocker):
        handlers = _capture_handlers(mocker)
        mocker.patch('models.events.logger.info', side_effect=RuntimeError('log'))
        warn = mocker.patch('models.events.logger.warning')
        from models.events import register_receipt_listeners

        register_receipt_listeners()
        target = SimpleNamespace(receipt_number='R-ERR', amount_aed=Decimal('1'), customer_id=1)
        handlers['Receipt'][0](None, MagicMock(), target)
        warn.assert_called()

    def test_receipt_before_delete_warning(self, mocker):
        handlers = _capture_handlers(mocker)
        warn = mocker.patch('models.events.logger.warning')
        from models.events import register_receipt_listeners

        register_receipt_listeners()
        target = SimpleNamespace(receipt_number='R-DEL')
        handlers['Receipt'][1](None, MagicMock(), target)
        warn.assert_called()


class TestPurchaseListeners:
    def test_purchase_debug_failure_is_swallowed(self, mocker):
        handlers = _capture_handlers(mocker)
        mocker.patch('models.events.logger.debug', side_effect=RuntimeError('log'))
        from models.events import register_purchase_listeners

        register_purchase_listeners()
        target = SimpleNamespace(purchase_number='P-ERR', supplier_id=1, status='confirmed')
        for fn in handlers.get('Purchase', []):
            if fn.__name__ == '_h':
                fn(None, MagicMock(), target)

    def test_purchase_cancelled_skips_debug(self, mocker):
        handlers = _capture_handlers(mocker)
        debug = mocker.patch('models.events.logger.debug')
        from models.events import register_purchase_listeners

        register_purchase_listeners()
        target = SimpleNamespace(purchase_number='P-CAN', supplier_id=1, status='cancelled')
        for fn in handlers.get('Purchase', []):
            if fn.__name__ == '_h':
                fn(None, MagicMock(), target)
        debug.assert_not_called()


class TestPaymentListeners:
    def test_payment_supplier_and_failure(self, mocker):
        handlers = _capture_handlers(mocker)
        info = mocker.patch('models.events.logger.info', side_effect=RuntimeError('fail'))
        warn = mocker.patch('models.events.logger.warning')
        from models.events import register_payment_listeners

        register_payment_listeners()
        target = SimpleNamespace(supplier_id=5, payment_number='PAY-1', amount_aed=Decimal('20'))
        handlers['Payment'][0](None, MagicMock(), target)
        warn.assert_called()


class TestBranchAndChequeListeners:
    def test_branch_delegates(self, mocker):
        reg = mocker.patch('services.branch_audit_service.register_branch_event_listeners')
        from models.events import register_branch_listeners

        register_branch_listeners()
        reg.assert_called_once()

    def test_cheque_delegates(self, mocker):
        reg = mocker.patch('services.cheque_service.register_cheque_event_listeners')
        from models.events import register_cheque_listeners

        register_cheque_listeners()
        reg.assert_called_once()


class TestStockMovementListeners:
    def test_stock_movement_types(self, mocker):
        handlers = _capture_handlers(mocker)
        info = mocker.patch('models.events.logger.info')
        from models.events import register_stock_movement_listeners

        register_stock_movement_listeners()
        for movement_type in ('sale', 'purchase', 'adjustment', 'return', 'transfer', 'unknown'):
            target = SimpleNamespace(
                movement_type=movement_type,
                product_id=1,
                quantity=Decimal('-3'),
                reference_type='sale',
                reference_id=9,
            )
            handlers['StockMovement'][0](None, MagicMock(), target)
        assert info.call_count == 6

    def test_stock_movement_failure(self, mocker):
        handlers = _capture_handlers(mocker)
        mocker.patch('models.events.logger.info', side_effect=RuntimeError('boom'))
        err = mocker.patch('models.events.logger.error')
        from models.events import register_stock_movement_listeners

        register_stock_movement_listeners()
        target = SimpleNamespace(
            movement_type='sale', product_id=1, quantity=Decimal('1'),
            reference_type='sale', reference_id=1,
        )
        handlers['StockMovement'][0](None, MagicMock(), target)
        err.assert_called()


class TestProductReturnAndExpenseListeners:
    def test_product_return_approved(self, mocker):
        handlers = _capture_handlers(mocker)
        info = mocker.patch('models.events.logger.info')
        from models.events import register_product_return_listeners

        register_product_return_listeners()
        target = SimpleNamespace(return_number='RET-1', status='approved')
        handlers['ProductReturn'][0](None, MagicMock(), target)
        info.assert_called()

    def test_product_return_failure(self, mocker):
        handlers = _capture_handlers(mocker)
        mocker.patch('models.events.logger.info', side_effect=RuntimeError('x'))
        err = mocker.patch('models.events.logger.error')
        from models.events import register_product_return_listeners

        register_product_return_listeners()
        handlers['ProductReturn'][0](None, MagicMock(), SimpleNamespace(return_number='R', status='approved'))
        err.assert_called()

    def test_expense_active_and_failure(self, mocker):
        handlers = _capture_handlers(mocker)
        info = mocker.patch('models.events.logger.info', side_effect=RuntimeError('x'))
        err = mocker.patch('models.events.logger.error')
        from models.events import register_expense_listeners

        register_expense_listeners()
        active = SimpleNamespace(amount_aed=Decimal('50'), category_id=1, is_active=True)
        inactive = SimpleNamespace(amount_aed=Decimal('50'), category_id=1, is_active=False)
        fn = handlers['Expense'][0]
        fn(None, MagicMock(), inactive)
        fn(None, MagicMock(), active)
        err.assert_called()


class TestGlAndValidationListeners:
    def test_gl_delegates(self, mocker):
        reg = mocker.patch('services.gl_auto_service.register_gl_event_listeners')
        from models.events import register_gl_listeners

        register_gl_listeners()
        reg.assert_called_once()

    def test_validation_delegates(self, mocker):
        reg = mocker.patch('services.gl_auto_service.register_validation_event_listeners')
        from models.events import register_validation_listeners

        register_validation_listeners()
        reg.assert_called_once()


class TestAuditListeners:
    def test_audit_delete_warnings(self, mocker):
        handlers = _capture_handlers(mocker)
        warn = mocker.patch('models.events.logger.warning')
        from models.events import register_audit_listeners

        register_audit_listeners()
        handlers['Sale'][0](None, MagicMock(), SimpleNamespace(sale_number='S', amount_aed=1))
        handlers['Purchase'][0](None, MagicMock(), SimpleNamespace(purchase_number='P', amount_aed=2))
        handlers['Receipt'][0](None, MagicMock(), SimpleNamespace(receipt_number='R', amount_aed=3))
        handlers['Payment'][0](None, MagicMock(), SimpleNamespace(amount_aed=4))
        assert warn.call_count == 4


class TestAiAndAutomaticListeners:
    def test_ai_delegates(self, mocker):
        reg = mocker.patch('services.events_ai_service.register_ai_event_listeners')
        from models.events import register_ai_listeners

        register_ai_listeners()
        reg.assert_called_once()

    def test_neural_delegates(self, mocker):
        reg = mocker.patch('services.events_ai_service.register_neural_event_listeners')
        from models.events import register_neural_training_listeners

        register_neural_training_listeners()
        reg.assert_called_once()

    def test_automatic_gl_skipped(self, mocker):
        info = mocker.patch('models.events.logger.info')
        from models.events import register_automatic_gl_listeners

        register_automatic_gl_listeners()
        info.assert_called()


class TestAdvancedSaleListener:
    def test_legacy_listener_disabled(self, mocker):
        warn = mocker.patch('models.events.logger.warning')
        from models.events import register_advanced_sale_listener

        register_advanced_sale_listener()
        warn.assert_called()

    def test_legacy_listener_skips_inactive_sale(self, mocker):
        import models.events as events_mod

        handlers = _capture_handlers(mocker)
        conn = MagicMock()
        info = mocker.patch('models.events.logger.info')
        prev = events_mod._ADVANCED_SALE_LISTENER_ALLOWED
        events_mod._ADVANCED_SALE_LISTENER_ALLOWED = True
        try:
            events_mod.register_advanced_sale_listener()
            target = SimpleNamespace(customer_id=9, is_active=False, status='confirmed')
            for fn in handlers.get('Sale', []):
                fn(None, conn, target)
            info.assert_not_called()
            conn.execute.assert_not_called()
        finally:
            events_mod._ADVANCED_SALE_LISTENER_ALLOWED = prev

    def test_legacy_listener_allowed_path(self, mocker):
        import models.events as events_mod

        handlers = _capture_handlers(mocker)
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            SimpleNamespace(amount_aed=Decimal('100'), paid_amount_aed=Decimal('40')),
        ]
        info = mocker.patch('models.events.logger.info')
        prev = events_mod._ADVANCED_SALE_LISTENER_ALLOWED
        events_mod._ADVANCED_SALE_LISTENER_ALLOWED = True
        try:
            events_mod.register_advanced_sale_listener()
            target = SimpleNamespace(customer_id=9, is_active=True, status='confirmed')
            for fn in handlers.get('Sale', []):
                fn(None, conn, target)
            info.assert_called()
        finally:
            events_mod._ADVANCED_SALE_LISTENER_ALLOWED = prev

    def test_legacy_listener_failure(self, mocker):
        import models.events as events_mod

        handlers = _capture_handlers(mocker)
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError('db')
        err = mocker.patch('models.events.logger.error')
        prev = events_mod._ADVANCED_SALE_LISTENER_ALLOWED
        events_mod._ADVANCED_SALE_LISTENER_ALLOWED = True
        try:
            events_mod.register_advanced_sale_listener()
            target = SimpleNamespace(customer_id=9, is_active=True, status='confirmed')
            for fn in handlers.get('Sale', []):
                fn(None, conn, target)
            err.assert_called()
        finally:
            events_mod._ADVANCED_SALE_LISTENER_ALLOWED = prev
