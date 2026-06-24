"""
🔒 قواعد الأمان - Security Rules
أزاد يحمي المعلومات الحساسة
"""

from flask_login import current_user


class SecurityRules:
    """قواعد الأمان لأزاد"""
    
    @staticmethod
    def is_owner():
        if not current_user or not current_user.is_authenticated:
            return False
        return bool(getattr(current_user, 'is_owner', False))
    
    @staticmethod
    def can_access_sensitive_info():
        """فحص إمكانية الوصول للمعلومات الحساسة"""
        return SecurityRules.is_owner()
    
    @staticmethod
    def filter_sensitive_data(data, user_id=None):
        """تصفية البيانات الحساسة"""
        if SecurityRules.can_access_sensitive_info():
            return data
        
        # إخفاء المعلومات الحساسة
        if isinstance(data, dict):
            filtered_data = {}
            for key, value in data.items():
                if key.lower() in ['password', 'secret', 'key', 'token', 'api_key']:
                    filtered_data[key] = "*** محمي ***"
                elif key.lower() in ['email', 'phone']:
                    # إخفاء جزئي للإيميل والهاتف
                    if key.lower() == 'email' and isinstance(value, str):
                        filtered_data[key] = value.split('@')[0] + '@***.***'
                    elif key.lower() == 'phone' and isinstance(value, str):
                        filtered_data[key] = value[:3] + '***' + value[-2:]
                    else:
                        filtered_data[key] = value
                else:
                    filtered_data[key] = value
            return filtered_data
        
        return data
    
    @staticmethod
    def get_security_response(request_type):
        """الحصول على رد أمني"""
        responses = {
            'password_request': "😊 عذراً، أزاد لا يشارك كلمات المرور. هذا لأمانك! 🔒",  # nosec B105
            'sensitive_info': "🌟 هذه المعلومات حساسة. يرجى التواصل مع المالك! 👑",
            'unauthorized': "🚫 عذراً، ليس لديك صلاحية للوصول لهذه المعلومات! 🔐",
            'owner_only': "👑 هذه الميزة متاحة للمالك فقط! 💎"
        }
        
        return responses.get(request_type, "🔒 عذراً، وصول غير مصرح به!")
    
    @staticmethod
    def check_user_permissions(action):
        """فحص صلاحيات المستخدم"""
        if not current_user or not current_user.is_authenticated:
            return False, "يجب تسجيل الدخول أولاً"
        
        if SecurityRules.is_owner():
            return True, "صلاحيات كاملة"
        role = getattr(current_user, 'role', None)
        slug = getattr(role, 'slug', None) if role else None
        role_permissions = {
            'super_admin': ['view_all', 'edit_all', 'delete_all'],
            'manager': ['view_all', 'edit_limited'],
            'seller': ['view_limited', 'edit_own'],
        }
        user_permissions = role_permissions.get(slug, [])
        if action in user_permissions:
            return True, "صلاحية ممنوحة"
        return False, "ليس لديك صلاحية لهذا الإجراء"
    
    @staticmethod
    def sanitize_input(text):
        """تنظيف المدخلات من المحتوى الضار"""
        if not text:
            return ""
        
        # إزالة الأحرف الضارة
        dangerous_chars = ['<', '>', '"', "'", '&', ';', '(', ')', '|', '`', '$']
        
        for char in dangerous_chars:
            text = text.replace(char, '')
        
        # تحديد طول النص
        if len(text) > 1000:
            text = text[:1000] + "..."
        
        return text.strip()
    
    @staticmethod
    def log_security_event(event_type, details):
        """تسجيل الأحداث الأمنية"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user = current_user.username if current_user and current_user.is_authenticated else 'غير مسجل'
        
        log_entry = f"[{timestamp}] {event_type}: {details} - المستخدم: {user}"
        
        # يمكن إضافة تسجيل في ملف أو قاعدة بيانات
        print(f"SECURITY_LOG: {log_entry}")
    
    @staticmethod
    def rate_limit_check(user_id, action):
        """فحص معدل الطلبات"""
        # يمكن تطوير نظام rate limiting أكثر تعقيداً
        # هنا مثال بسيط
        return True, "معدل طبيعي"


# إنشاء مثيل عالمي
security_rules = SecurityRules()
