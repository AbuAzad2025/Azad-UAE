from datetime import datetime, timezone
from flask import request
from flask_login import current_user
from extensions import db
import hashlib


def generate_device_fingerprint() -> str:
    components = [
        request.headers.get('User-Agent', ''),
        request.headers.get('Accept-Language', ''),
        request.headers.get('Accept-Encoding', ''),
        str(request.headers.get('Sec-Ch-Ua-Platform', ''))
    ]
    
    fingerprint_string = '|'.join(components)
    return hashlib.sha256(fingerprint_string.encode()).hexdigest()[:16]


def log_sensitive_action(action: str, table_name: str = None, record_id: int = None, 
                         changes: dict = None, severity: str = 'medium'):
    from models import AuditLog
    
    try:
        audit_entry = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            table_name=table_name,
            record_id=record_id,
            changes=changes,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None
        )
        
        db.session.add(audit_entry)
        db.session.commit()
        
        if severity == 'high':
            notify_admin_of_sensitive_action(action, audit_entry)
    
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception('Audit log failed: %s', action)
        db.session.rollback()


def notify_admin_of_sensitive_action(action: str, audit_entry):
    pass


def track_login_attempt(username: str, success: bool, ip_address: str):
    from models import User
    
    user = User.query.filter_by(username=username).first()
    
    if user:
        if success:
            user.login_attempts = 0
            user.last_login = datetime.now(timezone.utc)
        else:
            user.login_attempts = (user.login_attempts or 0) + 1
            
            if user.login_attempts >= 5:
                from datetime import timedelta
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        db.session.commit()


def get_security_events(user_id: int = None, days: int = 30):
    from models import AuditLog
    from datetime import timedelta
    
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = AuditLog.query.filter(AuditLog.created_at >= since)
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    
    query = query.filter(
        AuditLog.action.in_(['login', 'logout', 'delete', 'update'])
    ).order_by(AuditLog.created_at.desc())
    
    return query.limit(100).all()

