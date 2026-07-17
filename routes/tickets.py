from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import TicketCategory, TicketPriority, Customer, User
from services.ticket_service import TicketService
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id

tickets_bp = Blueprint("tickets", __name__, url_prefix="/tickets")


def _tenant_categories(tid):
    q = TicketCategory.query.filter(TicketCategory.is_active)
    if tid is not None:
        q = q.filter(TicketCategory.tenant_id == tid)
    return q.all()


def _tenant_priorities(tid):
    q = TicketPriority.query.filter(TicketPriority.is_active)
    if tid is not None:
        q = q.filter(TicketPriority.tenant_id == tid)
    return q.all()


def _tenant_customers(tid):
    q = Customer.query.filter(Customer.is_active)
    if tid is not None:
        q = q.filter(Customer.tenant_id == tid)
    return q.order_by(Customer.name).all()


@tickets_bp.route("/")
@login_required
@permission_required("support.view")
def list_tickets():
    filters = {k: v for k, v in request.args.items() if v}
    tickets = TicketService.search_tickets(filters, current_user)
    tid = get_active_tenant_id(current_user)
    categories = _tenant_categories(tid)
    priorities = _tenant_priorities(tid)
    users = (
        User.query.filter(User.tenant_id == tid, User.is_active)
        .order_by(User.full_name)
        .all()
        if tid
        else []
    )
    statuses = ["open", "waiting", "resolved", "closed"]
    return render_template(
        "tickets/list.html",
        tickets=tickets,
        categories=categories,
        priorities=priorities,
        users=users,
        statuses=statuses,
    )


@tickets_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("support.manage")
def create_ticket():
    if request.method == "POST":
        try:
            TicketService.create_ticket(request.form, current_user)
            flash("تم إنشاء التذكرة بنجاح", "success")
            return redirect(url_for("tickets.list_tickets"))
        except Exception as e:
            flash(f"حدث خطأ: {e}", "danger")
    tid = get_active_tenant_id(current_user)
    categories = _tenant_categories(tid)
    priorities = _tenant_priorities(tid)
    customers = _tenant_customers(tid)
    users = (
        User.query.filter(User.tenant_id == tid, User.is_active)
        .order_by(User.full_name)
        .all()
        if tid
        else []
    )
    return render_template(
        "tickets/detail.html",
        categories=categories,
        priorities=priorities,
        customers=customers,
        users=users,
    )


@tickets_bp.route("/<int:ticket_id>")
@login_required
@permission_required("support.view")
def ticket_detail(ticket_id):
    try:
        ticket = TicketService.get_ticket(ticket_id, current_user)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("tickets.list_tickets"))
    tid = get_active_tenant_id(current_user)
    categories = _tenant_categories(tid)
    priorities = _tenant_priorities(tid)
    users = (
        User.query.filter(User.tenant_id == tid, User.is_active)
        .order_by(User.full_name)
        .all()
        if tid
        else []
    )
    return render_template(
        "tickets/detail.html",
        ticket=ticket,
        categories=categories,
        priorities=priorities,
        users=users,
    )


@tickets_bp.route("/<int:ticket_id>/comment", methods=["POST"])
@login_required
@permission_required("support.manage")
def add_comment(ticket_id):
    try:
        TicketService.add_comment(ticket_id, request.form, current_user)
        flash("تم إضافة التعليق", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket_id))


@tickets_bp.route("/<int:ticket_id>/assign", methods=["POST"])
@login_required
@permission_required("support.manage")
def assign_ticket(ticket_id):
    user_id = request.form.get("assigned_user_id")
    try:
        TicketService.assign_ticket(ticket_id, user_id, current_user)
        flash("تم تعيين التذكرة", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket_id))


@tickets_bp.route("/<int:ticket_id>/resolve", methods=["POST"])
@login_required
@permission_required("support.manage")
def resolve_ticket(ticket_id):
    try:
        TicketService.resolve_ticket(ticket_id, current_user)
        flash("تم حل التذكرة", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket_id))


@tickets_bp.route("/<int:ticket_id>/close", methods=["POST"])
@login_required
@permission_required("support.manage")
def close_ticket(ticket_id):
    try:
        TicketService.close_ticket(ticket_id, current_user)
        flash("تم إغلاق التذكرة", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket_id))


@tickets_bp.route("/<int:ticket_id>/reopen", methods=["POST"])
@login_required
@permission_required("support.manage")
def reopen_ticket(ticket_id):
    try:
        TicketService.reopen_ticket(ticket_id, current_user)
        flash("تم إعادة فتح التذكرة", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket_id))
