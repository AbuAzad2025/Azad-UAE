"""Super Admin / Landlord Management Interface — tenant directory & manual billing overrides."""

import logging

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from services.owner_ops_service import OwnerOpsService
from utils.decorators import owner_required
from utils.security_helpers import enforce_owner_ip_if_needed

logger = logging.getLogger(__name__)

owner_admin_bp = Blueprint("owner_admin", __name__, url_prefix="/super-admin")


@owner_admin_bp.before_request
def _ip_guard():
    enforce_owner_ip_if_needed()


@owner_admin_bp.route("/")
@owner_required
def index():
    return redirect(url_for("owner_admin.dashboard"))


@owner_admin_bp.route("/dashboard")
@owner_required
def dashboard():
    ctx = OwnerOpsService.landlord_dashboard_context()
    tenants = ctx["tenants"]
    user_counts = ctx["user_counts"]
    branch_counts = ctx["branch_counts"]
    admin_emails = ctx["admin_emails"]
    packages = ctx["packages"]

    tenant_rows = []
    for t in tenants:
        tenant_rows.append(
            {
                "tenant": t,
                "owner_email": admin_emails.get(t.id, "—"),
                "users_used": user_counts.get(t.id, 0),
                "branches_used": branch_counts.get(t.id, 0),
            }
        )

    stats = {
        "total": len(tenants),
        "active": sum(1 for t in tenants if t.is_active and not t.is_suspended),
        "suspended": sum(1 for t in tenants if t.is_suspended),
        "trial": sum(1 for t in tenants if t.is_trial),
    }

    return render_template(
        "owner_admin/dashboard.html",
        tenant_rows=tenant_rows,
        packages=packages,
        stats=stats,
    )


_VALID_DURATIONS = ("monthly", "yearly", "annual", "lifetime", "trial")
_DURATION_LABELS = {
    "monthly": "1 Month",
    "annual": "1 Year",
    "lifetime": "Lifetime",
    "trial": "7-day Trial",
}


@owner_admin_bp.route("/activate-subscription", methods=["POST"])
@owner_required
def activate_subscription():
    from services.saas_provisioning_service import (
        SaaSProvisioningError,
        SaaSProvisioningService,
    )

    tenant_id = request.form.get("tenant_id", type=int)
    package_id = request.form.get("package_id", type=int)
    duration_type = (request.form.get("duration_type") or "monthly").strip().lower()

    if not tenant_id or not package_id:
        flash("Tenant and package are required.", "danger")
        return redirect(url_for("owner_admin.dashboard"))

    if duration_type not in _VALID_DURATIONS:
        flash("Invalid duration type.", "danger")
        return redirect(url_for("owner_admin.dashboard"))

    if duration_type == "yearly":
        duration_type = "annual"

    tenant = OwnerOpsService.get_tenant(tenant_id)
    package = OwnerOpsService.get_package(package_id)
    if not tenant:
        flash(f"Tenant {tenant_id} not found.", "danger")
        return redirect(url_for("owner_admin.dashboard"))
    if not package:
        flash(f"Package {package_id} not found.", "danger")
        return redirect(url_for("owner_admin.dashboard"))

    try:
        SaaSProvisioningService.activate_purchased_package(
            tenant_id=tenant_id,
            package_id=package_id,
            duration_type=duration_type,
        )
        label = _DURATION_LABELS.get(duration_type, duration_type)
        flash(
            f'Tenant "{tenant.name_ar or tenant.name}" successfully upgraded to {package.name_en} for {label}.',
            "success",
        )
        logger.info(
            "Owner %s activated package %s for tenant %s (%s)",
            current_user.email,
            package.slug,
            tenant.id,
            duration_type,
        )
    except SaaSProvisioningError as exc:
        flash(f"Provisioning failed: {exc}", "danger")
        logger.error("SaaS provisioning error: %s", exc)
    except Exception as exc:
        flash(f"Unexpected error: {exc}", "danger")
        logger.exception("Unexpected error during subscription activation")

    return redirect(url_for("owner_admin.dashboard"))
