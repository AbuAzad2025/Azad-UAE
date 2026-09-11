"""Cov4: cheque_accounting_integration — scoped-entries/FX/clear-fail/404/summary arcs."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from werkzeug.exceptions import NotFound

from models.gl import GLJournalEntry
from services.cheque_accounting_integration import ChequeAccountingIntegration
from utils.gl_reference_types import GLRef


def test_scoped_entries_variants(incoming_cheque):
    q_all = ChequeAccountingIntegration._scoped_entries(incoming_cheque)
    assert q_all.count() >= 0
    q_ref = ChequeAccountingIntegration._scoped_entries(
        incoming_cheque, reference_type=GLRef.CHEQUE_RECEIVE, reference_id=incoming_cheque.id)
    assert q_ref.count() == 0


def test_missing_cheque_404s():
    for fn in (ChequeAccountingIntegration.receive_cheque,
               ChequeAccountingIntegration.issue_cheque,
               ChequeAccountingIntegration.clear_cheque,
               ChequeAccountingIntegration.bounce_cheque,
               ChequeAccountingIntegration.get_cheque_accounting_summary):
        with pytest.raises(NotFound):
            fn(999999999)


def test_clear_fx_rate_computation(db_session, incoming_cheque, sample_tenant):
    from models.gl import GLJournalEntry as JE

    incoming_cheque.currency = "USD"
    incoming_cheque.amount = Decimal("100")
    incoming_cheque.amount_aed = Decimal("367")
    incoming_cheque.status = "deposited"
    db_session.flush()
    with patch("services.cheque_accounting_integration.process_cheque_clear") as p, \
         patch("services.cheque_accounting_integration.get_system_default_currency",
               return_value="AED"):
        entry = JE(tenant_id=sample_tenant.id, entry_number="JE-FX-1",
                   reference_type=GLRef.CHEQUE_CLEAR, reference_id=incoming_cheque.id)
        db_session.add(entry)
        db_session.flush()
        out = ChequeAccountingIntegration.clear_cheque(
            incoming_cheque.id, bank_charges=0, exchange_gain_loss=Decimal("3"))
        assert out.entry_number == "JE-FX-1"
        kwargs = p.call_args
        assert kwargs[1]["clearance_exchange_rate"] == Decimal("370") / Decimal("100")


def test_clear_same_currency_skips_fx(db_session, incoming_cheque):
    incoming_cheque.currency = "AED"
    incoming_cheque.status = "pending"
    db_session.flush()
    with patch("services.cheque_accounting_integration.process_cheque_clear") as p:
        ChequeAccountingIntegration.clear_cheque(incoming_cheque.id, exchange_gain_loss=5)
        assert p.call_args[1]["clearance_exchange_rate"] is None


def test_clear_flush_failure_reraises(db_session, incoming_cheque):
    incoming_cheque.status = "pending"
    db_session.flush()
    with patch("services.cheque_accounting_integration.process_cheque_clear"), \
         patch("services.cheque_accounting_integration.db.session") as sess:
        sess.flush.side_effect = RuntimeError("flush boom")
        with pytest.raises(Exception, match="flush boom"):
            ChequeAccountingIntegration.clear_cheque(incoming_cheque.id)


def test_bounce_failure_path(incoming_cheque):
    with patch("services.cheque_accounting_integration.process_cheque_bounce",
               side_effect=RuntimeError("gl down")):
        with pytest.raises(Exception, match="gl down"):
            ChequeAccountingIntegration.bounce_cheque(incoming_cheque.id, bounce_reason="NSF")


def test_summary_with_entries_and_impact(db_session, incoming_cheque, sample_tenant,
                                         sample_gl_accounts):
    entry = GLJournalEntry(
        tenant_id=sample_tenant.id, entry_number="JE-SUM-1",
        reference_type=GLRef.CHEQUE_RECEIVE, reference_id=incoming_cheque.id,
        description="recv",
    )
    db_session.add(entry)
    db_session.flush()
    summary = ChequeAccountingIntegration.get_cheque_accounting_summary(incoming_cheque.id)
    assert summary["cheque_info"]["id"] == incoming_cheque.id
    assert any(e["entry_number"] == "JE-SUM-1" for e in summary["journal_entries"])
    assert isinstance(summary["account_impact"], list)


def test_summary_no_dates_no_entries(db_session, incoming_cheque):
    incoming_cheque.issue_date = None
    incoming_cheque.due_date = None
    db_session.flush()
    summary = ChequeAccountingIntegration.get_cheque_accounting_summary(incoming_cheque.id)
    assert summary["cheque_info"]["date"] is None
    assert summary["journal_entries"] == []
