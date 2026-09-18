"""Shipments — الإرساليات الميدانية (قبل الفاتورة) + تتبع الشحن بعد البيع.

Dedicated flow distinct from stock_transfers (warehouse↔warehouse):
Shipment is a field sales expedition: take goods from any warehouse to a site,
then sell/charge/invoice until closed. Keeps legacy post-sale shipment
(source_type sale/purchase_return) for backward compat.
"""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models.shipment import Shipment
from services.shipment_service import ShipmentService
from utils.db_safety import atomic_transaction
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id

shipment_bp = Blueprint("shipments", __name__, url_prefix="/shipments")


def _tenant_id():
    try:
        return get_active_tenant_id()
    except Exception:
        return None


@shipment_bp.route("")
@login_required
@permission_required("manage_warehouse")
def list_shipments():
    tid = _tenant_id()
    status = request.args.get("status", "", type=str)
    q = db.session.query(Shipment).filter(Shipment.tenant_id == tid) if tid else db.session.query(Shipment)
    if status:
        q = q.filter(Shipment.status == status)
    shipments = q.order_by(Shipment.created_at.desc()).all()
    return render_template("shipments/list.html", shipments=shipments)


@shipment_bp.route("/<int:id>")
@login_required
@permission_required("manage_warehouse")
def view_shipment(id):
    s = db.get_or_404(Shipment, id)
    tid = _tenant_id()
    if tid and s.tenant_id != tid:
        from flask import abort

        abort(403)
    from models.sale import Sale

    sales = []
    if hasattr(Sale, "shipment_id"):
        sales = (
            db.session.query(Sale)
            .filter(Sale.shipment_id == s.id, Sale.tenant_id == tid)
            .order_by(Sale.created_at.desc())
            .all()
            if tid
            else []
        )
    return render_template("shipments/view.html", shipment=s, sales=sales)


@shipment_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_warehouse")
def create_shipment():
    if request.method == "POST":
        try:
            lines_data = []
            i = 0
            while True:
                pid = request.form.get(f"lines[{i}][product_id]", type=int)
                if not pid:
                    break
                qty = request.form.get(f"lines[{i}][quantity]", type=float)
                cost = request.form.get(f"lines[{i}][unit_cost]", 0, type=float)
                price = request.form.get(f"lines[{i}][unit_price]", 0, type=float)
                if pid and qty and qty > 0:
                    lines_data.append({"product_id": pid, "quantity": qty, "unit_cost": cost, "unit_price": price})
                i += 1
            if not lines_data:
                flash("⚠️ يجب إضافة منتج واحد على الأقل", "danger")
                return redirect(url_for("shipments.create_shipment"))
            tid = _tenant_id()
            with atomic_transaction("create_shipment"):
                s = ShipmentService.create_field_shipment(
                    from_warehouse_id=request.form.get("from_warehouse_id", type=int),
                    destination_name=request.form.get("destination_name"),
                    destination_warehouse_id=request.form.get("destination_warehouse_id", type=int),
                    destination_type=request.form.get("destination_type", "site"),
                    tenant_id=tid,
                    created_by_id=current_user.id,
                    assigned_to_id=request.form.get("assigned_to_id", type=int),
                    lines_data=lines_data,
                    notes=request.form.get("notes"),
                )
                try:
                    from services.logging_core import LoggingCore

                    LoggingCore.log_audit("create", "shipments", s.id, {"shipment_number": s.shipment_number})
                except Exception as exc:
                    import logging

                    logging.getLogger(__name__).debug("audit log failed: %s", exc)
            flash(f"✅ تم إنشاء الإرسالية {s.shipment_number}", "success")
            return redirect(url_for("shipments.view_shipment", id=s.id))
        except Exception as e:
            # atomic_transaction (line 89) already rolled back on exception;
            # no direct db.session.rollback() permitted (GRIMOIRE G1-ATOMICITY)
            flash(f"❌ خطأ: {str(e)}", "danger")
    from models.product import Product
    from models.user import User
    from models.warehouse import Warehouse
    from utils.tenanting import tenant_query

    tid = _tenant_id()
    warehouses = (
        tenant_query(Warehouse).filter_by(is_active=True).all()
        if tid
        else Warehouse.query.filter_by(is_active=True).all()
    )
    products = (
        tenant_query(Product).filter_by(is_active=True).order_by(Product.name).all()
        if tid
        else Product.query.filter_by(is_active=True).order_by(Product.name).all()
    )
    users = tenant_query(User).filter_by(is_active=True).all() if tid else User.query.filter_by(is_active=True).all()
    return render_template("shipments/create.html", warehouses=warehouses, products=products, users=users)


@shipment_bp.route("/<int:id>/send", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def send_shipment(id):
    try:
        with atomic_transaction("send_shipment"):
            ShipmentService.send_shipment(id, current_user.id)
        flash("✅ تم إرسال الإرسالية", "success")
    except ValueError as e:
        flash(f"⚠️ {str(e)}", "danger")
    return redirect(url_for("shipments.view_shipment", id=id))


@shipment_bp.route("/<int:id>/arrive", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def arrive_shipment(id):
    try:
        with atomic_transaction("arrive_shipment"):
            ShipmentService.arrive_shipment(id, current_user.id)
        flash("✅ تم تأكيد وصول الإرسالية", "success")
    except ValueError as e:
        flash(f"⚠️ {str(e)}", "danger")
    return redirect(url_for("shipments.view_shipment", id=id))


@shipment_bp.route("/<int:id>/start-selling", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def start_selling(id):
    try:
        with atomic_transaction("start_selling"):
            ShipmentService.start_selling(id, current_user.id)
        flash("✅ بدأ البيع الميداني", "success")
    except ValueError as e:
        flash(f"⚠️ {str(e)}", "danger")
    return redirect(url_for("shipments.view_shipment", id=id))


@shipment_bp.route("/<int:id>/close", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def close_shipment(id):
    try:
        with atomic_transaction("close_shipment"):
            ShipmentService.close_shipment(id, current_user.id)
        flash("✅ تم إغلاق الإرسالية", "success")
    except ValueError as e:
        flash(f"⚠️ {str(e)}", "danger")
    return redirect(url_for("shipments.view_shipment", id=id))


@shipment_bp.route("/<int:id>/cancel", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def cancel_shipment(id):
    try:
        with atomic_transaction("cancel_shipment"):
            ShipmentService.cancel_shipment(id, current_user.id)
        flash("✅ تم إلغاء الإرسالية", "success")
    except ValueError as e:
        flash(f"⚠️ {str(e)}", "danger")
    return redirect(url_for("shipments.view_shipment", id=id))


@shipment_bp.route("/api/warehouses")
@login_required
def api_warehouses():
    q = request.args.get("q", "", type=str).strip()
    from models.warehouse import Warehouse

    tid = _tenant_id()
    query = db.session.query(Warehouse).filter_by(is_active=True)
    if tid:
        query = query.filter(Warehouse.tenant_id == tid)
    if q:
        query = query.filter(Warehouse.name.ilike(f"%{q}%"))
    rows = query.limit(20).all()
    return jsonify([{"id": w.id, "text": w.name, "name": w.name} for w in rows])


@shipment_bp.route("/api/products")
@login_required
def api_products():
    q = request.args.get("q", "", type=str).strip()
    from models.product import Product

    tid = _tenant_id()
    query = db.session.query(Product).filter_by(is_active=True)
    if tid:
        query = query.filter(Product.tenant_id == tid)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    rows = query.limit(20).all()
    return jsonify(
        [{"id": p.id, "text": p.name, "name": p.name, "unit_price": str(p.regular_price or 0)} for p in rows]
    )
