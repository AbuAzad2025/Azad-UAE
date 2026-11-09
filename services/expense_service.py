"""Expense service — expense creation and management."""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from flask_babel import gettext

from extensions import db

logger = logging.getLogger(__name__)


class ExpenseService:
    """Pure business logic for expense operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def calculate_withholding(amount, rate, applies):
        """Calculate an explicitly configured withholding, in document currency.

        No statutory rate is inferred. A flagged payment must have an explicit
        rate, including an explicit zero when no withholding is applicable.
        """
        if not applies:
            return Decimal("0.000")
        if rate is None:
            raise ValueError(gettext("حدد نسبة ضريبة الاستقطاع قبل تسجيل المصروف."))
        try:
            rate = Decimal(str(rate))
            amount = Decimal(str(amount))
            if not rate.is_finite() or not amount.is_finite() or not 0 <= rate <= 100 or amount <= 0:
                raise ValueError
            return (amount * rate / Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            raise ValueError(gettext("نسبة أو مبلغ ضريبة الاستقطاع غير صالح.")) from None

    @staticmethod
    def resolve_warehouse(warehouse_id, tenant_id, branch_id):
        """Reject unknown, inactive, cross-tenant or cross-branch attribution."""
        from models import Warehouse
        from utils.tenanting import tenant_query

        warehouse = tenant_query(Warehouse).filter_by(id=warehouse_id, tenant_id=tenant_id, is_active=True).first()
        if warehouse is None or (branch_id is not None and warehouse.branch_id != branch_id):
            raise ValueError(gettext("المستودع غير متاح ضمن نطاق الشركة والفرع."))
        return warehouse

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

    @staticmethod
    def find_gl_account(code, tenant_id):
        from models import GLAccount

        return GLAccount.query.filter_by(
            code=str(code),
            tenant_id=int(tenant_id) if tenant_id else None,
        ).first()

    @staticmethod
    def get_category(category_id):
        if not category_id:
            return None
        from models import ExpenseCategory

        return ExpenseCategory.query.get(category_id)

    @staticmethod
    def get_expense_cheque(expense_id, tenant_id):
        from models import Cheque

        return Cheque.query.filter_by(expense_id=expense_id, tenant_id=tenant_id).first()

    @staticmethod
    def is_expense_archived(table_name, record_id):
        from models import ArchivedRecord

        return ArchivedRecord.query.filter_by(table_name=table_name, record_id=record_id).first() is not None

    @staticmethod
    def list_archived_expenses(tenant_id):
        from extensions import db
        from models import ArchivedRecord

        query = db.session.query(ArchivedRecord).filter(ArchivedRecord.table_name == "expenses")
        if tenant_id is not None:
            query = query.filter(ArchivedRecord.tenant_id == tenant_id)
        return query.all()

    @staticmethod
    def get_archived_expense_record(record_id, tenant_id):
        from models import ArchivedRecord

        query = ArchivedRecord.query.filter_by(table_name="expenses", record_id=record_id)
        if tenant_id is not None:
            query = query.filter(ArchivedRecord.tenant_id == tenant_id)
        return query.first_or_404()
