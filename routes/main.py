from datetime import datetime, timedelta, timezone
from decimal import Decimal
from flask import Blueprint, render_template, current_app, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from extensions import db
from models import Sale, Customer, Product, Payment, Receipt, GLAccount, GLJournalLine
from services.stock_service import StockService
from utils.decorators import branch_scope_id
from utils.branching import get_visible_products_query

main_bp = Blueprint('main', __name__)


@main_bp.route('/app')
def index():
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    # Dashboard route with error handling
    try:
        today = datetime.now(timezone.utc).date()
        month_start = today.replace(day=1)
        
        stats = {}
        scoped_branch_id = branch_scope_id()
        
        total_customers_query = Customer.query.filter_by(is_active=True)
        if scoped_branch_id is not None:
            total_customers_query = total_customers_query.join(
                Sale, Sale.customer_id == Customer.id
            ).filter(
                Sale.branch_id == scoped_branch_id,
                Sale.status == 'confirmed'
            ).distinct()
        total_customers = total_customers_query.count()
        stats['customers_count'] = total_customers
        
        if scoped_branch_id is not None:
            total_products = get_visible_products_query(current_user).count()
        else:
            total_products = Product.query.filter_by(is_active=True).count()
        stats['products_count'] = total_products
        
        low_stock = []
        try:
            low_stock = StockService.get_low_stock_products(limit=10, user=current_user)
        except Exception as e:
            current_app.logger.error(f"Failed to fetch low stock products: {e}")

        stats['low_stock_count'] = len(low_stock)
        stats['low_stock_products'] = low_stock
        
        out_of_stock = []
        try:
            out_of_stock = StockService.get_out_of_stock_products(user=current_user)
        except Exception as e:
            current_app.logger.error(f"Failed to fetch out of stock products: {e}")
            
        stats['out_of_stock_count'] = len(out_of_stock)
        
        today_sales_query = db.session.query(
            func.count(Sale.id),
            func.sum(Sale.amount_aed)
        ).filter(
            func.date(Sale.sale_date) == today,
            Sale.status == 'confirmed'
        )
        if scoped_branch_id is not None:
            today_sales_query = today_sales_query.filter(Sale.branch_id == scoped_branch_id)
        today_sales = today_sales_query.first()
        
        stats['today_sales_count'] = today_sales[0] or 0
        stats['today_sales_amount'] = float(today_sales[1] or 0)
        
        month_sales_query = db.session.query(
            func.count(Sale.id),
            func.sum(Sale.amount_aed)
        ).filter(
            func.date(Sale.sale_date) >= month_start,
            Sale.status == 'confirmed'
        )
        if scoped_branch_id is not None:
            month_sales_query = month_sales_query.filter(Sale.branch_id == scoped_branch_id)
        month_sales = month_sales_query.first()
        
        stats['month_sales_count'] = month_sales[0] or 0
        stats['month_sales_amount'] = float(month_sales[1] or 0)
        
        if current_user.can_see_costs():
            month_profit_query = db.session.query(
                func.sum(Sale.amount_aed)
            ).filter(
                func.date(Sale.sale_date) >= month_start,
                Sale.status == 'confirmed'
            )
            if scoped_branch_id is not None:
                month_profit_query = month_profit_query.filter(Sale.branch_id == scoped_branch_id)
            month_profit = month_profit_query.scalar() or Decimal('0')
            
            stats['month_profit'] = float(month_profit)
        
        total_receivables_query = db.session.query(
            func.sum(Sale.amount_aed - Sale.paid_amount_aed)
        ).filter(
            Sale.status == 'confirmed',
            Sale.balance_due > 0
        )
        if scoped_branch_id is not None:
            total_receivables_query = total_receivables_query.filter(Sale.branch_id == scoped_branch_id)
        total_receivables = total_receivables_query.scalar() or Decimal('0')
        
        stats['total_receivables'] = float(total_receivables)
        
        if current_user.can_see_costs():
            try:
                from utils.gl_tenant import get_gl_account_by_code, active_tenant_id
                tid = active_tenant_id()
                cash_acc = get_gl_account_by_code('1110', tenant_id=tid)
                if cash_acc:
                    cash_debit_query = db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=cash_acc.id)
                    cash_credit_query = db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=cash_acc.id)
                    if scoped_branch_id is not None:
                        cash_debit_query = cash_debit_query.join(GLJournalLine.entry).filter_by(branch_id=scoped_branch_id)
                        cash_credit_query = cash_credit_query.join(GLJournalLine.entry).filter_by(branch_id=scoped_branch_id)
                    cash_debit = cash_debit_query.scalar() or Decimal('0')
                    cash_credit = cash_credit_query.scalar() or Decimal('0')
                    stats['cash_balance'] = float(cash_debit - cash_credit)
                
                bank_acc = get_gl_account_by_code('1120', tenant_id=tid)
                if bank_acc:
                    bank_debit_query = db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=bank_acc.id)
                    bank_credit_query = db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=bank_acc.id)
                    if scoped_branch_id is not None:
                        bank_debit_query = bank_debit_query.join(GLJournalLine.entry).filter_by(branch_id=scoped_branch_id)
                        bank_credit_query = bank_credit_query.join(GLJournalLine.entry).filter_by(branch_id=scoped_branch_id)
                    bank_debit = bank_debit_query.scalar() or Decimal('0')
                    bank_credit = bank_credit_query.scalar() or Decimal('0')
                    stats['bank_balance'] = float(bank_debit - bank_credit)
                
                inventory_acc = get_gl_account_by_code('1140', tenant_id=tid)
                if inventory_acc:
                    inv_debit_query = db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=inventory_acc.id)
                    inv_credit_query = db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=inventory_acc.id)
                    if scoped_branch_id is not None:
                        inv_debit_query = inv_debit_query.join(GLJournalLine.entry).filter_by(branch_id=scoped_branch_id)
                        inv_credit_query = inv_credit_query.join(GLJournalLine.entry).filter_by(branch_id=scoped_branch_id)
                    inv_debit = inv_debit_query.scalar() or Decimal('0')
                    inv_credit = inv_credit_query.scalar() or Decimal('0')
                    stats['inventory_value_gl'] = float(inv_debit - inv_credit)
            except Exception:
                pass
        
        # Optimized query with eager loading (N+1 problem fix)
        recent_sales = Sale.query.options(
            joinedload(Sale.customer),
            joinedload(Sale.seller)
        ).filter_by(
            status='confirmed'
        )
        if scoped_branch_id is not None:
            recent_sales = recent_sales.filter(Sale.branch_id == scoped_branch_id)
        recent_sales = recent_sales.order_by(Sale.sale_date.desc()).limit(10).all()
        
        stats['recent_sales'] = recent_sales
        
        if current_user.is_seller():
            my_today_sales = db.session.query(
                func.count(Sale.id),
                func.sum(Sale.amount_aed)
            ).filter(
                func.date(Sale.sale_date) == today,
                Sale.seller_id == current_user.id,
                Sale.status == 'confirmed'
            ).first()
            
            stats['my_today_sales_count'] = my_today_sales[0] or 0
            stats['my_today_sales_amount'] = float(my_today_sales[1] or 0)
        
        return render_template('dashboard.html', stats=stats)

    except Exception as e:
        current_app.logger.error(f"Dashboard Error: {e}")
        # Return error directly to avoid template rendering issues (Double Fault)
        import traceback
        tb = traceback.format_exc()
        return f"""
        <html>
            <head><title>Dashboard Error</title></head>
            <body style="font-family: monospace; padding: 20px;">
                <h1 style="color: red;">Dashboard Error</h1>
                <h3>Exception: {str(e)}</h3>
                <pre style="background: #f0f0f0; padding: 15px; border: 1px solid #ccc;">{tb}</pre>
                <hr>
                <p>This is a raw error page to diagnose why the standard error page failed.</p>
                <a href="/">Go Home</a>
            </body>
        </html>
        """, 500
