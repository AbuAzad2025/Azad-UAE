from datetime import datetime, timezone
from extensions import db


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)

    # Tenant isolation
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    
    action = db.Column(db.String(50), nullable=False, index=True)
    
    table_name = db.Column(db.String(50), index=True)
    record_id = db.Column(db.Integer)
    
    changes = db.Column(db.JSON)
    
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    user = db.relationship('User', back_populates='audit_logs')
    
    def __repr__(self):
        return f'<AuditLog {self.action} on {self.table_name}>'
    
    def get_action_display(self, lang='ar'):
        actions = {
            'create': {'ar': 'إضافة', 'en': 'Create'},
            'update': {'ar': 'تعديل', 'en': 'Update'},
            'delete': {'ar': 'حذف', 'en': 'Delete'},
            'login': {'ar': 'تسجيل دخول', 'en': 'Login'},
            'logout': {'ar': 'تسجيل خروج', 'en': 'Logout'},
            'view': {'ar': 'عرض', 'en': 'View'},
            'export': {'ar': 'تصدير', 'en': 'Export'},
            'print': {'ar': 'طباعة', 'en': 'Print'},
        }
        return actions.get(self.action, {}).get(lang, self.action)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.username if self.user else 'System',
            'action': self.action,
            'table_name': self.table_name,
            'record_id': self.record_id,
            'created_at': self.created_at.isoformat(),
            'ip_address': self.ip_address,
        }

