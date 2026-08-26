from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import current_user, login_required

from services.transfer_service import TransferService
from utils.db_safety import atomic_transaction
from utils.decorators import permission_required

transfers_bp = Blueprint("transfers", __name__, url_prefix="/transfers")


@transfers_bp.route("/")
@login_required
@permission_required("manage_warehouse")
def index():
    filters = {k: v for k, v in request.args.items() if v}
    transfers = TransferService.list_transfers(None, filters)
    return render_template("warehouse/transfers.html", transfers=transfers)


@transfers_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_warehouse")
def create():
    if request.method == "POST":
        try:
            data = _parse_transfer_form(request.form)
            with atomic_transaction("transfer_create"):
                t = TransferService.create_transfer(data, current_user)
            flash(gettext("تم إنشاء طلب النقل"), "success")
            return redirect(url_for("transfers.detail", transfer_id=t.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
    return render_template("warehouse/transfer_form.html", transfer=None)


@transfers_bp.route("/<int:transfer_id>")
@login_required
@permission_required("manage_warehouse")
def detail(transfer_id):
    t = TransferService.get_transfer(transfer_id, None)
    return render_template("warehouse/transfer_detail.html", transfer=t)


@transfers_bp.route("/<int:transfer_id>/approve", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def approve(transfer_id):
    t = TransferService.get_transfer(transfer_id, None)
    try:
        with atomic_transaction("transfer_approve"):
            TransferService.approve_transfer(t, current_user)
        flash(gettext("تمت الموافقة على النقل"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("transfers.detail", transfer_id=t.id))


@transfers_bp.route("/<int:transfer_id>/ship", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def ship(transfer_id):
    t = TransferService.get_transfer(transfer_id, None)
    try:
        with atomic_transaction("transfer_ship"):
            TransferService.ship_transfer(t)
        flash(gettext("تم شحن النقل"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("transfers.detail", transfer_id=t.id))


@transfers_bp.route("/<int:transfer_id>/receive", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def receive(transfer_id):
    t = TransferService.get_transfer(transfer_id, None)
    try:
        with atomic_transaction("transfer_receive_complete"):
            TransferService.confirm_receive(t, current_user)
            TransferService.complete_transfer(t, current_user)
        flash(gettext("تم استلام وإتمام النقل"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("transfers.detail", transfer_id=t.id))


@transfers_bp.route("/<int:transfer_id>/cancel", methods=["POST"])
@login_required
@permission_required("manage_warehouse")
def cancel(transfer_id):
    t = TransferService.get_transfer(transfer_id, None)
    try:
        with atomic_transaction("transfer_cancel"):
            TransferService.cancel_transfer(t)
        flash(gettext("تم إلغاء النقل"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("transfers.detail", transfer_id=t.id))


def _parse_transfer_form(form):
    lines = []
    idx = 0
    while f"lines-{idx}-product_id" in form:
        lines.append(
            {
                "product_id": form.get(f"lines-{idx}-product_id"),
                "quantity": form.get(f"lines-{idx}-quantity", 0),
                "notes": form.get(f"lines-{idx}-notes", ""),
                "sort_order": idx,
            }
        )
        idx += 1

    return {
        "from_warehouse_id": form.get("from_warehouse_id"),
        "to_warehouse_id": form.get("to_warehouse_id"),
        "branch_id": form.get("branch_id") or None,
        "notes": form.get("notes"),
        "lines": lines,
    }
