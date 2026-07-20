"""Super Admin / Landlord Management Interface — tenant directory & manual billing overrides."""

import logging

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func
from extensions import db
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
    from models.tenant import Tenant
    from models.user import User, Role
    from models.branch import Branch
    from models.package import Package

    tenants = db.session.query(Tenant).order_by(Tenant.id.asc()).all()

    user_counts = dict(
        db.session.query(User.tenant_id, func.count(User.id))
        .filter(User.tenant_id.isnot(None))
        .group_by(User.tenant_id)
        .all()
    )
    branch_counts = dict(
        db.session.query(Branch.tenant_id, func.count(Branch.id))
        .filter(Branch.tenant_id.isnot(None))
        .group_by(Branch.tenant_id)
        .all()
    )

    admin_emails: dict[int, str] = {}
    admin_users = (
        db.session.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(
            User.tenant_id.isnot(None),
            Role.slug.in_(["super_admin", "owner", "developer"]),
        )
        .order_by(User.id.asc())
        .all()
    )
    for u in admin_users:
        admin_emails.setdefault(u.tenant_id, u.email)

    packages = (
        db.session.query(Package).filter_by(is_active=True).order_by(Package.sort_order.asc(), Package.id.asc()).all()
    )

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
        SaaSProvisioningService,
        SaaSProvisioningError,
    )
    from models.tenant import Tenant
    from models.package import Package

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

    tenant = db.session.get(Tenant, tenant_id)
    package = db.session.get(Package, package_id)
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
