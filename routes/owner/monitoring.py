"""Monitoring, analytics, and error audit routes for the owner blueprint."""

from datetime import datetime, timezone
from routes.owner import (
    render_template,
    request,
    flash,
    redirect,
    url_for,
    current_user,
    db,
    User,
    LoginHistory,
    SecurityAlert,
    APIKey,
    SystemSettings,
    owner_required,
    get_active_tenant_id,
    safe_redirect_target,
)
from services.logging_core import LoggingCore
from routes.owner import owner_bp
from routes.owner.shared import (
    _invalidate_owner_changes,
    _owner_branch_scope,
    _mask_api_key,
)
from utils.db_safety import atomic_transaction

import logging

logger = logging.getLogger(__name__)


@owner_bp.route("/system-health")
@owner_required
def system_health():
    """فحص صحة النظام — للمالك فقط"""
    from services.health_service import HealthCheckService

    try:
        health_data = HealthCheckService.get_health_data()
        return render_template("owner/system_health.html", health=health_data)
    except Exception as e:
        flash(f"خطأ في تحميل معلومات النظام: {str(e)}", "danger")
        return redirect(url_for("owner.dashboard"))


@owner_bp.route("/activity-monitor")
@owner_required
def activity_monitor():
    from services.logging_core import LoggingCore

    tid = get_active_tenant_id(current_user)
    scoped_branch_id = _owner_branch_scope()

    ctx = LoggingCore.get_activity_context(tid, scoped_branch_id)

    return render_template(
        "owner/activity_monitor.html",
        recent_audits=ctx["recent_audits"],
        active_users=ctx["active_users"],
        recent_sales=ctx["recent_sales"],
        stats=ctx["stats"],
    )


@owner_bp.route("/login-history")
@owner_required
def login_history():
    page = request.args.get("page", 1, type=int)
    user_filter = request.args.get("user_id", type=int)
    success_filter = request.args.get("success")
    tid = get_active_tenant_id(current_user)

    # LoginHistory has no tenant_id, so we join with User to scope where possible
    query = LoginHistory.query
    if tid:
        query = query.join(User, LoginHistory.user_id == User.id).filter(
            User.tenant_id == tid
        )

    if user_filter:
        query = query.filter(LoginHistory.user_id == user_filter)

    if success_filter is not None:
        query = query.filter(
            LoginHistory.__table__.c.success == (success_filter == "true")
        )

    pagination = query.order_by(LoginHistory.login_time.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    # Users list for filter dropdown, scoped by tenant
    users = User.query.filter_by(is_active=True)
    if tid:
        users = users.filter_by(tenant_id=tid)
    users = users.order_by(User.username).all()

    # Stats: base queries scoped by tenant via User join
    base_stats = LoginHistory.query
    if tid:
        base_stats = base_stats.join(User, LoginHistory.user_id == User.id).filter(
            User.tenant_id == tid
        )
    stats = {
        "total_logins": base_stats.filter(LoginHistory.success).count(),
        "failed_logins": base_stats.filter(not LoginHistory.success).count(),
        "today_logins": base_stats.filter(
            LoginHistory.login_time
            >= datetime.now(timezone.utc).replace(hour=0, minute=0)
        ).count(),
    }

    return render_template(
        "owner/login_history.html",
        logins=pagination.items,
        pagination=pagination,
        users=users,
        stats=stats,
    )


@owner_bp.route("/performance-metrics")
@owner_required
def performance_metrics():
    """مراقبة الأداء"""
    from services.logging_core import LoggingCore

    metrics = LoggingCore.get_performance_metrics_data()

    return render_template("owner/performance_metrics.html", metrics=metrics)


@owner_bp.route("/security-alerts")
@owner_required
def security_alerts():
    page = request.args.get("page", 1, type=int)
    severity_filter = request.args.get("severity")

    query = SecurityAlert.query

    if severity_filter:
        query = query.filter_by(severity=severity_filter)

    pagination = (
        query.filter_by(is_resolved=False)
        .order_by(SecurityAlert.created_at.desc())
        .paginate(page=page, per_page=30, error_out=False)
    )

    stats = {
        "unresolved": SecurityAlert.query.filter_by(is_resolved=False).count(),
        "critical": SecurityAlert.query.filter_by(
            severity="critical", is_resolved=False
        ).count(),
        "high": SecurityAlert.query.filter_by(
            severity="high", is_resolved=False
        ).count(),
    }

    return render_template(
        "owner/security_alerts.html",
        alerts=pagination.items,
        pagination=pagination,
        stats=stats,
    )


@owner_bp.route("/security-alerts/<int:id>/resolve", methods=["POST"])
@owner_required
def resolve_alert(id):  # noqa: A002
    alert = SecurityAlert.query.get_or_404(id)
    try:
        with atomic_transaction("resolve_alert"):
            alert.is_resolved = True
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolved_by = current_user.id
    except Exception as e:
        flash(f"❌ خطأ في حل التنبيه: {str(e)}", "danger")
        return redirect(url_for("owner.security_alerts"))
    _invalidate_owner_changes()
    flash("✅ تم حل التنبيه الأمني", "success")
    return redirect(url_for("owner.security_alerts"))


@owner_bp.route("/ip-whitelist", methods=["GET", "POST"])
@owner_required
def ip_whitelist():
    if request.method == "POST":
        ip_address = request.form.get("ip_address")
        description = request.form.get("description")

        settings = SystemSettings.get_current()
        whitelist = settings.owner_whitelist_ips or []

        try:
            with atomic_transaction("add_ip_whitelist"):
                whitelist.append({"ip": ip_address, "description": description})
                settings.owner_whitelist_ips = whitelist
        except Exception as e:
            flash(f"❌ خطأ في إضافة IP: {str(e)}", "danger")
            return redirect(url_for("owner.ip_whitelist"))
        _invalidate_owner_changes()
        flash("✅ تم إضافة IP للقائمة البيضاء", "success")
        return redirect(url_for("owner.ip_whitelist"))

    settings = SystemSettings.get_current()
    whitelist = settings.owner_whitelist_ips or []

    return render_template("owner/ip_whitelist.html", whitelist=whitelist)


@owner_bp.route("/ip-whitelist/<int:index>/delete", methods=["POST"])
@owner_required
def delete_ip_whitelist(index):
    settings = SystemSettings.get_current()
    whitelist = settings.owner_whitelist_ips or []

    if 0 <= index < len(whitelist):
        try:
            with atomic_transaction("delete_ip_whitelist"):
                whitelist.pop(index)
                settings.owner_whitelist_ips = whitelist
        except Exception as e:
            flash(f"❌ خطأ في حذف IP: {str(e)}", "danger")
            return redirect(url_for("owner.ip_whitelist"))
        _invalidate_owner_changes()
        flash("✅ تم حذف IP من القائمة البيضاء", "success")

    return redirect(url_for("owner.ip_whitelist"))


@owner_bp.route("/api-keys", methods=["GET", "POST"])
@owner_required
def api_keys():
    if request.method == "POST":
        name = request.form.get("name")
        service = request.form.get("service")

        key = APIKey(
            name=name,
            key=APIKey.generate_key(),
            service=service,
            created_by=current_user.id,
        )

        try:
            with atomic_transaction("create_api_key"):
                db.session.add(key)
        except Exception as e:
            flash(f"❌ خطأ في إنشاء المفتاح: {str(e)}", "danger")
            return redirect(url_for("owner.api_keys"))
        _invalidate_owner_changes()
        flash(f"✅ تم إنشاء API Key ({_mask_api_key(key.key)})", "success")
        return redirect(url_for("owner.api_keys"))

    keys = APIKey.query.order_by(APIKey.created_at.desc()).all()

    return render_template("owner/api_keys.html", keys=keys, mask_api_key=_mask_api_key)


@owner_bp.route("/api-keys/<int:id>/toggle", methods=["POST"])
@owner_required
def toggle_api_key(id):  # noqa: A002
    key = APIKey.query.get_or_404(id)
    try:
        with atomic_transaction("toggle_api_key"):
            key.is_active = not key.is_active
    except Exception as e:
        flash(f"❌ خطأ في تحديث المفتاح: {str(e)}", "danger")
        return redirect(url_for("owner.api_keys"))
    _invalidate_owner_changes()
    status = "تفعيل" if key.is_active else "تعطيل"
    flash(f"✅ تم {status} API Key", "success")
    return redirect(url_for("owner.api_keys"))


@owner_bp.route("/financial-dashboard-advanced")
@owner_required
def financial_dashboard_advanced():
    from services.financial_service import FinancialService

    tid = get_active_tenant_id(current_user)
    scoped_branch_id = _owner_branch_scope()
    context = FinancialService.get_financial_dashboard_advanced_context(
        tenant_id=tid, branch_id=scoped_branch_id
    )
    return render_template(
        "owner/financial_dashboard_advanced.html",
        months_data=context["months_data"],
        kpis=context["kpis"],
    )


@owner_bp.route("/sales-insights")
@owner_required
def sales_insights():
    from services.analytics_service import AnalyticsService

    scoped_branch_id = _owner_branch_scope()
    tid = get_active_tenant_id(current_user)
    insights = AnalyticsService.get_sales_insights(
        tenant_id=tid, branch_id=scoped_branch_id
    )
    return render_template("owner/sales_insights.html", insights=insights)


@owner_bp.route("/customer-insights")
@owner_required
def customer_insights():
    from services.analytics_service import AnalyticsService

    scoped_branch_id = _owner_branch_scope()
    tid = get_active_tenant_id(current_user)
    customers = AnalyticsService.get_customer_insights(
        tenant_id=tid, branch_id=scoped_branch_id
    )
    return render_template("owner/customer_insights.html", customers=customers)


@owner_bp.route("/product-performance")
@owner_required
def product_performance():
    from services.analytics_service import AnalyticsService

    scoped_branch_id = _owner_branch_scope()
    tid = get_active_tenant_id(current_user)
    products = AnalyticsService.get_product_performance(
        tenant_id=tid, branch_id=scoped_branch_id
    )
    return render_template("owner/product_performance.html", products=products)


@owner_bp.route("/forecasting")
@owner_required
def forecasting():
    from services.analytics_service import AnalyticsService

    scoped_branch_id = _owner_branch_scope()
    tid = get_active_tenant_id(current_user)
    historical, forecast = AnalyticsService.get_forecasting_data(
        tenant_id=tid, branch_id=scoped_branch_id
    )
    return render_template(
        "owner/forecasting.html", historical=historical, forecast=forecast
    )


# ───────────────────────────────────────────────────────────────
# Tenant Management — full control for the owner
# ───────────────────────────────────────────────────────────────


@owner_bp.route("/error-audit-logs")
@owner_required
def error_audit_logs():
    """Owner view of all system errors with classification."""
    category = request.args.get("category", "").strip()
    level = request.args.get("level", "").strip()
    is_resolved = request.args.get("resolved", "")
    page = request.args.get("page", 1, type=int)
    per_page = 50

    items, pagination, categories, levels, stats = LoggingCore.get_error_logs(
        category, level, is_resolved, page, per_page
    )

    return render_template(
        "owner/error_audit_logs.html",
        logs=items,
        pagination=pagination,
        categories=categories,
        levels=levels,
        selected_category=category,
        selected_level=level,
        selected_resolved=is_resolved,
        stats=stats,
    )


@owner_bp.route("/error-audit-logs/<int:log_id>/resolve", methods=["POST"])
@owner_required
def resolve_error_log(log_id):
    """Mark an error as resolved."""
    note = request.form.get("note", "")
    ok = LoggingCore.mark_error_resolved(log_id, current_user.id, note)
    if ok:
        flash("تم تحديث حالة الخطأ.", "success")
    else:
        flash("فشل تحديث حالة الخطأ.", "danger")
    return redirect(safe_redirect_target(request.referrer, "owner.error_audit_logs"))


@owner_bp.route("/error-audit-logs/export")
@owner_required
def export_error_audit_logs():
    """Export error logs as JSON or plain text."""
    fmt = request.args.get("format", "json").lower().strip()
    category = request.args.get("category", "").strip()
    level = request.args.get("level", "").strip()
    is_resolved = request.args.get("resolved", "")

    try:
        payload, mimetype, filename = LoggingCore.export_error_logs(
            category, level, is_resolved, fmt
        )
        return (
            payload,
            200,
            {
                "Content-Type": mimetype,
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except Exception:
        flash("صيغة التصدير غير مدعومة أو فشل التصدير.", "danger")
        return redirect(url_for("owner.error_audit_logs"))
