"""
Chunk 1 — Accounting & Finance Assurance.

Tests:
  * GL double-entry balanced posting enforcement
  * Partner multi-level profit/loss distribution & loss-sharing validation
  * Bank reconciliation auto-matching & orphan suspense routing
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


# ===================================================================
# TestGLDoubleEntryBalance
# ===================================================================

class TestGLDoubleEntryBalance:
    """assert_balanced_lines / post_or_fail enforce Sum(Debit)==Sum(Credit)."""

    def test_assert_balanced_lines_accepts_perfectly_balanced(self):
        from services.gl_posting import assert_balanced_lines
        lines = [
            {'debit': Decimal('100'), 'credit': Decimal('0')},
            {'debit': Decimal('0'), 'credit': Decimal('100')},
        ]
        assert_balanced_lines(lines, currency='AED')

    def test_assert_balanced_lines_rejects_debit_skew(self):
        from services.gl_posting import assert_balanced_lines, UnbalancedJournalEntryError
        lines = [
            {'debit': Decimal('200'), 'credit': Decimal('0')},
            {'debit': Decimal('0'), 'credit': Decimal('100')},
        ]
        with pytest.raises(UnbalancedJournalEntryError, match='غير متوازن'):
            assert_balanced_lines(lines, currency='AED')

    def test_assert_balanced_lines_rejects_credit_skew(self):
        from services.gl_posting import assert_balanced_lines, UnbalancedJournalEntryError
        lines = [
            {'debit': Decimal('50'), 'credit': Decimal('0')},
            {'debit': Decimal('0'), 'credit': Decimal('150')},
        ]
        with pytest.raises(UnbalancedJournalEntryError, match='غير متوازن'):
            assert_balanced_lines(lines, currency='AED')

    def test_post_or_fail_rejects_unbalanced_with_app_context(self, app):
        from services.gl_posting import post_or_fail, UnbalancedJournalEntryError
        unbalanced = [
            {'debit': Decimal('300'), 'credit': Decimal('0')},
            {'debit': Decimal('0'), 'credit': Decimal('100')},
        ]
        with pytest.raises(UnbalancedJournalEntryError, match='غير متوازن'):
            post_or_fail(unbalanced, description='Test', tenant_id=1)

    def test_post_or_fail_passes_balanced_with_app_context(self, app, mocker, sample_tenant):
        from services.gl_posting import post_or_fail
        mock_entry = MagicMock(id=42)
        mocker.patch('services.gl_posting.GLService.create_journal_entry', return_value=MagicMock(id=1))
        mocker.patch('services.advanced_journal_manager.AdvancedJournalEntryManager.validate_entry',
                      return_value=MagicMock(status='validated'))
        mocker.patch('services.advanced_journal_manager.AdvancedJournalEntryManager.post_entry',
                      return_value=mock_entry)
        balanced = [
            {'debit': Decimal('250'), 'credit': Decimal('0')},
            {'debit': Decimal('0'), 'credit': Decimal('250')},
        ]
        result = post_or_fail(balanced, description='Test balanced', tenant_id=sample_tenant.id)
        assert result.id == 42




# ===================================================================
# TestPartnerProfitAndLossDistribution
# ===================================================================

class TestPartnerProfitAndLossDistribution:
    """Parametrized profit/loss distribution with scope-level P&L."""

    @staticmethod
    def _make_partner(**kwargs):
        p = MagicMock()
        attrs = dict(id=1, tenant_id=1, is_active=True, scope_type='company',
                     scope_id=None, share_percentage=Decimal('50'),
                     expense_share_percentage=Decimal('0'),
                     loss_share_percentage=Decimal('0'),
                     fixed_monthly_amount=Decimal('0'),
                     min_profit_threshold=Decimal('0'))
        attrs.update(kwargs)
        for k, v in attrs.items():
            setattr(p, k, v)
        return p

    @staticmethod
    def _patch_partner_query(model_patch, partners):
        partner = model_patch('models.Partner', count=len(partners))
        partner.query.filter_by.return_value.all.return_value = partners
        debit_note = model_patch('models.PartnerProfitDistribution', count=0)
        debit_note.query.filter_by.return_value.first.return_value = None
        return partner

    def _run_dist(self, app, mocker, model_patch, partners, pnl):
        self._patch_partner_query(model_patch, partners)
        mocker.patch('services.partner_service.PartnerService.calculate_scope_profit', return_value=pnl)
        # Patch db session operations so create_distributions doesn't try to
        # flush/commit MagicMock model instances into the real DB.
        mocker.patch('services.partner_service.db.session.add')
        mocker.patch('services.partner_service.db.session.flush')
        mocker.patch('services.partner_service.db.session.commit')
        from services.partner_service import PartnerService
        return PartnerService.create_distributions(
            tenant_id=1, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        )

    def test_clean_profit_distribution(self, app, mocker, model_patch):
        ids = self._run_dist(app, mocker, model_patch,
            partners=[self._make_partner()],
            pnl={'revenue': 20000.0, 'cogs': 5000.0, 'expenses': 5000.0,
                 'gross_profit': 15000.0, 'net_profit': 10000.0},
        )

    def test_loss_sharing_distribution(self, app, mocker, model_patch):
        ids = self._run_dist(app, mocker, model_patch,
            partners=[self._make_partner(loss_share_percentage=Decimal('50'))],
            pnl={'revenue': 5000.0, 'cogs': 8000.0, 'expenses': 2000.0,
                 'gross_profit': -3000.0, 'net_profit': -5000.0},
        )

    def test_loss_sharing_missing_percentage_raises(self, app, mocker, model_patch):
        with pytest.raises(ValueError, match='نسبة تحمل خسارة'):
            self._run_dist(app, mocker, model_patch,
                partners=[self._make_partner(loss_share_percentage=Decimal('0'))],
                pnl={'revenue': 0, 'cogs': 0, 'expenses': 0,
                     'gross_profit': 0, 'net_profit': -3000.0},
            )

    def test_total_share_exceeds_100_raises(self, app, model_patch):
        partner = model_patch('models.Partner', count=2)
        partner.query.filter_by.return_value.all.return_value = [
            self._make_partner(share_percentage=Decimal('60')),
            self._make_partner(share_percentage=Decimal('50'), id=2),
        ]
        model_patch('models.PartnerProfitDistribution', count=0)
        from services.partner_service import PartnerService
        with pytest.raises(ValueError, match='يتجاوز 100%'):
            PartnerService.create_distributions(
                tenant_id=1, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
            )

    def test_distribution_scope_branch(self, app, mocker, model_patch):
        ids = self._run_dist(app, mocker, model_patch,
            partners=[self._make_partner(scope_type='branch', scope_id=5, share_percentage=Decimal('30'))],
            pnl={'revenue': 15000.0, 'cogs': 5000.0, 'expenses': 2000.0,
                 'gross_profit': 10000.0, 'net_profit': 8000.0},
        )

    def test_distribution_scope_warehouse(self, app, mocker, model_patch):
        ids = self._run_dist(app, mocker, model_patch,
            partners=[self._make_partner(scope_type='warehouse', scope_id=10, share_percentage=Decimal('20'))],
            pnl={'revenue': 10000.0, 'cogs': 4000.0, 'expenses': 1000.0,
                 'gross_profit': 6000.0, 'net_profit': 5000.0},
        )


# ===================================================================
# TestBankAutoMatchingAndSuspenseRouting
# ===================================================================

class TestBankAutoMatchingAndSuspenseRouting:
    """Auto-match on clean hits; route orphans to Suspense."""

    @staticmethod
    def _setup_match_mocks(mocker, stmt, gl_lines):
        mocker.patch('services.bank_reconciliation_service.db.session.get', return_value=stmt)
        mock_q = MagicMock()
        mock_q.return_value = mock_q
        mock_q.join.return_value.filter.return_value.all.return_value = gl_lines
        mocker.patch('services.bank_reconciliation_service.db.session.query', return_value=mock_q)

    def test_auto_match_exact_hit(self, app, mocker):
        stmt = MagicMock()
        stmt.id = 1
        stmt.tenant_id = 1
        stmt.bank_account_id = 100
        stmt.transaction_date = date(2026, 2, 15)
        stmt.amount = Decimal('1500')
        stmt.description = 'Test payment'
        stmt.reference = 'REF-001'
        stmt.status = 'imported'

        gl = MagicMock(id=10, debit=Decimal('1500'), credit=Decimal('0'))
        gl.entry = MagicMock(entry_date=date(2026, 2, 14))

        self._setup_match_mocks(mocker, stmt, [gl])

        from services.bank_reconciliation_service import BankReconciliationService
        result = BankReconciliationService.match_transaction(
            tenant_id=1, bank_account_id=100, stmt_line_id=1,
        )
        assert result is not None
        assert result['statement_line_id'] == 1
        assert result['journal_line_id'] == 10

    def test_auto_match_no_unique_candidate_returns_none(self, app, mocker):
        stmt = MagicMock()
        stmt.id = 1
        stmt.tenant_id = 1
        stmt.bank_account_id = 100
        stmt.transaction_date = date(2026, 2, 15)
        stmt.amount = Decimal('1500')
        stmt.status = 'imported'

        self._setup_match_mocks(mocker, stmt, [])

        from services.bank_reconciliation_service import BankReconciliationService
        result = BankReconciliationService.match_transaction(
            tenant_id=1, bank_account_id=100, stmt_line_id=1,
        )
        assert result is None

    @staticmethod
    def _setup_orphan_mocks(mocker, stmts):
        bsl = mocker.patch('services.bank_reconciliation_service.BankStatementLine')
        bsl.query.filter.return_value.all.return_value = stmts
        gla = mocker.patch('services.bank_reconciliation_service.GLAccount')
        gla.query.filter_by.return_value.filter.return_value.first.return_value = MagicMock(code='2999')
        mock_entry = MagicMock(id=99)
        mocker.patch('services.gl_posting.post_or_fail', return_value=mock_entry)
        return bsl

    def test_orphan_routed_to_suspense(self, app, mocker):
        stmt = MagicMock()
        stmt.id = 5
        stmt.tenant_id = 1
        stmt.bank_account_id = 100
        stmt.transaction_date = date(2026, 3, 1)
        stmt.amount = Decimal('750')
        stmt.description = 'Orphan payment'
        stmt.reference = 'ORPH-001'
        stmt.status = 'imported'

        self._setup_orphan_mocks(mocker, [stmt])

        from services.bank_reconciliation_service import BankReconciliationService
        results = BankReconciliationService.route_orphans_to_suspense(
            tenant_id=1, bank_account_id=100,
            period_start=date(2026, 3, 1), period_end=date(2026, 3, 31),
        )
        assert len(results) == 1
        assert results[0]['statement_line_id'] == 5

    def test_orphan_negative_amount_creates_reverse_entry(self, app, mocker):
        stmt = MagicMock()
        stmt.id = 6
        stmt.tenant_id = 1
        stmt.bank_account_id = 100
        stmt.transaction_date = date(2026, 3, 5)
        stmt.amount = Decimal('-200')
        stmt.description = 'Bank charge orphan'
        stmt.reference = 'ORPH-002'
        stmt.status = 'imported'

        self._setup_orphan_mocks(mocker, [stmt])

        from services.bank_reconciliation_service import BankReconciliationService
        results = BankReconciliationService.route_orphans_to_suspense(
            tenant_id=1, bank_account_id=100,
            period_start=date(2026, 3, 1), period_end=date(2026, 3, 31),
        )
        assert len(results) == 1

    def test_match_transaction_ambiguous_returns_none(self, app, mocker):
        stmt = MagicMock()
        stmt.id = 1
        stmt.tenant_id = 1
        stmt.bank_account_id = 100
        stmt.transaction_date = date(2026, 2, 15)
        stmt.amount = Decimal('1500')
        stmt.status = 'imported'

        gl_a = MagicMock(id=10, debit=Decimal('1500'), credit=Decimal('0'))
        gl_a.entry = MagicMock(entry_date=date(2026, 2, 14))
        gl_b = MagicMock(id=11, debit=Decimal('1500'), credit=Decimal('0'))
        gl_b.entry = MagicMock(entry_date=date(2026, 2, 16))

        mocker.patch('services.bank_reconciliation_service.db.session.get', return_value=stmt)
        mock_q = MagicMock()
        mock_q.return_value = mock_q
        mock_q.join.return_value.filter.return_value.all.return_value = [gl_a, gl_b]
        mocker.patch('services.bank_reconciliation_service.db.session.query', return_value=mock_q)

        from services.bank_reconciliation_service import BankReconciliationService
        result = BankReconciliationService.match_transaction(
            tenant_id=1, bank_account_id=100, stmt_line_id=1,
        )
        assert result is None

    def test_route_orphans_updates_status_to_suggested_match(self, app, mocker):
        stmt = MagicMock()
        stmt.id = 7
        stmt.tenant_id = 1
        stmt.bank_account_id = 100
        stmt.transaction_date = date(2026, 4, 1)
        stmt.amount = Decimal('1200')
        stmt.description = 'After suspense'
        stmt.reference = 'SUS-001'
        stmt.status = 'imported'

        bsl = self._setup_orphan_mocks(mocker, [stmt])
        bsl.query.get.return_value = stmt

        from services.bank_reconciliation_service import BankReconciliationService
        BankReconciliationService.route_orphans_to_suspense(
            tenant_id=1, bank_account_id=100,
            period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        )
        assert stmt.status == 'suggested_match'

    def test_no_orphans_returns_empty(self, app, mocker):
        bsl = mocker.patch('services.bank_reconciliation_service.BankStatementLine')
        bsl.query.filter.return_value.all.return_value = []
        from services.bank_reconciliation_service import BankReconciliationService
        results = BankReconciliationService.route_orphans_to_suspense(
            tenant_id=1, bank_account_id=100,
            period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
        )
        assert results == []


# ===================================================================
# TestGLConceptRegistry
# ===================================================================

class TestGLConceptRegistry:
    """SUSPENSE concept was added to the registry."""

    def test_suspense_concept_in_registry(self):
        from models._constants import GL_CONCEPT_SUSPENSE, GL_CONCEPT_REGISTRY
        assert GL_CONCEPT_SUSPENSE == 'SUSPENSE'
        assert GL_CONCEPT_SUSPENSE in GL_CONCEPT_REGISTRY
        assert GL_CONCEPT_REGISTRY[GL_CONCEPT_SUSPENSE]['legacy_code'] == '2999'

    def test_suspense_concept_in_codes(self):
        from models._constants import GL_CONCEPT_SUSPENSE, GL_CONCEPT_CODES
        assert GL_CONCEPT_SUSPENSE in GL_CONCEPT_CODES
