from datetime import datetime, timezone, timedelta
from decimal import Decimal
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
            month_date = month_start - timedelta(days=30*i)
            month_start_date = month_date.replace(day=1)
            
            if month_date.month == 12:
                month_end_date = month_date.replace(year=month_date.year+1, month=1, day=1) - timedelta(days=1)
            else:
                month_end_date = month_date.replace(month=month_date.month+1, day=1) - timedelta(days=1)
            
            revenue = db.session.query(func.sum(Sale.total_amount)).filter(
                Sale.sale_date >= month_start_date,
                Sale.sale_date <= month_end_date,
                Sale.status == 'confirmed',
                Sale.tenant_id == tenant_id,
            )
            if branch_id is not None:
                revenue = revenue.filter(Sale.branch_id == branch_id)
            revenue = revenue.scalar() or 0
            
            expenses = db.session.query(func.sum(Expense.amount)).filter(
                Expense.expense_date >= month_start_date,
                Expense.expense_date <= month_end_date,
                Expense.tenant_id == tenant_id,
            )
            if branch_id is not None:
                expenses = expenses.filter(Expense.branch_id == branch_id)
            expenses = expenses.scalar() or 0
            
            profit = revenue - expenses
            months_data.append({
                'month': month_date.strftime('%Y-%m'),
                'revenue': float(revenue),
                'expenses': float(expenses),
                'profit': float(profit),
                'margin': (profit / revenue * 100) if revenue > 0 else 0
            })
        months_data.reverse()
        kpis = {
            'avg_revenue': sum(m['revenue'] for m in months_data) / 12,
            'avg_profit': sum(m['profit'] for m in months_data) / 12,
            'avg_margin': sum(m['margin'] for m in months_data) / 12,
            'growth_rate': ((months_data[-1]['revenue'] - months_data[0]['revenue']) / months_data[0]['revenue'] * 100) if months_data[0]['revenue'] > 0 else 0
        }
        return {'months_data': months_data, 'kpis': kpis}

    @staticmethod
    def financial_overview(period, tid, scoped_branch_id):
        now = datetime.now(timezone.utc)
        if period == 'today':
            start_date = now.date()
        elif period == 'week':
            start_date = (now - timedelta(days=7)).date()
        elif period == 'month':
            start_date = now.date().replace(day=1)
        elif period == 'year':
            start_date = now.date().replace(month=1, day=1)
        else:
            start_date = now.date().replace(day=1)

        sales_data = db.session.query(
            func.sum(Sale.amount_aed).label('total_sales'),
            func.sum(Sale.paid_amount_aed).label('total_paid'),
            func.count(Sale.id).label('count')
        ).filter(
            func.date(Sale.sale_date) >= start_date,
            Sale.status == 'confirmed',
            Sale.tenant_id == tid,
        )
        if scoped_branch_id is not None:
            sales_data = sales_data.filter(Sale.branch_id == scoped_branch_id)
        sales_data = sales_data.first()

        purchases_data = db.session.query(
            func.sum(Purchase.amount_aed).label('total_purchases'),
            func.count(Purchase.id).label('count')
        ).filter(
            func.date(Purchase.purchase_date) >= start_date,
            Purchase.status == 'confirmed',
            Purchase.tenant_id == tid,
        )
        if scoped_branch_id is not None:
            purchases_data = purchases_data.filter(Purchase.branch_id == scoped_branch_id)
        purchases_data = purchases_data.first()

        receipts_total = db.session.query(
            func.sum(Receipt.amount_aed)
        ).filter(
            func.date(Receipt.receipt_date) >= start_date,
            Receipt.tenant_id == tid,
        )
        if scoped_branch_id is not None:
            receipts_total = receipts_total.filter(Receipt.branch_id == scoped_branch_id)
        receipts_total = receipts_total.scalar() or Decimal('0')

        financial_data = {
            'sales_total': float(sales_data[0] or 0),
            'sales_paid': float(sales_data[1] or 0),
            'sales_count': sales_data[2] or 0,
            'purchases_total': float(purchases_data[0] or 0),
            'purchases_count': purchases_data[1] or 0,
            'receipts_total': float(receipts_total),
            'net_revenue': float((sales_data[0] or 0) - (purchases_data[0] or 0)),
        }

        return render_template('owner/financial_overview.html',
                             financial_data=financial_data,
                             period=period)
