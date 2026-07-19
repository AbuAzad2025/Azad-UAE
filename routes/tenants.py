from flask_babel import gettext
from flask import Blueprint, abort, flash, redirect, request
from flask_login import current_user, login_required

from extensions import db
from models.tenant import Tenant
from utils.branching import clear_active_branch
from utils.safe_redirect import safe_redirect_target
from utils.tenanting import is_global_tenant_user, set_active_tenant

tenants_bp = Blueprint("tenants", __name__, url_prefix="/tenants")


@tenants_bp.route("/switch/<int:tenant_id>", methods=["GET", "POST"])
@login_required
def switch(tenant_id):
    if not is_global_tenant_user(current_user):
        abort(403)

    if tenant_id == 0:
        set_active_tenant(None, user=current_user)
        clear_active_branch()
        flash(gettext("تم إلغاء تحديد الشركة الحالية."), "success")
        return redirect(safe_redirect_target(request.referrer, "main.dashboard"))

    tenant = db.session.get(Tenant, int(tenant_id))
    if not tenant or not tenant.is_active or getattr(tenant, "is_suspended", False):
        flash(gettext("الشركة غير موجودة أو غير مفعلة أو معلقة."), "danger")
        return redirect(safe_redirect_target(request.referrer, "main.dashboard"))

    set_active_tenant(tenant.id, user=current_user)
    clear_active_branch()
    flash(gettext(f"تم التبديل إلى: {tenant.name_ar or tenant.name}"), "success")
    return redirect(safe_redirect_target(request.referrer, "main.dashboard"))
