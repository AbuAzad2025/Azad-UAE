from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import login_required

from services.budget_service import BudgetService
from utils.decorators import permission_required

budget_bp = Blueprint("budget", __name__, url_prefix="/budgets")


@budget_bp.route("/")
@login_required
@permission_required("view_ledger")
def index():
    filters = {k: v for k, v in request.args.items() if v}
    budgets = BudgetService.list_budgets(None, filters)
    return render_template("financials/budget/index.html", budgets=budgets)


@budget_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("budget:create")
def create():
    if request.method == "POST":
        try:
            data = _parse_budget_form(request.form)
            budget = BudgetService.create_budget(data, None)
            flash(gettext("تم إنشاء الميزانية"), "success")
            return redirect(url_for("budget.detail", budget_id=budget.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
    return render_template("financials/budget/form.html", budget=None)


@budget_bp.route("/<int:budget_id>")
@login_required
@permission_required("view_ledger")
def detail(budget_id):
    budget = BudgetService.get_budget(budget_id, None)
    return render_template("financials/budget/detail.html", budget=budget)


@budget_bp.route("/<int:budget_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("budget:create")
def edit(budget_id):
    budget = BudgetService.get_budget(budget_id, None)
    if request.method == "POST":
        try:
            data = _parse_budget_form(request.form)
            BudgetService.update_budget(budget, data)
            flash(gettext("تم تحديث الميزانية"), "success")
            return redirect(url_for("budget.detail", budget_id=budget.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
    return render_template("financials/budget/form.html", budget=budget)


@budget_bp.route("/<int:budget_id>/approve", methods=["POST"])
@login_required
@permission_required("budget:approve")
def approve(budget_id):
    budget = BudgetService.get_budget(budget_id, None)
    try:
        BudgetService.approve_budget(budget, None)
        flash(gettext("تمت الموافقة على الميزانية"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("budget.detail", budget_id=budget.id))


@budget_bp.route("/<int:budget_id>/activate", methods=["POST"])
@login_required
@permission_required("budget:approve")
def activate(budget_id):
    budget = BudgetService.get_budget(budget_id, None)
    try:
        BudgetService.activate_budget(budget)
        flash(gettext("تم تنشيط الميزانية"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("budget.detail", budget_id=budget.id))


@budget_bp.route("/<int:budget_id>/close", methods=["POST"])
@login_required
@permission_required("budget:approve")
def close(budget_id):
    budget = BudgetService.get_budget(budget_id, None)
    try:
        BudgetService.close_budget(budget)
        flash(gettext("تم إغلاق الميزانية"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("budget.detail", budget_id=budget.id))


@budget_bp.route("/<int:budget_id>/delete", methods=["POST"])
@login_required
@permission_required("budget:create")
def delete(budget_id):
    budget = BudgetService.get_budget(budget_id, None)
    try:
        BudgetService.delete_budget(budget)
        flash(gettext("تم حذف الميزانية"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("budget.index"))


@budget_bp.route("/<int:budget_id>/variance")
@login_required
@permission_required("view_ledger")
def variance(budget_id):
    report = BudgetService.variance_report(budget_id, None)
    return render_template("financials/budget/variance.html", report=report)


@budget_bp.route("/api/create", methods=["POST"])
@login_required
@permission_required("budget:create")
def api_create():
    data = request.get_json(silent=True) or {}
    try:
        budget = BudgetService.create_budget(data, None)
        return jsonify({"ok": True, "id": budget.id, "budget_number": budget.budget_number})
    except (ValueError, KeyError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400


def _parse_budget_form(form):
    lines = []
    line_index = 0
    while True:
        code = form.get(f"line_{line_index}_account_code")
        amount = form.get(f"line_{line_index}_budgeted_amount")
        if code is None or code == "":
            break
        lines.append(
            {
                "account_code": code,
                "budgeted_amount": amount or "0",
                "notes": form.get(f"line_{line_index}_notes", ""),
            }
        )
        line_index += 1

    return {
        "name_ar": form.get("name_ar", ""),
        "name_en": form.get("name_en"),
        "fiscal_year": form.get("fiscal_year", date.today().year),
        "period_type": form.get("period_type", "annual"),
        "period_start": form.get("period_start", date.today().isoformat()),
        "period_end": form.get("period_end", date.today().isoformat()),
        "enforcement": form.get("enforcement", "warn"),
        "branch_id": form.get("branch_id"),
        "notes": form.get("notes"),
        "lines": lines,
    }
