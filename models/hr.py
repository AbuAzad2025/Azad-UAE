from datetime import datetime, timezone
from extensions import db


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    manager_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    parent_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    color = db.Column(db.String(7), default="#3b82f6")
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    manager = db.relationship("User", foreign_keys=[manager_id])
    parent = db.relationship("Department", remote_side=[id], backref="sub_departments")

    def __repr__(self):
        return f"<Department {self.name}>"


class JobPosition(db.Model):
    __tablename__ = "job_positions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    no_of_employees = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    department = db.relationship("Department", foreign_keys=[department_id])

    def __repr__(self):
        return f"<JobPosition {self.name}>"


class HRContract(db.Model):
    __tablename__ = "hr_contracts"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("job_positions.id", ondelete="SET NULL"),
        nullable=True,
    )
    date_start = db.Column(db.Date, nullable=False)
    date_end = db.Column(db.Date, nullable=True)
    wage = db.Column(db.Numeric(15, 3), default=0)
    state = db.Column(db.String(20), default="draft")
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    user = db.relationship("User", foreign_keys=[user_id])
    department = db.relationship("Department", foreign_keys=[department_id])
    job = db.relationship("JobPosition", foreign_keys=[job_id])

    def __repr__(self):
        return f"<HRContract U{self.user_id} {self.state}>"


class Attendance(db.Model):
    __tablename__ = "attendances"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    check_in = db.Column(db.DateTime, nullable=False)
    check_out = db.Column(db.DateTime, nullable=True)
    work_hours = db.Column(db.Numeric(8, 2), nullable=True)
    state = db.Column(db.String(20), default="draft")
    notes = db.Column(db.String(500))
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (db.Index("ix_attendance_user_date", "user_id", "check_in"),)

    def __repr__(self):
        return f"<Attendance U{self.user_id} {self.check_in}>"


class LeaveType(db.Model):
    __tablename__ = "leave_types"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    color = db.Column(db.String(7), default="#10b981")
    allocation_type = db.Column(db.String(20), default="fixed")
    days_per_year = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<LeaveType {self.name}>"


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    leave_type_id = db.Column(
        db.Integer, db.ForeignKey("leave_types.id", ondelete="SET NULL"), nullable=True
    )
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
    duration = db.Column(db.Numeric(5, 1), nullable=False)
    reason = db.Column(db.Text)
    state = db.Column(db.String(20), default="draft", index=True)
    manager_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_reason = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    user = db.relationship("User", foreign_keys=[user_id])
    leave_type = db.relationship("LeaveType", foreign_keys=[leave_type_id])
    manager = db.relationship("User", foreign_keys=[manager_id])

    def __repr__(self):
        return f"<LeaveRequest U{self.user_id} {self.date_from}-{self.date_to}>"
