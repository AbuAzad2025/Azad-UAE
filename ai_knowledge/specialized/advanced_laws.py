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
