from datetime import datetime, timezone
from urllib.parse import urlparse
import os

from flask import Blueprint, jsonify, request, make_response, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy import select
from extensions import db, limiter, csrf
from models import Customer, Supplier, Product, User
from services.logging_core import LoggingCore
from services.payment_service import PaymentService
from services.stock_service import StockService
from utils.branching import get_accessible_warehouse_ids, get_accessible_warehouses, get_branch_stock_map
from utils.decorators import branch_scope_id, permission_required
from utils.tenanting import get_active_tenant_id

api_bp = Blueprint('api', __name__, url_prefix='/api')

_DEV_TRUSTED_ORIGINS = frozenset({
    'http://localhost:5000',
    'http://127.0.0.1:5000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:55014',
    'http://127.0.0.1:55014',
})


def _is_production_env() -> bool:
    app_env = (current_app.config.get('APP_ENV') or os.environ.get('APP_ENV') or 'production').strip().lower()
    debug = bool(current_app.config.get('DEBUG')) or (os.environ.get('DEBUG') or '').strip().lower() in ('1', 'true', 'yes', 'y')
    return app_env == 'production' and not debug


def _origin_from_referer(referer: str) -> str | None:
    try:
        parsed = urlparse(referer or '')
        if parsed.scheme and parsed.netloc:
            return f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')
    except Exception:
        return None
    return None


def _split_origins(value) -> set[str]:
    if not value:
        return set()
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = str(value).split(',')
    return {str(item).strip().rstrip('/') for item in raw_items if str(item).strip()}


def _trusted_telemetry_origins() -> frozenset[str]:
    origins: set[str] = set()
    for key in ('CLIENT_ERROR_TRUSTED_ORIGINS', 'TRUSTED_ORIGINS', 'CORS_ORIGINS', 'PAYMENT_VAULT_TRUSTED_ORIGINS'):
        origins.update(_split_origins(current_app.config.get(key) or os.environ.get(key)))
    if origins:
        return frozenset(origins)
    if _is_production_env():
        base = (current_app.config.get('BASE_URL') or os.environ.get('BASE_URL') or '').strip().rstrip('/')
        return frozenset({base}) if base else frozenset()
    return _DEV_TRUSTED_ORIGINS


def _validate_public_telemetry_origin():
    """Protect the public JS-error collector from cross-site log spam."""
    origin = (request.headers.get('Origin') or '').strip().rstrip('/')
    referer = (request.headers.get('Referer') or '').strip()

    # Native clients / local curl in development often omit Origin/Referer.
    if not _is_production_env() and not origin and not referer:
        return None

    trusted = _trusted_telemetry_origins()
    if not trusted:
        current_app.logger.warning('client_error telemetry rejected: no trusted origins configured')
        return jsonify({'success': False, 'error': 'Origin policy not configured'}), 503

    if origin:
        if origin in trusted:
            return None
        current_app.logger.warning('client_error telemetry rejected: origin=%s', origin[:120])
        return jsonify({'success': False, 'error': 'Origin غير مسموح'}), 403

    if referer:
        ref_origin = _origin_from_referer(referer)
        if ref_origin and ref_origin in trusted:
            return None
        current_app.logger.warning('client_error telemetry rejected: referer=%s', referer[:120])
        return jsonify({'success': False, 'error': 'Referer غير مسموح'}), 403

    return jsonify({'success': False, 'error': 'Origin أو Referer مطلوب'}), 403


def _scoped_customer_query():
    from models import Payment, Receipt, Sale

    query = Customer.query
    tid = get_active_tenant_id(current_user)
    if tid is not None:
        query = query.filter(Customer.tenant_id == tid)
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
    tid = get_active_tenant_id(current_user)
    if tid is not None:
        query = query.filter(Supplier.tenant_id == tid)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        return query

    purchase_ids = select(Purchase.supplier_id).where(Purchase.supplier_id.isnot(None), Purchase.branch_id == scoped_branch_id)
    payment_ids = select(Payment.supplier_id).where(Payment.supplier_id.isnot(None), Payment.branch_id == scoped_branch_id)
    return query.filter(Supplier.id.in_(purchase_ids.union(payment_ids)))


def _customer_balance(customer_id):
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        customer = _scoped_customer_query().filter(Customer.id == customer_id).first()
        return float(customer.get_balance_aed()) if customer else 0.0
    return float(PaymentService.get_customer_balance_scoped(customer_id, branch_id=scoped_branch_id))


def _supplier_balance(supplier_id):
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        supplier = _scoped_supplier_query().filter(Supplier.id == supplier_id).first()
        return float(supplier.get_balance_aed()) if supplier else 0.0
    return float(PaymentService.get_supplier_balance_scoped(supplier_id, branch_id=scoped_branch_id))


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
    except Exception:
        current_app.logger.exception('currency_rate failed from=%s to=%s', from_currency, to_currency)
        resp = make_response(jsonify({
            'success': False,
            'error': 'تعذر جلب سعر الصرف الآن. الرجاء المحاولة لاحقاً أو إدخال السعر يدوياً.',
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
        tid = get_active_tenant_id(current_user)
        if purpose == 'purchase':
            products_query = Product.query.filter(Product.is_active == True, Product.tenant_id == tid)
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
            'has_serial_number': getattr(p, 'has_serial_number', False),
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

    tid = get_active_tenant_id(current_user)
    existing = User.query.filter_by(username=username)
    if tid is not None:
        existing = existing.filter(User.tenant_id == tid)
    existing = existing.first()

    if existing:
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
@permission_required('view_reports')
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

    except Exception:
        current_app.logger.exception('products_low_stock failed')
        return jsonify({
            'success': False,
            'error': 'تعذر تحميل المنتجات قليلة المخزون حالياً'
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
    """Development-only HTTP method echo. Hidden in production."""
    if _is_production_env():
        abort(404)
    payload = request.get_json(silent=True) or {}
    return jsonify({'success': True, 'data': payload}), 200


@api_bp.route('/log-client-error', methods=['POST'])
@csrf.exempt
@limiter.limit("30 per minute")
def log_client_error():
    """Receive JS errors from the browser and store them via LoggingCore.

    Defenses:
    - Origin/Referer allowlist to prevent cross-site log spam.
    - Rate limit: 30/min per user/IP.
    - Payload capped at 50 KB (Nginx / WAF layer recommended for stricter limit).
    - Stack trace truncated by service layer.
    - Cookies / auth headers explicitly excluded from storage.
    """
    origin_error = _validate_public_telemetry_origin()
    if origin_error:
        return origin_error

    if request.content_length and request.content_length > 50 * 1024:
        return '', 413

    data = request.get_json(silent=True) or {}
    message = str(data.get('message', 'Unknown JS error'))[:2000]
    source_file = str(data.get('source', 'frontend.unknown'))[:500]
    event_type = str(data.get('type', 'runtime')).lower()[:40]
    allowed_types = {
        'runtime', 'promise', 'resource', 'fetch', 'fetch_slow',
        'ajax', 'api', 'api_slow', 'concurrency', 'longtask',
        'layout', 'theme',
    }
    if event_type not in allowed_types:
        event_type = 'runtime'
    lineno = data.get('lineno')
    colno = data.get('colno')
    stack = str(data.get('stack', '')) if data.get('stack') else None
    url = str(data.get('url', request.referrer or request.url))[:500]
    request_url = str(data.get('request_url', ''))[:500]
    status = data.get('status')
    method = str(data.get('method', ''))[:10]

    source = f"frontend.{event_type or 'runtime'}"
    level = "WARNING" if event_type in {
        "resource", "fetch", "fetch_slow", "ajax", "api_slow",
        "concurrency", "longtask", "layout", "theme",
    } else "ERROR"

    enriched_message = message
    if lineno:
        enriched_message += f" (line {lineno}, col {colno})"
    if status:
        enriched_message += f" [HTTP {status}]"

    # Build extra WITHOUT cookies, tokens, or auth headers
    extra = {
        'type': event_type,
        'source_file': source_file,
        'line': lineno,
        'column': colno,
        'request_url': request_url,
        'status': status,
        'method': method,
        'route': str(data.get('route', ''))[:300],
        'browser_time': str(data.get('browser_time', ''))[:80],
        'duration_ms': data.get('duration_ms'),
        'active_requests': data.get('active_requests'),
        'repeat_count': data.get('repeat_count'),
        'request_id': str(data.get('request_id', ''))[:80],
        'response_size': data.get('response_size'),
        'cls': data.get('cls'),
        'ui_mode': str(data.get('ui_mode', ''))[:40],
        'ui_variant': str(data.get('ui_variant', ''))[:40],
        'reason': str(data.get('reason', ''))[:120],
        'fingerprint_key': str(data.get('fingerprint_key', ''))[:300],
        'client': data.get('client') if isinstance(data.get('client'), dict) else {},
    }
    if getattr(current_user, 'is_authenticated', False):
        extra['user_id'] = getattr(current_user, 'id', None)
        extra['tenant_id'] = getattr(current_user, 'tenant_id', None)

    LoggingCore.log_frontend_error(
        message=enriched_message,
        level=level,
        source=source,
        url=url,
        user_agent=request.headers.get('User-Agent', '')[:255],
        stack=stack,
        extra=extra,
    )
    return '', 204


@api_bp.route('/industry-fields')
@login_required
def industry_fields():
    industry_code = request.args.get('industry', 'general')
    from services.industry_service import IndustryService
    fields = IndustryService.get_fields_for(industry_code)
    return jsonify({
        'industry': industry_code,
        'fields': [
            {
                'field_code': f.field_code,
                'field_name_ar': f.field_name_ar,
                'field_name_en': f.field_name_en,
                'field_type': f.field_type,
                'is_required': f.is_required,
            } for f in fields
        ],
    })


def _query_accessible_warehouses():
    from models import Warehouse
    q = request.args.get('q', '').strip()
    whs = get_accessible_warehouses(current_user)
    if q:
        whs = whs.filter(Warehouse.name.ilike(f'%{q}%'))
    whs = whs.order_by(Warehouse.name).limit(20).all()
    return [{'id': w.id, 'text': w.name, 'name': w.name} for w in whs]


def _query_products(warehouse_id=None):
    q = request.args.get('q', '').strip()
    products = StockService.get_visible_products_query(current_user)
    if q:
        products = products.filter(
            db.or_(
                Product.name.ilike(f'%{q}%'),
                Product.sku.ilike(f'%{q}%'),
                Product.barcode.ilike(f'%{q}%')
            )
        )
    products = products.order_by(Product.name).limit(20).all()
    warehouse_ids = [warehouse_id] if warehouse_id else get_accessible_warehouse_ids(current_user)
    stock_map = get_branch_stock_map(
        product_ids=[p.id for p in products],
        warehouse_ids=warehouse_ids,
    ) if warehouse_ids else {}
    return [{
        'id': p.id, 'text': f"{p.name} ({p.sku})" if p.sku else p.name,
        'name': p.name, 'sku': p.sku,
        'price': float(p.regular_price or 0),
        'stock': float(stock_map.get(p.id, p.current_stock or 0)),
    } for p in products]


@api_bp.route('/warehouses')
@login_required
def api_warehouses():
    return jsonify({'results': _query_accessible_warehouses()})


@api_bp.route('/products')
@login_required
@permission_required('view_reports')
def api_products():
    wid = request.args.get('warehouse_id', type=int)
    return jsonify({'results': _query_products(wid)})


@api_bp.route('/search_warehouses')
@login_required
def api_search_warehouses():
    return jsonify({'results': _query_accessible_warehouses()})


@api_bp.route('/warehouses/<int:wid>/products')
@login_required
def api_warehouse_products(wid):
    """منتجات مستودع محدد (Select2)"""
    return jsonify({'results': _query_products(wid)})


@api_bp.route('/products/<int:pid>/info')
@login_required
def api_product_info(pid):
    """معلومات منتج (سعر، مخزون)"""
    product = db.session.get(Product, pid)
    if not product:
        return jsonify({'success': False, 'error': 'المنتج غير موجود'}), 404
    tid = get_active_tenant_id(current_user)
    if tid is not None and product.tenant_id != tid:
        return jsonify({'success': False, 'error': 'المنتج غير موجود'}), 404
    warehouse_id = request.args.get('warehouse_id', type=int)
    if warehouse_id:
        from utils.branching import ensure_warehouse_access
        try:
            ensure_warehouse_access(warehouse_id, user=current_user)
        except Exception:
            return jsonify({'success': False, 'error': 'غير مصرح بالوصول إلى المستودع'}), 403
    stock = float(product.current_stock or 0)
    if warehouse_id:
        stock_map = get_branch_stock_map(
            product_ids=[product.id],
            warehouse_ids=[warehouse_id],
        )
        stock = float(stock_map.get(product.id, stock))
    return jsonify({
        'success': True,
        'id': product.id,
        'name': product.name,
        'sku': product.sku,
        'barcode': product.barcode,
        'price': float(product.regular_price or 0),
        'stock': stock,
        'unit': product.unit,
        'is_low_stock': stock <= float(product.min_stock_alert or 0),
    })


@api_bp.route('/products/barcode/<code>')
@login_required
def api_product_by_barcode(code):
    """البحث عن منتج بواسطة الباركود"""
    tid = get_active_tenant_id(current_user)
    query = Product.query.filter(Product.barcode == code)
    if tid is not None:
        query = query.filter(Product.tenant_id == tid)
    product = query.first()
    if not product:
        return jsonify({'success': False, 'error': 'لم يتم العثور على منتج بهذا الباركود'}), 404
    return jsonify({
        'success': True,
        'id': product.id,
        'name': product.name,
        'text': f"{product.name} ({product.sku})" if product.sku else product.name,
        'sku': product.sku,
    })


@api_bp.route('/barcode/validate')
@login_required
def api_barcode_validate():
    """التحقق من صلاحية الباركود"""
    code = request.args.get('code', '').strip()
    if not code:
        return jsonify({'valid': False, 'exists': False, 'normalized': ''})
    normalized = code
    tid = get_active_tenant_id(current_user)
    query = Product.query.filter(Product.barcode == code)
    if tid is not None:
        query = query.filter(Product.tenant_id == tid)
    exists = query.first() is not None
    return jsonify({
        'valid': not exists,
        'exists': exists,
        'normalized': normalized,
    })
