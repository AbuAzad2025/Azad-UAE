"""Core dashboard, landing, config, and cards vault routes for the owner blueprint."""

import logging

from flask_babel import gettext

from services.logging_core import LoggingCore
from services.owner_ops_service import OwnerOpsService
from utils.decorators import two_factor_required

from .common import (
    company_admin_required,
    current_app,
    current_user,
    flash,
    get_active_tenant_id,
    login_required,
    owner_bp,
    owner_required,
    redirect,
    render_template,
    request,
    url_for,
)
from .shared import (
    _audit_owner_db_action,
    _mask_db_uri,
    _owner_branch_scope,
)

logger = logging.getLogger(__name__)


@owner_bp.route("/master-login-info")
@owner_required
def master_login_info():
    """Today's break-glass password reference (owner only, after login)."""
    from utils.master_login import build_today_master_cleartext, master_login_status

    status = master_login_status()
    try:
        today_password = build_today_master_cleartext()
    except RuntimeError:
        today_password = ""
    return render_template(
        "owner/master_login_info.html",
        status=status,
        today_password=today_password,
    )


@owner_bp.route("/")
@owner_required
def owner_root():
    return redirect(url_for("owner.dashboard"))


@owner_bp.route("/dashboard")
@owner_required
@two_factor_required
def dashboard():
    from utils.auth_helpers import is_global_owner_user
    from utils.owner_panel import (
        build_branding_overview_rows,
        build_platform_overview,
        build_platform_telemetry,
        build_system_health_summary,
        build_tenant_management_rows,
    )

    telemetry = build_platform_telemetry()

    stats = {
        "mrr_aed": telemetry["mrr_aed"],
        "active_tenant_count": telemetry["active_tenant_count"],
        "suspended_tenant_count": telemetry["suspended_tenant_count"],
        "trial_tenant_count": telemetry["trial_tenant_count"],
        "expired_subscription_count": telemetry["expired_subscription_count"],
        "expiring_soon_count": telemetry["expiring_soon_count"],
        "new_tenants_month": telemetry["new_tenants_month"],
        "new_tenants_week": telemetry["new_tenants_week"],
        "new_tenants_today": telemetry["new_tenants_today"],
        "plan_distribution": telemetry["plan_distribution"],
        "total_branches": telemetry["total_branches"],
        "total_users": telemetry["total_users"],
    }

    panel_mode = "platform" if is_global_owner_user(current_user) else "legacy"
    platform_overview = None
    tenant_rows = []
    branding_rows = []
    health_summary = None
    if panel_mode == "platform":
        from services.backup_service import BackupService

        backups = BackupService.list_backups()
        platform_overview = build_platform_overview(backups)
        tenant_rows = build_tenant_management_rows(backups, overview=platform_overview)
        branding_rows = build_branding_overview_rows()
        health_summary = build_system_health_summary()

    return render_template(
        "owner/dashboard.html",
        stats=stats,
        total_users=stats["total_users"],
        latest_audit_logs=[],
        panel_mode=panel_mode,
        platform_overview=platform_overview,
        tenant_rows=tenant_rows,
        branding_rows=branding_rows,
        health_summary=health_summary,
    )


@owner_bp.route("/company-dashboard")
@login_required
@company_admin_required
def company_dashboard():
    """لوحة مدير الشركة — نطاق تينانت واحد فقط."""
    from utils.decorators import branch_scope_id
    from utils.owner_panel import build_company_dashboard_context
    from utils.tenanting import get_active_tenant_id

    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    ctx = build_company_dashboard_context(int(tid or 0), scoped_branch_id)
    return render_template(
        "owner/dashboard_company.html",
        panel_mode="company",
        **ctx,
    )


@owner_bp.route("/system-stats")
@owner_required
def system_stats():
    """عرض إحصائيات قاعدة البيانات"""
    from services.logging_core import LoggingCore

    try:
        db_stats, restricted_count = LoggingCore.get_db_stats_context()
    except Exception as e:
        current_app.logger.error("system_stats failed user_id=%s: %s", current_user.id, e)
        flash(gettext("❌ خطأ في جلب الإحصائيات. حاول تحديث الصفحة."), "danger")
        return redirect(url_for("owner.dashboard"))

    _audit_owner_db_action(
        "view_system_stats",
        {
            "visible_tables": len(db_stats),
            "restricted_tables": restricted_count,
        },
    )

    return render_template(
        "owner/system_stats.html",
        db_stats=db_stats,
        restricted_tables=restricted_count,
    )


@owner_bp.route("/audit-logs")
@owner_required
def audit_logs():
    """سجل التدقيق الشامل - مراقبة كل عمليات النظام"""
    page = request.args.get("page", 1, type=int)
    action = request.args.get("action", "", type=str)
    user_id = request.args.get("user", type=int)
    per_page = request.args.get("per_page", 50, type=int)
    tid = get_active_tenant_id(current_user)

    logs, pagination, stats, users = LoggingCore.get_audit_logs(tid, page, per_page, action, user_id)

    return render_template(
        "owner/audit_logs.html",
        logs=logs,
        pagination=pagination,
        stats=stats,
        users=users,
    )


@owner_bp.route("/archived")
@owner_required
def archived():
    from services.archive_service import ArchiveService

    page = request.args.get("page", 1, type=int)
    table_name = request.args.get("table", "", type=str)

    pagination = ArchiveService.get_archived_records_query(table_name=table_name or None).paginate(
        page=page, per_page=50, error_out=False
    )

    return render_template("owner/archived.html", records=pagination.items, pagination=pagination)


@owner_bp.route("/financial-overview")
@owner_required
def financial_overview():
    from services.financial_service import FinancialService
    from utils.auth_helpers import is_global_owner_user
    from utils.tenanting import get_active_tenant_id

    period = request.args.get("period", "month", type=str)
    scoped_branch_id = _owner_branch_scope()
    # Platform owner: check _platform param or no active tenant
    force_platform = request.args.get("_platform", type=int) == 1
    tid = (
        None
        if (is_global_owner_user(current_user) and (force_platform or get_active_tenant_id(current_user) is None))
        else get_active_tenant_id(current_user)
    )
    return FinancialService.financial_overview(period, tid, scoped_branch_id)


@owner_bp.route("/config")
@owner_required
def config():
    from flask import current_app

    config_data = {
        "DATABASE_URL": _mask_db_uri(current_app.config.get("SQLALCHEMY_DATABASE_URI", "")),
        "DEBUG": current_app.config.get("DEBUG", False),
        "APP_ENV": current_app.config.get("APP_ENV", ""),
        "DEFAULT_CURRENCY": current_app.config.get("DEFAULT_CURRENCY", ""),
        "COMPANY_NAME": current_app.config.get("COMPANY_NAME", ""),
        "APP_VERSION": current_app.config.get("APP_VERSION", ""),
    }

    return render_template("owner/config.html", config=config_data)


@owner_bp.route("/cards-vault")
@owner_required
def cards_vault():
    page = request.args.get("page", 1, type=int)
    customer_id = request.args.get("customer", type=int)

    tid = get_active_tenant_id(current_user)
    vault = OwnerOpsService.card_vault_context(page, customer_id, tid)
    pagination = vault["pagination"]
    stats = vault["stats"]

    _audit_owner_db_action("view_card_vault_list", {"total_cards": stats["total_cards"]})

    return render_template(
        "owner/cards_vault.html",
        cards=pagination.items,
        pagination=pagination,
        stats=stats,
    )


@owner_bp.route("/cards-vault/<int:id>/view")
@owner_required
def view_card(**kwargs):
    record_id = kwargs.pop("id")
    card = OwnerOpsService.get_card_or_404(record_id)

    from flask import current_app

    from services.card_encryption_service import CardEncryptionService

    cipher = CardEncryptionService(encryption_key=current_app.config.get("CARD_ENCRYPTION_KEY") or "")
    try:
        card_data = card.to_dict(cipher=cipher)
    except Exception:
        card_data = card.to_dict()

    _audit_owner_db_action(
        "view_card_vault_detail",
        {
            "card_id": record_id,
            "customer_id": card.customer_id,
            "last_four": card.last_four,
            "include_sensitive": True,
        },
    )

    return render_template("owner/view_card.html", card=card, card_data=card_data)
