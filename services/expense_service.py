"""Expense service — expense creation and management."""

from __future__ import annotations

import logging

from extensions import db

logger = logging.getLogger(__name__)


class ExpenseService:
    """Pure business logic for expense operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_expense(
        amount,
        description: str = "",
        category_id: int | None = None,
        payment_method: str = "cash",
        tenant_id: int | None = None,
        user_id: int | None = None,
    ):
        """Create a new expense. Returns the created expense (not yet committed)."""
        from models import Expense

        expense = Expense(
            amount=amount,
            description=description,
            payment_method=payment_method,
            category_id=category_id,
            user_id=user_id,
        )
        if tenant_id is not None:
            expense.tenant_id = tenant_id
        db.session.add(expense)
        return expense
