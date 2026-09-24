from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from extensions import db
from models import Expense, Purchase, Sale
from models.receipt import Receipt


class FinancialService:
    @staticmethod
    def get_financial_dashboard_advanced_context(tenant_id, branch_id=None):
        today = datetime.now().date()
        month_start = today.replace(day=1)
        months_data: list[dict[str, Any]] = []
        for i in range(12):
            month_date = month_start - timedelta(days=30 * i)
            month_start_date = month_date.replace(day=1)

            if month_date.month == 12:
                month_end_date = month_date.replace(year=month_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end_date = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)

            revenue = FinancialService.sum_sales(
                tenant_id,
                branch_id=branch_id,
                date_from=month_start_date,
                date_to=month_end_date,
                field=Sale.amount_aed,
            )

            expenses = db.session.query(func.sum(Expense.amount_aed)).filter(
                Expense.expense_date >= month_start_date,
                Expense.expense_date <= month_end_date,
                Expense.tenant_id == tenant_id,
            )
            if branch_id is not None:
                expenses = expenses.filter(Expense.branch_id == branch_id)
            expenses = expenses.scalar() or 0

            profit = revenue - expenses
            months_data.append(
                {
                    "month": month_date.strftime("%Y-%m"),
                    "revenue": float(revenue),
                    "expenses": float(expenses),
                    "profit": float(profit),
                    "margin": (profit / revenue * 100) if revenue > 0 else 0,
                }
            )
        months_data.reverse()
        kpis = {
            "avg_revenue": sum(m["revenue"] for m in months_data) / 12,
            "avg_profit": sum(m["profit"] for m in months_data) / 12,
            "avg_margin": sum(m["margin"] for m in months_data) / 12,
            "growth_rate": (
                ((months_data[-1]["revenue"] - months_data[0]["revenue"]) / months_data[0]["revenue"] * 100)
                if months_data[0]["revenue"] > 0
                else 0
            ),
        }
        return {"months_data": months_data, "kpis": kpis}

    @staticmethod
    def sum_sales(
        tenant_id,
        *,
        branch_id=None,
        seller_id=None,
        date_from=None,
        date_to=None,
        status="confirmed",
        field=Sale.amount_aed,
    ):
        """Centralized SUM(Sale.{field}) with consistent filtering.
        All params optional — pass only what you need to filter on.
        Returns scalar or 0."""
        q = db.session.query(func.sum(field)).filter(Sale.tenant_id == tenant_id)
        if branch_id is not None:
            q = q.filter(Sale.branch_id == branch_id)
        if seller_id is not None:
            q = q.filter(Sale.seller_id == seller_id)
        if date_from is not None:
            q = q.filter(Sale.sale_date >= date_from)
        if date_to is not None:
            q = q.filter(Sale.sale_date <= date_to)
        if status is not None:
            q = q.filter(Sale.status == status)
        return q.scalar() or 0

    @staticmethod
    def sum_purchases(tenant_id, *, branch_id=None, date_from=None, date_to=None, status="confirmed"):
        q = db.session.query(func.sum(Purchase.amount_aed)).filter(Purchase.tenant_id == tenant_id)
        if branch_id is not None:
            q = q.filter(Purchase.branch_id == branch_id)
        if date_from is not None:
            q = q.filter(Purchase.purchase_date >= date_from)
        if date_to is not None:
            q = q.filter(Purchase.purchase_date <= date_to)
        if status is not None:
            q = q.filter(Purchase.status == status)
        return q.scalar() or 0

    @staticmethod
    def sum_receipts(tenant_id, *, branch_id=None, date_from=None, date_to=None):
        q = db.session.query(func.sum(Receipt.amount_aed)).filter(Receipt.tenant_id == tenant_id)
        if branch_id is not None:
            q = q.filter(Receipt.branch_id == branch_id)
        if date_from is not None:
            q = q.filter(Receipt.receipt_date >= date_from)
        if date_to is not None:
            q = q.filter(Receipt.receipt_date <= date_to)
        return q.scalar() or 0
