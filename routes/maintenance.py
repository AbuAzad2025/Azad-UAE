"""
مسارات وحدة الصيانة - Routes Maintenance

جميع المسارات محمية بـ:
- @login_required
- @permission_required(كود الصلاحية)
- @feature_required("maintenance") عبر install_feature_gate

قاعدة الطبقة: المسارات معالجات HTTP فقط — لا منطق أعمال ولا استعلامات
مباشرة على قاعدة البيانات. كل عمل تجاري في ``services/``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext
from flask_login import current_user, login_required

from models import (
    Customer,
    MaintenanceOrder,
    MaintenancePurchaseOrder,
    MaintenanceServiceTemplate,
    MaintenanceWarrantyAudit,
    Product,
    Supplier,
    Warehouse,
)
from services.maintenance_order_service import MaintenanceService
from services.maintenance_purchase_service import MaintenancePurchaseService
from services.maintenance_warranty_service import WarrantyService
from utils.db_safety import atomic_transaction
from utils.decorators import permission_required
from utils.feature_guards import install_feature_gate
from utils.tenanting import (
    require_active_tenant_id,
    tenant_query,
)

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")
install_feature_gate(maintenance_bp, "maintenance")


def _order_or_404(order_id: int, tenant_id: int) -> MaintenanceOrder:
    """Load one maintenance order of this tenant, or 404."""
    order = tenant_query(MaintenanceOrder).filter_by(id=order_id, tenant_id=tenant_id).first()
    if order is None:
        abort(404, description=gettext("أمر الصيانة غير موجود"))
    return order


def _decimal_or_zero(name: str) -> Decimal:
    """Read a form amount. A malformed value is zero, never an exception.

    The service layer validates every amount against its own rules, so a
    typo in the form produces "the value is invalid" there rather than a
    500 here.
    """
    raw = request.form.get(name)
    if raw is None or str(raw).strip() == "":
        return Decimal("0")
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal("0")


def _optional_date(name: str, source=None) -> datetime | None:
    """Read a date. An empty or unreadable date is no date.

    A warranty period is optional - a device can be registered without
    one, and the module then answers "unknown" for it. A malformed date is
    therefore "not given" rather than an error, which also keeps a
    hand-edited query string from turning the report into a 500.
    """
    reader = source if source is not None else request.form
    raw = (reader.get(name) or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


# ============================================================================
# عرض قائمة أوامر الصيانة
# ============================================================================
@maintenance_bp.route("/")
@login_required
@permission_required("manage_maintenance")
def index():
    """قائمة أوامر الصيانة مع فلترة."""
    tid = require_active_tenant_id()
    status = request.args.get("status", "")
    search = request.args.get("search", "")
    warranty = request.args.get("warranty", "")

    q = tenant_query(MaintenanceOrder).filter_by(tenant_id=tid)
    if status:
        q = q.filter(MaintenanceOrder.status == status)
    if warranty:
        q = q.filter(MaintenanceOrder.warranty_status == warranty)
    if search:
        like = f"%{search}%"
        q = q.filter(
            MaintenanceOrder.order_number.ilike(like)
            | MaintenanceOrder.customer_name.ilike(like)
            | MaintenanceOrder.device_serial_number.ilike(like)
            | MaintenanceOrder.device_imei.ilike(like)
            | MaintenanceOrder.device_plate.ilike(like)
        )

    orders = q.order_by(MaintenanceOrder.created_at.desc()).all()
    return render_template(
        "maintenance/index.html",
        orders=orders,
        status=status,
        search=search,
        warranty=warranty,
        warranty_colors=MaintenanceService.get_warranty_colors(tid),
    )


# ============================================================================
# عرض تفاصيل أمر الصيانة
# ============================================================================
@maintenance_bp.route("/<int:order_id>")
@login_required
@permission_required("manage_maintenance")
def detail(order_id):
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)

    products = tenant_query(Product).filter_by(tenant_id=tid, is_active=True).order_by(Product.name).all()
    warehouses = tenant_query(Warehouse).filter_by(tenant_id=tid, is_active=True).all()
    templates = (
        tenant_query(MaintenanceServiceTemplate)
        .filter_by(tenant_id=tid, is_active=True)
        .order_by(MaintenanceServiceTemplate.sort_order)
        .all()
    )

    return render_template(
        "maintenance/detail.html",
        order=order,
        lines=list(order.lines),
        services_lines=list(order.services_lines),
        logs=list(order.status_logs),
        receipts=list(order.receipts),
        invoice=order.invoice,
        returns=list(order.returns),
        device=WarrantyService.find_device_for_order(order.id, tid),
        products=products,
        warehouses=warehouses,
        templates=templates,
        warranty_colors=MaintenanceService.get_warranty_colors(tid),
    )


# ============================================================================
# إنشاء أمر صيانة جديد
# ============================================================================
@maintenance_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("maintenance_receive")
def create():
    tid = require_active_tenant_id()

    if request.method == "POST":
        try:
            with atomic_transaction("maintenance_create_order"):
                order = MaintenanceService.create_order(
                    tenant_id=tid,
                    branch_id=request.form.get("branch_id") or None,
                    warehouse_id=request.form.get("warehouse_id") or None,
                    customer_id=request.form.get("customer_id") or None,
                    customer_name=request.form.get("customer_name") or None,
                    customer_phone=request.form.get("customer_phone") or None,
                    device_brand=request.form.get("device_brand") or None,
                    device_model=request.form.get("device_model") or None,
                    device_serial_number=request.form.get("device_serial_number") or None,
                    device_imei=request.form.get("device_imei") or None,
                    device_plate=request.form.get("device_plate") or None,
                    device_km=request.form.get("device_km") or None,
                    device_fault_description=request.form.get("device_fault_description") or None,
                    received_by=current_user.id,
                    warranty_sale_id=request.form.get("warranty_sale_id") or None,
                    notes=request.form.get("notes") or None,
                    currency=request.form.get("currency") or None,
                    exchange_rate=request.form.get("exchange_rate") or None,
                    prices_include_vat=request.form.get("prices_include_vat") == "on",
                )
                flash(
                    gettext("تم إنشاء أمر الصيانة رقم {number}").format(number=order.order_number),
                    "success",
                )
                return redirect(url_for("maintenance.detail", order_id=order.id))
        except ValueError as e:
            flash(str(e), "danger")
        except Exception as e:
            current_app.logger.exception("Maintenance order creation failed")
            flash(gettext("فشل إنشاء أمر الصيانة: {error}").format(error=str(e)), "danger")

    customers = tenant_query(Customer).filter_by(tenant_id=tid, is_active=True).all()
    warehouses = tenant_query(Warehouse).filter_by(tenant_id=tid, is_active=True).all()
    return render_template(
        "maintenance/create.html",
        customers=customers,
        warehouses=warehouses,
    )


# ============================================================================
# إضافة سطر قطع إلى أمر الصيانة
# ============================================================================
@maintenance_bp.route("/<int:order_id>/lines", methods=["POST"])
@login_required
@permission_required("maintenance_work")
def add_line(order_id):
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_add_line"):
            MaintenanceService.add_line(
                order_id=order_id,
                tenant_id=tid,
                product_id=request.form.get("product_id") or None,
                quantity=_decimal_or_zero("quantity") or Decimal("1"),
                unit_price=_decimal_or_zero("unit_price"),
                discount_percent=_decimal_or_zero("discount_percent"),
                discount_value=_decimal_or_zero("discount_value"),
                discount_mode=request.form.get("discount_mode", "percent"),
                tax_rate=None,
                warehouse_id=request.form.get("warehouse_id") or order.warehouse_id,
                actor_id=current_user.id,
            )
            flash(gettext("تم إضافة القطعة إلى الأمر"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.exception("Maintenance line creation failed")
        flash(gettext("فشل إضافة القطعة: {error}").format(error=str(e)), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# إضافة خدمة ثابتة إلى أمر الصيانة
# ============================================================================
@maintenance_bp.route("/<int:order_id>/services", methods=["POST"])
@login_required
@permission_required("maintenance_work")
def add_service(order_id):
    tid = require_active_tenant_id()
    _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_add_service"):
            MaintenanceService.add_service_line(
                order_id=order_id,
                tenant_id=tid,
                service_code=request.form.get("service_code") or "",
                service_name=request.form.get("service_name") or "",
                service_name_ar=request.form.get("service_name_ar") or None,
                service_category=request.form.get("service_category") or "other",
                unit_price=_decimal_or_zero("unit_price"),
                duration_minutes=int(request.form.get("duration_minutes") or 0),
                discount_percent=_decimal_or_zero("discount_percent"),
                discount_value=_decimal_or_zero("discount_value"),
                discount_mode=request.form.get("discount_mode", "percent"),
                tax_rate=None,
                engineer_id=request.form.get("engineer_id") or None,
                actor_id=current_user.id,
            )
            flash(gettext("تم إضافة الخدمة إلى الأمر"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.exception("Maintenance service line creation failed")
        flash(gettext("فشل إضافة الخدمة: {error}").format(error=str(e)), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# تغيير حالة الأمر
# ============================================================================
@maintenance_bp.route("/<int:order_id>/status", methods=["POST"])
@login_required
@permission_required("maintenance_work")
def change_status(order_id):
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)

    new_status = request.form.get("status")
    note = request.form.get("note") or None

    try:
        with atomic_transaction("maintenance_transition_status"):
            order = MaintenanceService.transition_status(
                order_id=order_id,
                tenant_id=tid,
                to_status=new_status,
                changed_by=current_user.id,
                note=note,
            )
            flash(
                gettext("تم تغيير حالة الأمر إلى {status}").format(status=order.status),
                "success",
            )
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# الخصم الإجمالي على الأمر
# ============================================================================
@maintenance_bp.route("/<int:order_id>/discount", methods=["POST"])
@login_required
@permission_required("maintenance_discount")
def set_order_discount(order_id):
    """تطبيق خصم على إجمالي أمر الصيانة.

    The guard is the discount permission; the cap is the tenant's own
    setting, and the service refuses a discount over it unless the actor
    also holds the override permission.
    """
    tid = require_active_tenant_id()
    _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_order_discount"):
            MaintenanceService.set_order_discount(
                order_id=order_id,
                tenant_id=tid,
                actor_id=current_user.id,
                discount_percent=_decimal_or_zero("discount_percent"),
                discount_value=_decimal_or_zero("discount_value"),
                discount_mode=request.form.get("discount_mode", "percent"),
                note=request.form.get("note") or None,
            )
            flash(gettext("تم تطبيق الخصم على الأمر"), "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# فحص الكفالة
# ============================================================================
@maintenance_bp.route("/<int:order_id>/warranty/check", methods=["POST"])
@login_required
@permission_required("maintenance_receive")
def check_warranty(order_id):
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_check_warranty"):
            order = MaintenanceService.check_warranty(
                order_id=order_id,
                tenant_id=tid,
                checked_by=current_user.id,
            )
            flash(
                gettext("تم فحص الكفالة: {status}").format(status=order.warranty_status),
                "success",
            )
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# تسجيل الجهاز في سجل الكفالات
# ============================================================================
@maintenance_bp.route("/<int:order_id>/device", methods=["POST"])
@login_required
@permission_required("maintenance_receive")
def register_device(order_id):
    """تسجيل جهاز الأمر في سجل الكفالات.

    The registry is what the warranty check compares the order against.
    Without a registration the check can only ever answer "unknown", so
    the reception counter has to be able to put the device into the
    registry - with the warranty period the customer is entitled to.
    """
    tid = require_active_tenant_id()
    _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_register_device"):
            WarrantyService.register_order_device(
                order_id=order_id,
                tenant_id=tid,
                performed_by=current_user.id,
                purchase_date=_optional_date("purchase_date"),
                warranty_start_date=_optional_date("warranty_start_date"),
                warranty_end_date=_optional_date("warranty_end_date"),
                warranty_type=request.form.get("warranty_type") or None,
            )
            flash(gettext("تم تسجيل الجهاز في سجل الكفالات"), "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# إلغاء الكفالة / إعادة تفعيلها
# ============================================================================
@maintenance_bp.route("/<int:order_id>/warranty/cancel", methods=["POST"])
@login_required
@permission_required("manage_maintenance")
def cancel_warranty(order_id):
    tid = require_active_tenant_id()
    _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_cancel_warranty"):
            MaintenanceService.cancel_warranty(
                order_id=order_id,
                tenant_id=tid,
                performed_by=current_user.id,
                reason=request.form.get("reason"),
            )
            flash(gettext("تم إلغاء الكفالة"), "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


@maintenance_bp.route("/<int:order_id>/warranty/restore", methods=["POST"])
@login_required
@permission_required("manage_maintenance")
def restore_warranty(order_id):
    tid = require_active_tenant_id()
    _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_restore_warranty"):
            MaintenanceService.restore_warranty(
                order_id=order_id,
                tenant_id=tid,
                performed_by=current_user.id,
                reason=request.form.get("reason"),
            )
            flash(gettext("تم إعادة تفعيل الكفالة"), "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# تحصيل عربون عند الاستلام
# ============================================================================
@maintenance_bp.route("/<int:order_id>/deposit", methods=["POST"])
@login_required
@permission_required("maintenance_close")
def collect_deposit(order_id):
    tid = require_active_tenant_id()
    _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_collect_deposit"):
            receipt = MaintenanceService.collect_deposit(
                order_id=order_id,
                tenant_id=tid,
                cashier_id=current_user.id,
                amount=_decimal_or_zero("amount"),
                payment_mode=request.form.get("payment_mode", "cash"),
                payment_reference=request.form.get("payment_reference") or None,
                notes=request.form.get("notes") or None,
            )
            flash(
                gettext("تم تحصيل عربون {amount} - سند {number}").format(
                    amount=receipt.amount, number=receipt.receipt_number
                ),
                "success",
            )
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.exception("Maintenance deposit collection failed")
        flash(gettext("فشل تحصيل العربون: {error}").format(error=str(e)), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# إغلاق الأمر وقبض المبلغ (الاستقبال فقط)
# ============================================================================
@maintenance_bp.route("/<int:order_id>/close", methods=["POST"])
@login_required
@permission_required("maintenance_close")
def close(order_id):
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_close"):
            order, receipt, invoice = MaintenanceService.close_and_collect(
                order_id=order_id,
                tenant_id=tid,
                cashier_id=current_user.id,
                payment_mode=request.form.get("payment_mode", "cash"),
                amount_received=_decimal_or_zero("amount_received"),
                payment_reference=request.form.get("payment_reference") or None,
                notes=request.form.get("notes") or None,
                actor_id=current_user.id,
            )
            flash(
                gettext("تم إغلاق الأمر وإصدار الفاتورة {invoice_number}").format(
                    invoice_number=invoice.invoice_number
                ),
                "success",
            )
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.exception("Maintenance close failed")
        flash(gettext("فشل إغلاق الأمر: {error}").format(error=str(e)), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# طباعة الفاتورة / سند القبض
# ============================================================================
@maintenance_bp.route("/<int:order_id>/invoice-print")
@login_required
@permission_required("manage_maintenance")
def print_invoice(order_id):
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)
    invoice = order.invoice
    if invoice is None:
        flash(gettext("لا توجد فاتورة لهذا الأمر بعد"), "warning")
        return redirect(url_for("maintenance.detail", order_id=order_id))
    return render_template(
        "maintenance/print_invoice.html",
        order=order,
        invoice=invoice,
        lines=list(order.lines),
        services_lines=list(order.services_lines),
        warranty_colors=MaintenanceService.get_warranty_colors(tid),
    )


@maintenance_bp.route("/<int:order_id>/receipt-print")
@login_required
@permission_required("manage_maintenance")
def print_receipt(order_id):
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)
    receipts = list(order.receipts)
    if not receipts:
        flash(gettext("لا توجد سندات قبض لهذا الأمر بعد"), "warning")
        return redirect(url_for("maintenance.detail", order_id=order_id))
    return render_template(
        "maintenance/print_receipt.html",
        order=order,
        receipts=receipts,
    )


# ============================================================================
# إنشاء مرتجع صيانة
# ============================================================================
@maintenance_bp.route("/<int:order_id>/returns", methods=["POST"])
@login_required
@permission_required("maintenance_close")
def create_return(order_id):
    tid = require_active_tenant_id()
    _order_or_404(order_id, tid)

    try:
        with atomic_transaction("maintenance_create_return"):
            maintenance_return = MaintenanceService.create_return(
                order_id=order_id,
                tenant_id=tid,
                returned_by=current_user.id,
                reason=request.form.get("reason") or "",
                quantities={
                    key: _decimal_or_zero(key)
                    for key, value in request.form.items()
                    if key.startswith("return_qty_") and value
                },
            )
            flash(
                gettext("تم إنشاء مرتجع الصيانة {number}").format(number=maintenance_return.return_number),
                "success",
            )
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.exception("Maintenance return creation failed")
        flash(gettext("فشل إنشاء المرتجع: {error}").format(error=str(e)), "danger")

    return redirect(url_for("maintenance.detail", order_id=order_id))


# ============================================================================
# قوالب الخدمات الثابتة (للمشرف)
# ============================================================================
@maintenance_bp.route("/service-templates", methods=["GET", "POST"])
@login_required
@permission_required("manage_maintenance")
def service_templates():
    tid = require_active_tenant_id()

    if request.method == "POST":
        try:
            with atomic_transaction("maintenance_create_service_template"):
                MaintenanceService.create_service_template(
                    tenant_id=tid,
                    service_code=request.form.get("service_code") or "",
                    name=request.form.get("name") or "",
                    name_ar=request.form.get("name_ar") or None,
                    service_category=request.form.get("service_category") or "other",
                    fixed_price=_decimal_or_zero("fixed_price"),
                    duration_minutes=int(request.form.get("duration_minutes") or 0),
                    tax_rate=_decimal_or_zero("tax_rate"),
                    requires_parts=request.form.get("requires_parts") == "on",
                    sort_order=int(request.form.get("sort_order") or 0),
                )
                flash(gettext("تم إضافة قالب الخدمة"), "success")
        except ValueError as e:
            flash(str(e), "danger")
        except Exception as e:
            current_app.logger.exception("Service template creation failed")
            flash(gettext("فشل إضافة قالب الخدمة: {error}").format(error=str(e)), "danger")

    templates = (
        tenant_query(MaintenanceServiceTemplate)
        .filter_by(tenant_id=tid)
        .order_by(MaintenanceServiceTemplate.sort_order)
        .all()
    )
    return render_template("maintenance/service_templates.html", templates=templates)


# ============================================================================
# إعدادات الصيانة (للمشرف)
# ============================================================================
@maintenance_bp.route("/settings", methods=["GET", "POST"])
@login_required
@permission_required("manage_maintenance")
def settings():
    tid = require_active_tenant_id()

    if request.method == "POST":
        try:
            with atomic_transaction("maintenance_settings"):
                setting = MaintenanceService.ensure_settings(tid)
                MaintenanceService.update_settings(
                    tenant_id=tid,
                    default_warehouse_id=request.form.get("default_warehouse_id") or None,
                    max_discount_percent=_decimal_or_zero("max_discount_percent"),
                    max_discount_value=_decimal_or_zero("max_discount_value"),
                    allow_engineer_discount=request.form.get("allow_engineer_discount") == "on",
                    require_manager_approval_above_discount=(
                        request.form.get("require_manager_approval_above_discount") == "on"
                    ),
                    require_warranty_check=request.form.get("require_warranty_check") == "on",
                    color_warranty=request.form.get("color_warranty") or "#10b981",
                    color_non_warranty=request.form.get("color_non_warranty") or "#ef4444",
                    color_unknown_warranty=request.form.get("color_unknown_warranty") or "#f59e0b",
                    allow_engineer_cancel_warranty=(request.form.get("allow_engineer_cancel_warranty") == "on"),
                    allow_engineer_restore_warranty=(request.form.get("allow_engineer_restore_warranty") == "on"),
                )
                flash(gettext("تم تحديث إعدادات الصيانة"), "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("maintenance.settings"))

    # The settings row is created on the first visit, so it has to be
    # committed: a row written outside the request's transaction is
    # discarded when the session is torn down, and the tenant would find
    # its settings gone the next time it opened the page.
    with atomic_transaction("maintenance_settings_ensure"):
        setting = MaintenanceService.ensure_settings(tid)

    warehouses = tenant_query(Warehouse).filter_by(tenant_id=tid, is_active=True).all()
    return render_template("maintenance/settings.html", setting=setting, warehouses=warehouses)


# ============================================================================
# سجل تدقيق الكفالات
# ============================================================================
@maintenance_bp.route("/warranty-audit")
@login_required
@permission_required("manage_maintenance")
def warranty_audit():
    tid = require_active_tenant_id()
    audits = (
        tenant_query(MaintenanceWarrantyAudit)
        .filter_by(tenant_id=tid)
        .order_by(MaintenanceWarrantyAudit.performed_at.desc())
        .all()
    )
    return render_template("maintenance/warranty_audit.html", audits=audits)


# ============================================================================
# تقرير إيرادات الصيانة
# ============================================================================
@maintenance_bp.route("/report")
@login_required
@permission_required("manage_maintenance")
def report():
    tid = require_active_tenant_id()

    df = _optional_date("date_from", request.args)
    dt = _optional_date("date_to", request.args)

    report = MaintenanceService.get_revenue_report(tid, date_from=df, date_to=dt)
    return render_template("maintenance/report.html", report=report)


# ============================================================================
# شراء قطع الصيانة
# ============================================================================
@maintenance_bp.route("/purchases")
@login_required
@permission_required("manage_maintenance")
def purchases():
    """قائمة أوامر شراء قطع الصيانة."""
    tid = require_active_tenant_id()
    orders = (
        tenant_query(MaintenancePurchaseOrder)
        .filter_by(tenant_id=tid)
        .order_by(MaintenancePurchaseOrder.created_at.desc())
        .all()
    )
    return render_template("maintenance/purchases.html", orders=orders)


@maintenance_bp.route("/purchases/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_maintenance")
def create_purchase():
    """فتح أمر شراء قطع صيانة جديد."""
    tid = require_active_tenant_id()

    if request.method == "POST":
        try:
            with atomic_transaction("maintenance_create_purchase"):
                order = MaintenancePurchaseService.create_purchase_order(
                    tenant_id=tid,
                    branch_id=request.form.get("branch_id") or None,
                    warehouse_id=request.form.get("warehouse_id") or None,
                    supplier_id=request.form.get("supplier_id") or None,
                    supplier_name=request.form.get("supplier_name") or None,
                    tax_rate=_decimal_or_zero("tax_rate"),
                    notes=request.form.get("notes") or None,
                )
                flash(
                    gettext("تم إنشاء أمر شراء قطع الصيانة {number}").format(number=order.po_number),
                    "success",
                )
                return redirect(url_for("maintenance.purchase_detail", purchase_order_id=order.id))
        except ValueError as e:
            flash(str(e), "danger")

    warehouses = tenant_query(Warehouse).filter_by(tenant_id=tid, is_active=True).all()
    suppliers = tenant_query(Supplier).filter_by(tenant_id=tid).all()
    return render_template("maintenance/purchase_create.html", warehouses=warehouses, suppliers=suppliers)


@maintenance_bp.route("/purchases/<int:purchase_order_id>")
@login_required
@permission_required("manage_maintenance")
def purchase_detail(purchase_order_id):
    """تفاصيل أمر شراء قطع الصيانة."""
    tid = require_active_tenant_id()
    order = tenant_query(MaintenancePurchaseOrder).filter_by(id=purchase_order_id, tenant_id=tid).first()
    if order is None:
        abort(404, description=gettext("أمر شراء قطع الصيانة غير موجود"))

    products = tenant_query(Product).filter_by(tenant_id=tid, is_active=True).order_by(Product.name).all()
    warehouses = tenant_query(Warehouse).filter_by(tenant_id=tid, is_active=True).all()
    return render_template(
        "maintenance/purchase_detail.html",
        order=order,
        lines=list(order.lines),
        products=products,
        warehouses=warehouses,
    )


@maintenance_bp.route("/purchases/<int:purchase_order_id>/lines", methods=["POST"])
@login_required
@permission_required("manage_maintenance")
def add_purchase_line(purchase_order_id):
    """إضافة قطعة إلى أمر شراء قطع الصيانة."""
    tid = require_active_tenant_id()

    try:
        with atomic_transaction("maintenance_add_purchase_line"):
            MaintenancePurchaseService.add_line(
                purchase_order_id=purchase_order_id,
                tenant_id=tid,
                product_id=request.form.get("product_id") or 0,
                quantity=_decimal_or_zero("quantity"),
                unit_cost=_decimal_or_zero("unit_cost"),
                warehouse_id=request.form.get("warehouse_id") or None,
            )
            flash(gettext("تم إضافة القطعة إلى أمر الشراء"), "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("maintenance.purchase_detail", purchase_order_id=purchase_order_id))


@maintenance_bp.route("/purchases/<int:purchase_order_id>/receive", methods=["POST"])
@login_required
@permission_required("manage_maintenance")
def receive_purchase(purchase_order_id):
    """استلام أمر شراء: القطع تدخل المستودع والقيود تُرحَّل."""
    tid = require_active_tenant_id()

    try:
        with atomic_transaction("maintenance_receive_purchase"):
            order = MaintenancePurchaseService.receive_purchase_order(
                purchase_order_id=purchase_order_id,
                tenant_id=tid,
                received_by=current_user.id,
            )
            flash(
                gettext("تم استلام أمر الشراء {number}").format(number=order.po_number),
                "success",
            )
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("maintenance.purchase_detail", purchase_order_id=purchase_order_id))


# ============================================================================
# الفاتورة الإلكترونية
# ============================================================================
@maintenance_bp.route("/<int:order_id>/einvoice.xml")
@login_required
@permission_required("manage_maintenance")
def maintenance_einvoice_xml(order_id):
    """تحميل مستند الفاتورة الإلكترونية لفاتورة الصيانة."""
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)
    invoice = order.invoice
    if invoice is None:
        abort(404, description=gettext("لا توجد فاتورة لهذا الأمر بعد"))

    from flask import Response

    from models import EInvoice

    row = EInvoice.query.filter_by(
        tenant_id=tid,
        maintenance_invoice_id=invoice.id,
    ).first()
    if row is None:
        abort(404)
    filename = f"einvoice-{invoice.invoice_number}.xml"
    return Response(
        row.xml_payload,
        mimetype="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@maintenance_bp.route("/<int:order_id>/einvoice-qr.png")
@login_required
@permission_required("manage_maintenance")
def maintenance_einvoice_qr(order_id):
    """عرض رمز QR Payload لفاتورة الصيانة (KSA). 404 في غير السعودية."""
    tid = require_active_tenant_id()
    order = _order_or_404(order_id, tid)
    invoice = order.invoice
    if invoice is None:
        abort(404, description=gettext("لا توجد فاتورة لهذا الأمر بعد"))

    from flask import Response

    from models import EInvoice

    row = EInvoice.query.filter_by(
        tenant_id=tid,
        maintenance_invoice_id=invoice.id,
    ).first()
    if row is None or not row.qr_base64:
        abort(404)
    import io

    import qrcode

    image = qrcode.make(row.qr_base64)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(buffer.getvalue(), mimetype="image/png")


# ============================================================================
# تقرير هامش الربح
# ============================================================================
@maintenance_bp.route("/report/margin")
@login_required
@permission_required("manage_maintenance")
def margin_report():
    tid = require_active_tenant_id()

    df = _optional_date("date_from", request.args)
    dt = _optional_date("date_to", request.args)

    report = MaintenanceService.get_margin_report(tid, date_from=df, date_to=dt)
    return render_template("maintenance/report_margin.html", report=report)


# ============================================================================
# تقرير أداء الفنيين
# ============================================================================
@maintenance_bp.route("/report/engineers")
@login_required
@permission_required("manage_maintenance")
def engineer_report():
    tid = require_active_tenant_id()

    df = _optional_date("date_from", request.args)
    dt = _optional_date("date_to", request.args)

    report = MaintenanceService.get_engineer_report(tid, date_from=df, date_to=dt)
    return render_template("maintenance/report_engineers.html", report=report)


# ============================================================================
# تقرير القطع المصروفة
# ============================================================================
@maintenance_bp.route("/report/parts")
@login_required
@permission_required("manage_maintenance")
def parts_report():
    tid = require_active_tenant_id()

    df = _optional_date("date_from", request.args)
    dt = _optional_date("date_to", request.args)

    report = MaintenanceService.get_parts_report(tid, date_from=df, date_to=dt)
    return render_template("maintenance/report_parts.html", report=report)


# ============================================================================
# تقرير الكفالات
# ============================================================================
@maintenance_bp.route("/report/warranty")
@login_required
@permission_required("manage_maintenance")
def warranty_report():
    tid = require_active_tenant_id()

    report = MaintenanceService.get_warranty_report(tid)
    return render_template(
        "maintenance/report_warranty.html",
        report=report,
        warranty_colors=MaintenanceService.get_warranty_colors(tid),
    )
