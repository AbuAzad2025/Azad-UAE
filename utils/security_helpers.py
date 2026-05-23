"""Security Helpers - مساعدات الأمان"""

from flask import request, abort
from functools import wraps


OWNER_ALLOWED_IPS = [
    '127.0.0.1',
    'localhost',
    '::1',
]


def owner_ip_check(f):
    """Decorator للتحقق من IP للمالك"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user

        if current_user.is_authenticated and current_user.is_owner:
            client_ip = request.remote_addr

            from flask import current_app
            if current_app.debug:
                return f(*args, **kwargs)

            if client_ip not in OWNER_ALLOWED_IPS:
                current_app.logger.warning(f'Owner access from unauthorized IP: {client_ip}')
                abort(403, 'IP غير مصرح به للمالك')

        return f(*args, **kwargs)
    return decorated_function


def sanitize_sql_like(text):
    """تنظيف نص للاستخدام في LIKE"""
    if not text:
        return ''

    text = str(text).replace('\\', '\\\\')
    text = text.replace('%', '\\%')
    text = text.replace('_', '\\_')
    text = text.replace('[', '\\[')

    return text


def validate_sql_order_by(field, allowed_fields):
    """التحقق من أمان ORDER BY"""
    if field not in allowed_fields:
        raise ValueError('حقل الترتيب غير مسموح')
    return field

