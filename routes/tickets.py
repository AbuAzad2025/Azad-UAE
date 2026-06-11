from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Ticket, TicketCategory, TicketPriority, TicketComment, Customer, User
from services.ticket_service import TicketService
from utils.decorators import permission_required, branch_scope_id
from utils.tenanting import get_active_tenant_id

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')


@tickets_bp.route('/')
@login_required
@permission_required('support.view')
def list_tickets():
    filters = {k: v for k, v in request.args.items() if v}
    tickets = TicketService.search_tickets(filters, current_user)
    categories = TicketCategory.query.filter_by(is_active=True).all()
    priorities = TicketPriority.query.filter_by(is_active=True).all()
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    statuses = ['open', 'waiting', 'resolved', 'closed']
    return render_template(
        'tickets/list.html',
        tickets=tickets,
        categories=categories,
        priorities=priorities,
        users=users,
        statuses=statuses,
    )


@tickets_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('support.manage')
def create_ticket():
    if request.method == 'POST':
        try:
            TicketService.create_ticket(request.form, current_user)
            flash('تم إنشاء التذكرة بنجاح', 'success')
            return redirect(url_for('tickets.list_tickets'))
        except Exception as e:
            flash(f'حدث خطأ: {e}', 'danger')
    categories = TicketCategory.query.filter_by(is_active=True).all()
    priorities = TicketPriority.query.filter_by(is_active=True).all()
    customers = Customer.query.filter_by(is_active=True).order_by(Customer.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template(
        'tickets/detail.html',
        categories=categories,
        priorities=priorities,
        customers=customers,
        users=users,
    )


@tickets_bp.route('/<int:ticket_id>')
@login_required
@permission_required('support.view')
def ticket_detail(ticket_id):
    try:
        ticket = TicketService.get_ticket(ticket_id, current_user)
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('tickets.list_tickets'))
    categories = TicketCategory.query.filter_by(is_active=True).all()
    priorities = TicketPriority.query.filter_by(is_active=True).all()
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template(
        'tickets/detail.html',
        ticket=ticket,
        categories=categories,
        priorities=priorities,
        users=users,
    )


@tickets_bp.route('/<int:ticket_id>/comment', methods=['POST'])
@login_required
@permission_required('support.manage')
def add_comment(ticket_id):
    try:
        TicketService.add_comment(ticket_id, request.form, current_user)
        flash('تم إضافة التعليق', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/<int:ticket_id>/assign', methods=['POST'])
@login_required
@permission_required('support.manage')
def assign_ticket(ticket_id):
    user_id = request.form.get('assigned_user_id')
    try:
        TicketService.assign_ticket(ticket_id, user_id, current_user)
        flash('تم تعيين التذكرة', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/<int:ticket_id>/resolve', methods=['POST'])
@login_required
@permission_required('support.manage')
def resolve_ticket(ticket_id):
    try:
        TicketService.resolve_ticket(ticket_id, current_user)
        flash('تم حل التذكرة', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/<int:ticket_id>/close', methods=['POST'])
@login_required
@permission_required('support.manage')
def close_ticket(ticket_id):
    try:
        TicketService.close_ticket(ticket_id, current_user)
        flash('تم إغلاق التذكرة', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/<int:ticket_id>/reopen', methods=['POST'])
@login_required
@permission_required('support.manage')
def reopen_ticket(ticket_id):
    try:
        TicketService.reopen_ticket(ticket_id, current_user)
        flash('تم إعادة فتح التذكرة', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
