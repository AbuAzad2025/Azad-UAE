"""
PrintHistory — سجل الطباعة
Audit trail for all printed documents.
"""
from datetime import datetime, timezone
from extensions import db


class PrintHistory(db.Model):
    __tablename__ = 'print_history'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    document_type = db.Column(db.String(50), nullable=False, index=True)

    document_id = db.Column(db.Integer, nullable=False, index=True)

    action = db.Column(db.String(20), nullable=False, default='print')

    metadata_json = db.Column(db.Text, nullable=True)

    ip_address = db.Column(db.String(45), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    user = db.relationship('User', backref='print_history', foreign_keys=[user_id])

    @property
    def meta(self):
        if self.metadata_json:
            import json
            try:
                return json.loads(self.metadata_json)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @meta.setter
    def meta(self, value):
        import json
        self.metadata_json = json.dumps(value, ensure_ascii=False) if value else None

    def __repr__(self):
        return f'<PrintHistory {self.document_type}#{self.document_id} {self.action} by user#{self.user_id}>'
