from flask import Blueprint, jsonify, request
from flask_login import login_required
from extensions import limiter
from utils.decorators import permission_required
from utils.cache_decorators import cached_query
from datetime import datetime, timedelta
from decimal import Decimal

api_analytics_bp = Blueprint('api_analytics', __name__, url_prefix='/api/analytics')


@api_analytics_bp.route('/overdue-payments')
@login_required
@permission_required('view_reports')
@limiter.limit("50 per minute")
@cached_query(timeout=300, key_prefix='overdue_payments')
def overdue_payments():
    from models import Customer
    
    customers = Customer.query.filter_by(is_active=True).all()
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
    
    today_sales = Sale.query.filter(
        db.func.date(Sale.sale_date) == today,
        Sale.status == 'confirmed'
    ).all()
    
    today_payments = Payment.query.filter(
        db.func.date(Payment.payment_date) == today
    ).all()
    
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
    
    customers = Customer.query.filter_by(is_active=True).order_by(
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
    
    products = Product.query.filter(
        Product.is_active == True,
        Product.current_stock <= Product.min_stock_alert
    ).all()
    
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
    
    daily_revenue = db.session.query(
        func.date(Sale.sale_date).label('date'),
        func.sum(Sale.amount_aed).label('total')
    ).filter(
        Sale.sale_date >= since,
        Sale.status == 'confirmed'
    ).group_by(func.date(Sale.sale_date)).all()
    
    return jsonify({
        'success': True,
        'data': [{
            'date': str(row.date),
            'revenue': float(row.total or 0)
        } for row in daily_revenue]
    })

