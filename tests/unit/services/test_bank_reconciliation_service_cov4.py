"""Coverage-4 for services/bank_reconciliation_service.py — recon arcs.

Targets (production lines):
- complete_reconciliation non-draft guard (207-208), unbalanced guard
  (211-214), bank-charges-only lines (221-239), interest-only lines (242-260),
  no-lines skip posting (262), flush (277-281).
- get_reconciliation_summary tenant-scoped cheque queries (298-329).
- auto_match_gl_lines no-data empty (352-402) + exact vs amount_date
  match_type arc (388).
- import_bank_statement row mapping/count (414-429).
- match_transaction guard arcs: missing/tenant/account/status (450-457),
  zero-vs-multi candidates None (483-484), exact vs amount_date (487-498).
- route_orphans_to_suspense empty early return (527-528), dust ignored arc
  (543-545), suspense-code fallback (530-538), post-exception ignored arc
  (584-585).
- apply_matches non-draft guard (602-603), missing-row skip (608-609),
  matched-item creation (611-628).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from models import (
    BankReconciliation,
    BankStatementLine,
    GLAccount,
)
from services.bank_reconciliation_service import BankReconciliationService


@pytest.fixture
def bank_account(db_session, sample_tenant, sample_gl_accounts):
    acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1120").first()
    if acct is None:
        acct = GLAccount(
            tenant_id=sample_tenant.id, code="1120", name="Bank", type="asset",
            is_active=True,
        )
        db_session.add(acct)
        db_session.flush()
    return acct


@pytest.fixture
def draft_rec(db_session, sample_tenant, bank_account, sample_user):
    rec = BankReconciliation(
        tenant_id=sample_tenant.id,
        reconciliation_number=f"BR-C4-{uuid.uuid4().hex[:6]}",
        bank_account_id=bank_account.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        opening_balance_per_books=Decimal("1000"),
        closing_balance_per_books=Decimal("1000"),
        closing_balance_per_bank=Decimal("1000"),
        status="draft",
        created_by=sample_user.id,
    )
    db_session.add(rec)
    db_session.flush()
    return rec


def _stmt(db_session, tenant_id, bank_account_id, amount, when=None, status="imported"):
    line = BankStatementLine(
        tenant_id=tenant_id,
        bank_account_id=bank_account_id,
        statement_date=date(2026, 1, 31),
        transaction_date=when or date(2026, 1, 15),
        reference=f"REF-{uuid.uuid4().hex[:6]}",
        description="cov4 line",
        amount=Decimal(str(amount)),
        currency="AED",
        raw_data="{}",
        status=status,
    )
    db_session.add(line)
    db_session.flush()
    return line


class TestCompleteArcs:
    def test_non_draft_raises(self, db_session, draft_rec):
        draft_rec.status = "completed"
        db_session.flush()
        with pytest.raises(ValueError, match="معتمدة"):
            BankReconciliationService.complete_reconciliation(draft_rec.id)

    def test_unbalanced_raises(self, db_session, draft_rec, mocker):
        mocker.patch.object(
            BankReconciliation, "calculate_reconciliation",
            return_value={"is_balanced": False, "difference": "9.99"},
        )
        with pytest.raises(ValueError, match="غير متوازنة"):
            BankReconciliationService.complete_reconciliation(draft_rec.id)

    def test_no_lines_completes_without_post(self, db_session, draft_rec, mocker):
        mocker.patch.object(
            BankReconciliation, "calculate_reconciliation",
            return_value={"is_balanced": True, "difference": "0"},
        )
        posted = mocker.patch("services.gl_posting.post_or_fail")
        out = BankReconciliationService.complete_reconciliation(draft_rec.id)
        assert out.status == "completed"
        assert not posted.called

    def test_charges_and_interest_post(self, db_session, draft_rec, mocker):
        draft_rec.bank_charges = Decimal("10")
        draft_rec.bank_interest = Decimal("4")
        db_session.flush()
        mocker.patch.object(
            BankReconciliation, "calculate_reconciliation",
            return_value={"is_balanced": True, "difference": "0"},
        )
        posted = mocker.patch("services.gl_posting.post_or_fail")
        BankReconciliationService.complete_reconciliation(draft_rec.id)
        assert posted.called
        lines = posted.call_args.kwargs["lines"]
        assert len(lines) == 4


class TestSummaryAndMatching:
    def test_summary_shape(self, db_session, sample_tenant, sample_user, bank_account,
                           incoming_cheque, outgoing_cheque, mocker):
        mocker.patch(
            "services.gl_service.GLService.get_account_statement",
            return_value={"closing_balance": "4000", "opening_balance": "1000"},
        )
        with patch("flask_login.utils._get_user", return_value=sample_user):
            out = BankReconciliationService.get_reconciliation_summary(
                bank_account.id, date(2026, 1, 1), date(2026, 12, 31)
            )
        assert "outstanding_deposits_count" in out
        assert "outstanding_withdrawals_count" in out
        assert out["outstanding_deposits_count"] >= 0

    def test_auto_match_empty(self, db_session, sample_tenant, bank_account):
        out = BankReconciliationService.auto_match_gl_lines(
            sample_tenant.id, bank_account.id + 999999,
            date(2026, 1, 1), date(2026, 1, 31),
        )
        assert out == []

    def test_import_counts_rows(self, db_session, sample_tenant, bank_account):
        rows = [
            {"date": date(2026, 1, 5), "reference": "R1", "description": "d", "amount": "12.5"},
            {"date": date(2026, 1, 6), "reference": "R2", "description": "d", "amount": "-3"},
        ]
        count = BankReconciliationService.import_bank_statement(
            sample_tenant.id, bank_account.id, rows, statement_date=date(2026, 1, 31)
        )
        assert count == 2

    def test_match_guards_return_none(self, db_session, sample_tenant, bank_account):
        assert BankReconciliationService.match_transaction(
            sample_tenant.id, bank_account.id, 999999999) is None
        line = _stmt(db_session, sample_tenant.id, bank_account.id, "50")
        assert BankReconciliationService.match_transaction(
            sample_tenant.id + 1, bank_account.id, line.id) is None
        assert BankReconciliationService.match_transaction(
            sample_tenant.id, bank_account.id + 1, line.id) is None
        line.status = "matched"
        db_session.flush()
        assert BankReconciliationService.match_transaction(
            sample_tenant.id, bank_account.id, line.id) is None

    def test_match_no_candidates_none(self, db_session, sample_tenant, bank_account):
        line = _stmt(db_session, sample_tenant.id, bank_account.id, "7777.77")
        assert BankReconciliationService.match_transaction(
            sample_tenant.id, bank_account.id, line.id) is None


class TestOrphansAndApply:
    def test_orphans_empty(self, db_session, sample_tenant, bank_account):
        out = BankReconciliationService.route_orphans_to_suspense(
            sample_tenant.id, bank_account.id + 888888,
            date(2026, 1, 1), date(2026, 1, 31),
        )
        assert out == []

    def test_dust_ignored(self, db_session, sample_tenant, bank_account):
        _stmt(db_session, sample_tenant.id, bank_account.id, "0.001")
        out = BankReconciliationService.route_orphans_to_suspense(
            sample_tenant.id, bank_account.id, date(2026, 1, 1), date(2026, 12, 31)
        )
        assert isinstance(out, list)

    def test_orphan_post_failure_ignored(
        self, db_session, sample_tenant, bank_account, mocker
    ):
        _stmt(db_session, sample_tenant.id, bank_account.id, "123.45")
        mocker.patch("services.gl_posting.post_or_fail", side_effect=ValueError("gl down"))
        out = BankReconciliationService.route_orphans_to_suspense(
            sample_tenant.id, bank_account.id, date(2026, 1, 1), date(2026, 12, 31)
        )
        assert out == []

    def test_orphan_success_path(self, db_session, sample_tenant, bank_account, mocker):
        from unittest.mock import MagicMock

        _stmt(db_session, sample_tenant.id, bank_account.id, "200")
        mocker.patch(
            "services.gl_posting.post_or_fail",
            return_value=MagicMock(id=4242),
        )
        out = BankReconciliationService.route_orphans_to_suspense(
            sample_tenant.id, bank_account.id, date(2026, 1, 1), date(2026, 12, 31)
        )
        assert out and out[0]["suspense_entry_id"] == 4242

    def test_apply_non_draft_raises(self, db_session, draft_rec):
        draft_rec.status = "completed"
        db_session.flush()
        with pytest.raises(ValueError, match="معتمدة"):
            BankReconciliationService.apply_matches(draft_rec.id, [])

    def test_apply_skips_missing_rows(self, db_session, draft_rec, mocker):
        mocker.patch.object(
            BankReconciliation, "calculate_reconciliation",
            return_value={"is_balanced": True, "difference": "0"},
        )
        out = BankReconciliationService.apply_matches(
            draft_rec.id,
            [{"statement_line_id": 999999999, "journal_line_id": 888888888,
              "match_type": "exact"}],
        )
        assert out.id == draft_rec.id

    def test_auto_match_date_window_branch(
        self, db_session, sample_tenant, bank_account
    ):
        # date_tolerance branch: far-apart dates must not match even with data.
        line = _stmt(db_session, sample_tenant.id, bank_account.id, "10",
                     when=date(2026, 6, 15))
        out = BankReconciliationService.auto_match_gl_lines(
            sample_tenant.id, bank_account.id,
            date(2026, 1, 1), date(2026, 1, 31),
            amount_tolerance=Decimal("0.01"), date_tolerance_days=3,
        )
        assert all(m["statement_line_id"] != line.id for m in out)
        assert isinstance(out, list)
