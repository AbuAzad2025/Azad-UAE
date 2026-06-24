"""
Consolidated module: specialized_knowledge.py
Merged: specialized/customer_service.py, specialized/tax_system.py, specialized/system_guide.py, specialized/security_rules.py, specialized/advanced_laws.py, specialized/user_guide.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: specialized/customer_service.py =====
"""
👥 خدمة العملاء - Customer Service
فن التعامل مع الزبائن
"""

CUSTOMER_SERVICE = {
    'greeting': [
        'السلام عليكم ورحمة الله وبركاته',
        'أهلاً وسهلاً بك في شركة أزاد',
        'تشرفنا بخدمتك',
        'كيف يمكنني مساعدتك اليوم؟'
    ],
    'principles': [
        '1. الاستماع الجيد: افهم احتياجات العميل قبل العرض',
        '2. الصدق والأمانة: لا تبالغ في مواصفات المنتج',
        '3. الاحترافية: التزم بالمواعيد والوعود',
        '4. الصبر: تعامل بهدوء حتى مع العملاء الصعبين',
        '5. المرونة: قدم حلول بديلة إذا لم يتوفر المطلوب',
        '6. المتابعة: اتصل بالعميل بعد البيع للاطمئنان'
    ],
    'handling_complaints': [
        '1. استمع للشكوى بإنصات كامل',
        '2. اعتذر عن الإزعاج (حتى لو لم يكن خطأك)',
        '3. افهم المشكلة بدقة',
        '4. قدم حل سريع وعملي',
        '5. تابع للتأكد من رضا العميل',
        '6. وثق الحالة للاستفادة منها مستقبلاً'
    ],
    'sales_tips': [
        '• ابدأ بالسؤال عن نوع المعدة أو السيارة',
        '• حدد المشكلة أو الاحتياج بدقة',
        '• اعرض المنتج المناسب مع الشرح',
        '• اذكر المزايا والفوائد (ليس فقط المواصفات)',
        '• قدم سعر تنافسي حسب نوع العميل',
        '• أغلق البيع بثقة وبشاشة',
        '• قدم الضمان وخدمة ما بعد البيع'
    ]
}

def get_customer_service_tip():
    """نصيحة في خدمة العملاء"""
    import secrets
    
    tips = [
        "😊 **الابتسامة أولاً:** حتى بالهاتف، الابتسامة تُسمع في نبرة الصوت",
        "👂 **استمع جيداً:** افهم المشكلة قبل أن تقدم الحل",
        "🎯 **كن محدداً:** بدلاً من 'قريباً' قل 'خلال 24 ساعة'",
        "💪 **ثق بنفسك:** العميل يشعر بثقتك في المنتج",
        "🤝 **امنح خيارات:** دائماً قدم بديلين أو ثلاثة",
        "📞 **تابع:** اتصل بالعميل بعد البيع - يبني الثقة",
        "🎁 **قدم قيمة:** أضف نصيحة أو معلومة مفيدة مجاناً",
        "⏰ **احترم الوقت:** لا تؤجل - نفذ الآن",
        "✍️ **وثق:** سجل ملاحظات عن تفضيلات كل عميل",
        "🌟 **تميز:** افعل شيئاً يتوقعه - ويفاجئ به!"
    ]
    
    return secrets.choice(tips)


# ===== Consolidated from: specialized/tax_system.py =====
"""
💰 النظام الضريبي في الإمارات - UAE Tax System
"""

UAE_TAX_SYSTEM = {
    'vat': {
        'name_ar': 'ضريبة القيمة المضافة',
        'name_en': 'VAT - Value Added Tax',
        'rate': 5,
        'description': 'ضريبة القيمة المضافة في الإمارات بنسبة 5%',
        'registration_threshold': 375000,  # AED
        'voluntary_threshold': 187500,  # AED
        'exemptions': [
            'الخدمات المالية (بعضها)',
            'الرعاية الصحية (بعضها)',
            'التعليم (بعضها)',
            'النقل الدولي',
            'بيع وإيجار العقارات السكنية'
        ],
        'zero_rated': [
            'الصادرات خارج دول الخليج',
            'النقل الدولي',
            'خدمات النقل الدولي',
            'بعض الأدوية والمعدات الطبية'
        ]
    },
    'corporate_tax': {
        'name_ar': 'ضريبة الشركات',
        'name_en': 'Corporate Tax',
        'effective_date': '2023-06-01',
        'rates': {
            'small_business': {'threshold': 375000, 'rate': 0},
            'standard': {'threshold': 'above_375000', 'rate': 9}
        },
        'description': 'ضريبة على أرباح الشركات بنسبة 9% للأرباح التي تزيد عن 375,000 درهم'
    },
    'excise_tax': {
        'name_ar': 'الضريبة الانتقائية',
        'name_en': 'Excise Tax',
        'items': {
            'tobacco': 100,
            'energy_drinks': 100,
            'soft_drinks': 50,
            'electronic_smoking': 100,
            'sweetened_drinks': 50
        }
    }
}

def get_tax_advice(question):
    """نصائح ضريبية"""
    q_lower = question.lower()
    
    if 'ضريبة' in q_lower or 'vat' in q_lower:
        if 'نسبة' in q_lower or 'كم' in q_lower:
            return """💰 **الضرائب في الإمارات:**

📊 **ضريبة القيمة المضافة (VAT):** 5%
• تُطبق على معظم السلع والخدمات
• التسجيل إلزامي للإيرادات > 375,000 درهم
• التسجيل اختياري للإيرادات > 187,500 درهم

🏢 **ضريبة الشركات:** 9%
• على الأرباح التي تزيد عن 375,000 درهم
• سارية من يونيو 2023
• الأرباح حتى 375,000 درهم معفاة

📝 **مثال حسابي:**
• قيمة البضاعة: 100,000 درهم
• ضريبة القيمة المضافة: 5,000 درهم
• الإجمالي: 105,000 درهم"""
        
        return "اسألني بشكل أوضح عن الضرائب"
    
    return "اسألني عن الضرائب بشكل أوضح"


# ===== Consolidated from: specialized/system_guide.py =====
"""
📚 دليل النظام - System Guide
مصطلحات النظام ودليل المستخدم
"""

# مصطلحات النظام
SYSTEM_TERMS = {
    'sales': {
        'invoice': 'فاتورة',
        'quote': 'عرض سعر',
        'sale': 'مبيعات',
        'discount': 'خصم',
        'tax': 'ضريبة',
        'total': 'الإجمالي',
        'paid': 'مدفوع',
        'balance': 'رصيد مستحق',
        'payment_method': 'طريقة الدفع'
    },
    'customers': {
        'customer': 'عميل/زبون',
        'individual': 'عميل عادي',
        'merchant': 'تاجر',
        'partner': 'شريك',
        'vip': 'عميل مميز',
        'credit_limit': 'حد ائتماني',
        'statement': 'كشف حساب'
    },
    'inventory': {
        'product': 'منتج/قطعة',
        'stock': 'مخزون',
        'warehouse': 'مستودع',
        'movement': 'حركة',
        'in': 'وارد/دخول',
        'out': 'صادر/خروج',
        'adjustment': 'تعديل',
        'low_stock': 'مخزون منخفض',
        'out_of_stock': 'نفذ من المخزون'
    },
    'accounting': {
        'ledger': 'دفتر الأستاذ',
        'journal': 'يومية',
        'debit': 'مدين',
        'credit': 'دائن',
        'asset': 'أصل',
        'liability': 'التزام',
        'equity': 'حقوق ملكية',
        'revenue': 'إيراد',
        'expense': 'مصروف',
        'profit': 'ربح',
        'loss': 'خسارة'
    }
}

# دليل المستخدم
USER_GUIDE = {
    'getting_started': [
        '1. سجل دخولك بحسابك',
        '2. ابدأ من لوحة التحكم - تعطيك نظرة شاملة',
        '3. أضف منتجاتك من قائمة "المنتجات"',
        '4. أضف عملاءك من قائمة "العملاء"',
        '5. ابدأ بإنشاء فاتورة من "مبيعات > فاتورة جديدة"'
    ],
    'sales_process': [
        '1. اختر العميل',
        '2. اختر العملة (AED, USD, EUR)',
        '3. سيظهر سعر الصرف تلقائياً (يمكن تعديله)',
        '4. أضف المنتجات (سيحسب السعر حسب نوع العميل)',
        '5. أضف خصم أو شحن أو ضريبة (إن لزم)',
        '6. اختر طريقة الدفع (ستظهر الحقول المناسبة)',
        '7. احفظ الفاتورة',
        '8. اطبعها وسلمها للعميل'
    ],
    'warehouse_management': [
        '1. راقب مؤشرات المخزون البصرية',
        '2. الأحمر = نفذ → اطلب فوراً',
        '3. الأصفر = منخفض → خطط للطلب',
        '4. الأخضر = جيد → استمر',
        '5. استخدم الفلاتر الذكية للبحث السريع',
        '6. راجع حركات المخزون من "المستودعات > الحركات"',
        '7. اطلب شراء من "مشتريات > طلب جديد"'
    ],
    'reports': [
        '1. تقرير المبيعات: الإيرادات والفواتير',
        '2. تقرير المشتريات: التكاليف والموردين',
        '3. تقرير المخزون: الكميات والقيم',
        '4. كشف حساب العميل: الذمم المدينة',
        '5. الميزانية: الوضع المالي الشامل',
        '6. قائمة الدخل: الأرباح والخسائر'
    ]
}

def get_system_guide():
    """دليل النظام"""
    return """📚 **دليل الاستخدام السريع:**

🚀 **البدء:**
""" + "\n".join(USER_GUIDE['getting_started']) + """

📝 **إنشاء فاتورة:**
""" + "\n".join(USER_GUIDE['sales_process'][:5])


# ===== Consolidated from: specialized/security_rules.py =====
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


# ===== Consolidated from: specialized/advanced_laws.py =====
"""
⚖️ القوانين المتقدمة - Advanced Laws Knowledge
أزاد يعرف القوانين الضريبية والشحن في المنطقة
"""

from datetime import datetime


class AdvancedLaws:
    """معرفة القوانين المتقدمة لأزاد"""
    
    # القوانين الضريبية الفلسطينية
    PALESTINIAN_TAX_LAWS = {
        'vat_rate': 16,
        'income_tax_rates': {
            'individual': {
                '0-48000': 0,
                '48001-96000': 5,
                '96001-192000': 10,
                '192001-384000': 15,
                '384001+': 20
            },
            'corporate': {
                'standard': 15
            }
        },
        'customs_duties': {
            'agricultural': 10,
            'industrial': 15,
            'luxury': 30
        },
        'special_regulations': [
            'الإعفاء الضريبي للمشاريع الصغيرة والمتوسطة',
            'الضرائب على الاستيراد والتصدير',
            'الضرائب على الخدمات المالية'
        ]
    }
    
    # القوانين الضريبية الإسرائيلية
    ISRAELI_TAX_LAWS = {
        'vat_rate': 17,
        'income_tax_rates': {
            'individual': {
                '0-77480': 10,
                '77481-110880': 14,
                '110881-178080': 20,
                '178081-247440': 31,
                '247441-514920': 35,
                '514921+': 47
            },
            'corporate': {
                'standard': 23
            }
        },
        'customs_duties': {
            'agricultural': 12,
            'industrial': 18,
            'luxury': 35
        },
        'special_regulations': [
            'قانون ضريبة القيمة المضافة',
            'الضرائب على الأرباح الرأسمالية',
            'الضرائب على الميراث والهبات'
        ]
    }
    
    # قوانين الخليج
    GULF_TAX_LAWS = {
        'uae': {
            'vat_rate': 5,
            'corporate_tax_rate': 9,
            'excise_tax': {
                'tobacco': 100,
                'energy_drinks': 100,
                'soft_drinks': 50
            }
        },
        'saudi': {
            'vat_rate': 15,
            'corporate_tax_rate': 20,
            'zakat_rate': 2.5
        },
        'kuwait': {
            'vat_rate': 0,  # لم تطبق بعد
            'corporate_tax_rate': 15
        },
        'qatar': {
            'vat_rate': 0,  # لم تطبق بعد
            'corporate_tax_rate': 10
        }
    }
    
    # قوانين الشحن والتخليص
    SHIPPING_LAWS = {
        'documentation_required': [
            'فاتورة تجارية',
            'قائمة تعبئة',
            'شهادة منشأ',
            'وثيقة نقل',
            'تأمين الشحن'
        ],
        'customs_procedures': {
            'declaration': 'إقرار جمركي',
            'inspection': 'فحص جمركي',
            'duty_calculation': 'حساب الرسوم',
            'clearance': 'تخليص جمركي'
        },
        'restricted_items': [
            'الأسلحة والذخيرة',
            'المخدرات والمواد المخدرة',
            'المواد المتفجرة',
            'المنتجات الغذائية غير المعتمدة',
            'الأدوية غير المرخصة'
        ],
        'duty_free_allowances': {
            'personal_effects': 'الأغراض الشخصية',
            'gifts_under_value': 'الهدايا تحت قيمة معينة',
            'diplomatic_items': 'الأغراض الدبلوماسية'
        }
    }
    
    # قوانين جودة البضائع
    QUALITY_LAWS = {
        'standards_organizations': {
            'uae': 'هيئة الإمارات للمواصفات والمقاييس',
            'saudi': 'الهيئة السعودية للمواصفات والمقاييس',
            'kuwait': 'معهد الكويت للأبحاث العلمية',
            'qatar': 'هيئة التقييس لدول مجلس التعاون'
        },
        'certification_required': [
            'شهادة مطابقة للمواصفات',
            'شهادة منشأ',
            'شهادة جودة',
            'شهادة سلامة'
        ],
        'quality_marks': {
            'halal': 'حلال',
            'organic': 'عضوي',
            'iso_9001': 'نظام إدارة الجودة',
            'iso_14001': 'نظام الإدارة البيئية'
        }
    }
    
    @staticmethod
    def get_tax_info(country, tax_type):
        """الحصول على معلومات ضريبية"""
        if country.lower() in ['palestine', 'فلسطين']:
            laws = AdvancedLaws.PALESTINIAN_TAX_LAWS
        elif country.lower() in ['israel', 'اسرائيل']:
            laws = AdvancedLaws.ISRAELI_TAX_LAWS
        elif country.lower() in ['uae', 'الامارات', 'دبي']:
            laws = AdvancedLaws.GULF_TAX_LAWS['uae']
        elif country.lower() in ['saudi', 'السعودية']:
            laws = AdvancedLaws.GULF_TAX_LAWS['saudi']
        else:
            return None
        
        if tax_type.lower() == 'vat':
            return f"ضريبة القيمة المضافة: {laws['vat_rate']}%"
        elif tax_type.lower() == 'corporate':
            if 'corporate_tax_rate' in laws:
                return f"ضريبة الشركات: {laws['corporate_tax_rate']}%"
            elif 'income_tax_rates' in laws:
                return f"ضريبة الشركات: {laws['income_tax_rates']['corporate']['standard']}%"
        
        return "معلومات ضريبية غير متاحة"
    
    @staticmethod
    def get_shipping_info(shipping_type):
        """الحصول على معلومات الشحن"""
        if shipping_type.lower() in ['sea', 'بحر', 'بحري']:
            return """
            الشحن البحري:
            • أبطأ وأرخص طريقة
            • مناسبة للبضائع الكبيرة
            • يحتاج 15-30 يوم
            • رسوم أقل
            """
        elif shipping_type.lower() in ['air', 'جو', 'جوي']:
            return """
            الشحن الجوي:
            • أسرع طريقة
            • مناسبة للبضائع القيمة
            • يحتاج 3-7 أيام
            • رسوم أعلى
            """
        elif shipping_type.lower() in ['land', 'بر', 'بري']:
            return """
            الشحن البري:
            • متوسط السرعة والسعر
            • مناسبة للمنطقة
            • يحتاج 5-15 يوم
            • رسوم متوسطة
            """
        
        return "نوع الشحن غير محدد"
    
    @staticmethod
    def get_customs_info(country):
        """الحصول على معلومات جمركية"""
        if country.lower() in ['uae', 'الامارات']:
            return """
            التخليص الجمركي في الإمارات:
            • رسوم جمركية: 5%
            • ضريبة القيمة المضافة: 5%
            • وثائق مطلوبة: فاتورة تجارية، قائمة تعبئة، شهادة منشأ
            • وقت التخليص: 1-3 أيام عمل
            """
        elif country.lower() in ['saudi', 'السعودية']:
            return """
            التخليص الجمركي في السعودية:
            • رسوم جمركية: متغيرة حسب السلعة
            • ضريبة القيمة المضافة: 15%
            • وثائق مطلوبة: فاتورة تجارية، شهادة منشأ، شهادة حلال (إن وجدت)
            • وقت التخليص: 2-5 أيام عمل
            """
        
        return "معلومات جمركية غير متاحة لهذا البلد"
    
    @staticmethod
    def get_quality_standards(product_category):
        """الحصول على معايير الجودة"""
        if product_category.lower() in ['food', 'طعام', 'غذاء']:
            return """
            معايير جودة الأغذية:
            • شهادة حلال
            • تاريخ انتهاء الصلاحية
            • شهادة صحية
            • معايير التغليف
            """
        elif product_category.lower() in ['electronics', 'إلكترونيات']:
            return """
            معايير جودة الإلكترونيات:
            • شهادة CE
            • شهادة FCC
            • شهادة السلامة
            • معايير الطاقة
            """
        elif product_category.lower() in ['textiles', 'أقمشة', 'ملابس']:
            return """
            معايير جودة المنسوجات:
            • شهادة الجودة
            • معايير الألوان
            • معايير المقاسات
            • شهادة السلامة
            """
        
        return "معايير جودة عامة: شهادة ISO 9001، شهادة منشأ، شهادة سلامة"


# إنشاء مثيل عالمي
advanced_laws = AdvancedLaws()


# ===== Consolidated from: specialized/user_guide.py =====
"""
Complete User Guide - دليل المستخدم الكامل
"""

QUICK_START = """
# البداية السريعة

## تسجيل الدخول:
1. افتح المتصفح
2. اذهب إلى عنوان النظام
3. أدخل اسم المستخدم وكلمة المرور
4. اضغط دخول

## أول استخدام:

### الخطوة 1: إضافة منتجات
**المسار**: المنتجات → إضافة منتج

املأ:
- الاسم
- SKU (مثال: PART-001)
- السعر العادي
- الكمية الأولية

### الخطوة 2: إضافة زبون
**المسار**: الزبائن → إضافة زبون

املأ:
- الاسم
- الهاتف
- نوع الزبون (عادي)

### الخطوة 3: أول فاتورة
**المسار**: المبيعات → فاتورة جديدة

1. اختر الزبون
2. أضف منتج
3. أدخل الكمية
4. اختر طريقة الدفع: نقدي
5. أدخل المبلغ المدفوع
6. احفظ

### الخطوة 4: طباعة الفاتورة
- اضغط زر "طباعة"
- ستفتح نافذة جديدة
- اطبع أو احفظ PDF

## نصائح للبداية:
✅ ابدأ بمنتجات قليلة
✅ جرب البحث والفلاتر
✅ اطبع فاتورة تجريبية
✅ تعرف على اختصارات لوحة المفاتيح (اضغط ?)
"""

DAILY_OPERATIONS = """
# العمليات اليومية

## صباحاً:
1. **فتح النظام**
2. **مراجعة لوحة التحكم**:
   - مبيعات الأمس
   - المخزون المنخفض
   - الفواتير المعلقة

3. **تحضير الكاشير**:
   - فتح سند قبض
   - رصيد البداية

## خلال اليوم:

### البيع للزبون Walk-in:
1. فاتورة جديدة
2. اختر "زبون عام" أو أضف جديد
3. امسح الباركود أو ابحث عن المنتج
4. أدخل الكمية
5. اطبع واحفظ

### البيع لزبون مسجل:
1. فاتورة جديدة
2. ابحث عن الزبون (بالاسم أو الهاتف)
3. أضف المنتجات
4. اختر "آجل" إذا لم يدفع
5. احفظ

### استقبال دفعة:
1. سندات القبض → إضافة سند
2. اختر الزبون
3. اختر الفاتورة
4. أدخل المبلغ
5. احفظ

### إرجاع منتج:
1. المبيعات → عرض الفاتورة
2. إرجاع
3. اختر المنتجات للإرجاع
4. أدخل السبب
5. احفظ (سترجع للمخزون تلقائياً)

## نهاية اليوم:
1. **طباعة تقرير المبيعات**
2. **مراجعة الكاش**
3. **جرد سريع للمنتجات المهمة**
4. **حفظ نسخة احتياطية** (تلقائي)
"""

COMMON_TASKS = """
# المهام الشائعة

## 1. تعديل سعر منتج:
- المنتجات → عرض المنتج → تعديل
- غيّر السعر
- احفظ

## 2. إضافة كمية للمخزون:
**الطريقة الأولى** (سريعة):
- في صفحة المنتجات
- اضغط زر "إضافة كمية"
- أدخل الكمية والسبب
- احفظ

**الطريقة الثانية** (من مشتريات):
- المشتريات → إضافة مشترية
- أضف المنتجات
- ستزيد تلقائياً

## 3. عمل خصم للزبون:
- في الفاتورة
- أدخل نسبة الخصم % أو المبلغ
- سيُحسب تلقائياً

## 4. تقسيط الدفع:
- أنشئ الفاتورة
- اختر "دفع جزئي"
- أدخل المبلغ المدفوع
- الباقي يصبح رصيد على الزبون
- ادفع لاحقاً من سندات القبض

## 5. البحث السريع:
- اضغط `Ctrl + K`
- ابحث عن أي شيء
- Enter للانتقال

## 6. طباعة كشف حساب:
- الزبائن → عرض الزبون → كشف حساب
- اطبع أو صدّر PDF

## 7. تصدير تقرير لـ Excel:
- افتح التقرير
- اضغط زر "Excel" أو `Ctrl + E`
- سيُحمّل تلقائياً
"""

ADVANCED_FEATURES = """
# المميزات المتقدمة

## 1. دفتر الأستاذ:

### عرض حساب معين:
- دفتر الأستاذ → حساب معين
- اختر الحساب (مثل: Cash)
- سترى كل الحركات

### ميزان المراجعة:
- دفتر الأستاذ → ميزان المراجعة
- يعرض كل الحسابات
- المدين والدائن يجب يتساويان

## 2. المستودعات المتعددة:

### نقل بين مستودعات:
- (قريباً)

### تقرير مخزون حسب المستودع:
- المستودعات → المخزون
- فلتر حسب المستودع

## 3. العملات المتعددة:

### سعر الصرف:
- يُحمّل تلقائياً من API
- يُخزن في جدول `exchange_rates`
- يُحدّث يومياً

### التقارير:
- كل المبالغ بـ AED
- لا خلط للعملات

## 4. المساعد الذكي (أزاد):

### الأسئلة الممكنة:
- "ما هو رصيد زبون [الاسم]؟"
- "كم مبيعات اليوم؟"
- "ما هي المنتجات الناقصة؟"
- "كيف أضيف زبون جديد؟"
- "ما هو الرقم الضريبي؟"

### توليد المستندات:
- "أنشئ تقرير المبيعات لهذا الشهر"
- "صدّر قائمة الزبائن"

### التحليل والتنبؤات:
- "توقع مبيعات الشهر القادم"
- "ما هي أكثر المنتجات مبيعاً؟"
- "أي زبون لديه أعلى رصيد؟"

## 5. الوضع الداكن:
- اضغط أيقونة القمر 🌙
- يحفظ تلقائياً
- مريح للعيون ليلاً

## 6. الأرشفة:
- **Owner فقط**
- حذف soft (قابل للاستعادة)
- حذف hard (نهائي - خطير!)
"""

REPORTING_GUIDE = """
# دليل التقارير الشامل

## التقارير المالية:

### 1. تقرير المبيعات اليومي:
**الاستخدام**: نهاية كل يوم
**يعرض**:
- إجمالي المبيعات
- عدد الفواتير
- المبلغ المحصّل
- المعلّق
- الربح

### 2. تقرير الذمم الشهري:
**الاستخدام**: نهاية كل شهر
**يعرض**:
- الزبائن المدينون
- المبالغ المستحقة
- عمر الدين
- توقعات التحصيل

### 3. تقرير المخزون:
**الاستخدام**: نهاية الشهر أو الربع
**يعرض**:
- قيمة المخزون
- المنتجات الراكدة
- المنتجات السريعة البيع
- الدوران (Turnover)

### 4. قائمة الدخل:
**الاستخدام**: شهري، ربع سنوي، سنوي
**يعرض**:
- الإيرادات
- تكلفة البضاعة المباعة
- إجمالي الربح
- المصروفات
- صافي الربح

### 5. الميزانية العمومية:
**الاستخدام**: نهاية السنة المالية
**يعرض**:
- الأصول (نقد، مخزون، ذمم)
- الخصوم (ديون، ذمم دائنة)
- حقوق الملكية (رأس المال، الأرباح)

## نصائح:
✅ صدّر التقارير شهرياً
✅ احتفظ بنسخ للمراجعة
✅ قارن الشهر الحالي مع السابق
✅ راقب الاتجاهات (Trends)
"""

# دليل شامل (user_guide version, aliased as USER_GUIDE_FULL for backward compat)
_USER_GUIDE_FULL = {
    'quick_start': QUICK_START,
    'daily_operations': DAILY_OPERATIONS,
    'common_tasks': COMMON_TASKS,
    'advanced': ADVANCED_FEATURES,
    'reporting': REPORTING_GUIDE,
}

def get_guide(topic):
    """الحصول على دليل معين"""
    return _USER_GUIDE_FULL.get(topic, "الموضوع غير موجود")

def get_help_for_task(task):
    """الحصول على مساعدة لمهمة محددة"""
    task = task.lower()
    
    # بحث في كل الأدلة
    for guide_name, content in _USER_GUIDE_FULL.items():
        if task in content.lower():
            return content
    
    return "لم أجد مساعدة لهذه المهمة. يمكنك سؤالي بطريقة أخرى!"

# Backward-compatible aliases
USER_GUIDE_FULL = _USER_GUIDE_FULL

