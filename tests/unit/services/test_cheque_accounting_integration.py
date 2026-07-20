from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from models.gl import GLJournalEntry, GLJournalLine
from services.cheque_accounting_integration import ChequeAccountingIntegration
from utils.gl_reference_types import GLRef


class TestReceiveCheque:
    def test_rejects_outgoing_type(self, db_session, outgoing_cheque):
        with pytest.raises(ValueError, match="وارد"):
            ChequeAccountingIntegration.receive_cheque(outgoing_cheque.id)

    def test_rejects_non_pending(self, db_session, incoming_cheque):
        incoming_cheque.status = "cleared"
        db_session.flush()
        with pytest.raises(ValueError, match="معلق"):
            ChequeAccountingIntegration.receive_cheque(incoming_cheque.id)

    def test_success_commits(self, mocker, incoming_cheque):
        entry = MagicMock()
        mocker.patch(
            "services.cheque_accounting_integration.process_cheque_receive",
            return_value=entry,
        )
        result = ChequeAccountingIntegration.receive_cheque(incoming_cheque.id)
        assert result is entry

    def test_failure_rolls_back(self, mocker, incoming_cheque):
        mocker.patch(
            "services.cheque_accounting_integration.process_cheque_receive",
            side_effect=RuntimeError("gl"),
        )
        with pytest.raises(Exception, match="فشل"):
            ChequeAccountingIntegration.receive_cheque(incoming_cheque.id)


class TestIssueCheque:
    def test_rejects_incoming_type(self, incoming_cheque):
        with pytest.raises(ValueError, match="صادر"):
            ChequeAccountingIntegration.issue_cheque(incoming_cheque.id)

    def test_rejects_non_pending(self, db_session, outgoing_cheque):
        outgoing_cheque.status = "cleared"
        db_session.flush()
        with pytest.raises(ValueError, match="معلق"):
            ChequeAccountingIntegration.issue_cheque(outgoing_cheque.id)

    def test_success_returns_entry(self, mocker, outgoing_cheque, db_session, sample_tenant):
        mocker.patch("services.cheque_accounting_integration.process_cheque_issue")
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-ISSUE-1",
            reference_type=GLRef.CHEQUE_ISSUE,
            reference_id=outgoing_cheque.id,
        )
        db_session.add(entry)
        db_session.flush()
        result = ChequeAccountingIntegration.issue_cheque(outgoing_cheque.id)
        assert result.entry_number == "JE-ISSUE-1"

    def test_failure_rolls_back(self, mocker, outgoing_cheque):
        mocker.patch(
            "services.cheque_accounting_integration.process_cheque_issue",
            side_effect=RuntimeError("x"),
        )
        with pytest.raises(Exception, match="فشل"):
            ChequeAccountingIntegration.issue_cheque(outgoing_cheque.id)


class TestClearCheque:
    def test_rejects_cleared_status(self, db_session, incoming_cheque):
        incoming_cheque.status = "cleared"
        db_session.flush()
        with pytest.raises(ValueError, match="صرفه"):
            ChequeAccountingIntegration.clear_cheque(incoming_cheque.id)

    def test_success_with_entry(self, mocker, incoming_cheque, db_session, sample_tenant):
        mocker.patch("services.cheque_accounting_integration.process_cheque_clear")
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-CLR-1",
            reference_type=GLRef.CHEQUE_CLEAR,
            reference_id=incoming_cheque.id,
        )
        db_session.add(entry)
        db_session.flush()
        result = ChequeAccountingIntegration.clear_cheque(incoming_cheque.id)
        assert result.entry_number == "JE-CLR-1"

    def test_dummy_entry_when_missing(self, mocker, incoming_cheque):
        mocker.patch("services.cheque_accounting_integration.process_cheque_clear")
        result = ChequeAccountingIntegration.clear_cheque(incoming_cheque.id)
        assert result.entry_number == "—"

    def test_clear_commit_failure_rolls_back(self, mocker, db_session, incoming_cheque):
        incoming_cheque.status = "deposited"
        db_session.flush()
        mocker.patch("services.cheque_accounting_integration.process_cheque_clear")
        mocker.patch(
            "services.cheque_accounting_integration.db.session.flush",
            side_effect=RuntimeError("db"),
        )
        mocker.patch(
            "services.cheque_accounting_integration.ChequeAccountingIntegration._scoped_entries",
        ).return_value.order_by.return_value.first.return_value = MagicMock()
        with pytest.raises(Exception, match="فشل"):
            ChequeAccountingIntegration.clear_cheque(incoming_cheque.id)

    def test_exchange_rate_branch(self, mocker, db_session, incoming_cheque):
        incoming_cheque.currency = "USD"
        incoming_cheque.amount = Decimal("100")
        incoming_cheque.amount_aed = Decimal("367")
        db_session.flush()
        mocker.patch(
            "services.cheque_accounting_integration.get_system_default_currency",
            return_value="AED",
        )
        clear_mock = mocker.patch("services.cheque_accounting_integration.process_cheque_clear")
        ChequeAccountingIntegration.clear_cheque(
            incoming_cheque.id,
            exchange_gain_loss=Decimal("3"),
        )
        assert clear_mock.call_args.kwargs["clearance_exchange_rate"] is not None

    def test_failure_rolls_back(self, mocker, incoming_cheque):
        mocker.patch(
            "services.cheque_accounting_integration.process_cheque_clear",
            side_effect=RuntimeError("x"),
        )
        with pytest.raises(Exception, match="فشل"):
            ChequeAccountingIntegration.clear_cheque(incoming_cheque.id)


class TestBounceCheque:
    def test_rejects_cleared(self, db_session, incoming_cheque):
        incoming_cheque.status = "cleared"
        db_session.flush()
        with pytest.raises(ValueError, match="ارتداده"):
            ChequeAccountingIntegration.bounce_cheque(incoming_cheque.id)

    def test_success(self, mocker, incoming_cheque, db_session, sample_tenant):
        mocker.patch("services.cheque_accounting_integration.process_cheque_bounce")
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-BNC-1",
            reference_type=GLRef.CHEQUE_BOUNCE,
            reference_id=incoming_cheque.id,
        )
        db_session.add(entry)
        db_session.flush()
        result = ChequeAccountingIntegration.bounce_cheque(incoming_cheque.id, bounce_reason="NSF")
        assert result.entry_number == "JE-BNC-1"

    def test_failure_rolls_back(self, mocker, incoming_cheque):
        mocker.patch(
            "services.cheque_accounting_integration.process_cheque_bounce",
            side_effect=RuntimeError("x"),
        )
        with pytest.raises(Exception, match="فشل"):
            ChequeAccountingIntegration.bounce_cheque(incoming_cheque.id)


class TestAccountingSummary:
    def test_summary_assembly(
        self,
        incoming_cheque,
        db_session,
        sample_tenant,
        sample_gl_accounts,
    ):
        from models.gl import GLAccount

        account = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id,
            code="1110",
        ).first()
        if not account:
            account = GLAccount(
                tenant_id=sample_tenant.id,
                code="1110",
                name="Cash",
                account_type="asset",
            )
            db_session.add(account)
            db_session.flush()

        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-SUM-1",
            reference_type=GLRef.CHEQUE_RECEIVE,
            reference_id=incoming_cheque.id,
            description="receive",
        )
        db_session.add(entry)
        db_session.flush()
        line = GLJournalLine(
            tenant_id=sample_tenant.id,
            entry_id=entry.id,
            account_id=account.id,
            debit=Decimal("100"),
            credit=Decimal("0"),
        )
        db_session.add(line)
        db_session.flush()

        summary = ChequeAccountingIntegration.get_cheque_accounting_summary(incoming_cheque.id)
        assert summary["cheque_info"]["id"] == incoming_cheque.id
        assert len(summary["journal_entries"]) >= 1
        assert summary["journal_entries"][0]["type"] == "receive"
        assert any(i["code"] == "1110" for i in summary["account_impact"])
