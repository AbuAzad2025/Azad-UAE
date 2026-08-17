"""
Treasury Routes - مسارات المركز المالي والخزينة
Phase 8: Treasury & Cash Position Reporting
"""

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import db
from utils.branching import get_accessible_branches, user_can_access_branch
from utils.decorators import permission_required, report_branch_scope_id
from utils.tenanting import get_active_tenant_id

treasury_bp = Blueprint("treasury", __name__, url_prefix="/reports")


@treasury_bp.route("/treasury")
@login_required
@permission_required("view_reports")
def treasury():
    from services.treasury_service import TreasuryService

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
    report = TreasuryService.build_dashboard(
        tenant_id=tenant_id,
        branch_id=branch_id,
    )
    branches = get_accessible_branches(current_user)
    return render_template(
        "reports/treasury.html",
        report=report,
        branches=branches,
        selected_branch=branch_id,
    )


@treasury_bp.route("/treasury/export")
@login_required
@permission_required("view_reports")
def treasury_export():
    from services.export_service import ExportService
    from services.treasury_service import TreasuryService

    fmt = (request.args.get("format") or "xlsx").strip().lower()
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
    report = TreasuryService.build_dashboard(
        tenant_id=tenant_id,
        branch_id=branch_id,
    )

    headers = ["kind", "code", "name", "currency", "balance_aed", "source"]
    data = []
    for a in report["liquidity"]["accounts"]:
        data.append(
            [
                a["kind_label"],
                a["code"],
                a["name"],
                a["currency"],
                a["balance_aed"],
                a["source"],
            ]
        )

    base_name = f"treasury_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == "xlsx":
        output = ExportService.export_to_xlsx(data, headers, filename=f"{base_name}.xlsx", sheet_name="Treasury")
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


@treasury_bp.route("/vat-return")
@login_required
@permission_required("view_reports")
def vat_return():
    from services.tax_service import TaxService

    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    tenant_id = get_active_tenant_id(current_user)
    report = TaxService.get_vat_return(date_from, date_to, tenant_id)
    return render_template("reports/vat_return.html", report=report)


@treasury_bp.route("/wps-export")
@login_required
@permission_required("view_reports")
def wps_export():
    from flask import Response

    from utils.localization import get_strategy
    from utils.tenanting import tenant_query

    tenant_id = get_active_tenant_id(current_user)
    if not tenant_id:
        flash(gettext("يجب تحديد الشركة أولاً."), "warning")
        return redirect(url_for("treasury.treasury"))

    from models import PayrollTransaction, Tenant

    tenant = db.session.get(Tenant, tenant_id) if tenant_id else None
    country = (getattr(tenant, "vat_country", None) or "AE").strip().upper()
    strategy = get_strategy(country)

    if not strategy.supports_wps:
        return (
            render_template("errors/403.html", message=gettext("WPS غير متاح لهذه الدولة")),
            403,
        )

    month = request.args.get("month", type=int) or datetime.now().month
    year = request.args.get("year", type=int) or datetime.now().year

    from models import Employee

    employees = (
        tenant_query(Employee)
        .filter(
            Employee.is_active.is_(True),
            Employee.bank_code.isnot(None),
            Employee.iban.isnot(None),
        )
        .all()
    )

    if not employees:
        flash(gettext("لا يوجد موظفين مرتبطين بحسابات بنكية."), "warning")
        return redirect(url_for("treasury.treasury"))

    employee_data = []
    for emp in employees:
        txn = PayrollTransaction.query.filter_by(
            tenant_id=tenant_id,
            employee_id=emp.id,
            month=month,
            year=year,
        ).first()
        if not txn:
            continue
        employee_data.append(
            {
                "wps_id": f"{emp.id:08d}",
                "employee_id": emp.id,
                "name": emp.name,
                "iban": emp.iban,
                "bank_code": emp.bank_code,
                "basic_salary": str(txn.basic_amount),
                "allowances": str(txn.allowances),
                "net_salary": str(txn.net_salary),
                "currency": emp.currency or "AED",
                "payment_date": txn.payment_date.isoformat() if txn.payment_date else "",
            }
        )

    if not employee_data:
        flash(gettext("لا توجد معاملات رواتب لهذا الشهر."), "warning")
        return redirect(url_for("treasury.treasury"))

    result = strategy.get_wps_format(employee_data)
    lines = result.get("content", "\n".join(result["lines"]))
    filename = f"wps_sif_{year}_{month:02d}.csv"
    return Response(
        lines,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
