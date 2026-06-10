from extensions import db
from datetime import datetime, timezone

class SecurityAlert(db.Model):
    __tablename__ = 'security_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default='medium')
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    username = db.Column(db.String(50))
    url = db.Column(db.String(500))
    method = db.Column(db.String(10))
    status_code = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    is_resolved = db.Column(db.Boolean, default=False)
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    
    user = db.relationship('User', foreign_keys=[user_id], backref='security_alerts')
    resolver = db.relationship('User', foreign_keys=[resolved_by])
    
    def __repr__(self):
        return f'<SecurityAlert {self.alert_type} - {self.severity}>'

