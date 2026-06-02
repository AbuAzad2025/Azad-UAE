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
