"""Error Audit Log — independent from AuditLog.

Records all system errors (backend, DB, frontend, system-init, API).
This table is NOT tenant-scoped; it stores tenant_id as metadata only
so errors can be traced to the tenant where they occurred.
"""

from datetime import datetime, timezone
from extensions import db


class ErrorAuditLog(db.Model):
    __tablename__ = "error_audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    # Classification
    level = db.Column(db.String(20), nullable=False, default="ERROR", index=True)
    # CRITICAL, ERROR, WARNING, INFO

    category = db.Column(db.String(30), nullable=False, index=True)
    # BACKEND, DATABASE, FRONTEND, SYSTEM_INIT, API, SECURITY, RATE_LIMIT

    source = db.Column(db.String(100), nullable=False, index=True)
    # module path or file name, e.g. "utils.system_init", "routes.api"

    # Content (never store secrets here)
    message = db.Column(db.Text, nullable=False)
    exception_type = db.Column(db.String(200))
    stack_trace = db.Column(db.Text)

    # Request context
    url = db.Column(db.String(500))
    method = db.Column(db.String(10))
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))

    # User / tenant context
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), index=True)

    # Sanitized request data (no passwords, tokens, secrets)
    request_data = db.Column(db.JSON)

    # Resolution tracking
    is_resolved = db.Column(db.Boolean, default=False, index=True)
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    resolution_note = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    def __repr__(self):
        return f"<ErrorAuditLog {self.category} {self.level}: {self.message[:60]}>"

    def to_dict(self):
        return {
            "id": self.id,
            "level": self.level,
            "category": self.category,
            "source": self.source,
            "message": self.message,
            "exception_type": self.exception_type,
            "url": self.url,
            "method": self.method,
            "ip_address": self.ip_address,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "is_resolved": self.is_resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_note": self.resolution_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
