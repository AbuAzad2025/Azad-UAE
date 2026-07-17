from datetime import datetime, timezone, timedelta
from extensions import db
from models import Ticket, TicketComment, TicketPriority
from utils.tenanting import get_active_tenant_id
from utils.branching import branch_scope_id_for
from utils.auth_helpers import is_global_owner_user


class TicketService:
    @staticmethod
    def _validate_tenant(ticket, user):
        tid = get_active_tenant_id(user)
        if tid is not None and int(ticket.tenant_id) != int(tid):
            raise ValueError("التذكرة لا تنتمي إلى شركتك النشطة.")

    @staticmethod
    def _next_number(tid):
        last = (
            Ticket.query.filter(
                Ticket.tenant_id == tid,
                Ticket.number.isnot(None),
            )
            .order_by(Ticket.id.desc())
            .first()
        )
        n = 1
        if last and last.number:
            try:
                n = int(last.number.split("-")[-1]) + 1
            except (ValueError, IndexError):
                n = 1
        from datetime import date

        today = date.today()
        return f"TKT-{today.year}{today.month:02d}-{n:04d}"

    @staticmethod
    def create_ticket(data, user):
        tid = get_active_tenant_id(user)
        if not tid and not is_global_owner_user(user):
            raise ValueError("لا توجد شركة نشطة.")
        if not data.get("subject"):
            raise ValueError("عنوان التذكرة مطلوب.")
        priority_id = data.get("priority_id")
        sla_deadline = None
        if priority_id:
            priority = db.session.get(TicketPriority, int(priority_id))
            if priority and priority.sla_hours > 0:
                sla_deadline = datetime.now(timezone.utc) + timedelta(
                    hours=priority.sla_hours
                )
        ticket = Ticket(
            tenant_id=int(tid) if tid else 0,
            number=TicketService._next_number(int(tid)) if tid else None,
            subject=data["subject"],
            body=data.get("body"),
            customer_id=int(data["customer_id"]) if data.get("customer_id") else None,
            category_id=int(data["category_id"]) if data.get("category_id") else None,
            priority_id=int(priority_id) if priority_id else None,
            assigned_user_id=(
                int(data["assigned_user_id"]) if data.get("assigned_user_id") else None
            ),
            source=data.get("source", "portal"),
            status="open",
            sla_deadline=sla_deadline,
        )
        db.session.add(ticket)
        try:
            db.session.flush()
        except Exception:
            raise
        return ticket

    @staticmethod
    def assign_ticket(ticket_id, user_id, current_user):
        ticket = db.session.get(Ticket, int(ticket_id))
        if not ticket:
            raise ValueError("التذكرة غير موجودة.")
        TicketService._validate_tenant(ticket, current_user)
        ticket.assigned_user_id = int(user_id) if user_id else None
        ticket.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            raise
        return ticket

    @staticmethod
    def resolve_ticket(ticket_id, current_user):
        ticket = db.session.get(Ticket, int(ticket_id))
        if not ticket:
            raise ValueError("التذكرة غير موجودة.")
        TicketService._validate_tenant(ticket, current_user)
        ticket.status = "resolved"
        ticket.resolved_at = datetime.now(timezone.utc)
        ticket.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            raise
        return ticket

    @staticmethod
    def close_ticket(ticket_id, current_user):
        ticket = db.session.get(Ticket, int(ticket_id))
        if not ticket:
            raise ValueError("التذكرة غير موجودة.")
        TicketService._validate_tenant(ticket, current_user)
        ticket.status = "closed"
        ticket.closed_at = datetime.now(timezone.utc)
        ticket.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            raise
        return ticket

    @staticmethod
    def reopen_ticket(ticket_id, current_user):
        ticket = db.session.get(Ticket, int(ticket_id))
        if not ticket:
            raise ValueError("التذكرة غير موجودة.")
        TicketService._validate_tenant(ticket, current_user)
        ticket.status = "open"
        ticket.resolved_at = None
        ticket.closed_at = None
        ticket.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            raise
        return ticket

    @staticmethod
    def add_comment(ticket_id, data, current_user):
        ticket = db.session.get(Ticket, int(ticket_id))
        if not ticket:
            raise ValueError("التذكرة غير موجودة.")
        TicketService._validate_tenant(ticket, current_user)
        if not data.get("body"):
            raise ValueError("نص التعليق مطلوب.")
        comment = TicketComment(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            user_id=current_user.id,
            body=data["body"],
            is_internal=data.get("is_internal", False),
        )
        db.session.add(comment)
        if ticket.status == "open":
            ticket.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            raise
        return comment

    @staticmethod
    def get_ticket(ticket_id, user):
        ticket = db.session.get(Ticket, int(ticket_id))
        if not ticket:
            raise ValueError("التذكرة غير موجودة.")
        TicketService._validate_tenant(ticket, user)
        return ticket

    @staticmethod
    def search_tickets(filters, user):
        tid = get_active_tenant_id(user)
        query = Ticket.query.filter(Ticket.is_active == True)
        if tid is not None:
            query = query.filter(Ticket.tenant_id == tid)
        if not is_global_owner_user(user):
            scoped = branch_scope_id_for(user)
            if scoped is not None:
                query = query.filter(Ticket.branch_id == scoped)
        if filters.get("status"):
            query = query.filter(Ticket.status == filters["status"])
        if filters.get("category_id"):
            query = query.filter(Ticket.category_id == int(filters["category_id"]))
        if filters.get("assigned_user_id"):
            query = query.filter(
                Ticket.assigned_user_id == int(filters["assigned_user_id"])
            )
        if filters.get("search"):
            q = f"%{filters['search']}%"
            query = query.filter(
                db.or_(Ticket.subject.ilike(q), Ticket.number.ilike(q))
            )
        return query.order_by(Ticket.created_at.desc()).all()
