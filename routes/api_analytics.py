from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from extensions import limiter
from utils.decorators import permission_required
from utils.cache_decorators import cached_query
from utils.tenanting import get_active_tenant_id
from utils.branching import branch_scope_id_for
from datetime import datetime, timedelta
from decimal import Decimal

api_analytics_bp = Blueprint('api_analytics', __name__, url_prefix='/api/analytics')


def _apply_branch_scope(query, model):
    """Apply branch-level scoping to an analytics query if the user is branch-scoped."""
    scoped_branch_id = branch_scope_id_for(current_user)
    if scoped_branch_id is not None:
        branch_col = getattr(model, 'branch_id', None)
        if branch_col is not None:
            query = query.filter(branch_col == scoped_branch_id)
    return query


@api_analytics_bp.route('/overdue-payments')
@login_required
@permission_required('view_reports')
@limiter.limit("50 per minute")
@cached_query(timeout=300, key_prefix='overdue_payments')
def overdue_payments():
    from models import Customer
    
    tid = get_active_tenant_id(current_user)
    customers = Customer.query.filter_by(is_active=True)
    if tid:
        customers = customers.filter(Customer.tenant_id == tid)
    customers = _apply_branch_scope(customers, Customer)
    customers = customers.all()
    overdue = [c for c in customers if c.get_balance_aed() > Decimal('1000')]
    
    return jsonify({
        'success': True,
        'count': len(overdue),
        'total_amount': sum(float(c.get_balance_aed()) for c in overdue),
        'customers': [{'id': c.id, 'name': c.name, 'balance': float(c.get_balance_aed())} for c in overdue[:10]]
    })


@api_analytics_bp.route('/daily-stats')
@login_required
@permission_required('view_reports')
@cached_query(timeout=60, key_prefix='daily_stats')
def daily_stats():
    from models import Sale, Payment
    from extensions import db
    
    today = datetime.now().date()
    
    tid = get_active_tenant_id(current_user)
    today_sales = Sale.query.filter(
        db.func.date(Sale.sale_date) == today,
        Sale.status == 'confirmed'
    )
    if tid:
        today_sales = today_sales.filter(Sale.tenant_id == tid)
    today_sales = _apply_branch_scope(today_sales, Sale)
    today_sales = today_sales.all()
    
    today_payments = Payment.query.filter(
        db.func.date(Payment.payment_date) == today
    )
    if tid:
        today_payments = today_payments.filter(Payment.tenant_id == tid)
    today_payments = _apply_branch_scope(today_payments, Payment)
    today_payments = today_payments.all()
    
    return jsonify({
        'success': True,
        'sales': {
            'count': len(today_sales),
            'total': sum(float(s.amount_aed) for s in today_sales)
        },
        'payments': {
            'count': len(today_payments),
            'total': sum(float(p.amount_aed) for p in today_payments)
        }
    })


@api_analytics_bp.route('/top-customers')
@login_required
@permission_required('view_reports')
@cached_query(timeout=600, key_prefix='top_customers')
def top_customers():
    from models import Customer
    
    limit = request.args.get('limit', 10, type=int)
    
    tid = get_active_tenant_id(current_user)
    customers = Customer.query.filter_by(is_active=True)
    if tid:
        customers = customers.filter(Customer.tenant_id == tid)
    customers = _apply_branch_scope(customers, Customer)
    customers = customers.order_by(
        Customer.total_purchases.desc()
    ).limit(limit).all()
    
    return jsonify({
        'success': True,
        'customers': [{
            'id': c.id,
            'name': c.name,
            'total_purchases': float(c.total_purchases or 0),
            'balance': float(c.get_balance_aed()),
            'classification': c.customer_classification
        } for c in customers]
    })


@api_analytics_bp.route('/low-stock-products')
@login_required
@permission_required('view_reports')
@cached_query(timeout=120, key_prefix='low_stock_products')
def low_stock_products():
    from models import Product

    tid = get_active_tenant_id(current_user)
    products = Product.query.filter(
        Product.is_active == True,
        Product.current_stock <= Product.min_stock_alert
    )
    if tid:
        products = products.filter(Product.tenant_id == tid)
    products = _apply_branch_scope(products, Product)
    products = products.all()
    
    return jsonify({
        'success': True,
        'count': len(products),
        'products': [{
            'id': p.id,
            'name': p.name,
            'current_stock': float(p.current_stock),
            'min_stock': float(p.min_stock_alert),
            'urgency': 'critical' if p.current_stock == 0 else 'high'
        } for p in products]
    })


@api_analytics_bp.route('/revenue-trend')
@login_required
@permission_required('view_reports')
@cached_query(timeout=300, key_prefix='revenue_trend')
def revenue_trend():
    from models import Sale
    from sqlalchemy import func
    from extensions import db
    
    days = request.args.get('days', 30, type=int)
    since = datetime.now() - timedelta(days=days)

    tid = get_active_tenant_id(current_user)
    daily_revenue = db.session.query(
        func.date(Sale.sale_date).label('date'),
        func.sum(Sale.amount_aed).label('total')
    ).filter(
        Sale.sale_date >= since,
        Sale.status == 'confirmed'
    )
    if tid:
        daily_revenue = daily_revenue.filter(Sale.tenant_id == tid)
    daily_revenue = _apply_branch_scope(daily_revenue, Sale)
    daily_revenue = daily_revenue.group_by(func.date(Sale.sale_date)).all()
    
    return jsonify({
        'success': True,
        'data': [{
            'date': str(row.date),
            'revenue': float(row.total or 0)
        } for row in daily_revenue]
    })

