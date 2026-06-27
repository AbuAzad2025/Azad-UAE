"""Expense model — amount_base alias, category, to_dict."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from models.expense import Expense, ExpenseCategory


class TestExpenseModel:
    def test_amount_base_alias(self):
        exp = Expense()
        exp.amount_aed = Decimal('150.000')
        assert exp.amount_base == Decimal('150.000')
        exp.amount_base = Decimal('200')
        assert exp.amount_aed == Decimal('200')

    def test_to_dict(self):
        exp = Expense()
        exp.id = 1
        exp.expense_number = 'EXP-1'
        exp.category = MagicMock(name='Office')
        exp.description = 'Supplies'
        exp.amount = Decimal('100')
        exp.currency = 'AED'
        exp.amount_aed = Decimal('100')
        exp.expense_date = datetime(2025, 6, 1, tzinfo=timezone.utc)
        exp.payment_method = 'cash'
        exp.status = 'confirmed'
        d = exp.to_dict()
        assert d['expense_number'] == 'EXP-1'
        assert d['amount'] == 100.0

    def test_repr(self):
        exp = Expense()
        exp.expense_number = 'EXP-99'
        assert 'EXP-99' in repr(exp)


class TestExpenseCategoryModel:
    def test_repr(self):
        cat = ExpenseCategory()
        cat.name = 'Travel'
        assert 'Travel' in repr(cat)
