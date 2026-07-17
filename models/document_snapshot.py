"""
DocumentSnapshot — لقطة المستند
Immutable snapshot of document state at print/finalize/amend time.
"""

from datetime import datetime, timezone
from extensions import db


class DocumentSnapshot(db.Model):
    __tablename__ = "document_snapshots"
    __table_args__ = (
        db.Index(
            "ix_doc_snapshots_tenant_doc_type",
            "tenant_id",
            "document_type",
            "document_id",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type = db.Column(db.String(50), nullable=False, index=True)
    document_id = db.Column(db.Integer, nullable=False)
    snapshot_data = db.Column(db.JSON, nullable=False)
    branding_snapshot = db.Column(db.JSON, nullable=True)
    snapshot_reason = db.Column(db.String(20), nullable=False, default="print")
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

    tenant = db.relationship(
        "Tenant", backref="document_snapshots", foreign_keys=[tenant_id]
    )
    user = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<DocumentSnapshot {self.document_type}#{self.document_id} {self.snapshot_reason}>"

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "document_type": self.document_type,
            "document_id": self.document_id,
            "snapshot_reason": self.snapshot_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }
