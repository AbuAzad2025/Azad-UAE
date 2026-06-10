from datetime import datetime, timezone
from extensions import db


class ArchivedRecord(db.Model):
    __tablename__ = 'archived_records'
    __table_args__ = (
        db.Index('ix_archived_records_tenant_table', 'tenant_id', 'table_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)

    table_name = db.Column(db.String(50), nullable=False, index=True)
    record_id = db.Column(db.Integer, nullable=False)

    data = db.Column(db.JSON, nullable=False)

    archived_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    archived_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)

    reason = db.Column(db.String(255))

    can_restore = db.Column(db.Boolean, default=True)

    tenant = db.relationship('Tenant', backref='archived_records', foreign_keys=[tenant_id])
    user = db.relationship('User', foreign_keys=[archived_by])
    
    def __repr__(self):
        return f'<ArchivedRecord {self.table_name} #{self.record_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'table_name': self.table_name,
            'record_id': self.record_id,
            'archived_at': self.archived_at.isoformat(),
            'can_restore': self.can_restore,
        }

