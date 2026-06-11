from datetime import datetime, timezone
from extensions import db


class TicketCategory(db.Model):
    __tablename__ = 'ticket_categories'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    color = db.Column(db.String(7), default='#3b82f6')
    auto_assign_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    auto_assign_user = db.relationship('User', foreign_keys=[auto_assign_user_id])

    def __repr__(self):
        return f'<TicketCategory {self.name}>'


class TicketPriority(db.Model):
    __tablename__ = 'ticket_priorities'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    name_ar = db.Column(db.String(50))
    sequence = db.Column(db.Integer, default=0)
    color = db.Column(db.String(7), default='#6b7280')
    sla_hours = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<TicketPriority {self.name}>'


class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True, index=True)
    number = db.Column(db.String(20), index=True)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('ticket_categories.id', ondelete='SET NULL'), nullable=True)
    priority_id = db.Column(db.Integer, db.ForeignKey('ticket_priorities.id', ondelete='SET NULL'), nullable=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    status = db.Column(db.String(20), default='open', index=True)
    source = db.Column(db.String(20), default='portal')
    sla_deadline = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    customer = db.relationship('Customer', foreign_keys=[customer_id])
    category = db.relationship('TicketCategory', foreign_keys=[category_id])
    priority = db.relationship('TicketPriority', foreign_keys=[priority_id])
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])
    comments = db.relationship('TicketComment', back_populates='ticket', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Ticket #{self.number} {self.subject}>'

    def to_dict(self):
        return {
            'id': self.id,
            'number': self.number,
            'subject': self.subject,
            'status': self.status,
            'source': self.source,
            'customer_id': self.customer_id,
            'assigned_user_id': self.assigned_user_id,
            'category_id': self.category_id,
            'priority_id': self.priority_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TicketComment(db.Model):
    __tablename__ = 'ticket_comments'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    body = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    ticket = db.relationship('Ticket', back_populates='comments', foreign_keys=[ticket_id])
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<TicketComment #{self.id} on T{self.ticket_id}>'
