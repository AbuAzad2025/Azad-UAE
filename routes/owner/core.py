"""Core dashboard, landing, config, and cards vault routes for the owner blueprint."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from routes.owner import (
    render_template,
    request,
    flash,
    redirect,
    url_for,
    current_app,
    login_required,
    current_user,
    func,
    desc,
    db,
    User,
    Customer,
    Product,
    Sale,
    SaleLine,
    Purchase,
    AuditLog,
    CardVault,
    Tenant,
    Expense,
    owner_required,
    company_admin_required,
    get_active_tenant_id,
    get_visible_products_query,
)
from services.logging_core import LoggingCore
from routes.owner import owner_bp
from routes.owner.shared import (
    _audit_owner_db_action,
    _owner_branch_scope,
    _mask_db_uri,
)

import logging

logger = logging.getLogger(__name__)


@owner_bp.route("/master-login-info")
@owner_required
def master_login_info():
    """Today's break-glass password reference (owner only, after login)."""
    from utils.master_login import master_login_status, build_today_master_cleartext

    return render_template(
        "owner/master_login_info.html",
        status=master_login_status(),
        today_password=build_today_master_cleartext(),
    )


@owner_bp.route("/")
@owner_required
def owner_root():
    return redirect(url_for("owner.dashboard"))


@owner_bp.route("/dashboard")
@owner_required
def dashboard():
    stats = {}
    scoped_branch_id = _owner_branch_scope()

    now = datetime.now(timezone.utc)
    today = datetime.now().date()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    cutoff_date = datetime.now() - timedelta(days=30)

    tid = get_active_tenant_id(current_user)
    stats["total_users"] = User.query.filter_by(
        is_active=True, is_owner=False, tenant_id=tid
    ).count()
    customers_query = Customer.query.filter_by(is_active=True, tenant_id=tid)
    if scoped_branch_id is not None:
        customers_query = (
            customers_query.join(Sale, Customer.id == Sale.customer_id)
            .filter(Sale.branch_id == scoped_branch_id)
            .distinct()
        )
    stats["total_customers"] = customers_query.count()
    stats["total_products"] = (
        get_visible_products_query(current_user).count()
        if scoped_branch_id is not None
        else Product.query.filter_by(is_active=True, tenant_id=tid).count()
    )

    vip_query = Customer.query.filter_by(
        customer_classification="vip", is_active=True, tenant_id=tid
    )
    if scoped_branch_id is not None:
        vip_query = (
            vip_query.join(Sale, Customer.id == Sale.customer_id)
            .filter(Sale.branch_id == scoped_branch_id)
            .distinct()
        )
    stats["vip_customers"] = vip_query.count()

    premium_query = Customer.query.filter_by(
        customer_classification="premium", is_active=True, tenant_id=tid
    )
    if scoped_branch_id is not None:
        premium_query = (
            premium_query.join(Sale, Customer.id == Sale.customer_id)
            .filter(Sale.branch_id == scoped_branch_id)
            .distinct()
        )
    stats["premium_customers"] = premium_query.count()

    today_sales = db.session.query(
        func.count(Sale.id),
        func.sum(Sale.amount_aed),
        func.sum(Sale.amount_aed - Sale.paid_amount_aed),
    ).filter(
        func.date(Sale.sale_date) == today,
        Sale.status == "confirmed",
        Sale.tenant_id == tid,
    )
    if scoped_branch_id is not None:
        today_sales = today_sales.filter(Sale.branch_id == scoped_branch_id)
    today_sales = today_sales.first()

    stats["today_sales_count"] = today_sales[0] or 0
    stats["today_sales_amount"] = float(today_sales[1] or 0)
    stats["today_receivables"] = float(today_sales[2] or 0)

    month_sales = db.session.query(
        func.count(Sale.id), func.sum(Sale.amount_aed)
    ).filter(
        func.date(Sale.sale_date) >= month_start,
        Sale.status == "confirmed",
        Sale.tenant_id == tid,
    )
    if scoped_branch_id is not None:
        month_sales = month_sales.filter(Sale.branch_id == scoped_branch_id)
    month_sales = month_sales.first()

    stats["month_sales_count"] = month_sales[0] or 0
    stats["month_sales_amount"] = float(month_sales[1] or 0)

    year_sales = db.session.query(func.sum(Sale.amount_aed)).filter(
        func.date(Sale.sale_date) >= year_start,
        Sale.status == "confirmed",
        Sale.tenant_id == tid,
    )
    if scoped_branch_id is not None:
        year_sales = year_sales.filter(Sale.branch_id == scoped_branch_id)
    year_sales = year_sales.scalar() or Decimal("0")

    stats["year_sales_amount"] = float(year_sales)

    month_purchases = db.session.query(func.sum(Purchase.amount_aed)).filter(
        func.date(Purchase.purchase_date) >= month_start,
        Purchase.status == "confirmed",
        Purchase.tenant_id == tid,
    )
    if scoped_branch_id is not None:
        month_purchases = month_purchases.filter(Purchase.branch_id == scoped_branch_id)
    month_purchases = month_purchases.scalar() or Decimal("0")

    stats["month_purchases_amount"] = float(month_purchases)

    profit_expr = func.sum(
        (SaleLine.unit_price - func.coalesce(SaleLine.cost_price, 0))
        * SaleLine.quantity
        * (100 - func.coalesce(SaleLine.discount_percent, 0))
        / 100
    )
    profit_q = (
        db.session.query(profit_expr)
        .select_from(SaleLine)
        .join(Sale, SaleLine.sale_id == Sale.id)
        .filter(
            func.date(Sale.sale_date) >= month_start,
            Sale.status == "confirmed",
            Sale.tenant_id == tid,
        )
    )
    if scoped_branch_id is not None:
        profit_q = profit_q.filter(Sale.branch_id == scoped_branch_id)
    total_profit = profit_q.scalar() or Decimal("0")

    stats["month_profit"] = float(total_profit)
    stats["profit_margin"] = (
        (float(total_profit) / float(month_sales[1] or 1)) * 100
        if month_sales[1]
        else 0
    )

    # Inventory value/cost: single aggregated query (optimized)
    inv_row = (
        db.session.query(
            func.sum(
                func.coalesce(Product.current_stock, 0)
                * func.coalesce(Product.regular_price, 0)
            ),
            func.sum(
                func.coalesce(Product.current_stock, 0)
                * func.coalesce(Product.cost_price, 0)
            ),
        )
        .filter(
            Product.is_active,
            Product.tenant_id == tid,
        )
        .first()
    )
    stats["inventory_value"] = float(inv_row[0] or Decimal("0"))
    stats["inventory_cost"] = float(inv_row[1] or Decimal("0"))

    # Receivables: single aggregated query (optimized)
    receivables_row = db.session.query(
        func.sum(Sale.amount_aed - Sale.paid_amount_aed), func.count(Sale.id)
    ).filter(
        Sale.status == "confirmed",
        Sale.amount_aed - Sale.paid_amount_aed > 0,
        Sale.tenant_id == tid,
    )
    if scoped_branch_id is not None:
        receivables_row = receivables_row.filter(Sale.branch_id == scoped_branch_id)
    receivables_row = receivables_row.first()
    total_receivables = receivables_row[0] or Decimal("0")
    stats["total_receivables"] = float(total_receivables)
    overdue_count = Sale.query.filter(
        Sale.status == "confirmed",
        Sale.amount_aed - Sale.paid_amount_aed > 0,
        Sale.sale_date < cutoff_date,
        Sale.tenant_id == tid,
    )
    if scoped_branch_id is not None:
        overdue_count = overdue_count.filter(Sale.branch_id == scoped_branch_id)
    overdue_count = overdue_count.count()
    stats["overdue_invoices"] = overdue_count

    top_customers = (
        db.session.query(
            Customer.id,
            Customer.name,
            Customer.customer_type,
            Customer.customer_classification,
            func.sum(Sale.amount_aed).label("total"),
        )
        .join(Sale, Customer.id == Sale.customer_id)
        .filter(
            Sale.status == "confirmed",
            func.date(Sale.sale_date) >= month_start,
            Sale.tenant_id == tid,
        )
    )
    if scoped_branch_id is not None:
        top_customers = top_customers.filter(Sale.branch_id == scoped_branch_id)
    top_customers = (
        top_customers.group_by(
            Customer.id,
            Customer.name,
            Customer.customer_type,
            Customer.customer_classification,
        )
        .order_by(desc("total"))
        .limit(10)
        .all()
    )

    stats["top_customers"] = top_customers

    # Top selling products
    try:
        top_products = (
            db.session.query(
                Product.id,
                Product.name,
                func.sum(SaleLine.quantity).label("quantity"),
                func.sum(SaleLine.line_total).label("revenue"),
            )
            .join(SaleLine, Product.id == SaleLine.product_id)
            .join(Sale, SaleLine.sale_id == Sale.id)
            .filter(
                Sale.status == "confirmed",
                func.date(Sale.sale_date) >= month_start,
                Sale.tenant_id == tid,
            )
        )
        if scoped_branch_id is not None:
            top_products = top_products.filter(Sale.branch_id == scoped_branch_id)
        top_products = (
            top_products.group_by(Product.id, Product.name)
            .order_by(desc("revenue"))
            .limit(10)
            .all()
        )

        stats["top_products"] = top_products
    except Exception as e:
        current_app.logger.error(f"Error getting top products: {e}")
        stats["top_products"] = []

    recent_actions = (
        AuditLog.query.filter_by(tenant_id=tid)
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )

    stats["recent_actions"] = recent_actions

    # Platform-wide stats for global owner with no active tenant
    from utils.auth_helpers import is_global_owner_user

    platform_mode = is_global_owner_user(current_user) and tid is None
    if platform_mode:
        stats["platform_total_users"] = User.query.filter_by(
            is_active=True, is_owner=False
        ).count()
        stats["platform_total_tenants"] = Tenant.query.filter_by(is_active=True).count()
        stats["platform_total_customers"] = Customer.query.filter_by(
            is_active=True
        ).count()
        stats["platform_total_products"] = Product.query.filter_by(
            is_active=True
        ).count()

        platform_today_sales = (
            db.session.query(
                func.count(Sale.id),
                func.sum(Sale.amount_aed),
                func.sum(Sale.amount_aed - Sale.paid_amount_aed),
            )
            .filter(
                func.date(Sale.sale_date) == today,
                Sale.status == "confirmed",
            )
            .first()
        )
        stats["platform_today_sales_count"] = platform_today_sales[0] or 0
        stats["platform_today_sales_amount"] = float(platform_today_sales[1] or 0)
        stats["platform_today_receivables"] = float(platform_today_sales[2] or 0)

        platform_month_sales = (
            db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
            .filter(
                func.date(Sale.sale_date) >= month_start,
                Sale.status == "confirmed",
            )
            .first()
        )
        stats["platform_month_sales_count"] = platform_month_sales[0] or 0
        stats["platform_month_sales_amount"] = float(platform_month_sales[1] or 0)

        platform_year_sales = db.session.query(func.sum(Sale.amount_aed)).filter(
            func.date(Sale.sale_date) >= year_start,
            Sale.status == "confirmed",
        ).scalar() or Decimal("0")
        stats["platform_year_sales_amount"] = float(platform_year_sales)

        platform_month_purchases = db.session.query(
            func.sum(Purchase.amount_aed)
        ).filter(
            func.date(Purchase.purchase_date) >= month_start,
            Purchase.status == "confirmed",
        ).scalar() or Decimal(
            "0"
        )
        stats["platform_month_purchases_amount"] = float(platform_month_purchases)

        platform_receivables = (
            db.session.query(
                func.sum(Sale.amount_aed - Sale.paid_amount_aed), func.count(Sale.id)
            )
            .filter(
                Sale.status == "confirmed",
                Sale.amount_aed > Sale.paid_amount_aed,
            )
            .first()
        )
        stats["platform_total_receivables"] = float(
            platform_receivables[0] or Decimal("0")
        )
        stats["platform_overdue_invoices"] = platform_receivables[1] or 0

        platform_inv = (
            db.session.query(
                func.sum(
                    func.coalesce(Product.current_stock, 0)
                    * func.coalesce(Product.regular_price, 0)
                ),
                func.sum(
                    func.coalesce(Product.current_stock, 0)
                    * func.coalesce(Product.cost_price, 0)
                ),
            )
            .filter(Product.is_active)
            .first()
        )
        stats["platform_inventory_value"] = float(platform_inv[0] or Decimal("0"))
        stats["platform_inventory_cost"] = float(platform_inv[1] or Decimal("0"))

    if scoped_branch_id is not None:
        low_stock = get_visible_products_query(current_user).all()
    else:
        low_stock = (
            Product.query.filter(
                Product.is_active,
                Product.tenant_id == tid,
                Product.current_stock <= Product.min_stock_alert,
            )
            .order_by(Product.current_stock)
            .limit(10)
            .all()
        )
    if scoped_branch_id is not None:
        low_stock = [
            p
            for p in low_stock
            if getattr(p, "visible_stock", p.current_stock or 0)
            <= (p.min_stock_alert or 0)
        ][:10]

    stats["low_stock"] = low_stock

    # --- Branch Performance Stats ---
    from models import Branch, Warehouse

    branches = Branch.query.filter_by(tenant_id=tid).all()
    if scoped_branch_id is not None:
        branches = [branch for branch in branches if branch.id == scoped_branch_id]
    branch_stats = []

    for branch in branches:
        # Sales Count & Amount for this branch (All time)
        b_sales = (
            db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
            .filter(
                Sale.branch_id == branch.id,
                Sale.status == "confirmed",
                Sale.tenant_id == tid,
            )
            .first()
        )

        # Monthly Sales
        b_month_sales = (
            db.session.query(func.sum(Sale.amount_aed))
            .filter(
                Sale.branch_id == branch.id,
                Sale.status == "confirmed",
                func.date(Sale.sale_date) >= month_start,
                Sale.tenant_id == tid,
            )
            .scalar()
            or 0
        )

        # Expenses (All time)
        b_expenses = (
            db.session.query(func.sum(Expense.amount_aed))
            .filter(
                Expense.branch_id == branch.id,
                not Expense.is_reversed,
                Expense.tenant_id == tid,
            )
            .scalar()
            or 0
        )

        # Inventory value for this branch (from stock in branch warehouses)
        warehouse_ids = [
            w.id
            for w in Warehouse.query.filter_by(
                branch_id=branch.id, is_active=True
            ).all()
        ]
        branch_inventory_value = float(0)
        if warehouse_ids:
            from models import ProductWarehouseCost

            pwc_vals = db.session.query(
                func.sum(ProductWarehouseCost.total_value)
            ).filter(
                ProductWarehouseCost.warehouse_id.in_(warehouse_ids)
            ).scalar() or Decimal(
                "0"
            )
            branch_inventory_value = float(pwc_vals)

        branch_stats.append(
            {
                "id": branch.id,
                "name": branch.name,
                "code": branch.code,
                "total_sales_count": b_sales[0] or 0,
                "total_sales_amount": float(b_sales[1] or 0),
                "month_sales_amount": float(b_month_sales),
                "total_expenses": float(b_expenses),
                "inventory_value": branch_inventory_value,
                "net_profit_indicator": float(b_sales[1] or 0) - float(b_expenses),
            }
        )

    from utils.auth_helpers import is_global_owner_user
    from utils.owner_panel import (
        build_platform_overview,
        build_tenant_management_rows,
        build_branding_overview_rows,
        build_system_health_summary,
    )

    # Platform-wide branch stats (all tenants) — aggregated, top 50 by sales
    platform_branch_stats = []
    if is_global_owner_user(current_user) and tid is None:
        from models import Branch, Warehouse, ProductWarehouseCost

        # Top 50 branches by all-time confirmed sales amount
        top_branches = (
            db.session.query(
                Branch.id,
                Branch.name,
                Branch.code,
                Branch.tenant_id,
                func.count(Sale.id).label("sale_count"),
                func.coalesce(func.sum(Sale.amount_aed), 0).label("sale_total"),
                func.coalesce(
                    func.sum(Sale.amount_aed).filter(
                        func.date(Sale.sale_date) >= month_start
                    ),
                    0,
                ).label("sale_month"),
            )
            .outerjoin(
                Sale, db.and_(Sale.branch_id == Branch.id, Sale.status == "confirmed")
            )
            .group_by(Branch.id, Branch.name, Branch.code, Branch.tenant_id)
            .order_by(desc("sale_total"))
            .limit(50)
            .all()
        )

        branch_ids = [r.id for r in top_branches]

        # Expenses per branch (single aggregated query)
        expense_map = {}
        if branch_ids:
            exp_rows = (
                db.session.query(
                    Expense.branch_id, func.coalesce(func.sum(Expense.amount_aed), 0)
                )
                .filter(
                    Expense.branch_id.in_(branch_ids),
                    not Expense.is_reversed,
                )
                .group_by(Expense.branch_id)
                .all()
            )
            expense_map = {r[0]: float(r[1]) for r in exp_rows}

        # Inventory value per branch (single aggregated query)
        inv_map = {}
        if branch_ids:
            wh_rows = (
                db.session.query(
                    Warehouse.branch_id,
                    func.coalesce(func.sum(ProductWarehouseCost.total_value), 0),
                )
                .join(
                    ProductWarehouseCost,
                    ProductWarehouseCost.warehouse_id == Warehouse.id,
                )
                .filter(
                    Warehouse.branch_id.in_(branch_ids),
                    Warehouse.is_active,
                )
                .group_by(Warehouse.branch_id)
                .all()
            )
            inv_map = {r[0]: float(r[1]) for r in wh_rows}

        # Build branch mapping for tenant name
        tenant_map = {
            t.id: getattr(t, "name_ar", t.name)
            for t in Tenant.query.filter(
                Tenant.id.in_(set(r.tenant_id for r in top_branches))
            ).all()
        }

        for row in top_branches:
            platform_branch_stats.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "code": row.code,
                    "tenant_name": tenant_map.get(row.tenant_id, "—"),
                    "total_sales_count": row.sale_count,
                    "total_sales_amount": float(row.sale_total),
                    "month_sales_amount": float(row.sale_month),
                    "total_expenses": expense_map.get(row.id, 0),
                    "inventory_value": inv_map.get(row.id, 0),
                    "net_profit_indicator": float(row.sale_total)
                    - expense_map.get(row.id, 0),
                }
            )

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
        branch_stats=branch_stats,
        platform_branch_stats=(
            platform_branch_stats if "platform_branch_stats" in locals() else []
        ),
        total_users=stats["total_users"],
        total_customers=stats["total_customers"],
        total_sales=stats.get("month_sales_count", 0),
        latest_audit_logs=stats["recent_actions"],
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
    from utils.tenanting import get_active_tenant_id
    from utils.owner_panel import build_company_dashboard_context
    from utils.decorators import branch_scope_id

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
        current_app.logger.error(
            "system_stats failed user_id=%s: %s", current_user.id, e
        )
        flash("❌ خطأ في جلب الإحصائيات. حاول تحديث الصفحة.", "danger")
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

    logs, pagination, stats, users = LoggingCore.get_audit_logs(
        tid, page, per_page, action, user_id
    )

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

    pagination = ArchiveService.get_archived_records_query(
        table_name=table_name or None
    ).paginate(page=page, per_page=50, error_out=False)

    return render_template(
        "owner/archived.html", records=pagination.items, pagination=pagination
    )


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
        if (
            is_global_owner_user(current_user)
            and (force_platform or get_active_tenant_id(current_user) is None)
        )
        else get_active_tenant_id(current_user)
    )
    return FinancialService.financial_overview(period, tid, scoped_branch_id)


@owner_bp.route("/config")
@owner_required
def config():
    from flask import current_app

    config_data = {
        "DATABASE_URL": _mask_db_uri(
            current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        ),
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

    query = CardVault.query.filter_by(is_active=True)

    if customer_id:
        query = query.filter_by(customer_id=customer_id)

    tid = get_active_tenant_id(current_user)
    if tid is not None:
        query = query.filter(CardVault.tenant_id == tid)

    pagination = query.order_by(CardVault.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    total_cards = CardVault.query.filter_by(is_active=True)
    if tid is not None:
        total_cards = total_cards.filter(CardVault.tenant_id == tid)
    total_cards = total_cards.count()

    total_usage = db.session.query(func.sum(CardVault.usage_count))
    if tid is not None:
        total_usage = total_usage.filter(CardVault.tenant_id == tid)
    total_usage = total_usage.scalar() or 0

    stats = {
        "total_cards": total_cards,
        "total_usage": total_usage,
        "visa_count": (
            CardVault.query.filter_by(card_type="visa", is_active=True)
            .filter(CardVault.tenant_id == tid)
            .count()
            if tid is not None
            else CardVault.query.filter_by(card_type="visa", is_active=True).count()
        ),
        "mastercard_count": (
            CardVault.query.filter_by(card_type="mastercard", is_active=True)
            .filter(CardVault.tenant_id == tid)
            .count()
            if tid is not None
            else CardVault.query.filter_by(
                card_type="mastercard", is_active=True
            ).count()
        ),
    }

    _audit_owner_db_action("view_card_vault_list", {"total_cards": total_cards})

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
    card = CardVault.query.get_or_404(record_id)

    card_data = card.to_dict(include_sensitive=True)

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
