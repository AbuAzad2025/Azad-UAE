from datetime import datetime, timezone
from extensions import db


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    description = db.Column(db.Text)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(20), default='planning', index=True)
    date_start = db.Column(db.DateTime, nullable=True)
    date_end = db.Column(db.DateTime, nullable=True)
    color = db.Column(db.String(7), default='#10b981')
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    customer = db.relationship('Customer', foreign_keys=[customer_id])
    stages = db.relationship('TaskStage', back_populates='project', cascade='all, delete-orphan')
    tasks = db.relationship('Task', back_populates='project', cascade='all, delete-orphan')
    members = db.relationship('ProjectMember', back_populates='project', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Project {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'date_start': self.date_start.isoformat() if self.date_start else None,
            'date_end': self.date_end.isoformat() if self.date_end else None,
        }


class TaskStage(db.Model):
    __tablename__ = 'task_stages'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    sequence = db.Column(db.Integer, default=0)
    is_closed = db.Column(db.Boolean, default=False)
    color = db.Column(db.String(7), default='#6b7280')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    project = db.relationship('Project', back_populates='stages', foreign_keys=[project_id])

    def __repr__(self):
        return f'<TaskStage {self.name}>'


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    stage_id = db.Column(db.Integer, db.ForeignKey('task_stages.id', ondelete='SET NULL'), nullable=True, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='SET NULL'), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    priority = db.Column(db.String(20), default='medium')
    date_deadline = db.Column(db.DateTime, nullable=True)
    planned_hours = db.Column(db.Numeric(8, 2), default=0)
    effective_hours = db.Column(db.Numeric(8, 2), default=0)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    project = db.relationship('Project', back_populates='tasks', foreign_keys=[project_id])
    stage = db.relationship('TaskStage', foreign_keys=[stage_id])
    parent = db.relationship('Task', remote_side=[id], backref='subtasks')
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])
    timesheets = db.relationship('Timesheet', back_populates='task', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Task {self.name}>'


class Timesheet(db.Model):
    __tablename__ = 'timesheets'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    hours = db.Column(db.Numeric(8, 2), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    task = db.relationship('Task', back_populates='timesheets', foreign_keys=[task_id])
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<Timesheet {self.date} {self.hours}h>'


class ProjectMember(db.Model):
    __tablename__ = 'project_members'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    role = db.Column(db.String(30), default='member')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    project = db.relationship('Project', back_populates='members', foreign_keys=[project_id])
    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint('project_id', 'user_id', name='uq_project_member'),
    )

    def __repr__(self):
        return f'<ProjectMember P{self.project_id} U{self.user_id}>'
