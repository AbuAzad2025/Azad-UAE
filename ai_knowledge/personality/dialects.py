"""
🗣️ اللهجات العربية - Arabic Dialects Support
دعم اللهجة الفلسطينية والخليجية
"""

PALESTINIAN_DIALECT = {
    # كلمات شائعة
    'greetings': {
        'أهلا': 'أهلين',
        'مرحبا': 'مرحبتين',
        'كيف حالك': 'كيفك',
        'ماذا تريد': 'إيش بدك',
        'نعم': 'آه / أيوه',
        'لا': 'لأ',
        'جيد': 'منيح',
        'ممتاز': 'خرافي',
        'شكراً': 'يسلموا',
    },
    
    'common_phrases': {
        'كيف يمكنني': 'كيف بقدر',
        'أريد أن': 'بدي',
        'لا أعرف': 'مش عارف',
        'هل تستطيع': 'بتقدر',
        'ممكن': 'ممكن',
        'تفضل': 'اتفضل',
        'الآن': 'هلأ',
        'ماذا حدث': 'شو صار',
        'لماذا': 'ليش',
        'أين': 'وين',
    },
    
    'business_terms': {
        'الفاتورة': 'الفاتورة',
        'الزبون': 'الزبون',
        'المنتج': 'البضاعة',
        'السعر': 'الثمن',
        'الدفع': 'الدفع',
        'الحساب': 'الحساب',
    },
    
    'encouragement': [
        'ماشي الحال! 👍',
        'تمام! ✅',
        'خرافي! 🌟',
        'يسلموا! 💚',
        'منيح كتير! 😊',
        'والله زبطت معك! 🚀',
    ],
    
    'responses': {
        'yes': 'أيوه',
        'no': 'لأ',
        'ok': 'ماشي',
        'great': 'خرافي',
        'thanks': 'يسلموا',
        'welcome': 'أهلين وسهلين',
    }
}

GULF_DIALECT = {
    # كلمات شائعة
    'greetings': {
        'أهلا': 'هلا',
        'مرحبا': 'مراحب',
        'كيف حالك': 'شلونك / شخبارك',
        'ماذا تريد': 'شو تبي',
        'نعم': 'إي / أيوا',
        'لا': 'لا',
        'جيد': 'زين',
        'ممتاز': 'خوش',
        'شكراً': 'مشكور / يزاك الله خير',
    },
    
    'common_phrases': {
        'كيف يمكنني': 'كيف أقدر',
        'أريد أن': 'أبي / أبغى',
        'لا أعرف': 'ما أدري',
        'هل تستطيع': 'تقدر',
        'ممكن': 'ممكن',
        'تفضل': 'تفضل',
        'الآن': 'حاليا / الحين',
        'ماذا حدث': 'شو صار',
        'لماذا': 'ليش',
        'أين': 'وين',
    },
    
    'business_terms': {
        'الفاتورة': 'الفاتورة',
        'الزبون': 'الزبون',
        'المنتج': 'البضاعة',
        'السعر': 'السعر',
        'الدفع': 'الدفع',
        'الحساب': 'الحساب',
    },
    
    'encouragement': [
        'زين! 👍',
        'خوش شغل! ✅',
        'ماشاء الله! 🌟',
        'يزاك الله خير! 💚',
        'والله زين! 😊',
        'تمام كذا! 🚀',
    ],
    
    'responses': {
        'yes': 'إي',
        'no': 'لا',
        'ok': 'زين',
        'great': 'خوش',
        'thanks': 'مشكور',
        'welcome': 'هلا والله',
    }
}

FORMAL_ARABIC = {
    'greetings': {
        'أهلا': 'أهلاً',
        'مرحبا': 'مرحباً',
        'كيف حالك': 'كيف حالك',
        'ماذا تريد': 'ماذا تريد',
        'نعم': 'نعم',
        'لا': 'لا',
        'جيد': 'جيد',
        'ممتاز': 'ممتاز',
        'شكراً': 'شكراً',
    },
    
    'encouragement': [
        'ممتاز! 👍',
        'جيد جداً! ✅',
        'رائع! 🌟',
        'شكراً! 💚',
        'أحسنت! 😊',
        'عمل رائع! 🚀',
    ],
    
    'responses': {
        'yes': 'نعم',
        'no': 'لا',
        'ok': 'حسناً',
        'great': 'رائع',
        'thanks': 'شكراً',
        'welcome': 'أهلاً وسهلاً',
    }
}


class DialectManager:
    """مدير اللهجات"""
    
    def __init__(self):
        self.dialects = {
            'palestinian': PALESTINIAN_DIALECT,
            'gulf': GULF_DIALECT,
            'formal': FORMAL_ARABIC
        }
        self.current_dialect = 'palestinian'
    
    def set_dialect(self, dialect):
        """تعيين اللهجة"""
        if dialect in self.dialects:
            self.current_dialect = dialect
            return True
        return False
    
    def translate_response(self, response, dialect=None):
        """تحويل الرد للهجة المحددة"""
        if dialect is None:
            dialect = self.current_dialect
        
        if dialect == 'formal' or dialect not in self.dialects:
            return response
        
        dialect_dict = self.dialects[dialect]
        translated = response
        
        # تحويل العبارات الشائعة
        if 'common_phrases' in dialect_dict:
            for formal, dialectal in dialect_dict['common_phrases'].items():  # type: ignore[union-attr]
                translated = translated.replace(formal, dialectal)
        
        # تحويل التحيات
        if 'greetings' in dialect_dict:
            for formal, dialectal in dialect_dict['greetings'].items():  # type: ignore[union-attr]
                translated = translated.replace(formal, dialectal)
        
        return translated
    
    def get_encouragement(self, dialect=None):
        """الحصول على عبارة تشجيع باللهجة"""
        import secrets
        if dialect is None:
            dialect = self.current_dialect
        
        if dialect in self.dialects and 'encouragement' in self.dialects[dialect]:
            return secrets.choice(self.dialects[dialect]['encouragement'])
        
        return 'ممتاز! 👍'
    
    def get_response_word(self, word_type, dialect=None):
        """الحصول على كلمة رد باللهجة"""
        if dialect is None:
            dialect = self.current_dialect
        
        if dialect in self.dialects and 'responses' in self.dialects[dialect]:
            return self.dialects[dialect]['responses'].get(word_type, word_type)  # type: ignore[union-attr]
        
        return word_type


# مثيل عالمي
dialect_manager = DialectManager()


def apply_dialect(text, dialect='palestinian'):
    """تطبيق اللهجة على النص"""
    return dialect_manager.translate_response(text, dialect)


def get_dialectal_greeting(dialect='palestinian'):
    """الحصول على تحية باللهجة"""
    greetings = {
        'palestinian': [
            'أهلين وسهلين! إيش بدك يا زميل؟ 😊',
            'مرحبتين! كيفك؟ شو الأخبار؟ 🌟',
            'يا هلا! إيش في عندك؟ 🚀',
            'أهلاً فيك! شو بتحتاج؟ 💚',
        ],
        'gulf': [
            'هلا والله! شلونك؟ 😊',
            'مراحب! شخبارك؟ 🌟',
            'يا هلا! شو تبي؟ 🚀',
            'حياك الله! كيف نقدر نساعدك؟ 💚',
        ],
        'formal': [
            'أهلاً وسهلاً! كيف يمكنني مساعدتك؟ 😊',
            'مرحباً! ماذا تحتاج؟ 🌟',
            'تحية طيبة! كيف أخدمك؟ 🚀',
        ]
    }
    
    import secrets
    return secrets.choice(greetings.get(dialect, greetings['formal']))

