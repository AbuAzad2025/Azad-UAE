from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from extensions import db
from models import BankReconciliation, BankReconciliationItem, BankStatementLine, GLAccount, GLJournalEntry, GLJournalLine
from services.bank_reconciliation_service import BankReconciliationService


@pytest.fixture
def bank_gl_account(db_session, sample_tenant, sample_gl_accounts):
    acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code='1101').first()
    if acct is None:
        acct = GLAccount(
            tenant_id=sample_tenant.id,
            code='1101',
            name='Bank',
            type='asset',
            is_active=True,
        )
        db_session.add(acct)
        db_session.flush()
    return acct


@pytest.fixture
def draft_reconciliation(db_session, sample_tenant, bank_gl_account, sample_user):
    rec = BankReconciliation(
        tenant_id=sample_tenant.id,
        reconciliation_number=f'BR-{uuid.uuid4().hex[:6]}',
        bank_account_id=bank_gl_account.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        opening_balance_per_books=Decimal('1000'),
        closing_balance_per_books=Decimal('5000'),
        closing_balance_per_bank=Decimal('5000'),
        status='draft',
        created_by=sample_user.id,
    )
    db_session.add(rec)
    db_session.flush()
    return rec


class TestCreateReconciliation:
    def test_creates_with_auto_items(self, mocker, db_session, sample_tenant, bank_gl_account, incoming_cheque, outgoing_cheque, sample_user):
        mocker.patch(
            'services.gl_service.GLService.get_account_statement',
            return_value={'closing_balance': '4000', 'opening_balance': '1000'},
        )
        mocker.patch('services.bank_reconciliation_service.generate_number', return_value='BR-NEW-001')
        period_end = date.today()
        with patch('flask_login.utils._get_user', return_value=sample_user):
            rec = BankReconciliationService.create_reconciliation(
                bank_gl_account.id,
                date(2026, 1, 1),
                period_end,
                Decimal('4200'),
                created_by=sample_user.id,
            )
        assert rec.reconciliation_number == 'BR-NEW-001'
        assert rec.outstanding_deposits >= Decimal('1000')
        assert rec.outstanding_withdrawals >= Decimal('500')


class TestAdjustments:
    def test_add_bank_charge_draft_only(self, db_session, draft_reconciliation):
        item = BankReconciliationService.add_bank_charge(
            draft_reconciliation.id,
            Decimal('25'),
            'Monthly fee',
            transaction_date=date(2026, 1, 15),
        )
        assert item.item_type == 'bank_charge'
        assert draft_reconciliation.bank_charges == Decimal('25')

    def test_add_bank_charge_rejects_completed(self, db_session, draft_reconciliation):
        draft_reconciliation.status = 'completed'
        db_session.flush()
        with pytest.raises(ValueError, match='معتمدة'):
            BankReconciliationService.add_bank_charge(draft_reconciliation.id, Decimal('10'), 'fee')

    def test_add_bank_interest(self, db_session, draft_reconciliation):
        item = BankReconciliationService.add_bank_interest(
            draft_reconciliation.id,
            Decimal('-15'),
            'Interest credit',
        )
        assert item.amount == Decimal('15')
        assert draft_reconciliation.bank_interest == Decimal('15')


class TestCompleteReconciliation:
    def test_complete_balanced_posts_gl(self, mocker, db_session, draft_reconciliation):
        draft_reconciliation.bank_charges = Decimal('50')
        draft_reconciliation.bank_interest = Decimal('20')
        draft_reconciliation.outstanding_deposits = Decimal('0')
        draft_reconciliation.outstanding_withdrawals = Decimal('0')
        draft_reconciliation.closing_balance_per_bank = Decimal('4970')
        draft_reconciliation.calculate_reconciliation()
        db_session.flush()
        post = mocker.patch('services.gl_posting.post_or_fail')
        rec = BankReconciliationService.complete_reconciliation(draft_reconciliation.id)
        assert rec.status == 'completed'
        post.assert_called_once()

    def test_complete_unbalanced_raises(self, db_session, draft_reconciliation):
        draft_reconciliation.closing_balance_per_bank = Decimal('9999')
        db_session.flush()
        with pytest.raises(ValueError, match='غير متوازنة'):
            BankReconciliationService.complete_reconciliation(draft_reconciliation.id)

    def test_complete_already_done_raises(self, db_session, draft_reconciliation):
        draft_reconciliation.status = 'completed'
        db_session.flush()
        with pytest.raises(ValueError, match='معتمدة'):
            BankReconciliationService.complete_reconciliation(draft_reconciliation.id)


class TestSummaryAndImport:
    def test_get_reconciliation_summary(self, mocker, db_session, bank_gl_account, incoming_cheque, sample_tenant):
        incoming_cheque.due_date = date(2026, 3, 10)
        db_session.flush()
        mocker.patch(
            'utils.tenanting.tenant_get_or_404',
            return_value=bank_gl_account,
        )
        mocker.patch(
            'services.gl_service.GLService.get_account_statement',
            return_value={'closing_balance': 3000},
        )
        summary = BankReconciliationService.get_reconciliation_summary(
            bank_gl_account.id,
            date(2026, 3, 1),
            date(2026, 3, 31),
        )
        assert summary['closing_balance_per_books'] == 3000
        assert summary['outstanding_deposits_count'] >= 1

    def test_import_bank_statement_rows(self, db_session, sample_tenant, bank_gl_account):
        rows = [
            {'date': date(2026, 4, 1), 'reference': 'REF1', 'description': 'Deposit', 'amount': '1500', 'currency': 'AED'},
            {'date': date(2026, 4, 2), 'reference': 'REF2', 'description': 'Withdrawal', 'amount': '-200'},
        ]
        count = BankReconciliationService.import_bank_statement(
            sample_tenant.id,
            bank_gl_account.id,
            rows,
            statement_date=date(2026, 4, 30),
        )
        assert count == 2
        lines = BankStatementLine.query.filter_by(tenant_id=sample_tenant.id).all()
        assert len(lines) == 2
        assert lines[0].amount == Decimal('1500')


class TestAutoMatch:
    def test_auto_match_gl_lines(self, db_session, sample_tenant, bank_gl_account):
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 5, 1),
            transaction_date=date(2026, 5, 5),
            reference='STMT-1',
            description='Wire',
            amount=Decimal('750'),
            status='imported',
        )
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number=f'JE-{uuid.uuid4().hex[:6]}',
            entry_date=date(2026, 5, 5),
            is_posted=True,
            description='Payment',
        )
        db_session.add_all([stmt, entry])
        db_session.flush()
        line = GLJournalLine(
            tenant_id=sample_tenant.id,
            entry_id=entry.id,
            account_id=bank_gl_account.id,
            debit=Decimal('750'),
            credit=Decimal('0'),
        )
        db_session.add(line)
        db_session.flush()

        matches = BankReconciliationService.auto_match_gl_lines(
            sample_tenant.id,
            bank_gl_account.id,
            date(2026, 5, 1),
            date(2026, 5, 31),
        )
        assert len(matches) == 1
        assert matches[0]['statement_line_id'] == stmt.id

    def test_match_transaction_unique(self, db_session, sample_tenant, bank_gl_account):
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 6, 1),
            transaction_date=date(2026, 6, 10),
            amount=Decimal('300'),
            status='imported',
        )
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number=f'JE-{uuid.uuid4().hex[:6]}',
            entry_date=date(2026, 6, 9),
            is_posted=True,
        )
        db_session.add_all([stmt, entry])
        db_session.flush()
        gl_line = GLJournalLine(
            tenant_id=sample_tenant.id,
            entry_id=entry.id,
            account_id=bank_gl_account.id,
            debit=Decimal('300'),
            credit=Decimal('0'),
        )
        db_session.add(gl_line)
        db_session.flush()

        result = BankReconciliationService.match_transaction(
            sample_tenant.id, bank_gl_account.id, stmt.id,
        )
        assert result is not None
        assert result['journal_line_id'] == gl_line.id

    def test_match_transaction_no_candidate(self, db_session, sample_tenant, bank_gl_account):
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 6, 1),
            transaction_date=date(2026, 6, 10),
            amount=Decimal('999'),
            status='imported',
        )
        db_session.add(stmt)
        db_session.flush()
        assert BankReconciliationService.match_transaction(sample_tenant.id, bank_gl_account.id, stmt.id) is None


class TestSuspenseAndApply:
    def test_route_orphans_to_suspense(self, mocker, db_session, sample_tenant, bank_gl_account):
        suspense = GLAccount(tenant_id=sample_tenant.id, code='2999', name='Suspense', type='liability', is_active=True)
        db_session.add(suspense)
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 7, 1),
            transaction_date=date(2026, 7, 5),
            amount=Decimal('400'),
            description='Unknown',
            status='imported',
        )
        db_session.add(stmt)
        db_session.flush()
        mock_entry = MagicMock(id=88)
        mocker.patch('services.gl_posting.post_or_fail', return_value=mock_entry)
        results = BankReconciliationService.route_orphans_to_suspense(
            sample_tenant.id,
            bank_gl_account.id,
            date(2026, 7, 1),
            date(2026, 7, 31),
        )
        assert len(results) == 1
        assert stmt.status == 'suggested_match'

    def test_apply_matches(self, db_session, draft_reconciliation, sample_tenant, bank_gl_account):
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 8, 1),
            transaction_date=date(2026, 8, 3),
            amount=Decimal('100'),
            status='imported',
        )
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number=f'JE-{uuid.uuid4().hex[:6]}',
            entry_date=date(2026, 8, 3),
            is_posted=True,
        )
        db_session.add_all([stmt, entry])
        db_session.flush()
        gl_line = GLJournalLine(
            tenant_id=sample_tenant.id,
            entry_id=entry.id,
            account_id=bank_gl_account.id,
            debit=Decimal('100'),
            credit=Decimal('0'),
        )
        db_session.add(gl_line)
        db_session.flush()

        rec = BankReconciliationService.apply_matches(
            draft_reconciliation.id,
            [{'statement_line_id': stmt.id, 'journal_line_id': gl_line.id, 'match_type': 'exact'}],
        )
        assert rec.id == draft_reconciliation.id
        assert stmt.status == 'matched'

    def test_apply_matches_rejects_completed(self, db_session, draft_reconciliation):
        draft_reconciliation.status = 'completed'
        db_session.flush()
        with pytest.raises(ValueError, match='معتمدة'):
            BankReconciliationService.apply_matches(draft_reconciliation.id, [])

    def test_apply_matches_skips_missing_rows(self, db_session, draft_reconciliation):
        rec = BankReconciliationService.apply_matches(
            draft_reconciliation.id,
            [{'statement_line_id': 99999, 'journal_line_id': 88888, 'match_type': 'exact'}],
        )
        assert rec.id == draft_reconciliation.id

    def test_import_bank_statement_empty(self, db_session, sample_tenant, bank_gl_account):
        assert BankReconciliationService.import_bank_statement(sample_tenant.id, bank_gl_account.id, []) == 0

    def test_match_transaction_wrong_tenant(self, db_session, sample_tenant, bank_gl_account):
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 6, 1),
            transaction_date=date(2026, 6, 10),
            amount=Decimal('300'),
            status='imported',
        )
        db_session.add(stmt)
        db_session.flush()
        assert BankReconciliationService.match_transaction(99999, bank_gl_account.id, stmt.id) is None

    def test_match_transaction_bad_status(self, db_session, sample_tenant, bank_gl_account):
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 6, 1),
            transaction_date=date(2026, 6, 10),
            amount=Decimal('300'),
            status='matched',
        )
        db_session.add(stmt)
        db_session.flush()
        assert BankReconciliationService.match_transaction(sample_tenant.id, bank_gl_account.id, stmt.id) is None

    def test_add_bank_interest_rejects_completed(self, db_session, draft_reconciliation):
        draft_reconciliation.status = 'completed'
        db_session.flush()
        with pytest.raises(ValueError, match='معتمدة'):
            BankReconciliationService.add_bank_interest(draft_reconciliation.id, Decimal('5'), 'int')

    def test_route_orphans_empty_period(self, db_session, sample_tenant, bank_gl_account):
        assert BankReconciliationService.route_orphans_to_suspense(
            sample_tenant.id, bank_gl_account.id, date(2026, 1, 1), date(2026, 1, 31),
        ) == []

    def test_route_orphans_post_failure(self, mocker, db_session, sample_tenant, bank_gl_account):
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 7, 1),
            transaction_date=date(2026, 7, 5),
            amount=Decimal('400'),
            status='imported',
        )
        db_session.add(stmt)
        db_session.flush()
        mocker.patch('services.gl_posting.post_or_fail', side_effect=RuntimeError('gl'))
        results = BankReconciliationService.route_orphans_to_suspense(
            sample_tenant.id, bank_gl_account.id, date(2026, 7, 1), date(2026, 7, 31),
        )
        assert results == []
        assert stmt.status == 'ignored'

    def test_route_orphans_ignores_tiny_amount(self, mocker, db_session, sample_tenant, bank_gl_account):
        stmt = BankStatementLine(
            tenant_id=sample_tenant.id,
            bank_account_id=bank_gl_account.id,
            statement_date=date(2026, 7, 1),
            transaction_date=date(2026, 7, 5),
            amount=Decimal('0.001'),
            status='imported',
        )
        db_session.add(stmt)
        db_session.flush()
        mocker.patch('services.gl_posting.post_or_fail')
        results = BankReconciliationService.route_orphans_to_suspense(
            sample_tenant.id, bank_gl_account.id, date(2026, 7, 1), date(2026, 7, 31),
        )
        assert results == []
        assert stmt.status == 'ignored'


class TestBankReconciliationModel:
    def test_status_ar_known_and_unknown(self, draft_reconciliation):
        draft_reconciliation.status = 'draft'
        assert draft_reconciliation.status_ar == 'مسودة'
        draft_reconciliation.status = 'unknown'
        assert draft_reconciliation.status_ar == 'unknown'

    def test_calculate_reconciliation_balanced(self, draft_reconciliation):
        draft_reconciliation.closing_balance_per_books = Decimal('1000')
        draft_reconciliation.closing_balance_per_bank = Decimal('1000')
        draft_reconciliation.outstanding_deposits = Decimal('0')
        draft_reconciliation.outstanding_withdrawals = Decimal('0')
        draft_reconciliation.bank_charges = Decimal('0')
        draft_reconciliation.bank_interest = Decimal('0')
        draft_reconciliation.errors_in_books = Decimal('0')
        draft_reconciliation.errors_in_bank = Decimal('0')
        result = draft_reconciliation.calculate_reconciliation()
        assert result['is_balanced'] is True
        assert draft_reconciliation.is_balanced is True

    def test_approve_balanced(self, db_session, draft_reconciliation, sample_user):
        draft_reconciliation.closing_balance_per_books = Decimal('500')
        draft_reconciliation.closing_balance_per_bank = Decimal('500')
        draft_reconciliation.calculate_reconciliation()
        draft_reconciliation.approve(sample_user.id)
        assert draft_reconciliation.status == 'approved'
        assert draft_reconciliation.approved_by == sample_user.id
        assert draft_reconciliation.approved_at is not None

    def test_approve_unbalanced_raises(self, draft_reconciliation, sample_user):
        draft_reconciliation.closing_balance_per_books = Decimal('500')
        draft_reconciliation.closing_balance_per_bank = Decimal('400')
        draft_reconciliation.calculate_reconciliation()
        with pytest.raises(ValueError, match='غير متوازنة'):
            draft_reconciliation.approve(sample_user.id)

    def test_item_type_ar(self, db_session, draft_reconciliation, sample_tenant):
        item = BankReconciliationItem(
            tenant_id=sample_tenant.id,
            reconciliation_id=draft_reconciliation.id,
            item_type='bank_charge',
            transaction_date=date(2026, 6, 1),
            description='Fee',
            amount=Decimal('10'),
        )
        assert item.item_type_ar == 'مصروف بنكي'
        item.item_type = 'custom_type'
        assert item.item_type_ar == 'custom_type'
