from decimal import Decimal

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user

from extensions import db
from models import Customer, Product, Warehouse
from services.sale_service import SaleService
from utils.decorators import permission_required


pos_bp = Blueprint('pos', __name__, url_prefix='/pos')


@pos_bp.route('/')
@login_required
@permission_required('manage_sales')
def index():
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.is_main.desc(), Warehouse.name).all()
    return render_template('pos/index.html', warehouses=warehouses)


@pos_bp.route('/api/products')
@login_required
@permission_required('manage_sales')
def api_products():
    q = (request.args.get('q') or '').strip()
    per_page = request.args.get('per_page', 20, type=int)
    per_page = max(1, min(per_page, 50))

    query = Product.query.filter_by(is_active=True)
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.barcode.ilike(like),
            )
        )

    products = query.order_by(Product.name).limit(per_page).all()
    results = []
    for p in products:
        results.append({
            'id': p.id,
            'name': p.name,
            'sku': p.sku or '',
            'barcode': p.barcode or '',
            'price': float(p.regular_price or 0),
            'stock': float(p.current_stock or 0),
            'unit': p.unit,
            'text': f"{p.name} ({p.sku})" if p.sku else p.name,
        })
    return jsonify(results)


@pos_bp.route('/api/customers')
@login_required
@permission_required('manage_sales')
def api_customers():
    q = (request.args.get('q') or '').strip()
    per_page = request.args.get('per_page', 20, type=int)
    per_page = max(1, min(per_page, 50))

    query = Customer.query.filter_by(is_active=True)
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
            )
        )

    customers = query.order_by(Customer.name).limit(per_page).all()
    results = []
    for c in customers:
        phone = (c.phone or '').strip()
        label = c.name
        if phone:
            label = f"{label} - {phone}"
        results.append({
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'customer_type': c.customer_type,
            'text': label,
        })
    return jsonify(results)


@pos_bp.route('/api/checkout', methods=['POST'])
@login_required
@permission_required('manage_sales')
def api_checkout():
    payload = request.get_json(silent=True) or {}

    customer_id = payload.get('customer_id')
    if not customer_id:
        return jsonify({'success': False, 'error': 'يرجى اختيار العميل.'}), 400

    customer = db.session.get(Customer, int(customer_id))
    if not customer or not customer.is_active:
        return jsonify({'success': False, 'error': 'العميل غير صالح أو غير نشط.'}), 400

    warehouse_id = payload.get('warehouse_id')
    if warehouse_id:
        warehouse = db.session.get(Warehouse, int(warehouse_id))
        if not warehouse or not warehouse.is_active:
            return jsonify({'success': False, 'error': 'المستودع المحدد غير صالح.'}), 400
        warehouse_id = warehouse.id
    else:
        warehouse_id = None

    currency = (payload.get('currency') or 'AED').strip().upper()
    exchange_rate = payload.get('exchange_rate', 1.0)

    lines = payload.get('lines') or []
    if not isinstance(lines, list) or not lines:
        return jsonify({'success': False, 'error': 'يرجى إضافة منتجات للسلة.'}), 400

    lines_data = []
    for row in lines:
        try:
            product_id = int(row.get('product_id'))
            qty = Decimal(str(row.get('quantity')))
            discount_percent = Decimal(str(row.get('discount_percent', 0) or 0))
            unit_price = row.get('unit_price', None)
            if unit_price is not None and str(unit_price).strip() != '':
                unit_price = Decimal(str(unit_price))
            else:
                unit_price = None
        except Exception:
            return jsonify({'success': False, 'error': 'بيانات السلة غير صالحة.'}), 400

        if qty <= 0:
            return jsonify({'success': False, 'error': 'الكمية يجب أن تكون أكبر من صفر.'}), 400

        product = db.session.get(Product, product_id)
        if not product or not product.is_active:
            return jsonify({'success': False, 'error': 'يوجد منتج غير صالح داخل السلة.'}), 400

        lines_data.append({
            'product': product,
            'quantity': qty,
            'discount_percent': float(discount_percent),
            'unit_price': float(unit_price) if unit_price is not None else None,
        })

    payment_method = (payload.get('payment_method') or '').strip()
    paid_amount = payload.get('paid_amount', 0) or 0
    payment_currency = (payload.get('payment_currency') or currency).strip().upper()
    payment_exchange_rate = payload.get('payment_exchange_rate', exchange_rate) or exchange_rate
    reference_number = (payload.get('reference_number') or '').strip() or None

    payment_data = None
    try:
        paid_amount_decimal = Decimal(str(paid_amount))
    except Exception:
        paid_amount_decimal = Decimal('0')

    if paid_amount_decimal > 0:
        if not payment_method:
            return jsonify({'success': False, 'error': 'يرجى اختيار طريقة الدفع.'}), 400
        payment_data = {
            'amount': float(paid_amount_decimal),
            'payment_method': payment_method,
            'currency': payment_currency,
            'exchange_rate': float(payment_exchange_rate),
            'reference_number': reference_number,
        }

    try:
        sale = SaleService.create_sale(
            customer=customer,
            seller=current_user,
            lines_data=lines_data,
            warehouse_id=warehouse_id,
            currency=currency,
            user_exchange_rate=exchange_rate,
            discount_amount=payload.get('discount_amount', 0) or 0,
            shipping_cost=payload.get('shipping_cost', 0) or 0,
            tax_rate=payload.get('tax_rate', 0) or 0,
            notes=(payload.get('notes') or '').strip() or None,
            payment_data=payment_data,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        return jsonify({'success': False, 'error': 'فشل إنشاء الفاتورة. تحقق من البيانات وحاول مرة أخرى.'}), 500

    return jsonify({
        'success': True,
        'sale_id': sale.id,
        'sale_number': sale.sale_number,
        'view_url': f"/sales/{sale.id}",
        'print_url': f"/sales/{sale.id}/print",
    })

