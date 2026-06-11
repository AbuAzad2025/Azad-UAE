from datetime import datetime, timezone
from extensions import db


class CRMStage(db.Model):
    __tablename__ = 'crm_stages'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    sequence = db.Column(db.Integer, default=0)
    probability = db.Column(db.Integer, default=0)
    color = db.Column(db.String(7), default='#6b7280')
    is_won = db.Column(db.Boolean, default=False)
    is_lost = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    leads = db.relationship('CRMLead', back_populates='stage', foreign_keys='CRMLead.stage_id', lazy='dynamic')

    def __repr__(self):
        return f'<CRMStage {self.name}>'

    def to_dict(self, lang='ar'):
        return {
            'id': self.id,
            'name': self.name_ar if lang == 'ar' and self.name_ar else self.name,
            'sequence': self.sequence,
            'probability': self.probability,
            'color': self.color,
            'is_won': self.is_won,
            'is_lost': self.is_lost,
        }


class CRMTeam(db.Model):
    __tablename__ = 'crm_teams'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    leader = db.relationship('User', foreign_keys=[leader_id])
    members = db.relationship('CRMTeamMember', back_populates='team', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<CRMTeam {self.name}>'


class CRMTeamMember(db.Model):
    __tablename__ = 'crm_team_members'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('crm_teams.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    team = db.relationship('CRMTeam', back_populates='members')
    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint('team_id', 'user_id', name='uq_crm_team_member'),
    )


class CRMLead(db.Model):
    __tablename__ = 'crm_leads'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    company = db.Column(db.String(200))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True, index=True)
    stage_id = db.Column(db.Integer, db.ForeignKey('crm_stages.id', ondelete='SET NULL'), nullable=True, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey('crm_teams.id', ondelete='SET NULL'), nullable=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    expected_revenue = db.Column(db.Numeric(15, 3), default=0)
    priority = db.Column(db.String(20), default='medium')
    source = db.Column(db.String(50))
    status = db.Column(db.String(20), default='open')
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    closed_at = db.Column(db.DateTime, nullable=True)

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    customer = db.relationship('Customer', foreign_keys=[customer_id])
    stage = db.relationship('CRMStage', back_populates='leads', foreign_keys=[stage_id])
    team = db.relationship('CRMTeam', foreign_keys=[team_id])
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])
    activities = db.relationship('CRMActivity', back_populates='lead', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<CRMLead {self.name}>'

    def to_dict(self, lang='ar'):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'company': self.company,
            'customer_id': self.customer_id,
            'stage_id': self.stage_id,
            'stage_name': self.stage.name_ar if self.stage and lang == 'ar' and self.stage.name_ar else (self.stage.name if self.stage else ''),
            'assigned_user_id': self.assigned_user_id,
            'expected_revenue': float(self.expected_revenue or 0),
            'priority': self.priority,
            'source': self.source,
            'status': self.status,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CRMActivity(db.Model):
    __tablename__ = 'crm_activities'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('crm_leads.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    activity_type = db.Column(db.String(30), nullable=False)
    summary = db.Column(db.String(500))
    date_deadline = db.Column(db.DateTime, nullable=True)
    done_date = db.Column(db.DateTime, nullable=True)
    is_done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    lead = db.relationship('CRMLead', back_populates='activities', foreign_keys=[lead_id])
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<CRMActivity {self.activity_type} on L{self.lead_id}>'
