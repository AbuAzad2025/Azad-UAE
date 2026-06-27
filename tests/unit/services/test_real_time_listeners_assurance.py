"""Real-time accounting listeners and event stream."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


def _entry(**kwargs):
    e = MagicMock()
    e.id = kwargs.get('id', 1)
    e.entry_number = kwargs.get('entry_number', 'JE-001')
    e.description = 'Test entry'
    e.total_debit = Decimal('1000')
    e.entry_type = 'manual'
    e.entry_date = datetime(2026, 1, 15, tzinfo=timezone.utc)
    e.is_posted = kwargs.get('is_posted', False)
    e.is_reversed = kwargs.get('is_reversed', False)
    e.updated_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return e


class TestSetupListeners:
    def test_idempotent_registration(self, mocker):
        from services import real_time_listeners as rtl
        original = rtl.RealTimeAccountingListeners._listeners_registered
        try:
            rtl.RealTimeAccountingListeners._listeners_registered = False
            mock_listen = mocker.patch('services.real_time_listeners.event.listens_for')
            rtl.RealTimeAccountingListeners.setup_listeners()
            first_count = mock_listen.call_count
            rtl.RealTimeAccountingListeners.setup_listeners()
            assert mock_listen.call_count == first_count
        finally:
            rtl.RealTimeAccountingListeners._listeners_registered = original

    def test_registered_callbacks_dispatch(self, mocker):
        from services import real_time_listeners as rtl
        callbacks = {}

        def capture(model, event_name):
            def decorator(fn):
                callbacks[f'{model.__name__}:{event_name}'] = fn
                return fn
            return decorator

        mocker.patch('services.real_time_listeners.event.listens_for', side_effect=capture)
        original = rtl.RealTimeAccountingListeners._listeners_registered
        try:
            rtl.RealTimeAccountingListeners._listeners_registered = False
            rtl.RealTimeAccountingListeners.setup_listeners()
            entry = _entry()
            for key in (
                'GLJournalEntry:after_insert',
                'GLJournalEntry:after_update',
                'GLJournalLine:after_insert',
                'GLAccount:after_update',
                'AdvancedExpense:after_insert',
                'Cheque:after_update',
            ):
                assert key in callbacks
            mocker.patch.object(rtl.RealTimeAccountingListeners, '_on_journal_entry_created')
            callbacks['GLJournalEntry:after_insert'](None, None, entry)
            rtl.RealTimeAccountingListeners._on_journal_entry_created.assert_called_once_with(entry)
        finally:
            rtl.RealTimeAccountingListeners._listeners_registered = original


class TestHandlerExceptionPaths:
    def test_journal_update_exception(self, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        bad = _entry()
        type(bad).is_posted = property(lambda self: (_ for _ in ()).throw(RuntimeError('x')))
        RealTimeAccountingListeners._on_journal_entry_updated(bad)
        assert 'خطأ' in capsys.readouterr().out

    def test_update_statistics_exception(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch('services.real_time_listeners.GLJournalEntry.query', side_effect=RuntimeError('stats'))
        RealTimeAccountingListeners._update_statistics()
        assert 'خطأ' in capsys.readouterr().out

    def test_all_sqlalchemy_callbacks_invoke_handlers(self, mocker):
        from services import real_time_listeners as rtl
        callbacks = {}

        def capture(model, event_name):
            def decorator(fn):
                callbacks[f'{model.__name__}:{event_name}'] = fn
                return fn
            return decorator

        mocker.patch('services.real_time_listeners.event.listens_for', side_effect=capture)
        original = rtl.RealTimeAccountingListeners._listeners_registered
        try:
            rtl.RealTimeAccountingListeners._listeners_registered = False
            rtl.RealTimeAccountingListeners.setup_listeners()
            updated = mocker.patch.object(rtl.RealTimeAccountingListeners, '_on_journal_entry_updated')
            line = mocker.patch.object(rtl.RealTimeAccountingListeners, '_on_journal_line_created')
            account = mocker.patch.object(rtl.RealTimeAccountingListeners, '_on_account_updated')
            expense = mocker.patch.object(rtl.RealTimeAccountingListeners, '_on_expense_created')
            cheque = mocker.patch.object(rtl.RealTimeAccountingListeners, '_on_cheque_updated')

            callbacks['GLJournalEntry:after_update'](None, None, _entry())
            callbacks['GLJournalLine:after_insert'](None, None, MagicMock())
            callbacks['GLAccount:after_update'](None, None, MagicMock())
            callbacks['AdvancedExpense:after_insert'](None, None, MagicMock())
            callbacks['Cheque:after_update'](None, None, MagicMock())

            updated.assert_called_once()
            line.assert_called_once()
            account.assert_called_once()
            expense.assert_called_once()
            cheque.assert_called_once()
        finally:
            rtl.RealTimeAccountingListeners._listeners_registered = original

    def test_line_handler_exception(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch.object(RealTimeAccountingListeners, '_log_event', side_effect=RuntimeError('log fail'))
        line = MagicMock(id=1, entry_id=2, account=None, account_id=None, debit=0, credit=0, description='')
        RealTimeAccountingListeners._on_journal_line_created(line)
        assert 'خطأ' in capsys.readouterr().out

    def test_account_handler_exception(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch.object(RealTimeAccountingListeners, '_log_event', side_effect=RuntimeError('log fail'))
        RealTimeAccountingListeners._on_account_updated(MagicMock())
        assert 'خطأ' in capsys.readouterr().out

    def test_expense_handler_exception(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch.object(RealTimeAccountingListeners, '_log_event', side_effect=RuntimeError('log fail'))
        RealTimeAccountingListeners._on_expense_created(MagicMock())
        assert 'خطأ' in capsys.readouterr().out

    def test_cheque_handler_exception(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch.object(RealTimeAccountingListeners, '_log_event', side_effect=RuntimeError('log fail'))
        RealTimeAccountingListeners._on_cheque_updated(MagicMock())
        assert 'خطأ' in capsys.readouterr().out

    def test_update_account_balance_exception(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch('services.real_time_listeners.db.session.get', side_effect=RuntimeError('db'))
        RealTimeAccountingListeners._update_account_balance(1)
        assert 'خطأ' in capsys.readouterr().out


class TestJournalEntryHandlers:
    def test_on_journal_entry_created(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch.object(RealTimeAccountingListeners, '_update_statistics')
        RealTimeAccountingListeners._on_journal_entry_created(_entry())
        out = capsys.readouterr().out
        assert 'journal_entry_created' in out or 'قيد جديد' in out

    def test_on_journal_entry_created_handles_error(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch.object(RealTimeAccountingListeners, '_log_event', side_effect=RuntimeError('bad'))
        RealTimeAccountingListeners._on_journal_entry_created(_entry())
        assert 'خطأ' in capsys.readouterr().out

    def test_on_journal_entry_updated_posted(self, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        RealTimeAccountingListeners._on_journal_entry_updated(_entry(is_posted=True))
        assert 'قيد مرحل' in capsys.readouterr().out

    def test_on_journal_entry_updated_reversed(self, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        RealTimeAccountingListeners._on_journal_entry_updated(_entry(is_reversed=True))
        assert 'قيد معكوس' in capsys.readouterr().out


class TestJournalLineHandler:
    def test_with_account_relationship(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        line = MagicMock()
        line.id = 1
        line.entry_id = 2
        line.account = MagicMock(code='1100', full_name='Cash')
        line.account_id = 5
        line.debit = Decimal('100')
        line.credit = None
        line.description = 'Debit'
        mocker.patch.object(RealTimeAccountingListeners, '_update_account_balance')
        RealTimeAccountingListeners._on_journal_line_created(line)
        assert 'journal_line_created' in capsys.readouterr().out

    def test_account_id_only(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        line = MagicMock()
        line.id = 1
        line.entry_id = 2
        line.account = None
        line.account_id = 99
        line.debit = 0
        line.credit = 0
        line.description = ''
        mock_update = mocker.patch.object(RealTimeAccountingListeners, '_update_account_balance')
        RealTimeAccountingListeners._on_journal_line_created(line)
        mock_update.assert_called_once_with(99)


class TestAccountHandler:
    def test_high_balance_warning(self, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        account = MagicMock()
        account.id = 1
        account.code = '1100'
        account.full_name = 'Cash'
        account.get_balance.return_value = Decimal('150000')
        account.updated_at = datetime.now(timezone.utc)
        RealTimeAccountingListeners._on_account_updated(account)
        assert 'رصيد عالي' in capsys.readouterr().out


class TestExpenseHandler:
    def test_approval_required_notification(self, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        expense = MagicMock()
        expense.id = 1
        expense.expense_number = 'EXP-1'
        expense.description_ar = 'مصروف'
        expense.amount_aed = Decimal('5000')
        expense.category = MagicMock(name_ar='Travel', approval_limit=Decimal('1000'))
        expense.tax_amount = Decimal('0')
        expense.customs_amount = Decimal('0')
        expense.requires_approval = True
        RealTimeAccountingListeners._on_expense_created(expense)
        assert 'موافقة مطلوبة' in capsys.readouterr().out


class TestChequeHandler:
    @pytest.mark.parametrize('status', ['received', 'issued', 'cleared', 'bounced'])
    def test_status_notifications(self, status, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        cheque = MagicMock()
        cheque.id = 1
        cheque.cheque_bank_number = 'CHQ-99'
        cheque.status = status
        cheque.status_ar = status
        cheque.amount_aed = Decimal('500')
        cheque.cheque_type = 'incoming'
        cheque.updated_at = datetime.now(timezone.utc)
        RealTimeAccountingListeners._on_cheque_updated(cheque)
        assert cheque.cheque_bank_number in capsys.readouterr().out


class TestHelpers:
    def test_log_event_json_error(self, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        with patch('services.real_time_listeners.json.dumps', side_effect=TypeError('bad')):
            RealTimeAccountingListeners._log_event('test', {'x': object()})
        assert 'خطأ' in capsys.readouterr().out

    def test_send_notification_unknown_level(self, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        RealTimeAccountingListeners._send_notification('Title', 'Msg', level='custom')
        assert 'Title' in capsys.readouterr().out

    def test_update_statistics(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch('services.real_time_listeners.GLJournalEntry.query.count', return_value=10)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.count.return_value = 3
        mocker.patch('services.real_time_listeners.GLJournalEntry.query', mock_q)
        RealTimeAccountingListeners._update_statistics()
        assert 'إحصائيات' in capsys.readouterr().out

    def test_update_account_balance(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        account = MagicMock(code='1100', get_balance=MagicMock(return_value=Decimal('500')))
        mocker.patch('services.real_time_listeners.db.session.get', return_value=account)
        RealTimeAccountingListeners._update_account_balance(1)
        assert 'account_balance_updated' in capsys.readouterr().out

    def test_update_account_balance_missing(self, mocker, capsys):
        from services.real_time_listeners import RealTimeAccountingListeners
        mocker.patch('services.real_time_listeners.db.session.get', return_value=None)
        RealTimeAccountingListeners._update_account_balance(999)
        assert capsys.readouterr().out == ''


class TestAccountingEventStream:
    def test_emit_and_query(self, capsys):
        from services.real_time_listeners import AccountingEventStream
        stream = AccountingEventStream()
        received = []
        stream.add_listener(lambda e: received.append(e))
        stream.emit_event('sale', {'id': 1})
        assert len(received) == 1
        assert stream.get_recent_events(10)[0]['type'] == 'sale'
        assert stream.get_events_by_type('sale')[0]['data']['id'] == 1

    def test_listener_exception_logged(self, capsys):
        from services.real_time_listeners import AccountingEventStream
        stream = AccountingEventStream()
        stream.add_listener(lambda e: (_ for _ in ()).throw(RuntimeError('fail')))
        stream.emit_event('x', {})
        assert 'خطأ في المستمع' in capsys.readouterr().out

    def test_empty_events(self):
        from services.real_time_listeners import AccountingEventStream
        stream = AccountingEventStream()
        assert stream.get_recent_events() == []
        assert stream.get_events_by_type('none') == []
