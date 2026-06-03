from decimal import Decimal

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from extensions import csrf, db
from models import Customer, Product
from services.sale_service import SaleService
from utils.branching import ensure_warehouse_access, get_accessible_warehouses
from utils.decorators import permission_required
from utils.pos_helpers import (
    POS_QA_MARKER,
    get_pos_walkin_customer,
    lookup_pos_product_exact,
    merge_checkout_lines,
    search_pos_products,
    serialize_pos_product,
)
from utils.tenanting import tenant_get, tenant_query


pos_bp = Blueprint("pos", __name__, url_prefix="/pos")


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

        lines_data.append(
            {
                "product": product,
                "quantity": row["quantity"],
                "discount_percent": float(row["discount_percent"]),
                "unit_price": float(row["unit_price"]) if row["unit_price"] is not None else None,
            }
        )

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
