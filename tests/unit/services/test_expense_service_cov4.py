"""Cov4: expense_service — create/find/category/cheque/archived arcs."""

from __future__ import annotations

import pytest

from services.expense_service import ExpenseService


def test_create_expense_with_and_without_tenant(db_session, sample_tenant, sample_user,
                                                  sample_expense_category):
    from decimal import Decimal

    e = ExpenseService.create_expense(Decimal("100"), "cov4 expense", tenant_id=sample_tenant.id,
                                      user_id=sample_user.id, category_id=sample_expense_category.id)
    e.expense_number = "EXP-COV4-1"
    e.amount_aed = Decimal("100")
    assert e.tenant_id == sample_tenant.id
    e2 = ExpenseService.create_expense(Decimal("50"), "no tenant", user_id=sample_user.id,
                                       category_id=sample_expense_category.id)
    assert e2.tenant_id is None
    e2.expense_number = "EXP-COV4-2"
    e2.amount_aed = Decimal("50")
    e2.tenant_id = sample_tenant.id
    db_session.flush()


def test_find_gl_account_hit_and_miss(db_session, sample_tenant):
    from services.gl_service import GLService

    GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
    hit = ExpenseService.find_gl_account("6100", sample_tenant.id)
    assert hit is not None and hit.code == "6100"
    assert ExpenseService.find_gl_account("no-such-code", sample_tenant.id) is None
    assert ExpenseService.find_gl_account("6100", None) is None


def test_get_category_none_and_missing():
    assert ExpenseService.get_category(None) is None
    assert ExpenseService.get_category(0) is None
    assert ExpenseService.get_category(999999999) is None


def test_get_expense_cheque_hit_and_miss(db_session, sample_tenant, incoming_cheque,
                                           sample_user, sample_expense_category):
    from models import Expense
    from decimal import Decimal

    exp = Expense(tenant_id=sample_tenant.id, expense_number="EXP-COV4",
                   category_id=sample_expense_category.id, description="x",
                   amount=Decimal("10"), amount_aed=Decimal("10"),
                   payment_method="cash", user_id=sample_user.id)
    db_session.add(exp)
    db_session.flush()
    incoming_cheque.expense_id = exp.id
    db_session.flush()
    assert ExpenseService.get_expense_cheque(exp.id, sample_tenant.id).id == incoming_cheque.id
    assert ExpenseService.get_expense_cheque(999999999, sample_tenant.id) is None


def test_archived_helpers(db_session, sample_tenant):
    assert ExpenseService.is_expense_archived("expenses", 999999999) is False
    assert ExpenseService.list_archived_expenses(sample_tenant.id) == []
    assert ExpenseService.list_archived_expenses(None) == []
    with pytest.raises(Exception):
        ExpenseService.get_archived_expense_record(999999999, sample_tenant.id)
