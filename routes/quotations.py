from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import current_user, login_required

from services.quotation_service import QuotationService
from utils.db_safety import atomic_transaction
from utils.decorators import permission_required

quotations_bp = Blueprint("quotations", __name__, url_prefix="/quotations")


@quotations_bp.route("/")
@login_required
@permission_required("manage_sales")
def index():
    filters = {k: v for k, v in request.args.items() if v}
    quotations = QuotationService.list_quotations(None, filters)
    return render_template("quotations/index.html", quotations=quotations)


@quotations_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_sales")
def create():
    if request.method == "POST":
        try:
            data = _parse_quotation_form(request.form)
            with atomic_transaction("quotation_create"):
                q = QuotationService.create_quotation(data, current_user)
            flash(gettext("تم إنشاء عرض السعر"), "success")
            return redirect(url_for("quotations.detail", quotation_id=q.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
    return render_template("quotations/form.html", quotation=None)


@quotations_bp.route("/<int:quotation_id>")
@login_required
@permission_required("manage_sales")
def detail(quotation_id):
    q = QuotationService.get_quotation(quotation_id, None)
    return render_template("quotations/detail.html", quotation=q)


@quotations_bp.route("/<int:quotation_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("manage_sales")
def edit(quotation_id):
    q = QuotationService.get_quotation(quotation_id, None)
    if request.method == "POST":
        try:
            data = _parse_quotation_form(request.form)
            with atomic_transaction("quotation_update"):
                QuotationService.update_quotation(q, data)
            flash(gettext("تم تحديث عرض السعر"), "success")
            return redirect(url_for("quotations.detail", quotation_id=q.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
    return render_template("quotations/form.html", quotation=q)


@quotations_bp.route("/<int:quotation_id>/send", methods=["POST"])
@login_required
@permission_required("manage_sales")
def send(quotation_id):
    q = QuotationService.get_quotation(quotation_id, None)
    try:
        with atomic_transaction("quotation_send"):
            QuotationService.send_quotation(q)
        flash(gettext("تم إرسال عرض السعر"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("quotations.detail", quotation_id=q.id))


@quotations_bp.route("/<int:quotation_id>/accept", methods=["POST"])
@login_required
@permission_required("manage_sales")
def accept(quotation_id):
    q = QuotationService.get_quotation(quotation_id, None)
    try:
        with atomic_transaction("quotation_accept"):
            QuotationService.accept_quotation(q)
        flash(gettext("تم قبول عرض السعر"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("quotations.detail", quotation_id=q.id))


@quotations_bp.route("/<int:quotation_id>/reject", methods=["POST"])
@login_required
@permission_required("manage_sales")
def reject(quotation_id):
    q = QuotationService.get_quotation(quotation_id, None)
    try:
        with atomic_transaction("quotation_reject"):
            QuotationService.reject_quotation(q)
        flash(gettext("تم رفض عرض السعر"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("quotations.detail", quotation_id=q.id))


@quotations_bp.route("/<int:quotation_id>/convert", methods=["POST"])
@login_required
@permission_required("manage_sales")
def convert(quotation_id):
    q = QuotationService.get_quotation(quotation_id, None)
    try:
        with atomic_transaction("quotation_convert_to_sale"):
            sale = QuotationService.convert_to_sale(q, current_user)
        flash(gettext("تم تحويل العرض إلى فاتورة"), "success")
        return redirect(url_for("sales.detail", id=sale.id))
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("quotations.detail", quotation_id=q.id))


@quotations_bp.route("/<int:quotation_id>/duplicate", methods=["POST"])
@login_required
@permission_required("manage_sales")
def duplicate(quotation_id):
    q = QuotationService.get_quotation(quotation_id, None)
    try:
        with atomic_transaction("quotation_duplicate"):
            new_q = QuotationService.duplicate_quotation(q, current_user)
        flash(gettext("تم نسخ عرض السعر"), "success")
        return redirect(url_for("quotations.detail", quotation_id=new_q.id))
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("quotations.detail", quotation_id=q.id))


def _parse_quotation_form(form):
    lines = []
    idx = 0
    while f"lines-{idx}-product_id" in form:
        lines.append(
            {
                "product_id": form.get(f"lines-{idx}-product_id"),
                "description": form.get(f"lines-{idx}-description", ""),
                "quantity": form.get(f"lines-{idx}-quantity", 1),
                "unit_price": form.get(f"lines-{idx}-unit_price", 0),
                "discount_percent": form.get(f"lines-{idx}-discount_percent", 0),
                "tax_rate": form.get(f"lines-{idx}-tax_rate", 0),
                "sort_order": idx,
            }
        )
        idx += 1

    return {
        "customer_id": form.get("customer_id"),
        "branch_id": form.get("branch_id") or None,
        "warehouse_id": form.get("warehouse_id") or None,
        "expiry_date": form.get("expiry_date") or None,
        "notes": form.get("notes"),
        "terms": form.get("terms"),
        "currency": form.get("currency", "AED"),
        "exchange_rate": form.get("exchange_rate", 1),
        "base_currency": form.get("base_currency", "AED"),
        "prices_include_vat": form.get("prices_include_vat"),
        "lines": lines,
    }
