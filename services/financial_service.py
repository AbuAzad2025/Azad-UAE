from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import render_template
from extensions import db
from models import Sale, Purchase, Receipt
from sqlalchemy import func

class FinancialService:
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
