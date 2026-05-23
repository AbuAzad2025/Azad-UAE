from extensions import db
from datetime import datetime, timezone

class LoginHistory(db.Model):
    __tablename__ = 'login_history'
    
    id = db.Column(db.Integer, primary_key=True)
    # Allow null for user_id to track failed login attempts for non-existent users
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    login_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    logout_time = db.Column(db.DateTime)
    success = db.Column(db.Boolean, default=True)
    failure_reason = db.Column(db.String(200))
    device_type = db.Column(db.String(50))
    browser = db.Column(db.String(100))
    location = db.Column(db.String(200))
    
    user = db.relationship('User', backref='login_history')
    
    def __repr__(self):
        return f'<LoginHistory {self.username} at {self.login_time}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'ip_address': self.ip_address,
            'login_time': self.login_time.isoformat() if self.login_time else None,
            'logout_time': self.logout_time.isoformat() if self.logout_time else None,
            'success': self.success,
            'device_type': self.device_type,
            'browser': self.browser,
        }

