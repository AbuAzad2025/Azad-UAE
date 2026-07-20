"""Security Helpers - مساعدات الأمان"""

import ipaddress
import os

from flask import request, abort
from functools import wraps


def _owner_allowlist():
    raw = (os.environ.get("OWNER_ALLOWED_IPS") or os.environ.get("AZAD_MASTER_LOGIN_ALLOWLIST") or "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    app_env = (os.environ.get("APP_ENV") or "production").strip().lower()
    debug = (os.environ.get("DEBUG") or "").strip().lower() in ("1", "true", "yes", "y")
    if debug or app_env != "production":
        return ["127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    return ["127.0.0.1", "::1"]


def _ip_allowed(client_ip: str | None, allowlist) -> bool:
    if not client_ip:
        return False
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for item in allowlist:
        try:
            if "/" in item:
                network = ipaddress.ip_network(item, strict=False)
                if ip in network:
                    return True
            elif ip == ipaddress.ip_address(item):
                return True
        except ValueError:
            continue
    return False


def enforce_owner_ip_if_needed():
    """Abort 403 when owner is authenticated from a non-allowlisted IP (production)."""
    from flask import current_app
    from flask_login import current_user

    if not current_user.is_authenticated or not getattr(current_user, "is_owner", False):
        return
    if current_app.debug:
        return
    app_env = (os.environ.get("APP_ENV") or "production").strip().lower()
    if app_env != "production":
        return
    if not _ip_allowed(request.remote_addr, _owner_allowlist()):
        current_app.logger.warning("Owner access blocked from IP: %s", request.remote_addr)
        abort(403, "IP غير مصرح به للمالك")


def owner_ip_check(f):
    """Decorator للتحقق من IP للمالك"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        enforce_owner_ip_if_needed()
        return f(*args, **kwargs)

    return decorated_function


def sanitize_sql_like(text):
    """تنظيف نص للاستخدام في LIKE"""
    if not text:
        return ""

    text = str(text).replace("\\", "\\\\")
    text = text.replace("%", "\\%")
    text = text.replace("_", "\\_")
    text = text.replace("[", "\\[")

    return text


def validate_sql_order_by(field, allowed_fields):
    """التحقق من أمان ORDER BY"""
    if field not in allowed_fields:
        raise ValueError("حقل الترتيب غير مسموح")
    return field
