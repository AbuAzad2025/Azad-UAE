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
    search_pos_products,
    serialize_pos_product,
)
from utils.structured_logging import log_mutation
from services.logging_core import LoggingCore
from utils.tenanting import tenant_get, tenant_query, get_active_tenant_id

pos_bp = Blueprint("pos", __name__, url_prefix="/pos")

@pos_bp.before_request
def _require_pos_enabled():
    global_setting = SystemSettings.query.order_by(SystemSettings.id.desc()).first()
    if global_setting and not global_setting.enable_pos:
        if request.is_json or request.path.startswith("/pos/api/"):
            return jsonify({"success": False, "error": "POS غير مفعل على مستوى النظام."}), 403
        return render_template("pos/disabled.html", reason="system"), 403
    tid = get_active_tenant_id()
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
    warehouses = [
        w
        for w in get_accessible_warehouses(current_user)
        if w.is_active and w.warehouse_type != w.TYPE_ONLINE
    ]
    return render_template("pos/index.html", warehouses=warehouses)


@pos_bp.route("/api/products")
@login_required
@permission_required("manage_sales")
def api_products():
    q = (request.args.get("q") or "").strip()
    per_page = request.args.get("per_page", 20, type=int)
    warehouse_id = request.args.get("warehouse_id", type=int)

    products, stock_map, _ = search_pos_products(
        q,
        user=current_user,
        warehouse_id=warehouse_id,
        per_page=per_page,
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

    currency = (payload.get("currency") or "AED").strip().upper()
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
    except ValueError:
        return jsonify({"success": False, "error": "تعذر إنشاء الفاتورة من البيانات المرسلة."}), 400
    except Exception:
        return jsonify(
            {"success": False, "error": "فشل إنشاء الفاتورة. تحقق من البيانات وحاول مرة أخرى."}
        ), 500

    log_mutation('create', 'Sale', sale.id, {'sale_number': sale.sale_number, 'source': 'pos', 'amount': float(sale.grand_total or 0)})

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
