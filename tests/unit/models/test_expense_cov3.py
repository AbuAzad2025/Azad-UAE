"""Gap coverage for models/expense.py — aliases, setters, to_dict branches."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from models.expense import Expense, ExpenseCategory


def _expense(**kwargs):
    params = {
        "tenant_id": 1,
        "expense_number": "EXP-COV3",
        "category_id": 1,
        "description": "Test expense",
        "amount": Decimal("100.500"),
        "amount_aed": Decimal("100.500"),
        "expense_date": datetime.now(UTC),
        "payment_method": "cash",
        "user_id": 1,
    }
    params.update(kwargs)
    return Expense(**params)


class TestAmountBaseAlias:
    def test_getter_returns_aed(self):
        exp = _expense(amount_aed=Decimal("42.125"))
        assert exp.amount_base == Decimal("42.125")

    def test_setter_writes_aed(self):
        exp = _expense()
        exp.amount_base = Decimal("7.5")
        assert exp.amount_aed == Decimal("7.5")


class TestBaseCurrencyDisplay:
    def test_alias(self):
        exp = _expense(base_currency="AED")
        assert exp.base_currency_display == "AED"


class TestExpenseToDict:
    def test_without_category(self):
        exp = _expense()
        exp.category = None
        data = exp.to_dict()
        assert data["category"] is None
        assert data["expense_number"] == "EXP-COV3"
        assert data["amount"] == float(Decimal("100.500"))

    def test_with_category(self):
        exp = _expense()
        exp.category = ExpenseCategory(name="Rent")
        data = exp.to_dict()
        assert data["category"] == "Rent"


class TestExpenseCategoryRepr:
    def test_repr(self):
        cat = ExpenseCategory(name="Fuel")
        assert "Fuel" in repr(cat)

    def test_expense_repr(self):
        assert "EXP-COV3" in repr(_expense())
