from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from services.advanced_journal_manager import AdvancedJournalEntryManager, add_helper_methods
from models.gl import GLJournalEntry


def _mock_entry(**kwargs):
    entry = MagicMock()
    entry.id = kwargs.get('id', 1)
    entry.tenant_id = kwargs.get('tenant_id', 1)
    entry.entry_number = kwargs.get('entry_number', 'JE-001')
    entry.entry_date = kwargs.get('entry_date', date.today())
    entry.description = kwargs.get('description', 'Test entry')
    entry.entry_type = kwargs.get('entry_type', 'manual')
    entry.total_debit = kwargs.get('total_debit', Decimal('100'))
    entry.total_credit = kwargs.get('total_credit', Decimal('100'))
    entry.status = kwargs.get('status', 'draft')
    entry.is_posted = kwargs.get('is_posted', entry.status in ('posted', 'reversed'))
    entry.is_reversed = kwargs.get('is_reversed', entry.status == 'reversed')
    entry.reversed_entry_id = kwargs.get('reversed_entry_id', None)
    entry.validation_errors = kwargs.get('validation_errors', None)
    entry.validated_at = kwargs.get('validated_at', None)
    entry.validated_by = kwargs.get('validated_by', None)
    entry.notes = kwargs.get('notes', '')
    line = MagicMock()
    line.account.code = '1100'
    line.account.full_name = 'Cash'
    line.debit = Decimal('100')
    line.credit = Decimal('0')
    line.description = 'line'
    entry.lines = kwargs.get('lines', [line])
    entry.to_dict.return_value = {'id': entry.id, 'description': entry.description}
    return entry


class TestEntryOr404:
    def test_returns_entry_when_found(self):
        entry = _mock_entry()
        q = MagicMock()
        q.filter_by.return_value.first.return_value = entry
        with patch('utils.gl_tenant.gl_entry_query', return_value=q), patch(
            'utils.gl_tenant.active_tenant_id', return_value=1
        ):
            assert AdvancedJournalEntryManager._entry_or_404(1) is entry

    def test_aborts_404_when_missing(self):
        q = MagicMock()
        q.filter_by.return_value.first.return_value = None
        with patch('utils.gl_tenant.gl_entry_query', return_value=q), patch(
            'utils.gl_tenant.active_tenant_id', return_value=1
        ), pytest.raises(NotFound):
            AdvancedJournalEntryManager._entry_or_404(999)


class TestCreateEntryWithValidation:
    def test_rejects_unbalanced_lines(self):
        lines = [{'debit': 100, 'credit': 0}, {'debit': 0, 'credit': 50}]
        with pytest.raises(ValueError, match='غير متوازن'):
            AdvancedJournalEntryManager.create_entry_with_validation('bad', lines)

    def test_rejects_header_account(self):
        account = MagicMock(is_header=True, full_name='Assets')
        lines = [{'account_code': '1000', 'debit': 50, 'credit': 0}, {'debit': 0, 'credit': 50, 'account_code': '2000'}]
        with patch('utils.gl_tenant.get_gl_account_by_code', return_value=account), patch(
            'utils.gl_tenant.active_tenant_id', return_value=1
        ), pytest.raises(ValueError, match='الحساب الرئيسي'):
            AdvancedJournalEntryManager.create_entry_with_validation('hdr', lines)

    def test_creates_balanced_entry(self, mocker):
        entry = _mock_entry()
        mocker.patch('services.gl_service.GLService.create_manual_entry', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        lines = [{'debit': 100, 'credit': 0}, {'debit': 0, 'credit': 100}]
        result = AdvancedJournalEntryManager.create_entry_with_validation('ok', lines, created_by=1)
        assert result is entry


class TestUpdateEntry:
    def test_rejects_posted_entry(self):
        entry = _mock_entry(status='posted')
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError
        ):
            AdvancedJournalEntryManager.update_entry(1, {}, 1)

    def test_rejects_reversed_entry(self):
        entry = _mock_entry(status='reversed')
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError
        ):
            AdvancedJournalEntryManager.update_entry(1, {}, 1)

    def test_rejects_unbalanced_line_update(self):
        entry = _mock_entry()
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError, match='غير متوازن'
        ):
            AdvancedJournalEntryManager.update_entry(
                1, {'lines': [{'debit': 100, 'credit': 0}, {'debit': 0, 'credit': 50}]}, 1
            )

    def test_commits_on_success(self, mocker):
        entry = _mock_entry()
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        result = AdvancedJournalEntryManager.update_entry(1, {'description': 'new'}, 1)
        mock_db.session.flush.assert_called_once()
        assert result is entry

    def test_rolls_back_on_commit_failure(self, mocker):
        entry = _mock_entry()
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        mock_db.session.flush.side_effect = RuntimeError('db fail')
        with pytest.raises(RuntimeError):
            AdvancedJournalEntryManager.update_entry(1, {'description': 'x'}, 1)
        mock_db.session.flush.assert_called_once()


class TestReverseEntryAdvanced:
    def test_rejects_already_reversed(self):
        entry = _mock_entry(status='reversed')
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError, match='معكوس مسبقاً'
        ):
            AdvancedJournalEntryManager.reverse_entry_advanced(1, 1, 'reason')

    def test_rejects_unposted(self):
        entry = _mock_entry(status='draft')
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError, match='لا يمكن عكس قيد بحالة'
        ):
            AdvancedJournalEntryManager.reverse_entry_advanced(1, 1, 'reason')

    def test_creates_reversal_and_commits(self, mocker):
        entry = _mock_entry(status='posted')
        reversal = _mock_entry(id=2, status='posted')
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, 'create_entry_with_validation', return_value=reversal)
        mocker.patch.object(AdvancedJournalEntryManager, 'validate_entry', return_value=reversal)
        mocker.patch.object(AdvancedJournalEntryManager, 'post_entry', return_value=reversal)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        result = AdvancedJournalEntryManager.reverse_entry_advanced(1, 1, 'correction')
        assert result is reversal
        assert entry.is_reversed is True
        mock_db.session.flush.assert_called_once()

    def test_rolls_back_on_commit_failure(self, mocker):
        entry = _mock_entry(status='posted')
        reversal = _mock_entry(id=2, status='posted')
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, 'create_entry_with_validation', return_value=reversal)
        mocker.patch.object(AdvancedJournalEntryManager, 'validate_entry', return_value=reversal)
        mocker.patch.object(AdvancedJournalEntryManager, 'post_entry', return_value=reversal)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        mock_db.session.flush.side_effect = RuntimeError('fail')
        with pytest.raises(RuntimeError):
            AdvancedJournalEntryManager.reverse_entry_advanced(1, 1, 'correction')
        mock_db.session.flush.assert_called_once()


class TestDeleteEntry:
    def test_rejects_posted(self):
        entry = _mock_entry(status='posted')
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError
        ):
            AdvancedJournalEntryManager.delete_entry(1, 1, 'reason')

    def test_rejects_reversed_entry(self):
        entry = _mock_entry(status='reversed')
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError
        ):
            AdvancedJournalEntryManager.delete_entry(1, 1, 'reason')

    def test_rejects_linked_reversal(self):
        entry = _mock_entry(status='draft', reversed_entry_id=5)
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError, match='قيود عكسية'
        ):
            AdvancedJournalEntryManager.delete_entry(1, 1, 'reason')

    def test_soft_deletes_and_commits(self, mocker):
        entry = _mock_entry(status='draft')
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        assert AdvancedJournalEntryManager.delete_entry(1, 1, 'cleanup') is True
        assert entry.status == 'cancelled'
        mock_db.session.flush.assert_called_once()

    def test_delete_rollback_on_commit_failure(self, mocker):
        entry = _mock_entry(status='draft')
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        mock_db.session.flush.side_effect = RuntimeError('delete fail')
        with pytest.raises(RuntimeError):
            AdvancedJournalEntryManager.delete_entry(1, 1, 'cleanup')
        mock_db.session.flush.assert_called_once()


class TestApproveEntry:
    def test_rejects_already_posted(self):
        entry = _mock_entry(status='posted')
        with patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry), pytest.raises(
            ValueError
        ):
            AdvancedJournalEntryManager.approve_entry(1, 1)

    def test_rejects_unbalanced(self, mocker):
        entry = _mock_entry(status='draft')
        entry.lines[0].debit = Decimal('200')
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mocker.patch('services.advanced_journal_manager.db')
        result = AdvancedJournalEntryManager.approve_entry(1, 1)
        # validate_entry catches balance errors and sets status='error' instead of raising
        assert entry.status == 'error'

    def test_validates_entry(self, mocker):
        credit_line = MagicMock()
        credit_line.debit = Decimal('0')
        credit_line.credit = Decimal('100')
        entry = _mock_entry(status='draft', lines=[_mock_entry().lines[0], credit_line])
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mocker.patch('services.advanced_journal_manager.db')
        result = AdvancedJournalEntryManager.approve_entry(1, 1, 'ok')
        assert result is entry

    def test_approve_rollback_on_commit_failure(self, mocker):
        credit_line = MagicMock()
        credit_line.debit = Decimal('0')
        credit_line.credit = Decimal('100')
        entry = _mock_entry(status='draft', lines=[_mock_entry().lines[0], credit_line])
        mocker.patch.object(AdvancedJournalEntryManager, '_entry_or_404', return_value=entry)
        mocker.patch.object(AdvancedJournalEntryManager, '_log_audit')
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        mock_db.session.flush.side_effect = RuntimeError('fail')
        with pytest.raises(RuntimeError):
            AdvancedJournalEntryManager.approve_entry(1, 1)
        mock_db.session.flush.assert_called_once()


class TestGetEntryHistory:
    def test_returns_empty_when_entry_missing(self):
        q = MagicMock()
        q.filter_by.return_value.first.return_value = None
        with patch('utils.gl_tenant.gl_entry_query', return_value=q), patch(
            'utils.gl_tenant.active_tenant_id', return_value=1
        ):
            assert AdvancedJournalEntryManager.get_entry_history(1) == []

    def test_returns_audits_for_tenant(self):
        entry = _mock_entry(tenant_id=7)
        audit = MagicMock()
        q = MagicMock()
        q.filter_by.return_value.first.return_value = entry
        audit_q = MagicMock()
        audit_q.filter_by.return_value.order_by.return_value.all.return_value = [audit]
        with patch('utils.gl_tenant.gl_entry_query', return_value=q), patch(
            'utils.gl_tenant.active_tenant_id', return_value=7
        ), patch('services.advanced_journal_manager.JournalEntryAudit') as JEA:
            JEA.query = audit_q
            result = AdvancedJournalEntryManager.get_entry_history(1)
            assert result == [audit]


class TestLogAudit:
    def test_creates_audit_record(self, mocker):
        entry = _mock_entry(tenant_id=3)
        mocker.patch('services.advanced_journal_manager.GLJournalEntry').query.get.return_value = entry
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        AdvancedJournalEntryManager._log_audit(1, 'create', None, {'x': 1}, 'reason', 5)
        mock_db.session.add.assert_called_once()

    def test_log_audit_when_entry_missing(self, mocker):
        mocker.patch('services.advanced_journal_manager.GLJournalEntry').query.get.return_value = None
        mock_db = mocker.patch('services.advanced_journal_manager.db')
        AdvancedJournalEntryManager._log_audit(99, 'delete', {'id': 1}, None, 'gone', 2)
        added = mock_db.session.add.call_args[0][0]
        assert added.tenant_id is None


class TestHelperMethods:
    def test_to_dict_and_balance_helpers(self):
        add_helper_methods()
        entry = MagicMock()
        entry.id = 1
        entry.entry_number = 'JE-1'
        entry.entry_date = date(2026, 1, 1)
        entry.description = 'd'
        entry.entry_type = 'manual'
        entry.status = 'draft'
        entry.total_debit = Decimal('100')
        entry.total_credit = Decimal('100')
        entry.is_posted = False
        entry.is_reversed = False
        entry.reversed_entry_id = None
        entry.validation_errors = None
        entry.validated_at = None
        entry.notes = 'n'
        line = MagicMock()
        line.account.code = '1100'
        line.account.full_name = 'Cash'
        line.debit = Decimal('100')
        line.credit = Decimal('0')
        line.description = 'l'
        entry.lines = [line]
        d = GLJournalEntry.to_dict(entry)
        assert d['id'] == 1
        assert d['status'] == 'draft'
        assert GLJournalEntry.get_balance_status(entry) == 'balanced'
        assert GLJournalEntry.can_be_modified(entry) is True
        assert GLJournalEntry.can_be_reversed(entry) is False
        assert GLJournalEntry.can_be_deleted(entry) is True

    def test_minor_and_major_imbalance(self):
        add_helper_methods()
        entry = MagicMock(total_debit=Decimal('100'), total_credit=Decimal('95'))
        assert GLJournalEntry.get_balance_status(entry) == 'minor_imbalance'
        entry.total_credit = Decimal('50')
        assert GLJournalEntry.get_balance_status(entry) == 'major_imbalance'
