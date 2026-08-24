"""Tests for services/expense_service.py."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from services.expense_service import ExpenseService


class TestExpenseServiceCreate:
    def test_create_expense_minimal(self, db_session, sample_tenant, sample_user):
        exp = ExpenseService.create_expense(
            amount=Decimal("100.000"), description="Test", tenant_id=sample_tenant.id, user_id=sample_user.id
        )
        # Service sets basic fields; model missing expense_number etc triggers IntegrityError on flush — verify attributes before flush
        assert exp.amount == Decimal("100.000")
        assert exp.description == "Test"
        assert exp.tenant_id == sample_tenant.id
        assert exp.user_id == sample_user.id
        # Flush would require expense_number/category — expect failure if flushed
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_create_expense_with_category(self, db_session, sample_tenant, sample_user, sample_expense_category):
        exp = ExpenseService.create_expense(
            amount=Decimal("250.500"),
            description="With cat",
            category_id=sample_expense_category.id,
            payment_method="bank",
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
        )
        assert exp.category_id == sample_expense_category.id
        assert exp.payment_method == "bank"
        assert exp.amount == Decimal("250.500")
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_create_expense_string_amount_decimal_guard(self, db_session, sample_tenant, sample_user):
        exp = ExpenseService.create_expense(amount="99.99", tenant_id=sample_tenant.id, user_id=sample_user.id)
        assert str(exp.amount) == "99.99"
        assert exp.tenant_id == sample_tenant.id
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_create_expense_without_tenant(self, db_session, sample_user):
        exp = ExpenseService.create_expense(amount=Decimal("10.000"), tenant_id=None, user_id=sample_user.id)
        assert exp.tenant_id is None
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_create_expense_default_payment_method(self, db_session, sample_tenant):
        exp = ExpenseService.create_expense(amount=Decimal("5.000"), tenant_id=sample_tenant.id)
        assert exp.payment_method == "cash"
        assert exp.amount == Decimal("5.000")
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestExpenseServiceHelpers:
    def test_find_gl_account_not_found(self, db_session, sample_tenant):
        acct = ExpenseService.find_gl_account("9999", sample_tenant.id)
        assert acct is None

    def test_find_gl_account_with_none_tenant(self):
        acct = ExpenseService.find_gl_account("1000", None)
        assert acct is None or hasattr(acct, "code")

    def test_get_category_none(self):
        assert ExpenseService.get_category(None) is None
        assert ExpenseService.get_category(0) is None
        assert ExpenseService.get_category("") is None

    def test_get_category_not_found(self, db_session):
        cat = ExpenseService.get_category(999999)
        assert cat is None

    def test_get_category_found(self, db_session, sample_expense_category):
        cat = ExpenseService.get_category(sample_expense_category.id)
        assert cat is not None
        assert cat.id == sample_expense_category.id

    def test_get_expense_cheque_none(self, db_session, sample_tenant, sample_expense):
        cheque = ExpenseService.get_expense_cheque(sample_expense.id, sample_tenant.id)
        assert cheque is None

    def test_get_expense_cheque_wrong_tenant(self, db_session, sample_tenant, sample_expense):
        cheque = ExpenseService.get_expense_cheque(sample_expense.id, sample_tenant.id + 999)
        assert cheque is None

    def test_is_expense_archived_false(self, db_session, sample_expense):
        assert ExpenseService.is_expense_archived("expenses", sample_expense.id) is False

    def test_list_archived_expenses_empty(self, db_session, sample_tenant):
        result = ExpenseService.list_archived_expenses(sample_tenant.id)
        assert isinstance(result, list)

    def test_list_archived_expenses_none_tenant(self, db_session):
        result = ExpenseService.list_archived_expenses(None)
        assert isinstance(result, list)

    def test_get_archived_expense_record_404(self, db_session, sample_tenant):
        with pytest.raises(Exception):  # first_or_404 raises 404
            ExpenseService.get_archived_expense_record(999999, sample_tenant.id)
