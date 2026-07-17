from datetime import datetime, timezone, timedelta
from flask import render_template
from extensions import db
from models import Sale, Purchase, Receipt, Expense
from sqlalchemy import func


class FinancialService:
    @staticmethod
    def get_financial_dashboard_advanced_context(tenant_id, branch_id=None):
        today = datetime.now().date()
        month_start = today.replace(day=1)
        months_data = []
        for i in range(12):
            month_date = month_start - timedelta(days=30 * i)
            month_start_date = month_date.replace(day=1)

            if month_date.month == 12:
                month_end_date = month_date.replace(
                    year=month_date.year + 1, month=1, day=1
                ) - timedelta(days=1)
            else:
                month_end_date = month_date.replace(
                    month=month_date.month + 1, day=1
                ) - timedelta(days=1)

            revenue = FinancialService.sum_sales(
                tenant_id,
                branch_id=branch_id,
                date_from=month_start_date,
                date_to=month_end_date,
                field=Sale.total_amount,
            )

            expenses = db.session.query(func.sum(Expense.amount)).filter(
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
                (
                    (months_data[-1]["revenue"] - months_data[0]["revenue"])
                    / months_data[0]["revenue"]
                    * 100
                )
                if months_data[0]["revenue"] > 0
                else 0
            ),
        }
        return {"months_data": months_data, "kpis": kpis}

    @staticmethod
    def financial_overview(period, tid, scoped_branch_id):
        """Tenant-scoped or platform-wide financial overview.
        If tid is None -> platform-wide (all tenants)."""
        now = datetime.now(timezone.utc)
        if period == "today":
            start_date = now.date()
        elif period == "week":
            start_date = (now - timedelta(days=7)).date()
        elif period == "month":
            start_date = now.date().replace(day=1)
        elif period == "year":
            start_date = now.date().replace(month=1, day=1)
        else:
            start_date = now.date().replace(day=1)

        platform_mode = tid is None
        tenant_filter = [] if platform_mode else [Sale.tenant_id == tid]

        sales_total = FinancialService.sum_sales(
            tid, branch_id=scoped_branch_id, date_from=start_date
        )
        sales_paid_q = db.session.query(func.sum(Sale.paid_amount_aed)).filter(
            func.date(Sale.sale_date) >= start_date,
            Sale.status == "confirmed",
            *tenant_filter,
        )
        if scoped_branch_id is not None:
            sales_paid_q = sales_paid_q.filter(Sale.branch_id == scoped_branch_id)
        sales_paid = sales_paid_q.scalar() or 0
        sales_count_q = db.session.query(func.count(Sale.id)).filter(
            func.date(Sale.sale_date) >= start_date,
            Sale.status == "confirmed",
            *tenant_filter,
        )
        if scoped_branch_id is not None:
            sales_count_q = sales_count_q.filter(Sale.branch_id == scoped_branch_id)
        sales_count = sales_count_q.scalar() or 0

        purchases_total = FinancialService.sum_purchases(
            tid, branch_id=scoped_branch_id, date_from=start_date
        )
        purchases_count_q = db.session.query(func.count(Purchase.id)).filter(
            func.date(Purchase.purchase_date) >= start_date,
            Purchase.status == "confirmed",
            *tenant_filter,
        )
        if scoped_branch_id is not None:
            purchases_count_q = purchases_count_q.filter(
                Purchase.branch_id == scoped_branch_id
            )
        purchases_count = purchases_count_q.scalar() or 0

        receipts_total = FinancialService.sum_receipts(
            tid, branch_id=scoped_branch_id, date_from=start_date
        )

        financial_data = {
            "sales_total": float(sales_total),
            "sales_paid": float(sales_paid),
            "sales_count": sales_count,
            "purchases_total": float(purchases_total),
            "purchases_count": purchases_count,
            "receipts_total": float(receipts_total),
            "net_revenue": float(sales_total - purchases_total),
            "platform_mode": tid is None,
        }

        return render_template(
            "owner/financial_overview.html",
            financial_data=financial_data,
            period=period,
        )

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
    def sum_purchases(
        tenant_id, *, branch_id=None, date_from=None, date_to=None, status="confirmed"
    ):
        q = db.session.query(func.sum(Purchase.amount_aed)).filter(
            Purchase.tenant_id == tenant_id
        )
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
        q = db.session.query(func.sum(Receipt.amount_aed)).filter(
            Receipt.tenant_id == tenant_id
        )
        if branch_id is not None:
            q = q.filter(Receipt.branch_id == branch_id)
        if date_from is not None:
            q = q.filter(Receipt.receipt_date >= date_from)
        if date_to is not None:
            q = q.filter(Receipt.receipt_date <= date_to)
        return q.scalar() or 0
