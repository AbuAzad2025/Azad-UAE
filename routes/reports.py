from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from flask import Blueprint, render_template, request
from flask_babel import gettext
from flask_login import current_user, login_required

from services.reports_query_service import ReportsQueryService
from utils.api_response import error_response, success_response
from utils.decorators import permission_required, report_branch_scope_id
from utils.feature_guards import install_feature_gate
from utils.tenanting import (
    get_active_tenant_id,
    require_report_tenant_id,
    tenant_get_or_404,
)

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")
install_feature_gate(reports_bp, "reports")


@reports_bp.before_request
def _enforce_report_tenant_scope():
    from utils.auth_helpers import is_global_owner_user

    if request.endpoint == "reports.index":
        return
    if request.endpoint and request.endpoint.startswith("reports."):
        if is_global_owner_user(current_user):
            return
        require_report_tenant_id()


@reports_bp.route("/")
@login_required
@permission_required("view_reports")
def index():
    return render_template("reports/index.html")


@reports_bp.route("/partners")
@login_required
@permission_required("view_reports")
def partners():
    """تقرير الشركاء والمنتجات التابعة للتجار"""
    date_from = request.args.get("date_from", "", type=str)
    date_to = request.args.get("date_to", "", type=str)
    scoped_branch_id = report_branch_scope_id()

    tenant_id = get_active_tenant_id(current_user)

    context = ReportsQueryService.build_partners_report(date_from, date_to, tenant_id, scoped_branch_id)

    return render_template(
        "reports/partners.html",
        partners_data=context["partners_data"],
        merchants_data=context["merchants_data"],
        partners_summary=context["partners_summary"],
        merchants_summary=context["merchants_summary"],
        suppliers_summary=context["suppliers_summary"],
    )


@reports_bp.route("/sales")
@login_required
@permission_required("view_reports")
def sales():
    from utils.gl_tenant import default_report_date_range

    date_from = request.args.get("date_from", "", type=str)
    date_to = request.args.get("date_to", "", type=str)
    if not date_from and not date_to:
        date_from, date_to = default_report_date_range(365)
    customer_id = request.args.get("customer", type=int)
    seller_id = request.args.get("seller", type=int)

    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)

    sales_list = ReportsQueryService.fetch_sales_report(
        tenant_id,
        scoped_branch_id,
        date_from,
        date_to,
        customer_id,
        seller_id,
        seller_user_id=current_user.id if current_user.is_seller() else None,
    )

    total_sales = Decimal("0")
    total_paid = Decimal("0")
    total_due = Decimal("0")

    for sale in sales_list:
        confirmed_paid = ReportsQueryService.get_confirmed_sale_paid_aed(sale.id, tenant_id, scoped_branch_id)
        sale._confirmed_paid = confirmed_paid
        total_sales += sale.amount_aed or Decimal("0")
        total_paid += confirmed_paid
        total_due += (sale.amount_aed or Decimal("0")) - confirmed_paid

    total_profit = Decimal("0")
    if current_user.can_see_costs():
        for sale in sales_list:
            total_profit += sale.get_profit() or Decimal("0")

    summary = {
        "sales_count": len(sales_list),
        "total_sales_aed": float(total_sales),
        "total_paid_aed": float(total_paid),
        "total_pending_aed": float(total_due),
        "total_profit": float(total_profit) if current_user.can_see_costs() else None,
    }

    customers = ReportsQueryService.fetch_report_customers(tenant_id, scoped_branch_id)

    sellers = [current_user] if current_user.is_seller() else ReportsQueryService.fetch_report_sellers(scoped_branch_id)

    return render_template(
        "reports/sales.html",
        sales=sales_list,
        summary=summary,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        seller_id=seller_id,
        customers=customers,
        sellers=sellers,
    )


@reports_bp.route("/sales/export")
@login_required
@permission_required("view_reports")
def sales_export():
    from flask import send_file

    from services.export_service import ExportService

    fmt = (request.args.get("format") or "csv").strip().lower()
    date_from = request.args.get("date_from", "", type=str)
    date_to = request.args.get("date_to", "", type=str)
    if not date_from and not date_to:
        from utils.gl_tenant import default_report_date_range

        date_from, date_to = default_report_date_range(365)
    customer_id = request.args.get("customer", type=int)
    seller_id = request.args.get("seller", type=int)

    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)

    sales_list = ReportsQueryService.fetch_sales_report(
        tenant_id,
        scoped_branch_id,
        date_from,
        date_to,
        customer_id,
        seller_id,
        seller_user_id=current_user.id if current_user.is_seller() else None,
    )

    headers = [
        gettext("رقم الفاتورة"),
        gettext("تاريخ الفاتورة"),
        gettext("الزبون"),
        gettext("البائع"),
        gettext("الفرع"),
        gettext("المستودع"),
        gettext("العملة"),
        gettext("سعر الصرف"),
        gettext("إجمالي"),
        gettext("مدفوع"),
        gettext("المتبقي"),
        gettext("حالة الدفع"),
    ]

    data = []
    for s in sales_list:
        total_aed = Decimal(str(s.amount_aed or 0))
        paid_aed = Decimal(str(ReportsQueryService.get_confirmed_sale_paid_aed(s.id, tenant_id, scoped_branch_id) or 0))
        due_aed = total_aed - paid_aed
        data.append(
            [
                s.sale_number,
                s.sale_date.strftime("%Y-%m-%d") if s.sale_date else "",
                s.customer.name if s.customer else "",
                s.seller.get_display_name() if s.seller else "",
                (s.branch.name if s.branch else ""),
                ((s.warehouse.name_ar or s.warehouse.name) if getattr(s, "warehouse", None) else ""),
                s.currency or "",
                float(s.exchange_rate or 1),
                float(total_aed),
                float(paid_aed),
                float(due_aed),
                s.payment_status or "",
            ]
        )

    base_name = f"sales_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == "xlsx":
        output = ExportService.export_to_xlsx(data, headers, filename=f"{base_name}.xlsx", sheet_name="Sales")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{base_name}.xlsx",
        )

    output = ExportService.export_to_csv(data, headers, filename=f"{base_name}.csv")
    return send_file(
        output,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"{base_name}.csv",
    )


@reports_bp.route("/purchases")
@login_required
@permission_required("view_reports")
def purchases():
    if current_user.is_seller():
        return render_template("errors/403.html"), 403

    from decimal import Decimal

    from utils.gl_tenant import default_report_date_range

    date_from = request.args.get("start_date", "", type=str)
    date_to = request.args.get("end_date", "", type=str)
    if not date_from and not date_to:
        date_from, date_to = default_report_date_range(365)
    supplier_id = request.args.get("supplier_id", type=int)

    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)

    purchases_list = ReportsQueryService.fetch_purchases_report(
        tenant_id, scoped_branch_id, date_from, date_to, supplier_id
    )

    total_amount = Decimal("0")
    total_paid = Decimal("0")
    total_due = Decimal("0")

    # Calculate purchase-level confirmed payments (FIFO allocation)

    supplier_payments, remaining_payments = ReportsQueryService.fetch_purchases_payments(
        tenant_id, scoped_branch_id, date_from, date_to, supplier_id
    )

    for p in purchases_list:
        amount = p.amount_aed or Decimal("0")
        total_amount += amount

        sid = p.supplier_id
        allocated = Decimal("0")
        if sid and sid in remaining_payments and remaining_payments[sid] > 0:
            allocated = min(amount, remaining_payments[sid])
            remaining_payments[sid] -= allocated

        p.paid_amount = allocated
        p.balance_due = amount - allocated
        total_paid += allocated
        total_due += p.balance_due

    stats = {
        "total_purchases": len(purchases_list),
        "total_amount": float(total_amount),
        "total_paid": float(total_paid),
        "total_due": float(total_due),
    }

    # Get suppliers for filter within the active branch scope only
    suppliers = ReportsQueryService.list_active_suppliers_for_filter()

    return render_template(
        "reports/purchases.html",
        purchases=purchases_list,
        stats=stats,
        suppliers=suppliers,
        start_date=date_from,
        end_date=date_to,
        supplier_id=supplier_id,
    )


@reports_bp.route("/purchases/export")
@login_required
@permission_required("view_reports")
def purchases_export():
    from flask import send_file

    from services.export_service import ExportService

    if current_user.is_seller():
        return render_template("errors/403.html"), 403

    fmt = (request.args.get("format") or "csv").strip().lower()
    from utils.gl_tenant import default_report_date_range

    date_from = request.args.get("start_date", "", type=str)
    date_to = request.args.get("end_date", "", type=str)
    if not date_from and not date_to:
        date_from, date_to = default_report_date_range(365)
    supplier_id = request.args.get("supplier_id", type=int)

    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)

    purchases_list = ReportsQueryService.fetch_purchases_report(
        tenant_id, scoped_branch_id, date_from, date_to, supplier_id
    )

    headers = [
        gettext("رقم الفاتورة"),
        gettext("تاريخ الفاتورة"),
        gettext("المورد"),
        gettext("الفرع"),
        gettext("المستودع"),
        gettext("العملة"),
        gettext("سعر الصرف"),
        gettext("الإجمالي"),
        gettext("الإجمالي (عملة الفاتورة)"),
        gettext("الحالة"),
    ]

    data = []
    for p in purchases_list:
        data.append(
            [
                p.purchase_number,
                p.purchase_date.strftime("%Y-%m-%d") if p.purchase_date else "",
                p.supplier.name if p.supplier else "",
                (p.branch.name if p.branch else ""),
                ((p.warehouse.name_ar or p.warehouse.name) if getattr(p, "warehouse", None) else ""),
                p.currency or "",
                float(p.exchange_rate or 1),
                float(Decimal(str(p.amount_aed or 0))),
                float(Decimal(str(p.total_amount or 0))),
                p.status or "",
            ]
        )

    base_name = f"purchases_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == "xlsx":
        output = ExportService.export_to_xlsx(data, headers, filename=f"{base_name}.xlsx", sheet_name="Purchases")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{base_name}.xlsx",
        )

    output = ExportService.export_to_csv(data, headers, filename=f"{base_name}.csv")
    return send_file(
        output,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"{base_name}.csv",
    )


@reports_bp.route("/ar-reconciliation")
@login_required
@permission_required("view_reports")
def ar_reconciliation():
    from services.ar_reconciliation_service import ARReconciliationService
    from utils.branching import get_accessible_branches, user_can_access_branch

    branch_id = request.args.get("branch_id", type=int)
    scoped_branch_id = report_branch_scope_id()
    if branch_id is None:
        branch_id = scoped_branch_id
    elif (
        scoped_branch_id is not None
        and branch_id != scoped_branch_id
        or scoped_branch_id is None
        and branch_id is not None
        and not user_can_access_branch(branch_id, current_user)
    ):
        return render_template("errors/403.html"), 403

    tenant_id = get_active_tenant_id(current_user)
    report = ARReconciliationService.build_report(tenant_id=tenant_id, branch_id=branch_id)
    branches = get_accessible_branches(current_user)
    return render_template(
        "reports/ar_reconciliation.html",
        report=report,
        branches=branches,
        selected_branch=branch_id,
    )


@reports_bp.route("/inventory-reconciliation")
@login_required
@permission_required("view_reports")
def inventory_reconciliation():
    from services.inventory_reconciliation_service import InventoryReconciliationService
    from utils.branching import (
        get_accessible_branches,
        user_can_access_branch,
    )

    branch_id = request.args.get("branch_id", type=int)
    warehouse_id = request.args.get("warehouse_id", type=int)
    date_from = request.args.get("date_from", type=str)
    date_to = request.args.get("date_to", type=str)
    scoped_branch_id = report_branch_scope_id()

    if branch_id is None:
        branch_id = scoped_branch_id
    elif (
        scoped_branch_id is not None
        and branch_id != scoped_branch_id
        or scoped_branch_id is None
        and branch_id is not None
        and not user_can_access_branch(branch_id, current_user)
    ):
        return render_template("errors/403.html"), 403

    tenant_id = get_active_tenant_id(current_user)

    warehouses = ReportsQueryService.fetch_inventory_reconciliation_warehouses(branch_id, current_user)

    if warehouse_id is not None and warehouse_id not in {w.id for w in warehouses}:
        return render_template("errors/403.html"), 403

    report = InventoryReconciliationService.build_warehouse_summary(
        tenant_id=tenant_id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        date_from=date_from,
        date_to=date_to,
    )
    branches = get_accessible_branches(current_user)
    return render_template(
        "reports/inventory_reconciliation.html",
        report=report,
        branches=branches,
        warehouses=warehouses,
        selected_branch=branch_id,
        selected_warehouse=warehouse_id,
        date_from=date_from,
        date_to=date_to,
    )


@reports_bp.route("/inventory-reconciliation/export")
@login_required
@permission_required("view_reports")
def inventory_reconciliation_export():
    from flask import send_file

    from models import Warehouse as WarehouseModel
    from services.export_service import ExportService
    from services.inventory_reconciliation_service import InventoryReconciliationService
    from utils.branching import get_accessible_warehouse_ids, user_can_access_branch

    fmt = (request.args.get("format") or "xlsx").strip().lower()
    branch_id = request.args.get("branch_id", type=int)
    warehouse_id = request.args.get("warehouse_id", type=int)
    date_from = request.args.get("date_from", type=str)
    date_to = request.args.get("date_to", type=str)
    scoped_branch_id = report_branch_scope_id()

    if branch_id is None:
        branch_id = scoped_branch_id
    elif (
        scoped_branch_id is not None
        and branch_id != scoped_branch_id
        or scoped_branch_id is None
        and branch_id is not None
        and not user_can_access_branch(branch_id, current_user)
    ):
        return render_template("errors/403.html"), 403

    tenant_id = get_active_tenant_id(current_user)
    if warehouse_id is not None:
        from utils.tenanting import tenant_get_or_404

        warehouse = tenant_get_or_404(WarehouseModel, warehouse_id)
        if not warehouse.is_active:
            return render_template("errors/403.html"), 403
        if branch_id is not None and warehouse.branch_id != branch_id:
            return render_template("errors/403.html"), 403

        accessible_ids = get_accessible_warehouse_ids(current_user)
        if warehouse_id not in accessible_ids and not current_user.is_admin():
            return render_template("errors/403.html"), 403

    report = InventoryReconciliationService.build_warehouse_summary(
        tenant_id=tenant_id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        date_from=date_from,
        date_to=date_to,
    )

    headers = [
        "tenant_id",
        "product_id",
        "product_name",
        "warehouse_id",
        "warehouse_name",
        "pwc_qty",
        "movement_qty",
        "qty_diff",
        "pwc_avg_cost",
        "pwc_value",
        "matched_qty",
    ]
    data = []
    for r in report["rows"]:
        data.append(
            [
                r["tenant_id"],
                r["product_id"],
                r["product_name"],
                r["warehouse_id"],
                r["warehouse_name"],
                r["pwc_qty"],
                r["movement_qty"],
                r["qty_diff"],
                r["pwc_avg_cost"],
                r["pwc_value"],
                "OK" if r["matched_qty"] else "REVIEW",
            ]
        )

    base_name = f"inventory_reconciliation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == "xlsx":
        output = ExportService.export_to_xlsx(data, headers, filename=f"{base_name}.xlsx", sheet_name="Inventory")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{base_name}.xlsx",
        )

    output = ExportService.export_to_csv(data, headers, filename=f"{base_name}.csv")
    return send_file(
        output,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"{base_name}.csv",
    )


@reports_bp.route("/receivables")
@login_required
@permission_required("view_reports")
def receivables():
    now = datetime.now(UTC)

    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)
    customer_id = request.args.get("customer", type=int)
    all_sales = ReportsQueryService.fetch_receivables_sales(tenant_id, scoped_branch_id, customer_id)

    all_sales = [
        sale for sale in all_sales if (sale.amount_aed or Decimal("0")) > (sale.paid_amount_aed or Decimal("0"))
    ]

    aging_data: dict[str, Any] = {
        "current": {"sales": [], "total": Decimal("0")},
        "days_30": {"sales": [], "total": Decimal("0")},
        "days_60": {"sales": [], "total": Decimal("0")},
        "days_90": {"sales": [], "total": Decimal("0")},
        "over_90": {"sales": [], "total": Decimal("0")},
    }

    for sale in all_sales:
        sale_date = sale.sale_date
        if sale_date.tzinfo is None:
            sale_date = sale_date.replace(tzinfo=UTC)
        days_old = (now - sale_date).days
        balance = (sale.amount_aed or Decimal("0")) - (sale.paid_amount_aed or Decimal("0"))

        sale.days_old = days_old
        sale.calculated_balance = balance

        if days_old <= 30:
            aging_data["current"]["sales"].append(sale)
            aging_data["current"]["total"] += balance
        elif days_old <= 60:
            aging_data["days_30"]["sales"].append(sale)
            aging_data["days_30"]["total"] += balance
        elif days_old <= 90:
            aging_data["days_60"]["sales"].append(sale)
            aging_data["days_60"]["total"] += balance
        elif days_old <= 120:
            aging_data["days_90"]["sales"].append(sale)
            aging_data["days_90"]["total"] += balance
        else:
            aging_data["over_90"]["sales"].append(sale)
            aging_data["over_90"]["total"] += balance

    total_receivables = sum(data["total"] for data in aging_data.values())

    summary = {
        "total_receivables": float(total_receivables),
        "current": float(aging_data["current"]["total"]),
        "days_30": float(aging_data["days_30"]["total"]),
        "days_60": float(aging_data["days_60"]["total"]),
        "days_90": float(aging_data["days_90"]["total"]),
        "over_90": float(aging_data["over_90"]["total"]),
    }

    customers = ReportsQueryService.fetch_report_customers(tenant_id, scoped_branch_id)

    return render_template(
        "reports/receivables.html",
        aging_data=aging_data,
        summary=summary,
        customers=customers,
        customer_id=customer_id,
    )


@reports_bp.route("/receivables/export")
@login_required
@permission_required("view_reports")
def receivables_export():
    from flask import send_file

    from services.export_service import ExportService

    fmt = (request.args.get("format") or "csv").strip().lower()
    customer_id = request.args.get("customer", type=int)

    now = datetime.now(UTC)
    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)
    all_sales = ReportsQueryService.fetch_receivables_sales(tenant_id, scoped_branch_id, customer_id)

    all_sales = [
        sale for sale in all_sales if (sale.amount_aed or Decimal("0")) > (sale.paid_amount_aed or Decimal("0"))
    ]

    def bucket_for(days_old: int) -> str:
        if days_old <= 30:
            return gettext("حالي (0-30)")
        if days_old <= 60:
            return "31-60"
        if days_old <= 90:
            return "61-90"
        if days_old <= 120:
            return "91-120"
        return "+120"

    headers = [
        gettext("الفئة"),
        gettext("رقم الفاتورة"),
        gettext("تاريخ الفاتورة"),
        gettext("العمر (يوم)"),
        gettext("الزبون"),
        gettext("الفرع"),
        gettext("العملة"),
        gettext("سعر الصرف"),
        gettext("الرصيد المستحق"),
    ]

    data = []
    for sale in all_sales:
        sale_date = sale.sale_date
        if sale_date and sale_date.tzinfo is None:
            sale_date = sale_date.replace(tzinfo=UTC)
        days_old = (now - sale_date).days if sale_date else 0
        balance = (sale.amount_aed or Decimal("0")) - (sale.paid_amount_aed or Decimal("0"))
        data.append(
            [
                bucket_for(days_old),
                sale.sale_number,
                sale.sale_date.strftime("%Y-%m-%d") if sale.sale_date else "",
                days_old,
                sale.customer.name if sale.customer else "",
                (sale.branch.name if sale.branch else ""),
                sale.currency or "",
                float(sale.exchange_rate or 1),
                float(Decimal(str(balance or 0))),
            ]
        )

    base_name = f"receivables_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == "xlsx":
        output = ExportService.export_to_xlsx(data, headers, filename=f"{base_name}.xlsx", sheet_name="Receivables")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{base_name}.xlsx",
        )

    output = ExportService.export_to_csv(data, headers, filename=f"{base_name}.csv")
    return send_file(
        output,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"{base_name}.csv",
    )


@reports_bp.route("/ap-aging")
@login_required
@permission_required("view_reports")
def ap_aging():
    """تقرير أعمار الذمم الدائنة (AP Aging)."""
    if current_user.is_seller():
        return render_template("errors/403.html"), 403

    as_of = request.args.get("as_of", "", type=str)
    supplier_id = request.args.get("supplier", type=int)

    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)

    report = ReportsQueryService.build_ap_aging_report(
        tenant_id, scoped_branch_id, as_of_date=as_of, supplier_id=supplier_id
    )
    suppliers = ReportsQueryService.list_active_suppliers_for_filter()

    return render_template(
        "reports/ap_aging.html",
        report=report,
        suppliers=suppliers,
        as_of=as_of,
        supplier_id=supplier_id,
    )


@reports_bp.route("/api/ap-aging")
@login_required
@permission_required("view_reports")
def api_ap_aging():
    """JSON envelope for the AP aging report."""
    if current_user.is_seller():
        return error_response(message=gettext("غير مصرح"), status_code=403)

    as_of = request.args.get("as_of", "", type=str)
    supplier_id = request.args.get("supplier", type=int)

    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)

    report = ReportsQueryService.build_ap_aging_report(
        tenant_id, scoped_branch_id, as_of_date=as_of, supplier_id=supplier_id
    )
    return success_response(data=report)


@reports_bp.route("/ap-aging/export")
@login_required
@permission_required("view_reports")
def ap_aging_export():
    """Download the AP aging report as a real PDF."""
    from flask import Response

    from services.print_service import PrintService

    if current_user.is_seller():
        return render_template("errors/403.html"), 403

    fmt = (request.args.get("format") or "pdf").strip().lower()
    if fmt != "pdf":
        return error_response(
            message=gettext("صيغة التصدير غير مدعومة لهذا التقرير"),
            status_code=400,
        )

    as_of = request.args.get("as_of", "", type=str)
    supplier_id = request.args.get("supplier", type=int)

    scoped_branch_id = report_branch_scope_id()
    tenant_id = get_active_tenant_id(current_user)

    report = ReportsQueryService.build_ap_aging_report(
        tenant_id, scoped_branch_id, as_of_date=as_of, supplier_id=supplier_id
    )

    context = {
        "title": gettext("تقرير أعمار الذمم الدائنة"),
        "report": report,
        "as_of": report["as_of"],
        "selected_branch": scoped_branch_id,
    }
    stamp = report["as_of"].replace("-", "")
    pdf_bytes = PrintService.render_pdf(
        "reports/ap_aging_pdf.html",
        extra_context=context,
        filename=f"ap_aging_{stamp}.pdf",
    )

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=ap_aging_{stamp}.pdf"},
    )


@reports_bp.route("/inventory")
@login_required
@permission_required("view_reports")
def inventory():
    from utils.branching import (
        get_accessible_branches,
        user_can_access_branch,
    )

    category_id = request.args.get("category", type=int)
    include_zero = (request.args.get("include_zero") or "").strip() in (
        "1",
        "true",
        "yes",
        "on",
    )
    warehouse_id = request.args.get("warehouse_id", type=int)
    in_date_from = (request.args.get("in_date_from") or "").strip()
    in_date_to = (request.args.get("in_date_to") or "").strip()
    out_date_from = (request.args.get("out_date_from") or "").strip()
    out_date_to = (request.args.get("out_date_to") or "").strip()

    branch_id = request.args.get("branch_id", type=int)
    scoped_branch_id = report_branch_scope_id()
    if branch_id is None:
        branch_id = scoped_branch_id
    elif (
        scoped_branch_id is not None
        and branch_id != scoped_branch_id
        or scoped_branch_id is None
        and branch_id is not None
        and not user_can_access_branch(branch_id, current_user)
    ):
        return render_template("errors/403.html"), 403

    tenant_id = get_active_tenant_id(current_user)

    warehouses = ReportsQueryService.fetch_inventory_warehouses(tenant_id, branch_id, current_user, ordered=True)

    selected_warehouse = None
    if warehouse_id is not None:
        selected_warehouse = next((w for w in warehouses if w.id == warehouse_id), None)
        if not selected_warehouse and not current_user.is_admin():
            return render_template("errors/403.html"), 403
        if not selected_warehouse:
            selected_warehouse = ReportsQueryService.find_active_warehouse(warehouse_id)
            if not selected_warehouse:
                return render_template("errors/404.html"), 404
            if tenant_id is not None and selected_warehouse.tenant_id != tenant_id:
                return render_template("errors/403.html"), 403
            if branch_id is not None and selected_warehouse.branch_id != branch_id:
                return render_template("errors/403.html"), 403
            warehouses.append(selected_warehouse)

    if selected_warehouse:
        warehouse_ids = [selected_warehouse.id]
    elif warehouses:
        warehouse_ids = [w.id for w in warehouses]
    else:
        warehouse_ids = [-1]

    stock_map, in_map, out_map, sold_map = ReportsQueryService.build_stock_maps(
        warehouse_ids, tenant_id, in_date_from, in_date_to, out_date_from, out_date_to
    )

    products = ReportsQueryService.fetch_inventory_products(category_id, include_zero, stock_map)

    total_value = Decimal("0")
    total_items = Decimal("0")
    for p in products:
        qty = Decimal(str(stock_map.get(p.id) or 0))
        total_items += qty
        if current_user.can_see_costs():
            total_value += qty * (p.cost_price or Decimal("0"))

    summary = {
        "products_count": len(products),
        "total_items": float(total_items),
        "total_value": float(total_value) if current_user.can_see_costs() else None,
    }
    branches = get_accessible_branches(current_user)
    stats = None
    if products:

        def qty_for(p):
            return Decimal(str(stock_map.get(p.id) or 0))

        in_stock = sum(1 for p in products if qty_for(p) > 0)
        low = sum(1 for p in products if 0 < qty_for(p) <= (p.min_stock_alert or 0))
        out = sum(1 for p in products if qty_for(p) <= 0)
        stats = {
            "total_products": len(products),
            "in_stock": in_stock,
            "low_stock": low,
            "out_of_stock": out,
        }

    return render_template(
        "reports/inventory.html",
        products=products,
        summary=summary,
        branches=branches,
        selected_branch_id=branch_id,
        warehouses=warehouses,
        selected_warehouse_id=warehouse_id,
        stock_map=stock_map,
        in_map=in_map,
        out_map=out_map,
        sold_map=sold_map,
        stats=stats,
        category_id=category_id,
        include_zero=include_zero,
        in_date_from=in_date_from,
        in_date_to=in_date_to,
        out_date_from=out_date_from,
        out_date_to=out_date_to,
    )


@reports_bp.route("/inventory/export")
@login_required
@permission_required("view_reports")
def inventory_export():
    from flask import send_file

    from services.export_service import ExportService
    from utils.branching import user_can_access_branch

    fmt = (request.args.get("format") or "csv").strip().lower()
    category_id = request.args.get("category", type=int)
    include_zero = (request.args.get("include_zero") or "").strip() in (
        "1",
        "true",
        "yes",
        "on",
    )
    warehouse_id = request.args.get("warehouse_id", type=int)
    in_date_from = (request.args.get("in_date_from") or "").strip()
    in_date_to = (request.args.get("in_date_to") or "").strip()
    out_date_from = (request.args.get("out_date_from") or "").strip()
    out_date_to = (request.args.get("out_date_to") or "").strip()

    branch_id = request.args.get("branch_id", type=int)
    scoped_branch_id = report_branch_scope_id()
    if branch_id is None:
        branch_id = scoped_branch_id
    elif (
        scoped_branch_id is not None
        and branch_id != scoped_branch_id
        or scoped_branch_id is None
        and branch_id is not None
        and not user_can_access_branch(branch_id, current_user)
    ):
        return render_template("errors/403.html"), 403

    tenant_id = get_active_tenant_id(current_user)

    warehouses = ReportsQueryService.fetch_inventory_warehouses(tenant_id, branch_id, current_user, ordered=False)

    selected_warehouse = None
    if warehouse_id is not None:
        selected_warehouse = next((w for w in warehouses if w.id == warehouse_id), None)
        if not selected_warehouse and not current_user.is_admin():
            return render_template("errors/403.html"), 403
        if not selected_warehouse:
            selected_warehouse = ReportsQueryService.find_active_warehouse(warehouse_id)
            if not selected_warehouse:
                return render_template("errors/404.html"), 404
            if tenant_id is not None and selected_warehouse.tenant_id != tenant_id:
                return render_template("errors/403.html"), 403
            if branch_id is not None and selected_warehouse.branch_id != branch_id:
                return render_template("errors/403.html"), 403
            warehouses = [selected_warehouse]

    if selected_warehouse:
        warehouse_ids = [selected_warehouse.id]
        warehouse_label = selected_warehouse.name_ar or selected_warehouse.name
    elif warehouses:
        warehouse_ids = [w.id for w in warehouses]
        warehouse_label = gettext("متعدد")
    else:
        warehouse_ids = [-1]
        warehouse_label = ""

    stock_map, in_map, out_map, sold_map = ReportsQueryService.build_stock_maps(
        warehouse_ids, tenant_id, in_date_from, in_date_to, out_date_from, out_date_to
    )

    products = ReportsQueryService.fetch_inventory_products(category_id, include_zero, stock_map)

    headers = [
        gettext("المنتج"),
        "SKU",
        "Barcode",
        gettext("المستودع"),
        gettext("الكمية المتاحة"),
        gettext("إدخال (حسب التاريخ)"),
        gettext("إخراج (حسب التاريخ)"),
        gettext("مباع (حسب التاريخ)"),
        gettext("سعر التكلفة"),
        gettext("سعر البيع"),
        gettext("قيمة المخزون (تكلفة)"),
    ]

    data = []
    for p in products:
        qty = Decimal(str(stock_map.get(p.id) or 0))
        in_qty = Decimal(str(in_map.get(p.id) or 0))
        out_qty = Decimal(str(out_map.get(p.id) or 0))
        sold_qty = Decimal(str(sold_map.get(p.id) or 0))
        cost = p.cost_price or Decimal("0")
        total_cost_value = qty * cost if current_user.can_see_costs() else None
        data.append(
            [
                p.name,
                p.sku or "",
                getattr(p, "barcode", "") or "",
                warehouse_label,
                float(qty),
                float(in_qty),
                float(out_qty),
                float(sold_qty),
                float(cost) if current_user.can_see_costs() else "",
                float(p.regular_price or 0),
                float(total_cost_value or 0) if current_user.can_see_costs() else "",
            ]
        )

    base_name = f"inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == "xlsx":
        output = ExportService.export_to_xlsx(data, headers, filename=f"{base_name}.xlsx", sheet_name="Inventory")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{base_name}.xlsx",
        )

    output = ExportService.export_to_csv(data, headers, filename=f"{base_name}.csv")
    return send_file(
        output,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"{base_name}.csv",
    )


@reports_bp.route("/api/model_fields")
@login_required
@permission_required("view_reports")
def api_model_fields():
    """Return column names and date fields for a given model/table (for dynamic report builder)."""
    model = (request.args.get("model") or "").strip()
    columns = []
    date_fields = []
    if model:
        model_lower = model.lower()
        if model_lower in ("sale", "sales"):
            columns = [
                "id",
                "sale_number",
                "sale_date",
                "customer_id",
                "total",
                "status",
                "branch_id",
                "created_at",
            ]
            date_fields = ["sale_date", "created_at"]
        elif model_lower in ("purchase", "purchases"):
            columns = [
                "id",
                "purchase_number",
                "purchase_date",
                "supplier_id",
                "total",
                "status",
                "branch_id",
                "created_at",
            ]
            date_fields = ["purchase_date", "created_at"]
        elif model_lower in ("customer", "customers"):
            columns = [
                "id",
                "name",
                "phone",
                "email",
                "customer_type",
                "balance",
                "created_at",
            ]
            date_fields = ["created_at"]
        elif model_lower in ("product", "products"):
            columns = [
                "id",
                "name",
                "sku",
                "barcode",
                "regular_price",
                "cost_price",
                "current_stock",
                "created_at",
            ]
            date_fields = ["created_at"]
        elif model_lower in ("expense", "expenses"):
            columns = [
                "id",
                "expense_date",
                "amount",
                "category_id",
                "description",
                "branch_id",
                "created_at",
            ]
            date_fields = ["expense_date", "created_at"]
        else:
            date_fields = ["created_at", "date", "updated_at"]
    all_fields = list(columns) if columns else []
    return success_response(data={"columns": columns, "date_fields": date_fields, "all_fields": all_fields})


@reports_bp.route("/api/entity-search")
@login_required
@permission_required("view_reports")
def api_entity_search():
    query = request.args.get("q", "").strip()
    entity_type = request.args.get("type", "supplier")

    results = ReportsQueryService.search_entities(query, entity_type)

    return success_response(data=results)


@reports_bp.route("/entity_report_fragment/<entity_type>/<id>")
@login_required
@permission_required("view_reports")
def entity_report_fragment(entity_type, **kwargs):
    record_id = kwargs.pop("id")
    try:
        from models import Customer, Supplier

        scoped_branch_id = report_branch_scope_id()
        tenant_id = get_active_tenant_id(current_user)

        context: dict[str, Any] = {
            "entity": None,
            "type_label": "",
            "balance": 0,
            "balance_label": "",
            "products": [],
            "invoices": [],
            "transactions": [],
        }

        if entity_type == "supplier":
            entity = tenant_get_or_404(Supplier, record_id)
            if report_branch_scope_id() is not None and not ReportsQueryService.supplier_in_branch_scope(record_id):
                return render_template("errors/403.html"), 403
            context["entity"] = entity
            context["type_label"] = gettext("مورد")
            context.update(ReportsQueryService.build_supplier_fragment_data(record_id, tenant_id, scoped_branch_id))

        else:  # Customer/Partner/Merchant
            entity = tenant_get_or_404(Customer, record_id)
            if report_branch_scope_id() is not None and not ReportsQueryService.customer_in_branch_scope(record_id):
                return render_template("errors/403.html"), 403
            context["entity"] = entity
            context["type_label"] = {
                "partner": gettext("شريك"),
                "merchant": gettext("تاجر"),
                "regular": gettext("زبون"),
                "vip": "VIP",
            }.get(entity.customer_type, gettext("زبون"))
            context.update(
                ReportsQueryService.build_customer_fragment_data(
                    record_id, entity.customer_type, tenant_id, scoped_branch_id
                )
            )
        return render_template("reports/partials/entity_report.html", **context)

    except Exception as e:
        return render_template("reports/partials/entity_report.html", error=str(e))


@reports_bp.route("/top-selling")
@login_required
@permission_required("view_reports")
def top_selling():
    date_from = request.args.get("date_from", "", type=str)
    date_to = request.args.get("date_to", "", type=str)
    limit = request.args.get("limit", 20, type=int)
    tenant_id = get_active_tenant_id(current_user)
    scoped_branch_id = report_branch_scope_id()

    products = ReportsQueryService.fetch_top_selling_products(date_from, date_to, tenant_id, scoped_branch_id, limit)

    return render_template("reports/top_selling.html", products=products)
