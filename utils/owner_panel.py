"""
Owner / company admin panel data builders — display-only, no schema changes.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import func

from extensions import db
from models import Branch, Sale, User
from models.tenant import Tenant
from utils.tenant_branding import resolve_tenant_branding, branding_path_warnings


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
    tenants = Tenant.query.order_by(Tenant.name_ar, Tenant.name).all()
    active_tenants = [t for t in tenants if getattr(t, "is_active", True)]
    suspended = [t for t in tenants if not getattr(t, "is_active", True)]

    user_counts = dict(
        db.session.query(User.tenant_id, func.count(User.id))
        .filter(User.is_owner == False)
        .group_by(User.tenant_id)
        .all()
    )
    branch_counts = dict(
        db.session.query(Branch.tenant_id, func.count(Branch.id))
        .filter(Branch.is_active == True)
        .group_by(Branch.tenant_id)
        .all()
    )

    month_start = datetime.now(timezone.utc).date().replace(day=1)
    sales_by_tenant = dict(
        db.session.query(Sale.tenant_id, func.sum(Sale.amount_aed))
        .filter(
            Sale.status == "confirmed",
            func.date(Sale.sale_date) >= month_start,
        )
        .group_by(Sale.tenant_id)
        .all()
    )

    try:
        from models.gl_journal_entry import GLJournalEntry

        gl_by_tenant = dict(
            db.session.query(GLJournalEntry.tenant_id, func.count(GLJournalEntry.id))
            .group_by(GLJournalEntry.tenant_id)
            .all()
        )
    except Exception:
        gl_by_tenant = {}

    backup_by_tenant = _latest_backup_by_tenant(backups)
    sys_backup = _system_backup_status(backups)
    warnings: list[str] = []

    for t in active_tenants:
        uc = int(user_counts.get(t.id) or 0)
        if uc == 0 and (t.slug or "").lower() != "nasrallah":
            warnings.append(f"Tenant {t.slug or t.id}: no users")
        if t.id not in backup_by_tenant:
            warnings.append(f"Tenant {t.slug or t.id}: no tenant backup")

    nasrallah = next((t for t in tenants if (t.slug or "").lower() == "nasrallah"), None)
    if nasrallah:
        n_users = int(user_counts.get(nasrallah.id) or 0)
        if n_users == 0:
            warnings.append("Nasrallah: active tenant with zero users (expected until manager created)")

    return {
        "tenant_count": len(tenants),
        "active_tenant_count": len(active_tenants),
        "suspended_tenant_count": len(suspended),
        "total_users": User.query.filter_by(is_owner=False).count(),
        "total_branches": Branch.query.filter_by(is_active=True).count(),
        "system_backup": sys_backup,
        "warnings": warnings,
        "user_counts": user_counts,
        "branch_counts": branch_counts,
        "sales_by_tenant": sales_by_tenant,
        "gl_by_tenant": gl_by_tenant,
        "backup_by_tenant": backup_by_tenant,
    }


def build_tenant_management_rows(backups: list | None = None) -> list[dict]:
    from services.backup_service import BackupService

    backups = backups if backups is not None else BackupService.list_backups()
    overview = build_platform_overview(backups)
    rows = []
    for tenant in Tenant.query.order_by(Tenant.name_ar, Tenant.name).all():
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
                "month_sales": float(overview["sales_by_tenant"].get(tid) or 0),
                "gl_entries": int(overview["gl_by_tenant"].get(tid) or 0),
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


def build_branding_overview_rows() -> list[dict]:
    rows = []
    for tenant in Tenant.query.filter_by(is_active=True).order_by(Tenant.slug).all():
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
        from flask import has_app_context
        from flask_migrate import current as alembic_current

        if has_app_context():
            rev = alembic_current()
            summary["migration"] = rev or "head"
    except Exception:
        summary["migration"] = "check alembic"

    return summary


def build_company_dashboard_context(tenant_id: int, branch_id: int | None = None) -> dict:
    """KPIs and readiness for tenant company admin (single tenant only)."""
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

    from models import Product, Customer

    prod_q = Product.query.filter_by(tenant_id=tenant_id, is_active=True)
    cust_q = Customer.query.filter_by(tenant_id=tenant_id, is_active=True)
    if branch_id is not None:
        cust_q = cust_q.join(Sale, Customer.id == Sale.customer_id).filter(
            Sale.branch_id == branch_id,
            Sale.tenant_id == tenant_id,
        ).distinct()

    users_count = User.query.filter(
        User.tenant_id == tenant_id,
        User.is_owner == False,
        User.is_active == True,
    ).count()
    branches_count = Branch.query.filter_by(tenant_id=tenant_id, is_active=True).count()

    from services.backup_service import BackupService

    all_backups = BackupService.list_backups()
    tenant_backups = [
        b
        for b in all_backups
        if b.get("backup_scope") == "tenant" and int(b.get("tenant_id") or -1) == int(tenant_id)
    ]

    return {
        "tenant": tenant,
        "branding": branding,
        "logo_url": _tenant_logo_display_url(tenant, branding),
        "readiness_warnings": readiness,
        "today_sales_count": today_sales[0] or 0,
        "today_sales_amount": float(today_sales[1] or 0),
        "month_sales_count": month_sales[0] or 0,
        "month_sales_amount": float(month_sales[1] or 0),
        "products_count": prod_q.count(),
        "customers_count": cust_q.count(),
        "users_count": users_count,
        "branches_count": branches_count,
        "tenant_backup_count": len(tenant_backups),
        "scoped_branch_id": branch_id,
    }


def tenants_without_users_allowlist() -> set[str]:
    raw = (os.environ.get("OWNER_PANEL_ALLOW_TENANTS_WITHOUT_USERS") or "nasrallah").strip()
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
