from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, make_response
from flask_login import login_required, current_user
from sqlalchemy import select
from extensions import db
from models import Customer, Supplier, Product, User
from services.stock_service import StockService
from utils.branching import get_accessible_warehouse_ids, get_branch_stock_map
from utils.decorators import branch_scope_id, permission_required

api_bp = Blueprint('api', __name__, url_prefix='/api')


def _scoped_customer_query():
    from models import Payment, Receipt, Sale

    query = Customer.query
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        return query

    sale_ids = select(Sale.customer_id).where(Sale.customer_id.isnot(None), Sale.branch_id == scoped_branch_id)
    payment_ids = select(Payment.customer_id).where(Payment.customer_id.isnot(None), Payment.branch_id == scoped_branch_id)
    receipt_ids = select(Receipt.customer_id).where(Receipt.customer_id.isnot(None), Receipt.branch_id == scoped_branch_id)
    return query.filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))


def _scoped_supplier_query():
    from models import Payment, Purchase

    query = Supplier.query
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        return query

    purchase_ids = select(Purchase.supplier_id).where(Purchase.supplier_id.isnot(None), Purchase.branch_id == scoped_branch_id)
    payment_ids = select(Payment.supplier_id).where(Payment.supplier_id.isnot(None), Payment.branch_id == scoped_branch_id)
    return query.filter(Supplier.id.in_(purchase_ids.union(payment_ids)))


def _customer_balance(customer_id):
    from models import Payment, Receipt, Sale

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        customer = db.session.get(Customer, customer_id)
        return float(customer.get_balance_aed()) if customer else 0.0

    sales_total = db.session.query(db.func.sum(Sale.amount_aed)).filter(
        Sale.customer_id == customer_id,
        Sale.status == 'confirmed',
        Sale.branch_id == scoped_branch_id,
    ).scalar() or 0
    receipts_total = db.session.query(db.func.sum(Receipt.amount_aed)).filter(
        Receipt.customer_id == customer_id,
        Receipt.branch_id == scoped_branch_id,
    ).scalar() or 0
    outgoing_total = db.session.query(db.func.sum(Payment.amount_aed)).filter(
        Payment.customer_id == customer_id,
        Payment.direction == 'outgoing',
        Payment.branch_id == scoped_branch_id,
    ).scalar() or 0
    return float((sales_total or 0) + (outgoing_total or 0) - (receipts_total or 0))


def _supplier_balance(supplier_id):
    from models import Payment, Purchase

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        supplier = db.session.get(Supplier, supplier_id)
        return float(supplier.get_balance_aed()) if supplier else 0.0

    purchases_total = db.session.query(db.func.sum(Purchase.amount_aed)).filter(
        Purchase.supplier_id == supplier_id,
        Purchase.status == 'confirmed',
        Purchase.branch_id == scoped_branch_id,
    ).scalar() or 0
    outgoing_total = db.session.query(db.func.sum(Payment.amount_aed)).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == 'outgoing',
        Payment.branch_id == scoped_branch_id,
    ).scalar() or 0
    incoming_total = db.session.query(db.func.sum(Payment.amount_aed)).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == 'incoming',
        Payment.branch_id == scoped_branch_id,
    ).scalar() or 0
    return float((purchases_total or 0) - ((outgoing_total or 0) - (incoming_total or 0)))


@api_bp.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'message': 'API is running'
    })


@api_bp.route('/version')
def version():
    return jsonify({
        'version': '1.0.0',
        'name': 'Warehouse & Sales Management System'
    })


@api_bp.route('/payment-fields/<payment_method>')
@login_required
def payment_fields(payment_method):
    fields = {
        'cash': {
            'fields': [],
            'ar_title': 'دفع نقدي',
            'en_title': 'Cash Payment'
        },
        'card': {
            'fields': [
                {'name': 'reference_number', 'type': 'text', 'label_ar': 'رقم المعاملة', 'label_en': 'Transaction Number', 'required': False},
                {'name': 'card_last4', 'type': 'text', 'label_ar': 'آخر 4 أرقام البطاقة', 'label_en': 'Card Last 4 Digits', 'required': False}
            ],
            'ar_title': 'دفع ببطاقة',
            'en_title': 'Card Payment'
        },
        'bank_transfer': {
            'fields': [
                {'name': 'reference_number', 'type': 'text', 'label_ar': 'رقم الحوالة', 'label_en': 'Transfer Reference', 'required': True},
                {'name': 'bank_name', 'type': 'text', 'label_ar': 'اسم البنك', 'label_en': 'Bank Name', 'required': False}
            ],
            'ar_title': 'تحويل بنكي',
            'en_title': 'Bank Transfer'
        },
        'cheque': {
            'fields': [
                {'name': 'cheque_number', 'type': 'text', 'label_ar': 'رقم الشيك', 'label_en': 'Cheque Number', 'required': True},
                {'name': 'cheque_date', 'type': 'date', 'label_ar': 'تاريخ الاستحقاق', 'label_en': 'Due Date', 'required': True},
                {'name': 'bank_name', 'type': 'text', 'label_ar': 'اسم البنك', 'label_en': 'Bank Name', 'required': True}
            ],
            'ar_title': 'دفع بشيك',
            'en_title': 'Cheque Payment'
        },
        'e_wallet': {
            'fields': [
                {'name': 'reference_number', 'type': 'text', 'label_ar': 'رقم المعاملة', 'label_en': 'Transaction ID', 'required': True},
                {'name': 'wallet_provider', 'type': 'select', 'label_ar': 'المحفظة', 'label_en': 'Wallet Provider', 'required': False, 
                 'options': [
                     {'value': 'apple_pay', 'label_ar': 'Apple Pay', 'label_en': 'Apple Pay'},
                     {'value': 'google_pay', 'label_ar': 'Google Pay', 'label_en': 'Google Pay'},
                     {'value': 'samsung_pay', 'label_ar': 'Samsung Pay', 'label_en': 'Samsung Pay'},
                     {'value': 'other', 'label_ar': 'أخرى', 'label_en': 'Other'}
                 ]}
            ],
            'ar_title': 'محفظة إلكترونية',
            'en_title': 'E-Wallet'
        }
    }
    
    return jsonify(fields.get(payment_method, {'fields': []}))


@api_bp.route('/currency-rate/<from_currency>/<to_currency>')
@login_required
def currency_rate(from_currency, to_currency):
    from services.currency_service import CurrencyService
    
    try:
        details = CurrencyService.get_exchange_rate_details(from_currency, to_currency)
        payload = {
            'from': from_currency,
            'to': to_currency,
            'rate': float(details['rate']),
            'success': True,
            'source': details.get('source', 'unknown'),
            'cached': bool(details.get('cached', False)),
            'age_seconds': int(details.get('age_seconds') or 0),
            'fetched_at': datetime.now(timezone.utc).isoformat(),
        }
        resp = make_response(jsonify(payload), 200)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    except Exception as e:
        resp = make_response(jsonify({
            'success': False,
            'error': str(e),
            'manual_input_required': True
        }), 400)
        resp.headers['Cache-Control'] = 'no-store'
        return resp


@api_bp.route('/currencies')
@login_required
def currencies():
    from services.currency_service import CurrencyService

    codes = CurrencyService.get_supported_currencies()
    currency_items = [
        {'code': c, 'label': CurrencyService.get_currency_label(c)}
        for c in codes
    ]
    return jsonify({
        'success': True,
        'currencies': codes,
        'currency_items': currency_items,
        'common': list(CurrencyService.COMMON_CURRENCIES),
    })


@api_bp.route('/search')
@login_required
@permission_required('view_reports')  # بحث موحد: منتجات، عملاء، موردين
def api_search():
    """
    🔍 API بحث موحد: زبائن، موردين، منتجات
    """
    query = request.args.get('q', '')
    search_type = request.args.get('type', 'customers')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # ========================================
    # 1. البحث عن المنتجات
    # ========================================
    if search_type == 'products':
        warehouse_id = request.args.get('warehouse_id', type=int)
        purpose = request.args.get('purpose', '').strip()
        warehouse_ids = [warehouse_id] if warehouse_id else get_accessible_warehouse_ids(current_user)
        if purpose == 'purchase':
            products_query = Product.query.filter(Product.is_active == True)
        else:
            products_query = StockService.get_visible_products_query(current_user)
        if query:
            products_query = products_query.filter(
                db.or_(
                    Product.name.ilike(f'%{query}%'),
                    Product.sku.ilike(f'%{query}%'),
                    Product.barcode.ilike(f'%{query}%')
                )
            )
        products = products_query.order_by(Product.name).limit(per_page).all()
        stock_map = get_branch_stock_map(
            product_ids=[p.id for p in products],
            warehouse_ids=warehouse_ids,
        ) if warehouse_ids else {}
        
        results = [{
            'id': p.id,
            'text': p.name,
            'name': p.name,
            'sku': p.sku,
            'current_stock': float(stock_map.get(p.id, p.current_stock or 0)),
            'default_price': float(p.regular_price or 0),
            'unit_price': float(p.regular_price or 0),
            'regular_price': float(p.regular_price or 0),
            'merchant_price': float(p.merchant_price) if p.merchant_price else None,
            'partner_price': float(p.partner_price) if p.partner_price else None,
            'cost_price': float(p.cost_price) if p.cost_price else 0,
            'unit': p.unit,
            'is_low_stock': p.is_low_stock(),
        } for p in products]
        
        return jsonify({'results': results, 'has_more': len(results) >= per_page})
    
    # ========================================
    # 2. البحث عن الموردين
    # ========================================
    elif search_type == 'suppliers':
        base_query = _scoped_supplier_query().filter(Supplier.is_active == True).order_by(Supplier.name)
        
        if query:
            base_query = base_query.filter(
                db.or_(
                    Supplier.name.ilike(f'%{query}%'),
                    Supplier.company_name.ilike(f'%{query}%'),
                    Supplier.phone.ilike(f'%{query}%'),
                    Supplier.email.ilike(f'%{query}%')
                )
            )
        
        offset = (page - 1) * per_page
        suppliers = base_query.limit(per_page + 1).offset(offset).all()
        has_more = len(suppliers) > per_page
        suppliers = suppliers[:per_page]
        
        results = [{
            'id': s.id,
            'text': f"{s.name} {('- ' + s.company_name) if s.company_name else ''} - {s.phone or 'لا يوجد رقم'}",
            'name': s.name,
            'company_name': s.company_name,
            'phone': s.phone,
            'email': s.email,
            'supplier_type': s.supplier_type,
            'type_display': s.get_type_display(),
            'balance_aed': _supplier_balance(s.id),
            'rating': s.rating,
            'is_verified': s.is_verified
        } for s in suppliers]
        
        return jsonify({'results': results, 'has_more': has_more})
    
    # ========================================
    # 3. البحث عن الزبائن (الافتراضي)
    # ========================================
    else:
        base_query = _scoped_customer_query().filter(Customer.is_active == True).order_by(Customer.name)
        
        if query:
            base_query = base_query.filter(
                db.or_(
                    Customer.name.ilike(f'%{query}%'),
                    Customer.phone.ilike(f'%{query}%'),
                    Customer.email.ilike(f'%{query}%') if Customer.email else False
                )
            )
        
        offset = (page - 1) * per_page
        customers = base_query.limit(per_page + 1).offset(offset).all()
        has_more = len(customers) > per_page
        customers = customers[:per_page]
        
        results = [{
            'id': c.id,
            'text': f"{c.name} - {c.phone or 'لا يوجد رقم'}",
            'name': c.name,
            'phone': c.phone,
            'email': c.email,
            'customer_type': c.customer_type,
            'balance_aed': _customer_balance(c.id)
        } for c in customers]
        
        return jsonify({'results': results, 'has_more': has_more})


@api_bp.route('/check-username')
@login_required
def check_username():
    """التحقق من توفر اسم المستخدم"""
    username = request.args.get('username', '').strip()
    
    if not username or len(username) < 3:
        return jsonify({'available': False, 'error': 'اسم المستخدم قصير جداً'})
    
    import re
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        return jsonify({'available': False, 'error': 'استخدم حروف إنجليزية وأرقام و_ فقط'})
    
    existing = User.query.filter_by(username=username).first()
    
    if existing:
        from datetime import datetime
        year = datetime.now().year
        suggestions = [f'{username}_{year}', f'{username}_2024', f'{username}_admin']
        
        return jsonify({
            'available': False,
            'message': f'اسم المستخدم "{username}" موجود مسبقاً',
            'suggestions': suggestions
        })
    
    return jsonify({'available': True, 'message': 'اسم المستخدم متاح ✓'})


@api_bp.route('/products/low-stock')
@login_required
def products_low_stock():
    """API للمنتجات قليلة المخزون"""
    try:
        low_stock_products = StockService.get_low_stock_products(user=current_user)

        products_data = []
        for product in low_stock_products:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'current_stock': float(getattr(product, 'visible_stock', product.current_stock or 0)),
                'min_stock_alert': float(product.min_stock_alert or 0),
                'needed': float((product.min_stock_alert or 0) - (getattr(product, 'visible_stock', product.current_stock or 0)))
            })
        
        return jsonify({
            'success': True,
            'products': products_data,
            'count': len(products_data)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api_bp.route('/exchange-rates/display')
@login_required
def exchange_rates_display():
    """
    Display-only exchange rates for the navbar / fxModal.
    NEVER use these for accounting, invoicing, payments, or GL entries.
    Use /api/currency-rate/<from>/<to> for accounting rates.
    """
    from services.exchange_rate_service import ExchangeRateService

    base = request.args.get('base', 'USD').upper()
    symbols_str = request.args.get('symbols', '')
    if symbols_str:
        symbols = tuple(s.strip().upper() for s in symbols_str.split(',') if s.strip())
    else:
        symbols = ExchangeRateService.DISPLAY_CURRENCIES

    result = ExchangeRateService.get_online_rates_for_display(base=base, symbols=symbols)
    resp = make_response(jsonify(result), 200)
    resp.headers['Cache-Control'] = 'private, max-age=300'
    return resp


@api_bp.route('/echo', methods=['PUT', 'PATCH', 'DELETE'])
@login_required
def echo():
    payload = request.get_json(silent=True) or {}
    return jsonify({'success': True, 'data': payload}), 200

