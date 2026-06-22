from decimal import Decimal
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from extensions import csrf, db
from models import Customer, PosSession, Product
from models.system_settings import SystemSettings
from models.tenant import Tenant
from services.sale_service import SaleService
from utils.branching import ensure_warehouse_access, get_accessible_warehouses, get_active_branch_id
from utils.decorators import permission_required
from utils.pos_helpers import (
    POS_QA_MARKER,
    create_pos_session,
    close_pos_session,
    get_active_session,
    get_pos_walkin_customer,
    lookup_pos_product_exact,
    merge_checkout_lines,
    require_active_session,
    search_pos_products,
    serialize_pos_product,
)
from utils.structured_logging import log_mutation
from services.logging_core import LoggingCore
from utils.tenanting import tenant_get, tenant_query, get_active_tenant_id
from utils.currency_utils import context_aware_default_currency

pos_bp = Blueprint("pos", __name__, url_prefix="/pos")

@pos_bp.before_request
def _require_pos_enabled():
    global_setting = SystemSettings.query.order_by(SystemSettings.id.desc()).first()
    if global_setting and not global_setting.enable_pos:
        if request.is_json or request.path.startswith("/pos/api/"):
            return jsonify({"success": False, "error": "POS غير مفعل على مستوى النظام."}), 403
        return render_template("pos/disabled.html", reason="system"), 403
    tid = get_active_tenant_id(current_user)
    if tid:
        tenant = Tenant.query.get(tid)
        if tenant and not tenant.enable_pos:
            if request.is_json or request.path.startswith("/pos/api/"):
                return jsonify({"success": False, "error": "POS غير مفعل لهذه الشركة."}), 403
            return render_template("pos/disabled.html", reason="tenant"), 403

@pos_bp.route("/")
@login_required
@permission_required("manage_sales")
def index():
    from utils.tax_settings import get_prices_include_vat
    from utils.currency_utils import context_aware_default_currency, resolve_default_currency
    warehouses = [
        w
        for w in get_accessible_warehouses(current_user)
        if w.is_active and w.warehouse_type != w.TYPE_ONLINE
    ]
    tenant = tenant_get(current_user)
    tenant_default_currency = resolve_default_currency(tenant) if tenant else 'AED'
    currency_symbol = tenant_default_currency if tenant_default_currency else 'AED'
    branch_id = get_active_branch_id()
    prices_include_vat = get_prices_include_vat(
        tenant_id=get_active_tenant_id(current_user),
        branch_id=branch_id
    )
    return render_template(
        "pos/index.html",
        warehouses=warehouses,
        tenant_default_currency=tenant_default_currency,
        currency_symbol=currency_symbol,
        prices_include_vat=prices_include_vat,
    )


@pos_bp.route("/grid")
@login_required
@permission_required("manage_sales")
def grid():
    from utils.tax_settings import get_prices_include_vat
    from utils.currency_utils import context_aware_default_currency, resolve_default_currency
    warehouses = [
        w
        for w in get_accessible_warehouses(current_user)
        if w.is_active and w.warehouse_type != w.TYPE_ONLINE
    ]
    tenant = tenant_get(current_user)
    tenant_default_currency = resolve_default_currency(tenant) if tenant else 'AED'
    currency_symbol = tenant_default_currency if tenant_default_currency else 'AED'
    branch_id = get_active_branch_id()
    prices_include_vat = get_prices_include_vat(
        tenant_id=get_active_tenant_id(current_user),
        branch_id=branch_id
    )
    return render_template(
        "pos/grid.html",
        warehouses=warehouses,
        tenant_default_currency=tenant_default_currency,
        currency_symbol=currency_symbol,
        prices_include_vat=prices_include_vat,
    )


@pos_bp.route("/api/categories")
@login_required
@permission_required("manage_sales")
def api_categories():
    from models import ProductCategory
    query = tenant_query(ProductCategory).filter_by(is_active=True)
    cats = query.order_by(ProductCategory.sort_order, ProductCategory.name).all()
    return jsonify([{"id": c.id, "name": c.name, "name_ar": c.name_ar} for c in cats])


@pos_bp.route("/api/products")
@login_required
@permission_required("manage_sales")
def api_products():
    q = (request.args.get("q") or "").strip()
    per_page = request.args.get("per_page", 20, type=int)
    warehouse_id = request.args.get("warehouse_id", type=int)
    category_id = request.args.get("category_id", type=int)

    products, stock_map, _ = search_pos_products(
        q,
        user=current_user,
        warehouse_id=warehouse_id,
        per_page=per_page,
        category_id=category_id,
    )
    results = [
        serialize_pos_product(p, stock_map, warehouse_id=warehouse_id) for p in products
    ]
    return jsonify(results)


@pos_bp.route("/api/product")
@login_required
@permission_required("manage_sales")
def api_product_lookup():
    """Exact barcode/SKU lookup — JSON 404 when not found."""
    code = (request.args.get("code") or request.args.get("barcode") or "").strip()
    if not code:
        return jsonify({"success": False, "error": "رمز المنتج مطلوب."}), 400

    warehouse_id = request.args.get("warehouse_id", type=int)
    product, stock_map = lookup_pos_product_exact(
        code,
        user=current_user,
        warehouse_id=warehouse_id,
    )
    if not product:
        return jsonify({"success": False, "error": "المنتج غير موجود."}), 404

    payload = serialize_pos_product(product, stock_map, warehouse_id=warehouse_id)
    payload["success"] = True
    if not product.is_active:
        payload["warning"] = "المنتج غير نشط."
    elif payload.get("is_out_of_stock"):
        payload["warning"] = "لا يوجد مخزون في المستودع المحدد."
    return jsonify(payload)


@pos_bp.route("/api/customers")
@login_required
@permission_required("manage_sales")
def api_customers():
    q = (request.args.get("q") or "").strip()
    per_page = request.args.get("per_page", 20, type=int)
    per_page = max(1, min(per_page, 50))

    query = tenant_query(Customer).filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Customer.name.ilike(like),
                Customer.name_ar.ilike(like),
                Customer.phone.ilike(like),
            )
        )

    customers = query.order_by(Customer.name).limit(per_page).all()
    results = []
    for c in customers:
        phone = (c.phone or "").strip()
        label = c.name
        if phone:
            label = f"{label} - {phone}"
        results.append(
            {
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "customer_type": c.customer_type,
                "text": label,
            }
        )
    return jsonify(results)


@pos_bp.route("/api/walkin-customer")
@login_required
@permission_required("manage_sales")
def api_walkin_customer():
    """Quick / walk-in customer for POS (tenant-scoped)."""
    try:
        customer = get_pos_walkin_customer()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify(
        {
            "success": True,
            "id": customer.id,
            "name": customer.name,
            "text": customer.name,
            "customer_type": customer.customer_type,
            "is_walkin": True,
        }
    )


@pos_bp.route("/api/checkout", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_checkout():
    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type يجب أن يكون application/json."}), 415
    payload = request.get_json(silent=True) or {}

    session = get_active_session(current_user)
    if not session:
        return jsonify({"success": False, "error": "لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً."}), 403

    use_quick = bool(payload.get("quick_customer") or payload.get("walkin"))
    customer_id = payload.get("customer_id")

    if use_quick or not customer_id:
        try:
            customer = get_pos_walkin_customer()
        except ValueError:
            return jsonify({"success": False, "error": "بيانات العميل غير صالحة."}), 400
    else:
        customer = tenant_get(Customer, int(customer_id))
        if not customer or not customer.is_active:
            return jsonify({"success": False, "error": "العميل غير صالح أو غير نشط."}), 400

    warehouse_id = payload.get("warehouse_id")
    if warehouse_id:
        try:
            warehouse = ensure_warehouse_access(int(warehouse_id), user=current_user)
            warehouse_id = warehouse.id
        except ValueError:
            return jsonify({"success": False, "error": "بيانات المستودع غير صالحة."}), 400
    else:
        warehouse_id = None

    currency = (payload.get("currency") or context_aware_default_currency()).strip().upper()
    exchange_rate = payload.get("exchange_rate", 1.0)

    lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines:
        return jsonify({"success": False, "error": "يرجى إضافة منتجات للسلة."}), 400

    try:
        merged = merge_checkout_lines(lines)
    except ValueError:
        return jsonify({"success": False, "error": "بيانات السلة غير صالحة."}), 400

    lines_data = []
    for row in merged:
        product = tenant_get(Product, row["product_id"])
        if not product or not product.is_active:
            return jsonify({"success": False, "error": "يوجد منتج غير صالح داخل السلة."}), 400

        # التحقق من السيريال للمنتجات ذات الأرقام التسلسلية
        if getattr(product, 'has_serial_number', False):
            serials = row.get("serials") or payload.get("serials", {}).get(str(product.id)) or []
            clean_serials = [s.strip() for s in serials if s and s.strip()]
            expected_qty = int(row["quantity"])
            if len(clean_serials) != expected_qty:
                return jsonify({
                    "success": False,
                    "error": f'⚠️ المنتج "{product.name}" يتطلب {expected_qty} أرقاماً تسلسلية، ولكن تم إدخال {len(clean_serials)} فقط.'
                }), 400
            row["serials"] = clean_serials

        lines_data.append(
            {
                "product": product,
                "quantity": row["quantity"],
                "discount_percent": float(row["discount_percent"]),
                "unit_price": float(row["unit_price"]) if row["unit_price"] is not None else None,
                "serials": row.get("serials", []),
            }
        )

    # التحقق من صلاحية تعديل السعر
    for ld in lines_data:
        product = ld["product"]
        unit_price = ld.get("unit_price")
        if unit_price is not None:
            standard_price = float(product.get_price_for_customer(customer.customer_type))
            if abs(float(unit_price) - standard_price) > 0.001:
                if not current_user.has_permission('override_sale_price') and not current_user.is_owner:
                    return jsonify({
                        "success": False,
                        "error": f'⚠️ ليس لديك صلاحية تغيير سعر المنتج "{product.name}".\n'
                                 f'السعر القياسي: {standard_price}'
                    }), 403
                # تسجيل التعديل
                LoggingCore.log_audit('price_override', 'pos', product.id, {
                    'product': product.name,
                    'standard_price': standard_price,
                    'override_price': float(unit_price),
                    'user_id': current_user.id,
                })

    payment_method = (payload.get("payment_method") or "").strip()
    paid_amount = payload.get("paid_amount", 0) or 0
    payment_currency = (payload.get("payment_currency") or currency).strip().upper()
    payment_exchange_rate = payload.get("payment_exchange_rate", exchange_rate) or exchange_rate
    reference_number = (payload.get("reference_number") or "").strip() or None

    payment_data = None
    try:
        paid_amount_decimal = Decimal(str(paid_amount))
    except Exception:
        paid_amount_decimal = Decimal("0")

    if paid_amount_decimal > 0:
        if not payment_method:
            return jsonify({"success": False, "error": "يرجى اختيار طريقة الدفع."}), 400
        payment_data = {
            "amount": float(paid_amount_decimal),
            "payment_method": payment_method,
            "currency": payment_currency,
            "exchange_rate": float(payment_exchange_rate),
            "reference_number": reference_number,
        }

    notes = (payload.get("notes") or "").strip() or None
    if payload.get("qa_marker"):
        tag = f"{POS_QA_MARKER}"
        notes = f"{tag} {notes}".strip() if notes else tag

    try:
        sale = SaleService.create_sale(
            customer=customer,
            seller=current_user,
            lines_data=lines_data,
            warehouse_id=warehouse_id,
            currency=currency,
            user_exchange_rate=exchange_rate,
            discount_amount=payload.get("discount_amount", 0) or 0,
            shipping_cost=payload.get("shipping_cost", 0) or 0,
            tax_rate=payload.get("tax_rate", 0) or 0,
            notes=notes,
            payment_data=payment_data,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"POS checkout error: {exc}")
        return jsonify(
            {"success": False, "error": "فشل إنشاء الفاتورة. تحقق من البيانات وحاول مرة أخرى."}
        ), 500

    sale.pos_session_id = session.id
    db.session.add(sale)
    db.session.flush()
    from decimal import Decimal as _Decimal
    session.total_sales = _Decimal(str(session.total_sales or 0)) + _Decimal(str(sale.total_amount or 0))
    if payment_data and payment_data.get('payment_method') == 'cash':
        session.total_cash_sales = _Decimal(str(session.total_cash_sales or 0)) + _Decimal(str(payment_data.get('amount', 0)))
    db.session.add(session)
    db.session.commit()
    log_mutation('create', 'Sale', sale.id, {'sale_number': sale.sale_number, 'source': 'pos', 'amount': float(sale.total_amount or 0)})

    order_type = (payload.get('order_type') or '').strip()
    if order_type in ('dine_in', 'takeaway', 'delivery'):
        from models import PosKdsOrder
        from flask import current_app
        kds_order = PosKdsOrder(
            tenant_id=sale.tenant_id,
            sale_id=sale.id,
            session_id=session.id,
            branch_id=get_active_branch_id(),
            order_number=sale.sale_number,
            items_json=json.dumps([{
                'name': getattr(ld['product'], 'name_ar', None) or ld['product'].name,
                'quantity': ld['quantity'],
                'unit_price': float(ld.get('unit_price') or 0),
                'notes': ld.get('notes', ''),
            } for ld in lines_data]),
            status='pending',
        )
        db.session.add(kds_order)
        db.session.commit()
        _notify_kds({'type': 'new_order', 'order_id': kds_order.id, 'order_number': kds_order.order_number})

    return jsonify(
        {
            "success": True,
            "sale_id": sale.id,
            "sale_number": sale.sale_number,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "view_url": f"/sales/{sale.id}",
            "print_url": f"/sales/{sale.id}/print",
        }
    )


@pos_bp.route("/api/session/current")
@login_required
@permission_required("manage_sales")
def api_session_current():
    session = get_active_session(current_user)
    if not session:
        return jsonify({"success": False, "session": None}), 200
    return jsonify({
        "success": True,
        "session": {
            "id": session.id,
            "number": session.session_number,
            "opened_at": session.opened_at.isoformat(),
            "duration_minutes": session.duration_minutes,
            "opening_balance": float(session.opening_balance_cash or 0),
            "total_sales": float(session.total_sales or 0),
            "total_cash_sales": float(session.total_cash_sales or 0),
            "total_card_sales": float(session.total_card_sales or 0),
            "status": session.status,
        }
    })


@pos_bp.route("/api/session/open", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_session_open():
    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type يجب أن يكون application/json."}), 415
    payload = request.get_json(silent=True) or {}
    opening_balance = payload.get("opening_balance", 0) or 0
    notes = (payload.get("notes") or "").strip() or None

    existing = get_active_session(current_user)
    if existing:
        return jsonify({
            "success": False,
            "error": f"توجد جلسة مفتوحة بالفعل: {existing.session_number}. يرجى إغلاقها أولاً."
        }), 409

    branch_id = get_active_branch_id(current_user)
    if not branch_id:
        return jsonify({"success": False, "error": "لا يوجد فرع نشط. يرجى تحديد فرع."}), 400

    try:
        session = create_pos_session(current_user, branch_id, opening_balance, notes)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({
        "success": True,
        "session": {
            "id": session.id,
            "number": session.session_number,
            "opened_at": session.opened_at.isoformat(),
            "opening_balance": float(session.opening_balance_cash or 0),
            "status": session.status,
        }
    }), 201


@pos_bp.route("/api/session/close", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_session_close():
    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type يجب أن يكون application/json."}), 415
    payload = request.get_json(silent=True) or {}
    closing_cash = payload.get("closing_balance", 0) or 0
    notes = (payload.get("notes") or "").strip() or None

    try:
        session = require_active_session(current_user)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    try:
        close_pos_session(session, closing_cash, notes)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({
        "success": True,
        "session": {
            "id": session.id,
            "number": session.session_number,
            "opened_at": session.opened_at.isoformat(),
            "closed_at": session.closed_at.isoformat() if session.closed_at else None,
            "opening_balance": float(session.opening_balance_cash or 0),
            "closing_balance": float(session.closing_balance_cash or 0),
            "expected_balance": float(session.expected_balance or 0),
            "difference": float(session.difference or 0),
            "total_sales": float(session.total_sales or 0),
            "total_cash_sales": float(session.total_cash_sales or 0),
            "total_card_sales": float(session.total_card_sales or 0),
            "duration_minutes": session.duration_minutes,
            "status": session.status,
        }
    })


@pos_bp.route("/api/session/report")
@login_required
@permission_required("manage_sales")
def api_session_report():
    session_id = request.args.get("session_id", type=int)
    if session_id:
        session = tenant_get(PosSession, session_id)
        if not session:
            return jsonify({"success": False, "error": "الجلسة غير موجودة."}), 404
    else:
        session = get_active_session(current_user)
        if not session:
            return jsonify({"success": False, "session": None, "error": "لا توجد جلسة مفتوحة."}), 200

    return jsonify({
        "success": True,
        "session": {
            "id": session.id,
            "number": session.session_number,
            "user_id": session.user_id,
            "branch_id": session.branch_id,
            "opened_at": session.opened_at.isoformat(),
            "closed_at": session.closed_at.isoformat() if session.closed_at else None,
            "opening_balance": float(session.opening_balance_cash or 0),
            "closing_balance": float(session.closing_balance_cash or 0) if session.closing_balance_cash is not None else None,
            "expected_balance": float(session.expected_balance or 0) if session.expected_balance is not None else None,
            "difference": float(session.difference or 0) if session.difference is not None else None,
            "total_sales": float(session.total_sales or 0),
            "total_cash_sales": float(session.total_cash_sales or 0),
            "total_card_sales": float(session.total_card_sales or 0),
            "duration_minutes": session.duration_minutes,
            "status": session.status,
            "notes": session.notes or "",
    }
})


import queue as _queue
import os as _os
import urllib.request

_HARDWARE_AGENT_URL = _os.environ.get('POS_HARDWARE_AGENT_URL', 'http://127.0.0.1:8567')
_KDS_SUBSCRIBERS: list[_queue.Queue] = []


def _notify_kds(data):
    msg = f'data: {json.dumps(data, ensure_ascii=False)}\n\n'
    for q in _KDS_SUBSCRIBERS[:]:
        try:
            q.put_nowait(msg)
        except Exception:
            _KDS_SUBSCRIBERS.remove(q)


@pos_bp.route("/api/kds/stream")
@login_required
@permission_required("manage_sales")
def kds_stream():
    def stream():
        q = _queue.Queue()
        _KDS_SUBSCRIBERS.append(q)
        try:
            while True:
                msg = q.get()
                yield msg
        except GeneratorExit:
            _KDS_SUBSCRIBERS.remove(q)

    return stream(), {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive'}


@pos_bp.route("/api/kds/orders")
@login_required
@permission_required("manage_sales")
def kds_orders():
    from models import PosKdsOrder
    tid = get_active_tenant_id(current_user)
    orders = PosKdsOrder.query.filter_by(tenant_id=tid).order_by(PosKdsOrder.created_at.desc()).limit(50).all()
    return jsonify([{
        'id': o.id,
        'order_number': o.order_number,
        'status': o.status,
        'created_at': o.created_at.isoformat(),
        'items': json.loads(o.items_json),
    } for o in orders])


@pos_bp.route("/api/kds/orders/<int:order_id>/status", methods=["POST"])
@login_required
@permission_required("manage_sales")
def kds_update_status(order_id):
    from models import PosKdsOrder
    from datetime import datetime, timezone
    tid = get_active_tenant_id(current_user)
    order = PosKdsOrder.query.filter_by(id=order_id, tenant_id=tid).first()
    if not order:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    payload = request.get_json(silent=True) or {}
    new_status = payload.get('status', '')
    if new_status not in ('pending', 'preparing', 'ready', 'served', 'cancelled'):
        return jsonify({'error': 'حالة غير صالحة'}), 400
    order.status = new_status
    if new_status in ('served', 'cancelled'):
        order.completed_at = datetime.now(timezone.utc)
    order.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    _notify_kds({'type': 'status_update', 'order_id': order.id, 'status': new_status})
    return jsonify({'success': True})


@pos_bp.route("/kds")
@login_required
@permission_required("manage_sales")
def kds_dashboard():
    return render_template("pos/kds.html")


@pos_bp.route("/api/customer-display/<int:session_id>/stream")
def customer_display_stream(session_id):
    def stream():
        last_status = None
        while True:
            from models import PosSession
            session = db.session.get(PosSession, session_id)
            if not session:
                yield f'data: {json.dumps({"type":"closed"})}\n\n'
                break
            from models import Sale
            sales = Sale.query.filter(
                Sale.tenant_id == session.tenant_id,
                Sale.pos_session_id == session_id,
            ).order_by(Sale.id.desc()).limit(5).all()
            if not sales:
                yield f'data: {json.dumps({"type":"waiting"})}\n\n'
                import time; time.sleep(3)
                continue
            latest = sales[0]
            from models import PosKdsOrder
            kds_order = PosKdsOrder.query.filter_by(sale_id=latest.id).first()
            status = kds_order.status if kds_order else 'confirmed'
            if status != last_status:
                last_status = status
                items = []
                for line in latest.lines:
                    items.append({
                        'name': line.product.name_ar or line.product.name,
                        'quantity': float(line.quantity),
                        'total': float(line.line_total or 0),
                    })
                yield f'data: {json.dumps({"type":"order_update","order_number":latest.sale_number,"items":items,"total":float(latest.total_amount or 0),"status":status})}\n\n'
            import time; time.sleep(3)
    resp = stream()
    resp.close = lambda: None
    return resp, {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache'}


@pos_bp.route("/customer-display")
def customer_display():
    return render_template("pos/customer_display.html")


@pos_bp.route("/api/hardware/print-receipt", methods=["POST"])
@login_required
@permission_required("manage_sales")
def hardware_print_receipt():
    """توجيه طباعة الفاتورة إلى وكيل الأجهزة المحلي"""
    try:
        body = request.get_data()
        req = urllib.request.Request(
            f'{_HARDWARE_AGENT_URL}/print-receipt',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return jsonify(result), resp.status
    except urllib.error.URLError:
        return jsonify({'error': 'وكيل الأجهزة غير متصل. تأكد من تشغيل pos_hardware_agent.py'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pos_bp.route("/api/hardware/open-drawer", methods=["POST"])
@login_required
@permission_required("manage_sales")
def hardware_open_drawer():
    """فتح درج النقود"""
    try:
        body = request.get_data()
        req = urllib.request.Request(
            f'{_HARDWARE_AGENT_URL}/open-drawer',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return jsonify(result), resp.status
    except urllib.error.URLError:
        return jsonify({'error': 'وكيل الأجهزة غير متصل'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pos_bp.route("/api/hardware/status")
@login_required
@permission_required("manage_sales")
def hardware_status():
    """حالة وكيل الأجهزة"""
    try:
        req = urllib.request.Request(f'{_HARDWARE_AGENT_URL}/status')
        with urllib.request.urlopen(req, timeout=3) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return jsonify(result)
    except urllib.error.URLError:
        return jsonify({'status': 'disconnected', 'error': 'غير متصل'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 200


@pos_bp.route("/api/floors")
@login_required
@permission_required("manage_sales")
def api_floors():
    from models import PosFloor
    tid = get_active_tenant_id(current_user)
    floors = PosFloor.query.filter_by(tenant_id=tid).order_by(PosFloor.sort_order).all()
    return jsonify([{
        'id': f.id,
        'name': f.name_ar or f.name,
        'sort_order': f.sort_order,
        'table_count': f.tables.filter_by(is_active=True).count(),
    } for f in floors])


@pos_bp.route("/api/floors/create", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_floor_create():
    from models import PosFloor
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    name_ar = (payload.get('name_ar') or '').strip()
    if not name:
        return jsonify({'error': 'اسم الطابق مطلوب'}), 400
    tid = get_active_tenant_id(current_user)
    floor = PosFloor(tenant_id=tid, name=name, name_ar=name_ar or None)
    db.session.add(floor)
    db.session.commit()
    return jsonify({'success': True, 'floor_id': floor.id})


@pos_bp.route("/api/floors/<int:floor_id>/tables")
@login_required
@permission_required("manage_sales")
def api_floor_tables(floor_id):
    from models import PosFloor, PosTable
    tid = get_active_tenant_id(current_user)
    floor = PosFloor.query.filter_by(id=floor_id, tenant_id=tid).first()
    if not floor:
        return jsonify({'error': 'الطابق غير موجود'}), 404
    tables = PosTable.query.filter_by(floor_id=floor_id, is_active=True).order_by(PosTable.sort_order).all()
    return jsonify([{
        'id': t.id,
        'label': t.label,
        'capacity': t.capacity,
        'pos_x': t.pos_x,
        'pos_y': t.pos_y,
        'shape': t.shape,
        'status': t.status,
    } for t in tables])


@pos_bp.route("/api/tables/create", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_table_create():
    from models import PosFloor, PosTable
    payload = request.get_json(silent=True) or {}
    floor_id = payload.get('floor_id')
    label = (payload.get('label') or '').strip()
    if not floor_id or not label:
        return jsonify({'error': 'الطابق والتسمية مطلوبان'}), 400
    tid = get_active_tenant_id(current_user)
    floor = PosFloor.query.filter_by(id=floor_id, tenant_id=tid).first()
    if not floor:
        return jsonify({'error': 'الطابق غير موجود'}), 404
    table = PosTable(
        tenant_id=tid,
        floor_id=floor_id,
        label=label,
        capacity=payload.get('capacity', 4),
        pos_x=payload.get('pos_x', 0),
        pos_y=payload.get('pos_y', 0),
        shape=payload.get('shape', 'rectangle'),
    )
    db.session.add(table)
    db.session.commit()
    return jsonify({'success': True, 'table_id': table.id})


@pos_bp.route("/api/tables/<int:table_id>/status", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_table_update_status(table_id):
    from models import PosTable
    tid = get_active_tenant_id(current_user)
    table = PosTable.query.filter_by(id=table_id, tenant_id=tid).first()
    if not table:
        return jsonify({'error': 'الطاولة غير موجودة'}), 404
    payload = request.get_json(silent=True) or {}
    new_status = payload.get('status', '')
    if new_status not in ('free', 'occupied', 'reserved'):
        return jsonify({'error': 'حالة غير صالحة'}), 400
    table.status = new_status
    db.session.commit()
    return jsonify({'success': True})


@pos_bp.route("/api/tables/<int:table_id>/assign", methods=["POST"])
@login_required
@permission_required("manage_sales")
def api_table_assign(table_id):
    from models import PosTable, PosTableOrder
    tid = get_active_tenant_id(current_user)
    table = PosTable.query.filter_by(id=table_id, tenant_id=tid).first()
    if not table:
        return jsonify({'error': 'الطاولة غير موجودة'}), 404
    payload = request.get_json(silent=True) or {}
    sale_id = payload.get('sale_id')
    if not sale_id:
        return jsonify({'error': 'رقم الفاتورة مطلوب'}), 400
    table.status = 'occupied'
    torder = PosTableOrder(
        tenant_id=tid,
        table_id=table_id,
        sale_id=sale_id,
        guest_count=payload.get('guest_count', 1),
    )
    db.session.add(torder)
    db.session.commit()
    return jsonify({'success': True})

