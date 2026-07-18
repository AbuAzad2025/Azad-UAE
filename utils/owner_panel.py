"""
Owner / company admin panel data builders — display-only, no schema changes.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import func

from extensions import db
from models import Branch, User, Warehouse
from models.tenant import Tenant
from utils.tenant_branding import resolve_tenant_branding, branding_path_warnings


# Platform-level monthly price per subscription plan (telemetry only, not
# tenant business data). Used to derive indicative MRR for the owner plane.
_PLAN_MONTHLY_PRICE_AED = {
    "basic": 199,
    "standard": 499,
    "professional": 999,
    "enterprise": 2499,
    "trial": 0,
}


def _plan_monthly_price(plan: str | None) -> Decimal:
    if not plan:
        return Decimal("0")
    return Decimal(str(_PLAN_MONTHLY_PRICE_AED.get(plan.lower(), 0)))


def _tenant_logo_display_url(tenant: Tenant, branding: dict) -> str:
    logo = branding.get("logo_url") or tenant.logo_url or ""
    if logo.startswith("http"):
        return logo
    if logo:
        return f"/static/{logo.lstrip('/')}"
    return ""


def _latest_backup_by_tenant(backups: list) -> dict[int, dict]:
    by_tid: dict[int, dict] = {}
    for meta in backups:
        tid = meta.get("tenant_id")
        if tid is None:
            continue
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            continue
        if tid not in by_tid:
            by_tid[tid] = meta
    return by_tid


def _system_backup_status(backups: list) -> dict:
    system = [
        b
        for b in backups
        if (b.get("backup_scope") == "system")
        or str(b.get("filename", "")).startswith("azad_backup_system_")
    ]
    if not system:
        return {"status": "missing", "label": "Missing Backup", "latest": None}
    latest = system[0]
    return {"status": "ok", "label": "Active", "latest": latest}


def build_platform_overview(backups: list | None = None) -> dict:
    """Aggregate counts for platform owner dashboard."""
    from services.backup_service import BackupService

    backups = backups if backups is not None else BackupService.list_backups()
    tenant_count = db.session.query(func.count(Tenant.id)).scalar() or 0
    active_tenant_count = (
        db.session.query(func.count(Tenant.id)).filter(Tenant.is_active).scalar() or 0
    )
    suspended_tenant_count = tenant_count - active_tenant_count

    user_counts = dict(
        db.session.query(User.tenant_id, func.count(User.id))
        .filter(not User.is_owner)
        .group_by(User.tenant_id)
        .all()
    )
    branch_counts = dict(
        db.session.query(Branch.tenant_id, func.count(Branch.id))
        .filter(Branch.is_active)
        .group_by(Branch.tenant_id)
        .all()
    )

    month_start = datetime.now(timezone.utc).date().replace(day=1)

    backup_by_tenant = _latest_backup_by_tenant(backups)
    sys_backup = _system_backup_status(backups)
    warnings: list[str] = []

    recent_active = (
        Tenant.query.filter(Tenant.is_active)
        .order_by(Tenant.id.desc())
        .limit(200)
        .all()
    )
    for t in recent_active:
        uc = int(user_counts.get(t.id) or 0)
        if uc == 0 and (t.slug or "").lower() != "nasrallah":
            warnings.append(f"Tenant {t.slug or t.id}: no users")
        if t.id not in backup_by_tenant:
            warnings.append(f"Tenant {t.slug or t.id}: no tenant backup")

    nasrallah = next(
        (t for t in recent_active if (t.slug or "").lower() == "nasrallah"), None
    )
    if nasrallah:
        n_users = int(user_counts.get(nasrallah.id) or 0)
        if n_users == 0:
            warnings.append(
                "Nasrallah: active tenant with zero users (expected until manager created)"
            )

    return {
        "tenant_count": tenant_count,
        "active_tenant_count": active_tenant_count,
        "suspended_tenant_count": suspended_tenant_count,
        "total_users": User.query.filter_by(is_owner=False).count(),
        "total_branches": Branch.query.filter_by(is_active=True).count(),
        "system_backup": sys_backup,
        "warnings": warnings,
        "user_counts": user_counts,
        "branch_counts": branch_counts,
        "backup_by_tenant": backup_by_tenant,
    }


def build_platform_telemetry() -> dict:
    """Owner-plane-only telemetry: SaaS growth, subscription lifecycle, MRR, health."""
    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())
    day_start = today

    tenants = Tenant.query.all()
    total = len(tenants)
    active = sum(1 for t in tenants if getattr(t, "is_active", False))
    suspended = total - active

    trial = sum(1 for t in tenants if getattr(t, "is_trial", False))
    expired = 0
    expiring_soon = 0
    new_this_month = 0
    new_this_week = 0
    new_today = 0
    mrr = Decimal("0")
    plan_distribution: dict[str, int] = {}

    for t in tenants:
        plan = (getattr(t, "subscription_plan", None) or "basic") or "basic"
        plan_distribution[plan] = plan_distribution.get(plan, 0) + 1
        mrr += _plan_monthly_price(plan)

        end = getattr(t, "subscription_end", None)
        if end is not None:
            end_d = end.date() if hasattr(end, "date") else end
            if end_d < today:
                expired += 1
            elif (end_d - today).days <= 7:
                expiring_soon += 1

        created = getattr(t, "created_at", None)
        if created is not None:
            cd = created.date() if hasattr(created, "date") else created
            if cd >= month_start:
                new_this_month += 1
            if cd >= week_start:
                new_this_week += 1
            if cd >= day_start:
                new_today += 1

    return {
        "tenant_count": total,
        "active_tenant_count": active,
        "suspended_tenant_count": suspended,
        "trial_tenant_count": trial,
        "expired_subscription_count": expired,
        "expiring_soon_count": expiring_soon,
        "new_tenants_month": new_this_month,
        "new_tenants_week": new_this_week,
        "new_tenants_today": new_today,
        "mrr_aed": float(mrr),
        "plan_distribution": plan_distribution,
        "total_branches": Branch.query.filter_by(is_active=True).count(),
        "total_users": User.query.filter_by(is_owner=False).count(),
    }


def build_tenant_management_rows(
    backups: list | None = None, overview: dict | None = None, limit: int | None = 200
) -> list[dict]:
    from services.backup_service import BackupService

    backups = backups if backups is not None else BackupService.list_backups()
    overview = overview if overview is not None else build_platform_overview(backups)
    rows = []
    tenant_query = Tenant.query.order_by(Tenant.is_active.desc(), Tenant.id.desc())
    if limit is not None:
        tenant_query = tenant_query.limit(limit)
    for tenant in tenant_query.all():
        tid = tenant.id
        branding = resolve_tenant_branding(tid)
        path_warns = branding_path_warnings(branding)
        uc = int(overview["user_counts"].get(tid) or 0)
        backup_meta = overview["backup_by_tenant"].get(tid)
        if backup_meta:
            backup_status = "ok"
            backup_label = "Backed up"
        else:
            backup_status = "missing"
            backup_label = "Missing Backup"

        status = "active" if getattr(tenant, "is_active", True) else "suspended"
        warn_users = uc == 0
        rows.append(
            {
                "tenant": tenant,
                "logo_url": _tenant_logo_display_url(tenant, branding),
                "user_count": uc,
                "branch_count": int(overview["branch_counts"].get(tid) or 0),
                "plan": (getattr(tenant, "subscription_plan", None) or "—"),
                "country": tenant.country or "—",
                "backup_status": backup_status,
                "backup_label": backup_label,
                "status": status,
                "status_label": "Active" if status == "active" else "Suspended",
                "warn_no_users": warn_users,
                "warn_slug": (tenant.slug or "").lower(),
                "branding_warnings": path_warns,
                "branding": branding,
            }
        )
    return rows


def build_branding_overview_rows(limit: int | None = 200) -> list[dict]:
    rows = []
    branding_query = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.desc())
    if limit is not None:
        branding_query = branding_query.limit(limit)
    for tenant in branding_query.all():
        branding = resolve_tenant_branding(tenant.id)
        rows.append(
            {
                "tenant": tenant,
                "logo_url": _tenant_logo_display_url(tenant, branding),
                "branding": branding,
                "warnings": branding_path_warnings(branding),
                "invoice_preview_url": f"/owner/preview-invoice/modern?tenant_id={tenant.id}",
                "receipt_preview_url": f"/owner/preview-receipt/classic?tenant_id={tenant.id}",
            }
        )
    return rows


def build_system_health_summary() -> dict:
    """Lightweight hints for owner dashboard — full audits via predeploy_check."""
    summary = {
        "migration": "unknown",
        "static_audit": "run predeploy",
        "branding_audit": "run predeploy",
        "predeploy_hint": "python tools/qa/predeploy_check.py --profile local",
    }
    try:
        from sqlalchemy import create_engine, text

        url = os.environ.get("DATABASE_URL") or os.environ.get(
            "SQLALCHEMY_DATABASE_URI"
        )
        if url:
            with create_engine(url).connect() as conn:
                rev = conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar()
                summary["migration"] = str(rev) if rev else "head"
    except Exception:
        summary["migration"] = "check alembic"

    return summary


def build_company_dashboard_context(
    tenant_id: int, branch_id: int | None = None
) -> dict:
    """KPIs and readiness for tenant company admin (single tenant only)."""
    from models import Customer, Product, Sale, SaleLine

    tenant = db.session.get(Tenant, int(tenant_id))
    if not tenant:
        return {}

    branding = resolve_tenant_branding(tenant_id)
    readiness: list[str] = []
    if branding_path_warnings(branding):
        readiness.append("Branding paths need attention — check invoice settings")
    if not (branding.get("logo_url") or tenant.logo_url):
        readiness.append("No tenant logo configured")

    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)

    sales_q = db.session.query(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.amount_aed), 0),
    ).filter(
        Sale.tenant_id == tenant_id,
        Sale.status == "confirmed",
    )
    if branch_id is not None:
        sales_q = sales_q.filter(Sale.branch_id == branch_id)

    today_sales = sales_q.filter(func.date(Sale.sale_date) == today).first()
    month_sales = sales_q.filter(func.date(Sale.sale_date) >= month_start).first()

    prod_q = Product.query.filter_by(tenant_id=tenant_id, is_active=True)
    cust_q = Customer.query.filter_by(tenant_id=tenant_id, is_active=True)
    if branch_id is not None:
        cust_q = (
            cust_q.join(Sale, Customer.id == Sale.customer_id)
            .filter(
                Sale.branch_id == branch_id,
                Sale.tenant_id == tenant_id,
            )
            .distinct()
        )

    users_count = User.query.filter(
        User.tenant_id == tenant_id,
        not User.is_owner,
        User.is_active,
    ).count()
    branches_count = Branch.query.filter_by(tenant_id=tenant_id, is_active=True).count()

    from services.backup_service import BackupService

    all_backups = BackupService.list_backups()
    tenant_backups = [
        b
        for b in all_backups
        if b.get("backup_scope") == "tenant"
        and int(b.get("tenant_id") or -1) == int(tenant_id)
    ]

    # COGS (cost of goods sold) for the month
    cogs_q = (
        db.session.query(
            func.coalesce(func.sum(SaleLine.cost_price * SaleLine.quantity), 0)
        )
        .select_from(SaleLine)
        .join(Sale, SaleLine.sale_id == Sale.id)
        .filter(
            func.date(Sale.sale_date) >= month_start,
            Sale.status == "confirmed",
            Sale.tenant_id == tenant_id,
        )
    )
    if branch_id is not None:
        cogs_q = cogs_q.filter(Sale.branch_id == branch_id)
    month_cogs = float(cogs_q.scalar() or Decimal("0"))

    try:
        from models.partner_commission import PartnerCommissionEntry

        comm_q = db.session.query(
            func.coalesce(func.sum(PartnerCommissionEntry.commission_amount_aed), 0)
        ).filter(
            PartnerCommissionEntry.tenant_id == tenant_id,
            func.date(PartnerCommissionEntry.created_at) >= month_start,
        )
        if branch_id is not None:
            comm_q = comm_q.filter(PartnerCommissionEntry.branch_id == branch_id)
        month_commissions = float(comm_q.scalar() or Decimal("0"))
    except Exception:
        month_commissions = 0.0

    warehouses = (
        Warehouse.query.filter_by(tenant_id=tenant_id).order_by(Warehouse.name).all()
    )

    return {
        "tenant": tenant,
        "branding": branding,
        "logo_url": _tenant_logo_display_url(tenant, branding),
        "readiness_warnings": readiness,
        "today_sales_count": today_sales[0] or 0,
        "today_sales_amount": float(today_sales[1] or 0),
        "month_sales_count": month_sales[0] or 0,
        "month_sales_amount": float(month_sales[1] or 0),
        "month_cogs": month_cogs,
        "month_commissions": month_commissions,
        "month_net_profit": float(month_sales[1] or 0) - month_cogs - month_commissions,
        "products_count": prod_q.count(),
        "customers_count": cust_q.count(),
        "users_count": users_count,
        "branches_count": branches_count,
        "tenant_backup_count": len(tenant_backups),
        "scoped_branch_id": branch_id,
        "warehouses": warehouses,
    }


def tenants_without_users_allowlist() -> set[str]:
    raw = (
        os.environ.get("OWNER_PANEL_ALLOW_TENANTS_WITHOUT_USERS") or "nasrallah"
    ).strip()
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def evaluate_tenant_user_warnings(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Returns (fail_messages, warn_messages) for QA."""
    allow = tenants_without_users_allowlist()
    fails: list[str] = []
    warns: list[str] = []
    for row in rows:
        if not getattr(row.get("tenant"), "is_active", True):
            continue
        slug = (row.get("warn_slug") or "").lower()
        if not row.get("warn_no_users"):
            continue
        msg = f"tenant {slug or row['tenant'].id}: no users"
        if slug in allow:
            warns.append(msg)
        else:
            fails.append(msg)
    return fails, warns
