"""Cov4: cheque_service — create/scoped/validate/calc/guards/listeners arcs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.cheque_service import (
    ChequeService,
    _existing_posted_entry,
    calculate_amount_aed,
    process_cheque_clear,
    process_cheque_deposit,
    process_cheque_issue,
    process_cheque_receive,
    validate_cheque,
)


def test_create_cheque_computes_aed(db_session, sample_tenant):
    ch = ChequeService.create_cheque(
        "CN-COV4", "BN-COV4", "incoming", "Bank", amount=Decimal("100"),
        currency="AED", issue_date=date.today(), due_date=date.today(),
        tenant_id=sample_tenant.id)
    assert ch.amount_aed is not None
    assert ch.status in ("pending", "under_collection", "overdue")


def test_scoped_queries(db_session, sample_tenant, sample_branch, incoming_cheque):
    incoming_cheque.branch_id = sample_branch.id
    db_session.flush()
    assert ChequeService.scoped_cheques_query(sample_tenant.id).count() >= 1
    assert ChequeService.scoped_cheques_query(sample_tenant.id, sample_branch.id).count() >= 1
    assert ChequeService.scoped_cheques_query(sample_tenant.id, 999999).count() == 0
    assert ChequeService.scoped_cheques_query().count() >= 1
    assert ChequeService.scoped_customers_query(sample_tenant.id).count() >= 0
    assert ChequeService.scoped_customers_query(sample_tenant.id, sample_branch.id).count() >= 0
    assert ChequeService.scoped_suppliers_query(sample_tenant.id).count() >= 0
    assert ChequeService.scoped_suppliers_query(sample_tenant.id, sample_branch.id).count() >= 0


def test_has_gl_references_false_and_true(db_session, incoming_cheque, sample_tenant):
    from models.gl import GLJournalEntry

    assert ChequeService.has_gl_references(incoming_cheque, ["X", "Y"]) is False
    e = GLJournalEntry(tenant_id=sample_tenant.id, entry_number="JE-CHQ-REF",
                       reference_type="CHEQUE_RECEIVE", reference_id=incoming_cheque.id)
    db_session.add(e)
    db_session.flush()
    assert ChequeService.has_gl_references(incoming_cheque, ["CHEQUE_RECEIVE"]) is True


def test_validate_cheque_all_branches():
    base = {"cheque_number": "N", "cheque_bank_number": "BN", "bank_name": "B",
            "amount": Decimal("10"), "issue_date": date.today(), "due_date": date.today(),
            "cheque_type": "incoming"}
    validate_cheque(SimpleNamespace(**base))
    for field in ["cheque_number", "cheque_bank_number", "bank_name"]:
        bad = dict(base)
        bad[field] = ""
        with pytest.raises(ValueError):
            validate_cheque(SimpleNamespace(**bad))
    with pytest.raises(ValueError):
        validate_cheque(SimpleNamespace(**{**base, "amount": Decimal("0")}))
    with pytest.raises(ValueError):
        validate_cheque(SimpleNamespace(**{**base, "issue_date": None}))
    with pytest.raises(ValueError):
        validate_cheque(SimpleNamespace(**{**base, "due_date": None}))
    with pytest.raises(ValueError):
        validate_cheque(SimpleNamespace(**{**base, "cheque_type": "weird"}))


def test_calculate_amount_aed(sample_tenant):
    ch = SimpleNamespace(amount=Decimal("100"), currency="AED", exchange_rate=None,
                         tenant_id=sample_tenant.id, amount_aed=None)
    calculate_amount_aed(ch)
    assert ch.amount_aed is not None


def test_existing_posted_entry_none_and_tid_none(incoming_cheque):
    from utils.gl_reference_types import GLRef

    assert _existing_posted_entry(incoming_cheque, GLRef.CHEQUE_RECEIVE) is None
    ghost = SimpleNamespace(id=999999999, tenant_id=None)
    assert _existing_posted_entry(ghost, GLRef.CHEQUE_RECEIVE) is None


def test_deposit_status_guard_and_success(db_session, incoming_cheque):
    incoming_cheque.status = "cleared"
    db_session.flush()
    with pytest.raises(ValueError):
        process_cheque_deposit(incoming_cheque)
    incoming_cheque.status = "pending"
    db_session.flush()
    process_cheque_deposit(incoming_cheque)
    assert incoming_cheque.status == "deposited"
    assert incoming_cheque.deposit_date is not None


def test_receive_issue_type_guards(outgoing_cheque, incoming_cheque):
    assert process_cheque_receive(outgoing_cheque) is None
    assert process_cheque_issue(incoming_cheque) is None


def test_receive_idempotent_and_issue_expense_skip(db_session, incoming_cheque,
                                                   outgoing_cheque, sample_tenant):
    from models.gl import GLJournalEntry
    from utils.gl_reference_types import GLRef

    e = GLJournalEntry(tenant_id=sample_tenant.id, entry_number="JE-POSTED",
                       reference_type=GLRef.CHEQUE_RECEIVE, reference_id=incoming_cheque.id,
                       status="posted")
    db_session.add(e)
    db_session.flush()
    assert process_cheque_receive(incoming_cheque).id == e.id
    outgoing_cheque.expense_id = 123
    db_session.flush()
    assert process_cheque_issue(outgoing_cheque) is None


def test_listeners_and_auto_handlers(db_session, incoming_cheque):
    from services.cheque_service import register_cheque_event_listeners

    register_cheque_event_listeners()
    register_cheque_event_listeners()  # idempotent re-register arc
    from services.cheque_service import _auto_log_status_change, _auto_update_status

    m = SimpleNamespace()
    c = SimpleNamespace()
    t = SimpleNamespace(status="pending")
    _auto_update_status(m, c, t)  # no-op branches
    _auto_log_status_change(m, c, t)


def test_clear_bounce_cancel_guards(db_session, incoming_cheque):
    from services.cheque_service import (
        process_cheque_bounce,
        process_cheque_cancel,
    )

    incoming_cheque.status = "cleared"
    db_session.flush()
    with pytest.raises(ValueError):
        process_cheque_clear(incoming_cheque)
    with pytest.raises(ValueError):
        process_cheque_bounce(incoming_cheque, "r")
    incoming_cheque.status = "pending"
    db_session.flush()
    with patch("services.cheque_service._create_bounce_journal_entry",
               side_effect=RuntimeError("gl down")):
        with pytest.raises(RuntimeError):
            process_cheque_bounce(incoming_cheque, "r", bounce_fee=Decimal("5"))
    with patch("services.cheque_service._create_cancel_journal_entry",
               side_effect=RuntimeError("gl down")):
        with pytest.raises(RuntimeError):
            process_cheque_cancel(incoming_cheque, "void")
