from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import db
from models import Branch
from utils.db_safety import atomic_transaction
from utils.decorators import admin_required
from utils.tenanting import get_active_tenant_id, tenant_get_or_404, tenant_query

branches_bp = Blueprint("branches", __name__, url_prefix="/branches")


def _sync_branch_financial_accounts(tenant_id):
    from services.gl_service import GLService

    GLService.ensure_core_accounts(tenant_id=tenant_id)


@branches_bp.route("/")
@login_required
@admin_required
def index():
    tid = get_active_tenant_id(current_user)
    if tid is None:
        flash(gettext("اختر الشركة أولاً من قائمة التينانتس."), "warning")
        return redirect(url_for("owner.tenants_list"))
    q = tenant_query(Branch)
    branches = q.order_by(Branch.is_main.desc(), Branch.code, Branch.name).all()
    return render_template("branches/index.html", branches=branches)


@branches_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def create():
    from models import Tenant

    tid = get_active_tenant_id(current_user)
    if tid is None:
        flash(gettext("اختر الشركة أولاً من قائمة التينانتس قبل إنشاء فرع."), "warning")
        return redirect(url_for("owner.tenants_list"))
    tenant = db.session.get(Tenant, int(tid))
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        city = request.form.get("city")
        address = request.form.get("address")
        from utils.field_validators import normalize_phone_optional

        phone = normalize_phone_optional(request.form.get("phone")) or ""
        is_main = request.form.get("is_main") == "on"

        if not name or not code:
            flash(gettext("الاسم والكود مطلوبان"), "danger")
            return redirect(url_for("branches.create"))

        # Check tenant branch limit
        from utils.tenant_limits import TenantLimitError, check_branches_limit

        try:
            check_branches_limit()
        except TenantLimitError as e:
            flash(str(e), "warning")
            return redirect(url_for("branches.create"))

        if tenant_query(Branch).filter_by(code=code).first():
            flash(gettext("الكود مستخدم مسبقاً"), "danger")
            return redirect(url_for("branches.create"))

        from services.branch_service import BranchService

        branch = BranchService.create_branch(
            name=name,
            code=code,
            city=city or "",
            address=address or "",
            phone=phone,
            is_main=is_main,
            tenant_id=int(tid),
        )

        with atomic_transaction("branch_create"):
            db.session.flush()
            _sync_branch_financial_accounts(branch.tenant_id)

        flash(gettext("تم إضافة الفرع بنجاح"), "success")
        return redirect(url_for("branches.index"))

    return render_template("branches/create.html", tenant=tenant)


@branches_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit(**kwargs):
    record_id = kwargs.pop("id")
    branch = tenant_get_or_404(Branch, record_id)

    if request.method == "POST":
        branch.name = request.form.get("name")
        branch.city = request.form.get("city")
        branch.address = request.form.get("address")
        from utils.field_validators import normalize_phone_optional

        branch.phone = normalize_phone_optional(request.form.get("phone"))
        branch.is_main = request.form.get("is_main") == "on"
        raw_piv = request.form.get("prices_include_vat")
        branch.prices_include_vat = True if raw_piv == "on" else (False if raw_piv == "off" else None)

        with atomic_transaction("branch_update"):
            db.session.flush()
            _sync_branch_financial_accounts(branch.tenant_id)

        flash(gettext("تم تحديث الفرع بنجاح"), "success")
        return redirect(url_for("branches.index"))

    return render_template("branches/edit.html", branch=branch)


@branches_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete(**kwargs):
    record_id = kwargs.pop("id")
    branch = tenant_get_or_404(Branch, record_id)

    # Check for related data before deletion
    # This is a basic check. In a real system, you might want to soft-delete or strict check.
    if branch.users or branch.warehouses or branch.sales or branch.budgets:
        flash(
            gettext("لا يمكن حذف الفرع لوجود بيانات مرتبطة به (مستخدمين، مستودعات، أو مبيعات)"),
            "danger",
        )
        return redirect(url_for("branches.index"))

    # Dozens of tables reference branches with ondelete=RESTRICT
    # (gl_accounts via auto-synced chart, payments, cheques, ...).
    # Catch the FK violation and explain instead of returning 500.
    from sqlalchemy.exc import IntegrityError

    try:
        with atomic_transaction("branch_delete"):
            db.session.delete(branch)
    except IntegrityError:
        # atomic_transaction already rolled back; just explain.
        flash(
            gettext("لا يمكن حذف الفرع لوجود قيود محاسبية مرتبطة به (حسابات GL أو حركات). عطّله بدل الحذف."),
            "danger",
        )
        return redirect(url_for("branches.index"))
    flash(gettext("تم حذف الفرع بنجاح"), "success")
    return redirect(url_for("branches.index"))
