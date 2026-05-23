"""
Password Validation - التحقق من قوة كلمات المرور
"""

import re
from typing import Tuple, List


class PasswordValidator:
    """مدقق كلمات المرور"""
    
    MIN_LENGTH = 10
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGIT = True
    REQUIRE_SPECIAL = True
    
    SPECIAL_CHARS = r'!@#$%^&*()_+-=[]{}|;:,.<>?'
    
    @classmethod
    def validate(cls, password: str) -> Tuple[bool, List[str]]:
        """
        التحقق من كلمة المرور
        
        Args:
            password: كلمة المرور للتحقق منها
            
        Returns:
            (is_valid, errors): (True/False, قائمة الأخطاء)
        """
        errors = []
        
        if not password:
            return False, ['كلمة المرور مطلوبة']
        
        if len(password) < cls.MIN_LENGTH:
            errors.append(f'يجب أن تكون كلمة المرور {cls.MIN_LENGTH} أحرف على الأقل')
        
        if cls.REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            errors.append('يجب أن تحتوي على حرف كبير واحد على الأقل (A-Z)')
        
        if cls.REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            errors.append('يجب أن تحتوي على حرف صغير واحد على الأقل (a-z)')
        
        if cls.REQUIRE_DIGIT and not re.search(r'\d', password):
            errors.append('يجب أن تحتوي على رقم واحد على الأقل (0-9)')
        
        if cls.REQUIRE_SPECIAL:
            special_pattern = f'[{re.escape(cls.SPECIAL_CHARS)}]'
            if not re.search(special_pattern, password):
                errors.append(f'يجب أن تحتوي على رمز خاص واحد على الأقل ({cls.SPECIAL_CHARS[:10]}...)')
        
        common_passwords = [
            'password', '123456', '12345678', 'qwerty', 'admin',
            'admin123', 'password123', '12341234', 'test', 'user'
        ]
        
        if password.lower() in common_passwords:
            errors.append('كلمة المرور شائعة جداً، اختر كلمة أكثر تعقيداً')
        
        sequences = ['123', '234', '345', 'abc', 'bcd', 'qwe', 'wer']
        for seq in sequences:
            if seq in password.lower():
                errors.append('تجنب استخدام تسلسلات سهلة (123, abc, qwe)')
                break
        
        return len(errors) == 0, errors
    
    @classmethod
    def get_strength_score(cls, password: str) -> int:
        """
        حساب قوة كلمة المرور (0-100)
        
        Returns:
            score: درجة القوة من 0 إلى 100
        """
        if not password:
            return 0
        
        score = 0
        
        length_score = min(len(password) * 3, 40)
        score += length_score
        
        if re.search(r'[A-Z]', password):
            score += 15
        if re.search(r'[a-z]', password):
            score += 15
        if re.search(r'\d', password):
            score += 15
        if re.search(f'[{re.escape(cls.SPECIAL_CHARS)}]', password):
            score += 15
        
        if len(set(password)) < len(password) * 0.7:
            score -= 10
        
        return min(max(score, 0), 100)
    
    @classmethod
    def get_strength_label(cls, score: int) -> Tuple[str, str]:
        """
        الحصول على تصنيف القوة
        
        Returns:
            (label, color): ('ضعيف', 'danger')
        """
        if score < 30:
            return 'ضعيف جداً', 'danger'
        elif score < 50:
            return 'ضعيف', 'warning'
        elif score < 70:
            return 'متوسط', 'info'
        elif score < 90:
            return 'قوي', 'primary'
        else:
            return 'قوي جداً', 'success'
    
    @classmethod
    def generate_suggestion(cls, username: str = None) -> str:
        """
        اقتراح كلمة مرور قوية
        
        Args:
            username: اسم المستخدم (اختياري)
            
        Returns:
            suggested_password: كلمة مرور مقترحة
        """
        import secrets
        import string
        
        length = 12
        chars = string.ascii_letters + string.digits + '!@#$%^&*'
        
        while True:
            password = ''.join(secrets.choice(chars) for _ in range(length))
            
            is_valid, _ = cls.validate(password)
            if is_valid:
                return password


def validate_password_with_helpful_message(password: str) -> Tuple[bool, str]:
    """
    دالة مساعدة للتحقق مع رسالة واضحة
    
    Returns:
        (is_valid, message): (True/False, رسالة)
    """
    is_valid, errors = PasswordValidator.validate(password)
    
    if is_valid:
        score = PasswordValidator.get_strength_score(password)
        label, color = PasswordValidator.get_strength_label(score)
        return True, f'✅ كلمة مرور {label} ({score}/100)'
    else:
        message = '⚠️ كلمة المرور لا تستوفي المتطلبات:\n'
        for i, error in enumerate(errors, 1):
            message += f'{i}. {error}\n'
        
        suggestion = PasswordValidator.generate_suggestion()
        message += f'\n💡 اقتراح: {suggestion}'
        
        return False, message

