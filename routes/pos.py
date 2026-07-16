from decimal import Decimal
from datetime import datetime, timezone
import json

from flask import Blueprint, jsonify, render_template, request, current_app, redirect, url_for, flash
from flask_login import current_user, login_required
from extensions import csrf, db
from models import Customer, PosSession, Product, PosOrderType
from models.enums import PermissionEnum
from models.pos_shift import PosShift
from models.system_settings import SystemSettings
from models.tenant import Tenant
from services.sale_service import SaleService
from utils.branching import ensure_warehouse_access, get_accessible_warehouses, get_active_branch_id
from utils.decorators import permission_required
from utils.db_safety import atomic_transaction
from utils.helpers import generate_number
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


def _pos_register_context():
    from utils.tax_settings import get_prices_include_vat
    from utils.currency_utils import resolve_default_currency
    from services.industry_service import get_pos_profile
    warehouses = [
        w
        for w in get_accessible_warehouses(current_user)
        if w.is_active and w.warehouse_type != w.TYPE_ONLINE
    ]
    tenant = Tenant.get_current()
    tenant_default_currency = resolve_default_currency(tenant) if tenant else 'AED'
    branch_id = get_active_branch_id()
    return {
        'warehouses': warehouses,
        'tenant_default_currency': tenant_default_currency,
        'currency_symbol': tenant_default_currency or 'AED',
        'prices_include_vat': get_prices_include_vat(
            tenant_id=get_active_tenant_id(current_user),
            branch_id=branch_id,
        ),
        'pos_config': get_pos_profile(tenant) if tenant else {
            'business_type': 'general', 'mode': 'retail',
            'enable_tables': False, 'enable_hold': True, 'enable_kds': True,
        },
    }


@pos_bp.before_request
def _require_pos_enabled():
    global_setting = SystemSettings.query.order_by(SystemSettings.id.desc()).first()
    if global_setting and not global_setting.enable_pos:
        if request.is_json or request.path.startswith("/pos/api/"):
            return jsonify({"success": False, "error": "POS غير مفعل على مستوى النظام."}), 403
        return render_template("pos/disabled.html", reason="system"), 403
    tid = get_active_tenant_id(current_user)
    if tid:
        tenant = db.session.get(Tenant, tid)
        if tenant and not tenant.enable_pos:
            if request.is_json or request.path.startswith("/pos/api/"):
                return jsonify({"success": False, "error": "POS غير مفعل لهذه الشركة."}), 403
            return render_template("pos/disabled.html", reason="tenant"), 403
    return None

@pos_bp.route("/")
@login_required
@permission_required("manage_sales")
def index():
    return render_template("pos/index.html", **_pos_register_context())


@pos_bp.route("/grid")
@login_required
@permission_required("manage_sales")
def grid():
    return render_template("pos/grid.html", **_pos_register_context())


@pos_bp.route("/api/order-types")
@login_required
@permission_required("manage_sales")
def api_order_types():
    """Return the tenant's configured, active POS order types."""
    tid = get_active_tenant_id(current_user)
    if not tid:
        return jsonify({"success": False, "error": "لا يوجد فرع/شركة نشطة"}), 400
    types = PosOrderType.for_tenant(tid, active_only=True)
    default = PosOrderType.default_for_tenant(tid)
    return jsonify({
        "success": True,
        "order_types": [t.to_dict() for t in types],
        "default_code": default.code if default else None,
    })


@pos_bp.route("/settings/order-types", methods=["GET", "POST"])
@login_required
@permission_required("manage_sales")
def order_type_settings():
    """Per-company configuration of POS order types (replaces hard-coded restaurant types)."""
    tid = get_active_tenant_id(current_user)
    if not tid:
        flash("لا يوجد فرع/شركة نشطة.", "warning")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        action = request.form.get("action") or ""
        try:
            if action == "create":
                code = (request.form.get("code") or "").strip()
                if not code:
                    raise ValueError("يرجى إدخال رمز النوع (code).")
                if PosOrderType.get_by_code(tid, code):
                    raise ValueError("رمز النوع موجود مسبقاً.")
                db.session.add(PosOrderType(
                    tenant_id=tid,
                    code=code,
                    name_ar=(request.form.get("name_ar") or "").strip() or code,
                    name_en=(request.form.get("name_en") or "").strip() or None,
                    is_active=request.form.get("is_active") == "on",
                    sort_order=int(request.form.get("sort_order") or 0),
                    is_default=request.form.get("is_default") == "on",
                    kds_enabled=request.form.get("kds_enabled") == "on",
                ))
                flash("تمت إضافة نوع الطلب.", "success")
            elif action == "edit":
                ot = db.session.get(PosOrderType, int(request.form.get("ot_id")))
                if not ot or ot.tenant_id != tid:
                    raise ValueError("نوع الطلب غير موجود.")
                ot.name_ar = (request.form.get("name_ar") or "").strip() or ot.code
                ot.name_en = (request.form.get("name_en") or "").strip() or None
                ot.is_active = request.form.get("is_active") == "on"
                ot.sort_order = int(request.form.get("sort_order") or 0)
                ot.kds_enabled = request.form.get("kds_enabled") == "on"
                ot.is_default = request.form.get("is_default") == "on"
                flash("تم تحديث نوع الطلب.", "success")
            elif action == "toggle":
                ot = db.session.get(PosOrderType, int(request.form.get("ot_id")))
                if not ot or ot.tenant_id != tid:
                    raise ValueError("نوع الطلب غير موجود.")
                ot.is_active = not ot.is_active
                flash("تم تحديث حالة نوع الطلب.", "success")
            elif action == "set_default":
                ot = db.session.get(PosOrderType, int(request.form.get("ot_id")))
                if not ot or ot.tenant_id != tid:
                    raise ValueError("نوع الطلب غير موجود.")
                for o in PosOrderType.for_tenant(tid, active_only=False):
                    o.is_default = (o.id == ot.id)
                flash("تم تعيين النوع الافتراضي.", "success")
            elif action == "delete":
                ot = db.session.get(PosOrderType, int(request.form.get("ot_id")))
                if not ot or ot.tenant_id != tid:
                    raise ValueError("نوع الطلب غير موجود.")
                if ot.is_default:
                    raise ValueError("لا يمكن حذف النوع الافتراضي.")
                db.session.delete(ot)
                flash("تم حذف نوع الطلب.", "success")
            else:
                raise ValueError("إجراء غير معروف.")
            db.session.commit()
        except ValueError as exc:
            flash(str(exc), "warning")
        except Exception as exc:
            db.session.rollback()
            flash(f"خطأ: {exc}", "danger")
        return redirect(url_for("pos.order_type_settings"))

    types = PosOrderType.for_tenant(tid, active_only=False)
    return render_template("pos/order_types.html", types=types)


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
        with atomic_transaction('pos_walkin_customer'):
            customer = get_pos_walkin_customer()
    except Exception as exc:
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
@permission_required(PermissionEnum.MANAGE_SALES)
def api_checkout():
    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type يجب أن يكون application/json."}), 415
    payload = request.get_json(silent=True) or {}

    session = get_active_session(current_user)
    if not session:
        return jsonify({"success": False, "error": "لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً."}), 403

    shift = _get_active_shift(current_user)
    if not shift:
        return jsonify({"success": False, "error": "لا توجد وردية مفتوحة. يرجى فتح وردية أولاً."}), 403

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
    product_ids = [int(r["product_id"]) for r in merged]
    if product_ids:
        tid = get_active_tenant_id(current_user)
        locked = {
            p.id: p
            for p in db.session.query(Product)
            .filter(Product.id.in_(product_ids), Product.tenant_id == tid)
            .with_for_update()
            .all()
        }
    else:
        locked = {}

    for row in merged:
        product = locked.get(int(row["product_id"]))
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
                if not current_user.has_permission(PermissionEnum.OVERRIDE_SALE_PRICE) and not current_user.is_owner:
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
        with atomic_transaction('pos_checkout_flow'):
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
            # Resolve the configured order type (legacy fallback preserved).
            tid = get_active_tenant_id(current_user)
            order_type = (payload.get('order_type') or '').strip()
            ot = PosOrderType.get_by_code(tid, order_type, active_only=True) if order_type else None
            if not ot:
                ot = PosOrderType.default_for_tenant(tid)
                order_type = ot.code if ot else ''
            sale.order_type = order_type
            sale.pos_session_id = session.id
            db.session.add(sale)
            session.total_sales = Decimal(str(session.total_sales or 0)) + Decimal(str(sale.total_amount or 0))
            if payment_data and payment_data.get('payment_method') == 'cash':
                session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + Decimal(str(payment_data.get('amount', 0)))
            db.session.add(session)
            log_mutation('create', 'Sale', sale.id, {'sale_number': sale.sale_number, 'source': 'pos', 'amount': float(sale.total_amount or 0)})

            kds_enabled = bool(ot.kds_enabled) if ot else (order_type in ('dine_in', 'takeaway', 'delivery'))
            if kds_enabled:
                from models import PosKdsOrder
                kds_order = PosKdsOrder(
                    tenant_id=sale.tenant_id,
                    sale_id=sale.id,
                    session_id=session.id,
                    branch_id=get_active_branch_id(),
                    order_number=sale.sale_number,
                    items_json=json.dumps([{
                        'name': getattr(ld['product'], 'name_ar', None) or ld['product'].name,
                        'quantity': float(ld['quantity']),
                        'unit_price': float(ld.get('unit_price') or 0),
                        'notes': ld.get('notes', ''),
                    } for ld in lines_data]),
                    status='pending',
                )
                db.session.add(kds_order)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"POS checkout error: {exc}")
        return jsonify(
            {"success": False, "error": "فشل إنشاء الفاتورة. تحقق من البيانات وحاول مرة أخرى."}
        ), 500

    if order_type in ('dine_in', 'takeaway', 'delivery'):
        _notify_kds(
            {
                'type': 'new_order',
                'order_id': kds_order.id,
                'order_number': kds_order.order_number,
                'tenant_id': sale.tenant_id,
            },
            tenant_id=sale.tenant_id,
        )

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
        with atomic_transaction('pos_session_open'):
            session = create_pos_session(current_user, branch_id, opening_balance, notes)
    except Exception as exc:
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
        with atomic_transaction('pos_session_close'):
            close_pos_session(session, closing_cash, notes)
    except Exception as exc:
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


def _get_active_shift(user=None) -> PosShift | None:
    from utils.tenanting import get_active_tenant_id
    tid = get_active_tenant_id(current_user)
    if not tid:
        return None
    session = get_active_session(current_user)
    if not session:
        return None
    return (
        PosShift.query
        .filter(
            PosShift.tenant_id == int(tid),
            PosShift.session_id == session.id,
            PosShift.user_id == current_user.id,
            PosShift.status == PosShift.SHIFT_OPEN,
        )
        .order_by(PosShift.id.desc())
        .first()
    )


@pos_bp.route("/api/shift/current")
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_shift_current():
    shift = _get_active_shift(current_user)
    if not shift:
        return jsonify({"success": False, "shift": None}), 200
    return jsonify({"success": True, "shift": shift.to_dict()})


@pos_bp.route("/api/shift/open", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_shift_open():
    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type يجب أن يكون application/json."}), 415
    payload = request.get_json(silent=True) or {}
    starting_cash = payload.get("starting_cash", 0) or 0

    session = get_active_session(current_user)
    if not session:
        return jsonify({"success": False, "error": "لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً."}), 403

    existing = _get_active_shift(current_user)
    if existing:
        return jsonify({"success": False, "error": f"يوجد وردية مفتوحة: {existing.shift_number}."}), 409

    try:
        with atomic_transaction("pos_shift_open"):
            tid = get_active_tenant_id(current_user)
            number = generate_number(
                prefix="SHF", model=PosShift, field_name="shift_number",
                branch_code=session.branch_id, tenant_id=int(tid),
            )
            shift = PosShift(
                tenant_id=int(tid),
                session_id=session.id,
                user_id=current_user.id,
                shift_number=number,
                starting_cash=Decimal(str(starting_cash)),
                status=PosShift.SHIFT_OPEN,
            )
            db.session.add(shift)
            db.session.flush()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "shift": shift.to_dict()}), 201


@pos_bp.route("/api/shift/reconcile", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_shift_reconcile():
    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type يجب أن يكون application/json."}), 415
    payload = request.get_json(silent=True) or {}
    actual_cash = payload.get("actual_cash", 0) or 0
    notes = (payload.get("notes") or "").strip() or None

    shift = _get_active_shift(current_user)
    if not shift:
        return jsonify({"success": False, "error": "لا توجد وردية مفتوحة."}), 404

    try:
        with atomic_transaction("pos_shift_reconcile"):
            _accumulate_shift_totals(shift)
            shift.reconcile(Decimal(str(actual_cash)), notes)
            db.session.flush()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "shift": shift.to_dict()})


@pos_bp.route("/api/shift/close", methods=["POST"])
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def api_shift_close():
    shift = _get_active_shift(current_user)
    if not shift:
        return jsonify({"success": False, "error": "لا توجد وردية مفتوحة."}), 404

    if shift.status == PosShift.SHIFT_OPEN:
        return jsonify({"success": False, "error": "يرجى تسوية الوردية قبل إغلاقها."}), 400

    try:
        with atomic_transaction("pos_shift_close"):
            shift.close()
            db.session.flush()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "shift": shift.to_dict()})


def _accumulate_shift_totals(shift: PosShift):
    from models import Sale
    sales = (
        Sale.query
        .filter(Sale.tenant_id == shift.tenant_id, Sale.pos_session_id == shift.session_id)
        .all()
    )
    total = Decimal("0")
    cash = Decimal("0")
    card = Decimal("0")
    for sale in sales:
        total += Decimal(str(sale.total_amount or 0))
        for payment in sale.payments:
            method = getattr(payment, "payment_method", "")
            amt = Decimal(str(payment.amount or 0))
            if method == "cash":
                cash += amt
            elif method in ("card", "bank_transfer", "e_wallet"):
                card += amt
    shift.total_sales = total
    shift.total_cash_sales = cash
    shift.total_card_sales = card


import queue as _queue
import os as _os
import urllib.request

_HARDWARE_AGENT_URL = _os.environ.get('POS_HARDWARE_AGENT_URL', 'http://127.0.0.1:8567')
_KDS_SUBSCRIBERS: list[tuple[int | None, _queue.Queue]] = []


def _notify_kds(data, tenant_id: int | None = None):
    msg = f'data: {json.dumps(data, ensure_ascii=False)}\n\n'
    target_tid = tenant_id if tenant_id is not None else data.get('tenant_id')
    stale: list[tuple[int | None, _queue.Queue]] = []
    for sub_tid, q in _KDS_SUBSCRIBERS[:]:
        if target_tid is not None and sub_tid is not None and sub_tid != target_tid:
            continue
        try:
            q.put_nowait(msg)
        except Exception:
            stale.append((sub_tid, q))
    for entry in stale:
        if entry in _KDS_SUBSCRIBERS:
            _KDS_SUBSCRIBERS.remove(entry)


@pos_bp.route("/api/kds/stream")
@login_required
@permission_required("view_kds")
def kds_stream():
    subscriber_tid = get_active_tenant_id(current_user)

    def stream():
        q = _queue.Queue()
        _KDS_SUBSCRIBERS.append((subscriber_tid, q))
        try:
            while True:
                msg = q.get()
                yield msg
        except GeneratorExit:
            _KDS_SUBSCRIBERS[:] = [entry for entry in _KDS_SUBSCRIBERS if entry[1] is not q]

    return stream(), {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive'}


@pos_bp.route("/api/kds/orders")
@login_required
@permission_required("view_kds")
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
@permission_required("view_kds")
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
    with atomic_transaction('pos_kds_status'):
        order.status = new_status
        if new_status in ('served', 'cancelled'):
            order.completed_at = datetime.now(timezone.utc)
        order.updated_at = datetime.now(timezone.utc)
    _notify_kds(
        {'type': 'status_update', 'order_id': order.id, 'status': new_status, 'tenant_id': tid},
        tenant_id=tid,
    )
    return jsonify({'success': True})


@pos_bp.route("/kds")
@login_required
@permission_required("view_kds")
def kds_dashboard():
    return render_template("pos/kds.html")


@pos_bp.route("/api/customer-display/<int:session_id>/stream")
def customer_display_stream(session_id):
    display_tenant_id = request.args.get('tenant_id', type=int)

    def stream():
        last_status = None
        while True:
            if not display_tenant_id:
                yield f'data: {json.dumps({"type":"closed"})}\n\n'
                break
            session = db.session.get(PosSession, session_id)
            if not session or session.tenant_id != display_tenant_id:
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
            kds_order = PosKdsOrder.query.filter_by(
                sale_id=latest.id,
                tenant_id=session.tenant_id,
            ).first()
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
    return stream(), {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache'}


@pos_bp.route("/customer-display")
def customer_display():
    return render_template("pos/customer_display.html")


@pos_bp.route("/receipt/<int:sale_id>")
@login_required
@permission_required(PermissionEnum.MANAGE_SALES)
def thermal_receipt(sale_id):
    from models import Sale
    sale = tenant_get(Sale, sale_id)
    if not sale:
        abort(404)
    customer = sale.customer
    return render_template("pos/receipt.html", sale=sale, customer=customer)


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
    with atomic_transaction('pos_floor_create'):
        db.session.add(floor)
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
    with atomic_transaction('pos_table_create'):
        db.session.add(table)
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
    with atomic_transaction('pos_table_status'):
        table.status = new_status
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
    with atomic_transaction('pos_table_assign'):
        table.status = 'occupied'
        db.session.add(torder)
    return jsonify({'success': True})

