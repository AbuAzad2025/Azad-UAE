from flask import Blueprint, abort, flash, redirect, request
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import db
from models.tenant import Tenant
from utils.auth_helpers import is_global_owner_user
from utils.branching import clear_active_branch
from utils.decorators import owner_required
from utils.safe_redirect import safe_redirect_target
from utils.tenanting import is_global_tenant_user, set_active_tenant

tenants_bp = Blueprint("tenants", __name__, url_prefix="/tenants")


@tenants_bp.route("/switch/<int:tenant_id>", methods=["GET", "POST"])
@login_required
@owner_required
def switch(tenant_id):
    """Tenant context switch — platform owner only.

    Defense-in-depth:
    * ``@owner_required`` enforces platform-owner on the decorator stack
      (returns 404 for non-owners, never 401 to avoid leaking existence).
    * ``is_global_tenant_user`` is retained as the explicit service-layer
      check because it is also called by non-route paths (signals,
      scheduled jobs, etc.).
    * When the target tenant is non-zero the user's ``tenant_id`` must
      match it OR they must hold ``is_owner=True``; otherwise a tenant-admin
      could pivot into another tenant's records.
    """
    if not is_global_tenant_user(current_user):
        abort(403)

    target_tenant = db.session.get(Tenant, int(tenant_id)) if tenant_id else None
    if target_tenant is not None:
        current_tenant_id = getattr(current_user, "tenant_id", None)
        is_owner = bool(getattr(current_user, "is_owner", False))
        if (
            current_tenant_id is not None
            and current_tenant_id != target_tenant.id
            and not is_owner
        ):
            abort(403)

    if tenant_id == 0:
        set_active_tenant(None, user=current_user)
        clear_active_branch()
        flash(gettext("تم إلغاء تحديد الشركة الحالية."), "success")
        return redirect(safe_redirect_target(request.referrer, "main.dashboard"))

    if (
        not target_tenant
        or not target_tenant.is_active
        or getattr(target_tenant, "is_suspended", False)
    ):
        flash(gettext("الشركة غير موجودة أو غير مفعلة أو معلقة."), "danger")
        return redirect(safe_redirect_target(request.referrer, "main.dashboard"))

    set_active_tenant(target_tenant.id, user=current_user)
    clear_active_branch()
    flash(
        gettext(f"تم التبديل إلى: {target_tenant.name_ar or target_tenant.name}"),
        "success",
    )
    return redirect(safe_redirect_target(request.referrer, "main.dashboard"))
