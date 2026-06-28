"""
XSS Prevention & Input Sanitization
"""

from markupsafe import escape, Markup
import re


def _resolve_bleach():
    try:
        import bleach as bleach_module
    except ImportError:
        return None, False
    return bleach_module, True


bleach, _BLEACH_AVAILABLE = _resolve_bleach()


class InputSanitizer:
    """منظف المدخلات ضد XSS"""

    ALLOWED_TAGS = ['b', 'i', 'u', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li']
    ALLOWED_ATTRS = {}

    @staticmethod
    def sanitize_html(text, allow_tags=False):
        """تنظيف HTML"""
        if not text:
            return ''

        if allow_tags and _BLEACH_AVAILABLE:
            return bleach.clean(
                text,
                tags=InputSanitizer.ALLOWED_TAGS,
                attributes=InputSanitizer.ALLOWED_ATTRS,
                strip=True
            )
        else:
            return escape(text)

    @staticmethod
    def sanitize_text(text, max_length=None):
        """تنظيف نص عادي"""
        if not text:
            return ''

        text = re.sub(r'<[^>]+>', '', str(text))

        text = escape(text)

        text = text.strip()

        if max_length and len(text) > max_length:
            text = text[:max_length]

        return text

    @staticmethod
    def sanitize_email(email):
        """تنظيف وتحقق من email"""
        if not email:
            return None

        email = str(email).strip().lower()

        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, email):
            return None

        return email

    @staticmethod
    def sanitize_phone(phone):
        """تنظيف رقم هاتف"""
        if not phone:
            return None

        phone = re.sub(r'[^\d\+\-\s\(\)]', '', str(phone))

        return phone.strip()

    @staticmethod
    def sanitize_number(value, allow_negative=True, allow_decimal=True):
        """تنظيف رقم"""
        if value is None or value == '':
            return None

        try:
            if allow_decimal:
                num = float(value)
            else:
                num = int(value)

            if not allow_negative and num < 0:
                return None

            return num
        except (ValueError, TypeError):
            return None

    @staticmethod
    def sanitize_sql_input(text):
        """حماية من SQL Injection"""
        if not text:
            return ''

        dangerous_chars = [';', '--', '/*', '*/', 'xp_', 'sp_', 'exec', 'execute']

        text = str(text)
        for char in dangerous_chars:
            text = text.replace(char, '')

        return text.strip()


def sanitize_form_data(form_data, rules=None):
    """
    تنظيف بيانات form كاملة
    
    Args:
        form_data: dict من بيانات الفورم
        rules: dict من القواعد لكل حقل
        
    Returns:
        cleaned_data: dict منظف
    """
    rules = rules or {}
    cleaned = {}

    for key, value in form_data.items():
        rule = rules.get(key, {})

        if rule.get('type') == 'email':
            cleaned[key] = InputSanitizer.sanitize_email(value)
        elif rule.get('type') == 'phone':
            cleaned[key] = InputSanitizer.sanitize_phone(value)
        elif rule.get('type') == 'number':
            cleaned[key] = InputSanitizer.sanitize_number(value)
        elif rule.get('type') == 'html':
            cleaned[key] = InputSanitizer.sanitize_html(value, allow_tags=True)
        else:
            max_len = rule.get('max_length')
            cleaned[key] = InputSanitizer.sanitize_text(value, max_len)

    return cleaned

