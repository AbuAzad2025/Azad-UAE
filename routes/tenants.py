from flask import Blueprint, abort, flash, redirect, request, url_for
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
        set_active_tenant(None)
        clear_active_branch()
        flash("تم إلغاء تحديد الشركة الحالية.", "success")
        return redirect(safe_redirect_target(request.referrer, 'main.dashboard'))

    tenant = db.session.get(Tenant, int(tenant_id))
    if not tenant or not getattr(tenant, "is_active", False):
        flash("الشركة غير موجودة أو غير مفعلة.", "danger")
        return redirect(safe_redirect_target(request.referrer, 'main.dashboard'))

    set_active_tenant(tenant.id)
    clear_active_branch()
    flash(f"تم التبديل إلى: {tenant.name_ar or tenant.name}", "success")
    return redirect(safe_redirect_target(request.referrer, 'main.dashboard'))

