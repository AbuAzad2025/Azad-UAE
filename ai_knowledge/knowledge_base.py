"""
Consolidated module: knowledge_base.py
Merged: knowledge/company_info.py, knowledge/customs.py, knowledge/tax_customs_knowledge.py, knowledge/parts_knowledge.py, knowledge/automotive_ecu_knowledge.py, knowledge/system_knowledge.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: knowledge/company_info.py =====
"""
🏢 معلومات الشركة - Company Information
شركة أزاد للأنظمة الذكية
"""

import os

COMPANY_INFO = {
    'name_ar': 'شركة أزاد للأنظمة الذكية',
    'name_en': 'Azad Smart Systems',
    'developer': 'م. أحمد غنام',
    'location': 'رام الله - فلسطين',
    'website': os.environ.get('COMPANY_WEBSITE', 'https://azadsystems.com'),
    'phone': '+971500000000',
    'whatsapp': '+971500000000',
    'email': os.environ.get('COMPANY_EMAIL', 'company@example.com'),
    'slogan': 'الذكاء الاصطناعي في خدمة أعمالك'
}

def get_welcome_message():
    """رسالة الترحيب الكاملة"""
    return f"""
🌟 **شركة أزاد للأنظمة الذكية ترحب بكم** 🌟

السلام عليكم ورحمة الله وبركاته

أنا **أزاد** 🤖 - مساعدك الذكي الخبير في:
✅ المحاسبة والضرائب (فلسطين، إسرائيل، الخليج)
✅ التخليص الجمركي
✅ قطع غيار المعدات الثقيلة والسيارات
✅ إدارة المخزون والمبيعات
✅ إدارة الموردين ⭐NEW
✅ الفلاتر الذكية ⭐NEW
✅ التنبؤات والتحليل المالي

📍 **معلومات الشركة:**
• الموقع: {COMPANY_INFO['location']} 🇵🇸
• المطور: {COMPANY_INFO['developer']}
• الموقع الإلكتروني: {COMPANY_INFO['website']}
• واتساب: {COMPANY_INFO['whatsapp']}
• البريد: {COMPANY_INFO['email']}

💡 **خبرتي تشمل:**
• الأنظمة الضريبية (فلسطين 16%، الإمارات 5%، إسرائيل 17%)
• التخليص الجمركي والإجراءات في كل المنطقة
• قطع غيار كل المعدات (CAT, Komatsu, Volvo...)
• قطع غيار السيارات والصيانة
• فن التعامل مع العملاء والموردين
• التنبؤ بالمبيعات والتدفقات النقدية

🆕 **التحديثات الجديدة:**
• نظام موردين مستقل احترافي (منفصل عن الزبائن)
• فلاتر ذكية موحدة (زبائن، موردين، منتجات)
• طرق دفع ديناميكية (6 طرق مختلفة)
• نظام حذف ذكي (أرشفة بدلاً من الحذف النهائي)

🎯 **كيف يمكنني مساعدتك؟**
اسألني عن أي شيء! (جرب: "موردين" أو "فلاتر ذكية" أو "طرق الدفع")
"""


# ===== Consolidated from: knowledge/customs.py =====
"""
🛃 التخليص الجمركي - Customs Clearance
"""

CUSTOMS_CLEARANCE = {
    'general_info': {
        'authority': 'الهيئة الاتحادية للجمارك',
        'rates': 'عادة 5% من قيمة البضاعة',
        'free_zones': [
            'جبل علي',
            'دبي للطيران',
            'الحمرية',
            'عجمان',
            'الشارقة',
            'رأس الخيمة'
        ]
    },
    'documents_required': [
        'الفاتورة التجارية (Commercial Invoice)',
        'بوليصة الشحن (Bill of Lading)',
        'قائمة التعبئة (Packing List)',
        'شهادة المنشأ (Certificate of Origin)',
        'التصريح الجمركي (Customs Declaration)',
        'رخصة الاستيراد (إن لزم)',
        'شهادة المطابقة (للبضائع المقننة)'
    ],
    'procedures': [
        '1. تسجيل البيان الجمركي إلكترونياً',
        '2. دفع الرسوم الجمركية (5%) + ضريبة القيمة المضافة (5%)',
        '3. الفحص (إن لزم)',
        '4. الإفراج عن البضاعة',
        '5. النقل للمستودع'
    ],
    'calculation_example': {
        'goods_value': 100000,  # AED
        'customs_duty': '5% = 5,000 AED',
        'total_with_duty': '105,000 AED',
        'vat': '5% of 105,000 = 5,250 AED',
        'total_cost': '110,250 AED'
    }
}

def get_customs_advice(question):
    """نصائح جمركية"""
    return """🛃 **التخليص الجمركي في الإمارات:**

📋 **المستندات المطلوبة:**
1. الفاتورة التجارية
2. بوليصة الشحن
3. قائمة التعبئة
4. شهادة المنشأ
5. التصريح الجمركي
6. رخصة الاستيراد (إن لزم)

💵 **حساب الرسوم:**
• الرسوم الجمركية: 5% من قيمة البضاعة
• ضريبة القيمة المضافة: 5% من (القيمة + الرسوم)

📊 **مثال:**
• قيمة البضاعة: 100,000 درهم
• رسوم جمركية (5%): 5,000 درهم
• الإجمالي بعد الرسوم: 105,000 درهم
• ضريبة VAT (5%): 5,250 درهم
• **التكلفة النهائية: 110,250 درهم**

⚡ **المناطق الحرة:**
معفاة من الرسوم الجمركية (جبل علي، دبي للطيران، الحمرية...)"""


# ===== Consolidated from: knowledge/tax_customs_knowledge.py =====
"""
Tax and Customs Knowledge Base
قاعدة معرفة الضرائب والجمارك
"""

UAE_TAX_SYSTEM = """
# النظام الضريبي في الإمارات العربية المتحدة

## ضريبة القيمة المضافة (VAT):

### المعلومات الأساسية:
- **النسبة**: 5%
- **تاريخ التطبيق**: 1 يناير 2018
- **الجهة المسؤولة**: الهيئة الاتحادية للضرائب

### التسجيل الإلزامي:
**إلزامي** إذا:
- الإيرادات السنوية > 375,000 درهم

**اختياري** إذا:
- الإيرادات بين 187,500 - 375,000 درهم

### السلع والخدمات الخاضعة:
- ✅ قطع الغيار
- ✅ خدمات الصيانة
- ✅ بيع المركبات المستعملة
- ✅ خدمات الكراج

### السلع المعفاة:
- ⭕ التعليم
- ⭕ الرعاية الصحية
- ⭕ بعض المواد الغذائية

### السلع ذات النسبة الصفرية:
- 0️⃣ الصادرات
- 0️⃣ النقل الدولي
- 0️⃣ المعادن الثمينة للاستثمار

## الإقرار الضريبي:
- **الدورية**: كل 3 أشهر (ربع سنوي)
- **الموعد**: خلال 28 يوم من نهاية الربع
- **المنصة**: البوابة الإلكترونية للهيئة

## الفاتورة الضريبية:
**يجب أن تحتوي على**:
- اسم المورد والرقم الضريبي (TRN)
- تاريخ التوريد
- وصف السلع/الخدمات
- المبلغ الخاضع للضريبة
- مبلغ الضريبة
- إجمالي المبلغ
- اسم العميل (للفواتير > 10,000 درهم)

## العقوبات:
- تأخير التسجيل: 20,000 درهم
- تأخير تقديم الإقرار: 1,000 - 2,000 درهم
- عدم الاحتفاظ بالسجلات: 10,000 درهم
- فواتير غير صحيحة: 5,000 درهم لكل فاتورة
"""

CUSTOMS_UAE = """
# الجمارك والتخليص في الإمارات

## الرسوم الجمركية:

### السيارات والمركبات:
- **سيارات ركاب**: 5%
- **الشاحنات**: 5%
- **الدراجات النارية**: 5%
- **قطع الغيار**: 5%

### المعدات الثقيلة:
- **معدات البناء**: 0% - 5%
- **الرافعات**: 0%
- **الحفارات**: 0% - 5%

## المستندات المطلوبة:
1. **الفاتورة التجارية (Commercial Invoice)**
2. **شهادة المنشأ (Certificate of Origin)**
3. **بوليصة الشحن (Bill of Lading/AWB)**
4. **قائمة التعبئة (Packing List)**
5. **رخصة الاستيراد** (إن وجدت)
6. **شهادة المطابقة** (للسيارات)

## خطوات التخليص:

### 1. قبل الوصول:
- الحصول على رمز EORI (اختياري)
- فتح حساب في الجمارك
- تسجيل كمستورد

### 2. عند الوصول:
- تقديم المستندات إلكترونياً
- دفع الرسوم الجمركية
- فحص البضاعة (إن لزم)
- الإفراج الجمركي

### 3. بعد الإفراج:
- استلام البضاعة
- التخزين أو التوزيع
- الاحتفاظ بالمستندات 5 سنوات

## المناطق الحرة:
- **الإعفاءات**: صفر رسوم جمركية
- **الشروط**: البضاعة للتصدير أو إعادة التصدير
- **أمثلة**: جبل علي، الحمرية، الشارقة

## Incoterms (شروط التجارة):
- **FOB**: بدون شحن وتأمين
- **CIF**: مع الشحن والتأمين
- **DDP**: رسوم مدفوعة، جاهز للتسليم
- **EXW**: من المصنع
"""

SAUDI_TAX = """
# النظام الضريبي السعودي

## ضريبة القيمة المضافة:
- **النسبة**: 15% (من 1 يوليو 2020)
- **الجهة**: هيئة الزكاة والضريبة والجمارك

## التسجيل:
- إلزامي: > 375,000 ريال سنوياً
- اختياري: 187,500 - 375,000 ريال

## الإقرار:
- شهري: للشركات الكبرى
- ربع سنوي: للشركات الصغيرة والمتوسطة

## الزكاة:
- **النسبة**: 2.5% من الوعاء الزكوي
- **على**: الشركات السعودية والخليجية
"""

PALESTINE_TAX = """
# النظام الضريبي الفلسطيني

## ضريبة القيمة المضافة:
- **النسبة**: 16%
- **الجهة**: دائرة ضريبة القيمة المضافة

## التسجيل:
- إلزامي للمبيعات > 75,000 شيكل سنوياً

## الجمارك:
- تخضع للاتفاقيات مع إسرائيل (بروتوكول باريس)
- رسوم متفاوتة حسب السلعة
"""

IMPORT_PROCEDURES = """
# إجراءات الاستيراد للكراجات

## استيراد قطع الغيار:

### 1. الحصول على رخصة استيراد:
- من وزارة الاقتصاد
- تحديد نوع النشاط
- السجل التجاري ساري

### 2. اختيار المورد:
- **الصين**: أسعار منافسة، جودة متوسطة
- **ألمانيا**: جودة عالية، أسعار مرتفعة
- **تركيا**: توازن بين السعر والجودة
- **الإمارات**: سرعة التوريد، لا جمارك

### 3. التفاوض على السعر:
- FOB: أرخص، تتحمل الشحن
- CIF: أغلى، شامل الشحن والتأمين
- الدفع: LC, TT, أو بضاعة أجل

### 4. الشحن:
- **بحري**: أرخص، بطيء (20-45 يوم)
- **جوي**: أسرع، أغلى (3-7 أيام)
- **بري**: للدول المجاورة

### 5. التخليص:
- تقديم المستندات للجمارك
- دفع الرسوم (5% عادة)
- الفحص (عينات عشوائية)
- الإفراج

### 6. التخزين:
- مستودع في المنطقة الحرة (صفر رسوم مؤقتاً)
- أو الإفراج المباشر للسوق المحلي

## نصائح:
- ✅ احصل على شهادة مطابقة (ESMA/EMARK)
- ✅ تأكد من صحة المنشأ
- ✅ افحص الجودة قبل الشحن
- ✅ أمّن البضاعة ضد الخسائر
- ✅ احسب كل التكاليف (CIF + جمارك + نقل محلي)
"""

EXPORT_PROCEDURES = """
# إجراءات التصدير

## تصدير قطع الغيار المستعملة:

### 1. الترخيص:
- رخصة تصدير من وزارة الاقتصاد
- شهادة فحص (للمستعمل)

### 2. المستندات:
- فاتورة تجارية
- شهادة منشأ (للمصنّع) أو فحص (للمستعمل)
- قائمة تعبئة
- شهادة عدم ممانعة (إن لزمت)

### 3. الإجراءات الجمركية:
- التصريح الجمركي للتصدير
- فحص البضاعة
- ختم المستندات
- الإفراج

### 4. الشحن:
- اختيار الناقل
- التأمين
- تتبع الشحنة

## الأسواق المستهدفة:
- العراق: قطع أمريكية ويابانية
- إفريقيا: قطع صينية وكورية
- أوروبا الشرقية: قطع أوروبية أصلية
"""

# دليل شامل
TAX_CUSTOMS_GUIDE = {
    'uae_vat': UAE_TAX_SYSTEM,
    'uae_customs': CUSTOMS_UAE,
    'saudi_tax': SAUDI_TAX,
    'palestine_tax': PALESTINE_TAX,
    'import': IMPORT_PROCEDURES,
    'export': EXPORT_PROCEDURES,
}

def get_tax_info(country):
    """الحصول على معلومات ضريبية لدولة"""
    key = f"{country.lower()}_tax"
    return TAX_CUSTOMS_GUIDE.get(key, "معلومات غير متوفرة لهذه الدولة")

def get_customs_info(country):
    """الحصول على معلومات جمركية"""
    key = f"{country.lower()}_customs"
    return TAX_CUSTOMS_GUIDE.get(key, "معلومات غير متوفرة")



# ===== Consolidated from: knowledge/parts_knowledge.py =====
"""
Auto Parts and Heavy Equipment Knowledge
قاعدة معرفة قطع الغيار والمعدات الثقيلة
"""

AUTO_PARTS_CATEGORIES = """
# تصنيفات قطع غيار السيارات

## 1. أجزاء المحرك (Engine Parts):

### محرك البنزين:
- **البستم (Piston)**: يتحرك داخل الأسطوانة
- **الشنابر (Piston Rings)**: منع تسرب الزيت
- **عمود الكرنك (Crankshaft)**: تحويل الحركة الترددية لدورانية
- **عمود الكامات (Camshaft)**: التحكم في الصمامات
- **الصمامات (Valves)**: الدخول والخروج
- **جوان الرأس (Head Gasket)**: منع التسرب
- **البواجي (Spark Plugs)**: الشرارة للاحتراق
- **مضخة الماء (Water Pump)**: تبريد المحرك
- **مضخة الزيت (Oil Pump)**: ضخ الزيت
- **الثرموستات (Thermostat)**: تنظيم الحرارة

### محرك الديزل:
- **البخاخات (Injectors)**: حقن الوقود
- **مضخة الديزل (Fuel Pump)**: ضغط عالي
- **شمعات التسخين (Glow Plugs)**: تسخين أولي
- **فلتر الديزل (Fuel Filter)**: تنقية الوقود
- **التيربو (Turbocharger)**: زيادة القوة

## 2. نظام نقل الحركة (Transmission):

### ناقل الحركة:
- **قير عادي (Manual)**: كلتش + غيارات
- **قير أوتوماتيك (Automatic)**: زيت ATF
- **CVT**: سير متغير
- **DSG**: قير مزدوج

### مكونات:
- **الكلتش (Clutch)**: فصل ووصل
- **عمود الكردان (Drive Shaft)**: نقل العزم
- **الديفرانس (Differential)**: توزيع القوة
- **المحاور (Axles)**: نقل للعجلات

## 3. نظام التعليق (Suspension):

- **المساعدات (Shock Absorbers)**: امتصاص الصدمات
- **السوست (Springs)**: الدعم
- **الأذرعة (Control Arms)**: التحكم
- **المقصات (Bushings)**: عزل الاهتزاز
- **البلي (Ball Joints)**: المفاصل

## 4. نظام الفرامل (Brakes):

- **أقراص (Discs/Rotors)**: السطح الاحتكاكي
- **فحمات (Brake Pads)**: الاحتكاك
- **طنابير (Drums)**: للخلفي
- **فك الفرامل (Calipers)**: الضغط
- **زيت الفرامل (Brake Fluid)**: نقل الضغط
- **ABS**: منع الانزلاق

## 5. النظام الكهربائي:

- **البطارية (Battery)**: 12V عادي، 24V شاحنات
- **الدينمو (Alternator)**: الشحن
- **السلف (Starter)**: بدء التشغيل
- **الكويلات (Ignition Coils)**: الجهد العالي
- **الحساسات (Sensors)**: القراءة والتحكم

## 6. نظام التكييف:

- **الكمبروسر (Compressor)**: ضغط الغاز
- **الكوندنسر (Condenser)**: تبريد
- **المبخر (Evaporator)**: التبخير
- **غاز التبريد (Refrigerant)**: R134a, R1234yf

## 7. قطع الهيكل:

- **الرفارف (Fenders)**: الحماية
- **الأبواب (Doors)**: الدخول
- **الكبوت (Hood)**: غطاء المحرك
- **الشنطة (Trunk)**: الحقيبة
- **الصدام (Bumper)**: الامتصاص
- **الأضواء (Lights)**: الإضاءة

## 8. السوائل والزيوت:

- **زيت المحرك**: 5W-30, 10W-40, etc.
- **زيت القير**: ATF, MTF
- **زيت الفرامل**: DOT 3, DOT 4
- **سائل التبريد**: Coolant
- **سائل الباور**: Power Steering Fluid
"""

HEAVY_EQUIPMENT_PARTS = """
# قطع غيار المعدات الثقيلة

## 1. الحفارات (Excavators):

### المحرك:
- محركات ديزل قوية (100-500 HP)
- فلاتر زيت وهواء كبيرة
- مبردات ضخمة

### نظام الهيدروليك:
- **المضخات الهيدروليكية**: قلب النظام
- **الاسطوانات**: الحركة
- **الخراطيم**: نقل الزيت
- **زيت هيدروليك**: عالي الجودة

### الأطراف:
- **البوم (Boom)**: الذراع الرئيسي
- **الأرم (Arm)**: الذراع الثانوي
- **الباكت (Bucket)**: الجرافة
- **الأسنان (Teeth)**: للحفر

## 2. اللوادر (Loaders):

### مكونات خاصة:
- صندوق التروس الثقيل
- محاور أمامية قوية
- إطارات ضخمة (23.5R25, etc.)
- جرافات متعددة الأحجام

## 3. الرافعات (Cranes):

### الأجزاء الحيوية:
- كابلات الرفع
- البكرات والونشات
- نظام الثقل الموازن
- نظام الأمان

## 4. الشاحنات الثقيلة:

### محركات:
- **Cummins**: أمريكي، قوي
- **Volvo**: أوروبي، موثوق
- **Mercedes**: ألماني، فاخر
- **Hino**: ياباني، اقتصادي

### قطع خاصة:
- صندوق القير (9-18 غيار)
- المحاور الخلفية المزدوجة
- نظام الهواء (Air Brake)
- كابينة القيادة
"""

PARTS_QUALITY = """
# تمييز جودة قطع الغيار

## 1. الأصلي (OEM - Original Equipment Manufacturer):
- **المميزات**:
  ✅ جودة المصنع الأصلي
  ✅ كفالة طويلة
  ✅ مطابقة 100%
- **العيوب**:
  ❌ سعر مرتفع
  ❌ توفر محدود أحياناً

## 2. البديل الأصلي (OES - Original Equipment Supplier):
- **المميزات**:
  ✅ نفس المصنع الذي يزود الشركة الأم
  ✅ جودة ممتازة
  ✅ سعر أقل قليلاً
- **العيوب**:
  ❌ كفالة أقصر قليلاً

## 3. ما بعد البيع (Aftermarket):
- **المميزات**:
  ✅ سعر منافس
  ✅ توفر عالي
  ✅ خيارات متعددة
- **العيوب**:
  ❌ جودة متفاوتة
  ❌ كفالة محدودة

## 4. التقليد (Imitation):
- **تحذير**:
  ⚠️ جودة منخفضة جداً
  ⚠️ عمر قصير
  ⚠️ خطر على السلامة
  ⚠️ لا كفالة

## علامات الجودة:
- **ISO 9001**: إدارة الجودة
- **TS 16949**: معيار صناعة السيارات
- **E-Mark**: معتمد أوروبياً
- **SASO**: معتمد خليجياً
"""

BRANDS_GUIDE = """
# دليل العلامات التجارية

## قطع غيار السيارات:

### ألمانية (جودة عالية):
- **Bosch**: كهرباء، حقن، فرامل
- **ZF**: قير، توجيه
- **Sachs**: كلتش، مساعدات
- **Brembo**: فرامل رياضية
- **Mann**: فلاتر
- **Mahle**: محركات

### أمريكية:
- **Delphi**: حساسات، كهرباء
- **Motorcraft**: Ford أصلي
- **ACDelco**: GM أصلي
- **Mopar**: Chrysler أصلي

### يابانية:
- **Denso**: كهرباء، تكييف (Toyota)
- **NGK**: بواجي
- **Koyo**: بلي، محامل
- **Aisin**: قير، كلتش

### كورية:
- **Mobis**: Hyundai/Kia أصلي
- **Mando**: فرامل، توجيه

### صينية (متوسطة):
- **Geely Parts**
- **Chery Parts**
- **Great Wall**

## المعدات الثقيلة:

### أصلية:
- **Caterpillar (CAT)**: أمريكي، الأفضل عالمياً
- **Komatsu**: ياباني، موثوق
- **Volvo CE**: سويدي، فاخر
- **Hitachi**: ياباني، ممتاز
- **Liebherr**: ألماني، رافعات

### بديل جيد:
- **JCB**: بريطاني
- **Doosan**: كوري
- **XCMG**: صيني (جودة محسّنة)
- **SANY**: صيني
"""

COMPATIBILITY_GUIDE = """
# دليل التوافق والتبديل

## قواعد التوافق:

### 1. السنة والموديل:
- نفس الجيل: متوافق 95%
- جيل مختلف: تحقق من الأرقام

### 2. رقم القطعة (Part Number):
- **OEM Number**: الرقم الأصلي
- **Interchange Numbers**: أرقام بديلة
- **Cross Reference**: مرجع متقاطع

### 3. المواصفات:
- القياسات (Dimensions)
- نوع التثبيت (Mounting Type)
- التوصيلات الكهربائية

## أمثلة للتبديل:

### فلاتر الزيت:
```
Toyota Camry 2.4L (2007-2011):
- OEM: 90915-YZZD2
- Mann: W67/2
- Bosch: 0986452041
- Fram: PH4967
```

### فحمات الفرامل:
```
Honda Accord (2008-2012):
- OEM: 45022-TA0-A00
- Brembo: P28049
- Akebono: ACT1089
- TRW: GDB3401
```

### بطارية:
```
معظم السيارات:
- 12V, 60-100Ah
- DIN: 60Ah, 540A
- مقاس: 242x175x190mm
```

## نصائح:
✅ دائماً تحقق من VIN للتأكد
✅ استخدم كتالوجات إلكترونية (TecDoc, Partslink)
✅ اسأل الموزع عن الضمان
✅ احتفظ برقم القطعة القديمة
"""

DIAGNOSTIC_GUIDE = """
# دليل التشخيص

## أعطال شائعة:

### 1. المحرك لا يدور:
**الأسباب**:
- بطارية فارغة → فحص الفولت (12.6V)
- سلف معطل → فحص الصوت
- فيوز محروق → فحص الفيوزات

### 2. المحرك يدور لكن لا يشتغل:
**الأسباب**:
- لا يوجد وقود → فحص المضخة
- لا يوجد شرارة → فحص البواجي والكويل
- توقيت خاطئ → فحص السير

### 3. حرارة زائدة:
**الأسباب**:
- نقص ماء → أضف وفحص التسريب
- ثرموستات معطل → استبدل
- مضخة ماء → فحص وغيّر
- راديتر مسدود → نظّف أو استبدل

### 4. استهلاك زيت:
**الأسباب**:
- شنابر تالفة → تصليح محرك
- جوان صبابات → استبدل
- PCV معطل → نظف أو غيّر

### 5. اهتزاز:
**الأسباب**:
- عدم توازن → ميزان عجل
- محور معوج → استبدل
- مساعدات تالفة → غيّر
- جنط ملخبط → صفّر أو غيّر

## أدوات التشخيص:
- **OBD2 Scanner**: قراءة الأخطاء
- **Multimeter**: فحص كهرباء
- **Compression Tester**: ضغط المحرك
- **Vacuum Gauge**: فحص الفاكيوم
"""

MAINTENANCE_SCHEDULE = """
# جدول الصيانة الدورية

## كل 5,000 كم أو 3 شهور:
- ✅ تغيير زيت المحرك
- ✅ تغيير فلتر الزيت
- ✅ فحص مستويات السوائل
- ✅ فحص الإطارات والضغط

## كل 10,000 كم أو 6 شهور:
- ✅ تغيير فلتر الهواء
- ✅ فحص الفرامل
- ✅ دوران الإطارات
- ✅ فحص البطارية

## كل 20,000 كم أو سنة:
- ✅ تغيير فلتر المكيف
- ✅ تغيير البواجي
- ✅ فحص سير المحرك
- ✅ تغيير زيت الفرامل

## كل 40,000 كم أو سنتين:
- ✅ تغيير سير التايمن
- ✅ تغيير زيت القير
- ✅ تغيير سائل التبريد
- ✅ فحص شامل للتعليق

## للمعدات الثقيلة:

### كل 250 ساعة تشغيل:
- زيت المحرك والفلتر
- فلتر الهواء
- تشحيم النقاط

### كل 500 ساعة:
- فلتر الوقود
- فحص الهيدروليك
- زيت الديفرانس

### كل 1000 ساعة:
- زيت القير
- فلتر الهيدروليك
- صيانة شاملة
"""

# قاموس شامل
PARTS_DATABASE = {
    'categories': AUTO_PARTS_CATEGORIES,
    'heavy_equipment': HEAVY_EQUIPMENT_PARTS,
    'quality': PARTS_QUALITY,
    'brands': BRANDS_GUIDE,
    'compatibility': COMPATIBILITY_GUIDE,
    'diagnostic': DIAGNOSTIC_GUIDE,
    'maintenance': MAINTENANCE_SCHEDULE,
}

def get_part_info(category):
    """الحصول على معلومات قطعة غيار"""
    return PARTS_DATABASE.get(category, "معلومات غير متوفرة")

def search_parts(query):
    """البحث في قاعدة قطع الغيار"""
    query = query.lower()
    results = []
    
    for category, content in PARTS_DATABASE.items():
        if query in content.lower():
            results.append({
                'category': category,
                'excerpt': content[:300] + '...'
            })
    
    return results

def get_compatible_parts(part_name, vehicle_info):
    """البحث عن قطع متوافقة"""
    # هذه دالة تمهيدية - ستتطور مع الوقت
    return f"قطع متوافقة لـ {part_name} في {vehicle_info}"


# ===== Consolidated from: knowledge/automotive_ecu_knowledge.py =====
"""
🚗 معرفة كمبيوترات السيارات المتقدمة - Automotive ECU Knowledge
خبير في أنظمة التحكم الإلكترونية للسيارات (ECU)

المعرفة الشاملة:
- Engine Control Unit (ECU)
- Transmission Control Unit (TCU)
- ABS/ESP Control Units
- Body Control Module (BCM)
- OBD-II Protocols
- CAN Bus Systems
- Diagnostic Trouble Codes (DTC)
- ECU Programming & Tuning
- Sensor Systems
- Actuator Systems

شركة أزاد للأنظمة الذكية
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AutomotiveECUKnowledge:
    """
    خبير كمبيوترات السيارات والأنظمة الإلكترونية
    """
    
    def __init__(self):
        self.knowledge_base = self._build_comprehensive_knowledge()
        logger.info("🚗 Automotive ECU Knowledge initialized")
    
    def _build_comprehensive_knowledge(self) -> dict:
        """بناء قاعدة المعرفة الشاملة"""
        return {
            # ========== ECU - وحدة التحكم في المحرك ==========
            'engine_ecu': {
                'description': 'وحدة التحكم الإلكترونية في المحرك - الدماغ الرئيسي',
                'functions': {
                    'fuel_injection': {
                        'name': 'التحكم في الحقن',
                        'description': 'تحديد كمية الوقود ووقت الحقن',
                        'sensors': ['MAF', 'MAP', 'TPS', 'IAT', 'CTS', 'O2'],
                        'formula': 'Injection Time = (Base Pulse × Load Factor × Temp Correction) / Battery Voltage',
                        'common_issues': [
                            'حاقن مسدود → خشونة في المحرك',
                            'خلل في O2 sensor → استهلاك وقود عالي',
                            'ضغط وقود منخفض → فقدان قوة'
                        ]
                    },
                    'ignition_timing': {
                        'name': 'توقيت الإشعال',
                        'description': 'تحديد اللحظة المثلى لإشعال الشمعة',
                        'formula': 'Advance = Base Timing + (RPM Factor × Load Factor) - (Knock Correction)',
                        'range': '10-40 درجة قبل النقطة الميتة العليا (BTDC)',
                        'common_issues': [
                            'Knock Sensor خلل → إشعال متأخر → فقدان قوة',
                            'توقيت مبكر جداً → طرق في المحرك',
                            'توقيت متأخر → ارتفاع حرارة'
                        ]
                    },
                    'idle_control': {
                        'name': 'التحكم في الخمول',
                        'description': 'ضبط RPM عند الخمول',
                        'target': '600-900 RPM (حسب المحرك)',
                        'actuator': 'IAC (Idle Air Control) Valve',
                        'common_issues': [
                            'IAC متسخ → خمول غير مستقر',
                            'تسريب هواء → RPM عالي',
                            'TPS غير معاير → خمول منخفض'
                        ]
                    },
                    'vvt_control': {
                        'name': 'التحكم في توقيت الصمامات المتغير',
                        'description': 'VVT/VTEC - تغيير توقيت فتح الصمامات حسب الحمل',
                        'benefit': 'قوة أعلى + استهلاك أقل',
                        'solenoid': 'VVT Solenoid',
                        'common_issues': [
                            'VVT Solenoid خلل → P0010-P0014',
                            'زيت متسخ → تأخر في الاستجابة',
                            'سلسلة التوقيت مرتخية → صوت طقطقة'
                        ]
                    }
                },
                'sensors': {
                    'MAF': {
                        'name': 'Mass Air Flow Sensor',
                        'name_ar': 'حساس تدفق الهواء',
                        'function': 'قياس كمية الهواء الداخل للمحرك',
                        'range': '0-5V (Analog) أو Digital',
                        'formula': 'Air Mass (g/s) = MAF Voltage × Calibration Factor',
                        'testing': 'عند الخمول: 2-3 g/s، عند 2500 RPM: 15-25 g/s',
                        'common_codes': ['P0100', 'P0101', 'P0102', 'P0103', 'P0104'],
                        'symptoms': ['استهلاك وقود عالي', 'فقدان قوة', 'خشونة']
                    },
                    'MAP': {
                        'name': 'Manifold Absolute Pressure',
                        'name_ar': 'حساس ضغط المنفولد',
                        'function': 'قياس ضغط الهواء في مجمع السحب',
                        'range': '0-5V (0-100 kPa أو 0-14.5 PSI)',
                        'testing': 'عند الخمول: 0.5-1.5V (20-30 kPa)',
                        'formula': 'Pressure (kPa) = (Voltage × 20) - 4',
                        'common_codes': ['P0105', 'P0106', 'P0107', 'P0108']
                    },
                    'TPS': {
                        'name': 'Throttle Position Sensor',
                        'name_ar': 'حساس وضعية البوابة',
                        'function': 'قياس فتحة صمام الخانق (الثروتل)',
                        'range': '0.5V (مغلق) إلى 4.5V (مفتوح كلياً)',
                        'testing': 'يجب أن يتغير بشكل سلس بدون قفزات',
                        'calibration': 'يحتاج معايرة بعد التركيب',
                        'common_codes': ['P0120', 'P0121', 'P0122', 'P0123']
                    },
                    'O2': {
                        'name': 'Oxygen Sensor (Lambda)',
                        'name_ar': 'حساس الأكسجين',
                        'function': 'قياس نسبة الأكسجين في العادم',
                        'types': ['Narrow Band (0-1V)', 'Wide Band (0-5V)'],
                        'target': 'Lambda = 1.0 (14.7:1 air/fuel ratio)',
                        'testing': 'يجب أن يتأرجح بين 0.1-0.9V عند التسخين',
                        'common_codes': ['P0130-P0167'],
                        'lifespan': '100,000-150,000 كم'
                    },
                    'CTS': {
                        'name': 'Coolant Temperature Sensor',
                        'name_ar': 'حساس حرارة الماء',
                        'function': 'قياس درجة حرارة سائل التبريد',
                        'type': 'NTC (مقاومة سالبة)',
                        'testing': '20°C = 3kΩ، 80°C = 300Ω، 100°C = 180Ω',
                        'common_codes': ['P0115', 'P0116', 'P0117', 'P0118']
                    },
                    'IAT': {
                        'name': 'Intake Air Temperature',
                        'name_ar': 'حساس حرارة الهواء الداخل',
                        'function': 'قياس حرارة الهواء الداخل',
                        'purpose': 'تصحيح كثافة الهواء',
                        'common_codes': ['P0110', 'P0111', 'P0112', 'P0113']
                    },
                    'CKP': {
                        'name': 'Crankshaft Position Sensor',
                        'name_ar': 'حساس عمود الكرنك',
                        'function': 'تحديد موضع وسرعة دوران المحرك',
                        'type': 'Magnetic (Hall Effect أو Inductive)',
                        'critical': True,
                        'symptoms': 'لا يعمل المحرك إذا تعطل',
                        'common_codes': ['P0335', 'P0336', 'P0337', 'P0338']
                    },
                    'CMP': {
                        'name': 'Camshaft Position Sensor',
                        'name_ar': 'حساس عمود الكامات',
                        'function': 'تحديد موضع الصمامات',
                        'purpose': 'تزامن الحقن والإشعال',
                        'common_codes': ['P0340', 'P0341', 'P0342', 'P0343']
                    },
                    'Knock': {
                        'name': 'Knock Sensor',
                        'name_ar': 'حساس الطرق',
                        'function': 'كشف الطرق (Detonation) في المحرك',
                        'type': 'Piezoelectric',
                        'action': 'تأخير الإشعال عند الطرق',
                        'common_codes': ['P0325', 'P0326', 'P0327', 'P0328']
                    }
                }
            },
            
            # ========== OBD-II Codes ==========
            'obd2_codes': {
                'P0': 'Powertrain (المحرك ونقل الحركة)',
                'C0': 'Chassis (الشاسيه - ABS/ESP)',
                'B0': 'Body (الهيكل - BCM)',
                'U0': 'Network (شبكة الاتصال - CAN Bus)',
                'common_codes': {
                    'P0300': 'Random Misfire - عدم احتراق عشوائي',
                    'P0301-P0308': 'Misfire Cylinder 1-8 - عدم احتراق سلندر محدد',
                    'P0420': 'Catalyst Efficiency Below Threshold - كفاءة الكتلايزر منخفضة',
                    'P0171': 'System Too Lean Bank 1 - خليط فقير',
                    'P0172': 'System Too Rich Bank 1 - خليط غني',
                    'P0401': 'EGR Flow Insufficient - تدفق EGR غير كافي',
                    'P0505': 'Idle Control System Malfunction - خلل في نظام الخمول',
                    'P0128': 'Coolant Temp Below Thermostat Temp - حرارة منخفضة',
                    'P0134': 'O2 Sensor No Activity - حساس أكسجين لا يعمل',
                    'P0335': 'Crankshaft Position Sensor Circuit - دائرة حساس الكرنك',
                    'P0340': 'Camshaft Position Sensor Circuit - دائرة حساس الكامات',
                    'P0442': 'EVAP Small Leak - تسريب صغير في نظام البخار',
                    'P0455': 'EVAP Large Leak - تسريب كبير في نظام البخار',
                    'P0500': 'Vehicle Speed Sensor - حساس السرعة',
                    'P0562': 'System Voltage Low - جهد النظام منخفض',
                    'P0700': 'Transmission Control System - نظام التحكم في القير',
                    'P1000': 'OBD System Readiness Test - اختبار جاهزية النظام'
                }
            },
            
            # ========== CAN Bus ==========
            'can_bus': {
                'description': 'Controller Area Network - شبكة التحكم',
                'speed': {
                    'high_speed': '500 kbps (المحرك والأنظمة الحيوية)',
                    'medium_speed': '125 kbps (الراحة)',
                    'low_speed': '33.3 kbps (التشخيص)'
                },
                'structure': {
                    'wires': 'CAN High + CAN Low (2 أسلاك ملتوية)',
                    'voltage': 'CAN High: 3.5V، CAN Low: 1.5V (عند الإرسال)',
                    'termination': '120Ω في كل طرف',
                    'nodes': 'حتى 110 وحدة على نفس الشبكة'
                },
                'protocols': {
                    'CAN 2.0A': 'Standard 11-bit ID',
                    'CAN 2.0B': 'Extended 29-bit ID',
                    'CAN FD': 'Flexible Data Rate (أحدث)'
                },
                'diagnosis': {
                    'U0100': 'Lost Communication with ECU',
                    'U0101': 'Lost Communication with TCM',
                    'U0121': 'Lost Communication with ABS',
                    'U0155': 'Lost Communication with BCM'
                },
                'testing': [
                    'فحص الفولتية: CAN H = 2.5V عند الراحة',
                    'فحص المقاومة: 60Ω بين CAN H & CAN L',
                    'فحص الإشارة بالأوسلسكوب',
                    'استخدام CAN Bus Analyzer'
                ]
            },
            
            # ========== TCU/TCM - القير الأوتوماتيك ==========
            'transmission': {
                'description': 'Transmission Control Unit - وحدة التحكم في القير',
                'types': {
                    'conventional': 'قير عادي 4-10 سرعات',
                    'cvt': 'CVT - نسب متغيرة لا نهائية',
                    'dct': 'DCT/DSG - قير مزدوج',
                    'amt': 'AMT - يدوي آلي'
                },
                'sensors': {
                    'input_speed': 'سرعة عمود الإدخال',
                    'output_speed': 'سرعة عمود الإخراج',
                    'atf_temp': 'حرارة زيت القير',
                    'pressure': 'ضغط الزيت',
                    'gear_position': 'وضع الغيار'
                },
                'shift_logic': {
                    'parameters': ['السرعة', 'الحمل', 'TPS', 'حرارة الزيت'],
                    'modes': ['Eco', 'Normal', 'Sport', 'Manual'],
                    'protection': 'منع التعشيق عند RPM عالي'
                },
                'common_codes': {
                    'P0700': 'TCM Malfunction',
                    'P0715': 'Input Speed Sensor',
                    'P0720': 'Output Speed Sensor',
                    'P0731-P0734': 'Gear Ratio Incorrect',
                    'P0750-P0770': 'Shift Solenoid Malfunction'
                },
                'maintenance': [
                    'تغيير زيت القير: 60,000 كم',
                    'فحص الفلتر: كل تغيير زيت',
                    'معايرة التعلم: بعد إصلاحات كبيرة'
                ]
            },
            
            # ========== ABS/ESP ==========
            'abs_esp': {
                'description': 'Anti-lock Braking System & Electronic Stability Program',
                'abs': {
                    'function': 'منع انغلاق العجلات عند الفرملة',
                    'components': ['ECU', 'Hydraulic Unit', 'Wheel Speed Sensors'],
                    'operation': 'نبض الفرامل 15 مرة/ثانية',
                    'benefit': 'توقف أقصر + تحكم أفضل'
                },
                'esp': {
                    'function': 'منع الانزلاق والانقلاب',
                    'sensors': ['Yaw Rate', 'Lateral G', 'Steering Angle'],
                    'action': 'فرملة عجلات فردية + تقليل عزم المحرك'
                },
                'wheel_speed_sensors': {
                    'types': ['Active (Hall Effect)', 'Passive (Magnetic)'],
                    'location': 'عند كل عجلة',
                    'testing': '1000-2000 mV AC عند الدوران اليدوي'
                },
                'common_codes': {
                    'C0035-C0038': 'Left/Right Front/Rear Wheel Speed Sensor',
                    'C0040': 'ABS Motor Relay Circuit',
                    'C0045': 'Wheel Speed Sensor Frequency Error',
                    'C0050': 'Yaw Rate Sensor Malfunction'
                }
            },
            
            # ========== Body Control Module ==========
            'bcm': {
                'description': 'Body Control Module - وحدة التحكم في الهيكل',
                'functions': [
                    'الإضاءة الداخلية والخارجية',
                    'القفل المركزي',
                    'النوافذ الكهربائية',
                    'المساحات',
                    'نظام الإنذار',
                    'Immobilizer (منع الحركة)',
                    'Climate Control'
                ],
                'programming': {
                    'required_after': ['استبدال BCM', 'استبدال المفاتيح'],
                    'tools': ['Factory Scan Tool', 'Dealer-level Access'],
                    'data': 'VIN Programming + Key Learning'
                }
            },
            
            # ========== Diagnostic Tools ==========
            'diagnostic_tools': {
                'basic': {
                    'code_reader': 'قارئ أكواد بسيط - P codes فقط',
                    'cost': '50-200 درهم',
                    'limitation': 'قراءة وحذف أكواد فقط'
                },
                'advanced': {
                    'scan_tool': 'جهاز فحص متقدم',
                    'capabilities': [
                        'Live Data (بيانات حية)',
                        'Bi-Directional Control (تحكم)',
                        'Adaptations (تكييفات)',
                        'Coding (برمجة)',
                        'All Modules (جميع الوحدات)'
                    ],
                    'examples': ['Autel MaxiSys', 'Launch X431', 'Snap-on'],
                    'cost': '5,000-50,000 درهم'
                },
                'factory': {
                    'name': 'أجهزة الوكالة',
                    'examples': {
                        'Toyota': 'Techstream',
                        'Honda': 'HDS',
                        'BMW': 'ISTA',
                        'Mercedes': 'Xentry',
                        'VW/Audi': 'ODIS',
                        'Ford': 'IDS',
                        'GM': 'Tech2/MDI'
                    },
                    'access': 'يحتاج اشتراك'
                }
            },
            
            # ========== ECU Tuning ==========
            'ecu_tuning': {
                'description': 'تعديل برمجة ECU لزيادة الأداء',
                'methods': {
                    'chip_tuning': {
                        'method': 'قراءة وتعديل الملف من EEPROM',
                        'connection': 'OBD-II أو فتح ECU',
                        'gains': '+10-30% قوة وعزم'
                    },
                    'piggyback': {
                        'method': 'جهاز إضافي يعترض الإشارات',
                        'examples': ['Apexi SAFC', 'Unichip'],
                        'reversible': True
                    },
                    'standalone': {
                        'method': 'استبدال ECU بالكامل',
                        'examples': ['Haltech', 'AEM', 'MoTeC'],
                        'for': 'سيارات السباق'
                    }
                },
                'parameters': {
                    'fuel_map': 'جدول الوقود (AFR)',
                    'ignition_map': 'جدول الإشعال (Advance)',
                    'boost_pressure': 'ضغط التيربو (للمحركات التيربو)',
                    'rev_limiter': 'محدد الدوران',
                    'speed_limiter': 'محدد السرعة'
                },
                'risks': [
                    'ضمان الوكيل يلغى',
                    'استهلاك وقود أعلى',
                    'عمر المحرك قد يقل',
                    'قد يسبب أعطال إذا لم يتم بشكل صحيح'
                ],
                'recommendations': [
                    'استخدم ورشة محترفة',
                    'Dyno Tuning (على الداينو)',
                    'مراقبة AFR و Knock',
                    'استخدم بنزين عالي الأوكتان'
                ]
            },
            
            # ========== Modern Systems ==========
            'modern_systems': {
                'adas': {
                    'name': 'Advanced Driver Assistance Systems',
                    'features': [
                        'Adaptive Cruise Control (ACC)',
                        'Lane Keeping Assist (LKA)',
                        'Automatic Emergency Braking (AEB)',
                        'Blind Spot Monitoring (BSM)',
                        'Parking Sensors',
                        'Surround View Camera'
                    ],
                    'sensors': ['Radar', 'Camera', 'Ultrasonic', 'LiDAR'],
                    'calibration': 'يحتاج معايرة بعد تصليح الزجاج الأمامي'
                },
                'hybrid': {
                    'types': ['Mild Hybrid', 'Full Hybrid', 'Plug-in Hybrid'],
                    'components': [
                        'Electric Motor/Generator',
                        'High Voltage Battery (200-400V)',
                        'Power Control Unit (PCU)',
                        'DC-DC Converter',
                        'Regenerative Braking'
                    ],
                    'safety': '⚠️ HIGH VOLTAGE - خطر صعق كهربائي!'
                },
                'ev': {
                    'name': 'Electric Vehicle',
                    'components': [
                        'Battery Pack (400-800V)',
                        'Inverter',
                        'Electric Motor(s)',
                        'Onboard Charger',
                        'Battery Management System (BMS)',
                        'Thermal Management'
                    ],
                    'no_maintenance': ['زيت محرك', 'فلاتر', 'شمعات'],
                    'maintenance': ['فرامل', 'إطارات', 'تبريد', 'فحص كهربائي']
                }
            }
        }
    
    def get_ecu_info(self, ecu_type: str) -> dict:
        """الحصول على معلومات عن وحدة تحكم محددة"""
        return self.knowledge_base.get(ecu_type, {})
    
    def diagnose_code(self, dtc_code: str) -> dict:
        """تشخيص كود خطأ"""
        codes_db = self.knowledge_base.get('obd2_codes', {}).get('common_codes', {})
        
        if dtc_code in codes_db:
            return {
                'code': dtc_code,
                'description': codes_db[dtc_code],
                'found': True
            }
        
        # تحليل نوع الكود
        if dtc_code.startswith('P0'):
            category = 'Powertrain'
        elif dtc_code.startswith('C0'):
            category = 'Chassis'
        elif dtc_code.startswith('B0'):
            category = 'Body'
        elif dtc_code.startswith('U0'):
            category = 'Network'
        else:
            category = 'Unknown'
        
        return {
            'code': dtc_code,
            'category': category,
            'found': False,
            'recommendation': 'ابحث في قاعدة بيانات الكودات الخاصة بالصانع'
        }
    
    def get_sensor_info(self, sensor_name: str) -> dict:
        """معلومات عن حساس محدد"""
        sensors = self.knowledge_base.get('engine_ecu', {}).get('sensors', {})
        return sensors.get(sensor_name.upper(), {})


# ============================================================================
# Singleton
# ============================================================================

_automotive_ecu_instance = None

def get_automotive_ecu_knowledge():
    """الحصول على خبير كمبيوترات السيارات"""
    global _automotive_ecu_instance
    if _automotive_ecu_instance is None:
        _automotive_ecu_instance = AutomotiveECUKnowledge()
    return _automotive_ecu_instance



# ===== Consolidated from: knowledge/system_knowledge.py =====
"""
System Knowledge Base - Complete System Documentation
قاعدة المعرفة الشاملة للنظام
"""

SYSTEM_OVERVIEW = """
# نظام أزاد لإدارة الكراجات والمعدات الثقيلة

## نظرة عامة:
نظام محاسبي متكامل مصمم خصيصاً للكراجات، ورش الصيانة، ومحلات قطع الغيار.

## الوحدات الرئيسية:
1. **المبيعات (Sales)**: إدارة فواتير البيع والمرتجعات
2. **المشتريات (Purchases)**: إدارة المشتريات من الموردين
3. **المخزون (Inventory)**: تتبع المنتجات والمخزون
4. **الزبائن (Customers)**: إدارة العملاء والحسابات
5. **المدفوعات (Payments)**: تتبع المدفوعات وسندات القبض
6. **المصروفات (Expenses)**: تسجيل المصروفات
7. **دفتر الأستاذ (GL)**: المحاسبة المالية
8. **التقارير (Reports)**: تقارير مالية شاملة
9. **المستودعات (Warehouses)**: إدارة مستودعات متعددة
10. **المساعد الذكي (AI)**: مساعد ذكي محلي

## المميزات الخاصة:
- ✅ دعم عملات متعددة مع تحويل تلقائي
- ✅ نظام صلاحيات متقدم (Owner, Admin, Manager, Seller)
- ✅ تشفير البطاقات البنكية (AES-256)
- ✅ نظام تدقيق شامل (Audit Logs)
- ✅ نسخ احتياطي تلقائي
- ✅ وضع داكن + اختصارات لوحة مفاتيح
- ✅ تصميم عصري خليجي فلسطيني
"""

SALES_MODULE = """
# وحدة المبيعات

## إنشاء فاتورة بيع:
**المسار**: المبيعات → فاتورة جديدة

### الخطوات:
1. اختر الزبون (بحث ذكي بالاسم أو الهاتف)
2. اختر عملة الدفع (افتراضي: AED)
3. أضف المنتجات:
   - ابحث عن المنتج
   - أدخل الكمية
   - السعر يُحمّل تلقائياً حسب نوع الزبون:
     * Regular: regular_price
     * Merchant: merchant_price
     * VIP: partner_price
4. أضف خصم (اختياري)
5. اختر طريقة الدفع:
   - نقدي (Cash)
   - بطاقة (Card)
   - تحويل بنكي (Bank Transfer)
   - شيك (Cheque)
   - محفظة إلكترونية (E-Wallet)
6. أدخل المبلغ المدفوع
7. احفظ الفاتورة

### ملاحظات مهمة:
- الفاتورة دائماً بالدرهم (AED) - العملة الأساسية
- إذا كان الدفع بعملة أخرى، يتم التحويل تلقائياً
- يتم خصم الكمية من المخزون فوراً
- يُسجل في دفتر الأستاذ تلقائياً

### التقارير:
- عرض الفاتورة: المبيعات → عرض
- طباعة: المبيعات → طباعة
- إلغاء: المبيعات → إلغاء (للمدراء فقط)

## أنواع الزبائن:
1. **Regular (عادي)**: سعر عادي
2. **Merchant (تاجر)**: سعر تاجر (أقل)
3. **VIP (مميز)**: سعر شريك (أقل سعر)
"""

CUSTOMERS_MODULE = """
# وحدة الزبائن

## إضافة زبون جديد:
**المسار**: الزبائن → إضافة زبون

### المعلومات المطلوبة:
- **الاسم** (إجباري)
- **الهاتف**
- **البريد الإلكتروني**
- **العنوان**
- **نوع الزبون**: Regular, Merchant, VIP
- **الرقم الضريبي** (للشركات)
- **حد الائتمان**

## حساب الزبون:
- **إجمالي المبيعات**: كل الفواتير
- **المدفوع**: المبالغ المدفوعة
- **الرصيد**: المتبقي على الزبون

## كشف الحساب:
**المسار**: الزبائن → عرض → كشف حساب

يعرض:
- جميع الفواتير
- المدفوعات
- الرصيد الحالي

## الأزرار السريعة:
- **دفع**: فتح سند قبض مباشر
- **بيع**: فتح فاتورة جديدة للزبون
"""

PRODUCTS_MODULE = """
# وحدة المنتجات

## إضافة منتج:
**المسار**: المنتجات → إضافة منتج

### المعلومات:
- **الاسم** (عربي + إنجليزي)
- **SKU** (رمز فريد)
- **Barcode** (باركود فريد)
- **Part Number** (رقم القطعة)
- **التصنيف**
- **بلد المنشأ**

### الأسعار:
- **سعر التكلفة**: سعر الشراء
- **السعر العادي**: للزبائن العاديين
- **سعر التاجر**: للتجار
- **سعر الشريك**: لـ VIP

### المخزون:
- **الكمية الحالية**
- **حد التنبيه**: عندما تقل الكمية

### الكفالة:
- **مدة الكفالة**
- **وحدة الكفالة**: أيام، أسابيع، شهور، سنوات

## البحث عن منتج:
- بالاسم
- بـ SKU
- بـ Barcode
- برقم القطعة

## الأزرار السريعة:
- **بيع**: فتح فاتورة مباشرة
- **إضافة كمية**: تعديل المخزون
"""

PAYMENTS_MODULE = """
# وحدة المدفوعات

## إنشاء سند قبض:
**المسار**: سندات القبض → إضافة سند

### الخطوات:
1. اختر الزبون
2. يعرض النظام الفواتير غير المدفوعة
3. اختر الفاتورة أو دفع عام
4. أدخل المبلغ
5. اختر العملة
6. اختر طريقة الدفع
7. احفظ السند

### طرق الدفع:
- **نقدي**: بدون حقول إضافية
- **بطاقة**: رقم المعاملة، آخر 4 أرقام
- **تحويل بنكي**: رقم الحوالة، البنك
- **شيك**: رقم الشيك، تاريخ الاستحقاق، البنك
- **محفظة**: رقم المعاملة، نوع المحفظة

## تحويل العملات:
- يتم التحويل تلقائياً لـ AED
- سعر الصرف من API حقيقي
- يمكن التعديل اليدوي (مع تدقيق)
"""

REPORTS_MODULE = """
# وحدة التقارير

## التقارير المتاحة:

### 1. تقرير المبيعات:
**المسار**: التقارير → المبيعات

**يعرض**:
- إجمالي المبيعات (AED)
- عدد الفواتير
- متوسط الفاتورة
- الربح الإجمالي
- فلترة حسب التاريخ، الحالة، البائع

### 2. تقرير المشتريات:
**المسار**: التقارير → المشتريات

**يعرض**:
- إجمالي المشتريات
- عدد الفواتير
- فلترة حسب التاريخ

### 3. تقرير المخزون:
**المسار**: التقارير → المخزون

**يعرض**:
- قيمة المخزون الإجمالية
- المنتجات منخفضة المخزون
- المنتجات نافدة
- حركات المخزون

### 4. تقرير الذمم:
**المسار**: التقارير → الذمم المدينة

**يعرض**:
- الزبائن المدينون
- المبالغ المستحقة
- عمر الديون (بالأيام)
- إجمالي الذمم

### 5. التقارير المالية:
- **Trial Balance**: ميزان المراجعة
- **Income Statement**: قائمة الدخل
- **Balance Sheet**: الميزانية العمومية

## التصدير:
كل التقارير قابلة للتصدير:
- Excel
- CSV
- PDF (طباعة)
"""

WAREHOUSE_MODULE = """
# وحدة المستودعات

## إدارة المخزون:
**المسار**: المستودعات والمخزون → إدارة المخزون

### عرض المنتجات:
- قائمة كل المنتجات
- الكمية الحالية
- حالة المخزون (جيد، منخفض، نافد)

### الفلاتر الذكية:
- **الكل**: جميع المنتجات
- **منخفض**: أقل من حد التنبيه
- **نافد**: الكمية = 0

## إضافة مستودع:
**المسار**: المستودعات → إضافة مستودع (للأدمن)

### المعلومات:
- الاسم (عربي + إنجليزي)
- الرمز (كود فريد)
- الموقع
- مستودع رئيسي (نعم/لا)

## حركات المخزون:
**المسار**: المستودعات → حركات المخزون

**أنواع الحركات**:
- **شراء (Purchase)**: زيادة من مشتريات
- **بيع (Sale)**: نقص من مبيعات
- **تسوية (Adjustment)**: تعديل يدوي
- **إرجاع (Return)**: إضافة من مرتجعات
- **تالف (Damage)**: نقص بسبب تلف

## تنبيهات المخزون:
- منخفض: عندما الكمية <= حد التنبيه
- نافد: عندما الكمية = 0
- تنبيهات تلقائية للمدراء
"""

GL_MODULE = """
# وحدة دفتر الأستاذ (General Ledger)

## الحسابات:
**المسار**: دفتر الأستاذ → الحسابات

### أنواع الحسابات:
1. **Asset (أصول)**:
   - Cash (نقدية)
   - Bank (بنك)
   - Inventory (مخزون)
   - Accounts Receivable (ذمم مدينة)

2. **Liability (خصوم)**:
   - Accounts Payable (ذمم دائنة)
   - Loans (قروض)

3. **Equity (حقوق ملكية)**:
   - Capital (رأس المال)
   - Retained Earnings (أرباح محتجزة)

4. **Revenue (إيرادات)**:
   - Sales Revenue (إيرادات المبيعات)

5. **Expense (مصروفات)**:
   - Cost of Goods Sold (تكلفة البضاعة)
   - Operating Expenses (مصروفات تشغيل)

## القيود التلقائية:
- عند البيع: Debit (AR/Cash), Credit (Sales Revenue)
- عند الشراء: Debit (Inventory), Credit (AP/Cash)
- عند الدفع: Debit (AP), Credit (Cash/Bank)

## التقارير المالية:
1. **ميزان المراجعة**: كل الحسابات مع أرصدتها
2. **قائمة الدخل**: الإيرادات - المصروفات = الربح
3. **الميزانية**: الأصول = الخصوم + حقوق الملكية
"""

PERMISSIONS_SYSTEM = """
# نظام الصلاحيات

## الأدوار (Roles):

### 1. Owner (المالك):
- **الصلاحيات**: كل شيء بدون قيود
- **الوصول الخاص**:
  - لوحة المالك (Owner Dashboard)
  - قاعدة البيانات المباشرة
  - خزينة البطاقات المشفرة
  - إعدادات النظام الكاملة
  - سجلات التدقيق
  - الأرشيف والحذف النهائي

### 2. Super Admin (مدير عام):
- إدارة المستخدمين
- إدارة الصلاحيات
- عرض كل التقارير
- تعديل الإعدادات (محدود)

### 3. Manager (مدير):
- إدارة المبيعات والمشتريات
- إدارة الزبائن والمنتجات
- عرض التقارير
- إدارة المخزون

### 4. Seller (بائع):
- إنشاء فواتير بيع فقط
- عرض فواتيره فقط
- بحث عن منتجات وزبائن
- لا يمكنه الحذف أو الإلغاء

## الصلاحيات المتاحة:
- `manage_sales`: إدارة المبيعات
- `manage_purchases`: إدارة المشتريات
- `manage_customers`: إدارة الزبائن
- `manage_products`: إدارة المنتجات
- `manage_warehouse`: إدارة المخزون
- `manage_payments`: إدارة المدفوعات
- `manage_expenses`: إدارة المصروفات
- `view_ledger`: عرض دفتر الأستاذ
- `manage_ledger`: إدارة دفتر الأستاذ
- `view_reports`: عرض التقارير
- `manage_users`: إدارة المستخدمين
- `admin`: صلاحيات إدارية
"""

CURRENCY_SYSTEM = """
# نظام العملات

## القاعدة الذهبية:
**الفاتورة دائماً بالدرهم (AED) - لا استثناءات!**

## كيف يعمل النظام:

### عند إنشاء فاتورة:
1. الزبون يختار عملة الدفع (AED, USD, EUR, etc.)
2. المنتجات تُسعّر بالدرهم
3. الإجمالي يُحسب بالدرهم
4. عند الدفع:
   - إذا الدفع بـ AED: لا تحويل
   - إذا الدفع بعملة أخرى: يتم التحويل

### مصادر سعر الصرف:
1. **API خارجي**: سعر حقيقي من:
   - exchangerate-api.com
   - currencyapi.com
   - fixer.io (fallback)
2. **يدوي**: يمكن التعديل (مع تسجيل في الملاحظات)

### التحويل في التقارير:
- **كل المبالغ تُخزن بـ AED**
- `amount_aed`: المبلغ بالدرهم
- `paid_amount_aed`: المدفوع بالدرهم
- التقارير تجمع `amount_aed` فقط

## العملات المدعومة:
- AED (درهم إماراتي)
- USD (دولار أمريكي)
- EUR (يورو)
- GBP (جنيه استرليني)
- SAR (ريال سعودي)
- KWD (دينار كويتي)
- QAR (ريال قطري)
- OMR (ريال عماني)
- BHD (دينار بحريني)
- ILS (شيكل إسرائيلي)
"""

KEYBOARD_SHORTCUTS = """
# اختصارات لوحة المفاتيح

## التنقل:
- `Alt + H`: الرئيسية
- `Alt + S`: المبيعات
- `Alt + C`: الزبائن
- `Alt + P`: المنتجات

## الإجراءات:
- `Ctrl + N`: إنشاء جديد
- `Ctrl + S`: حفظ النموذج
- `Ctrl + K`: بحث سريع
- `Ctrl + E`: تصدير البيانات
- `Ctrl + P`: طباعة
- `Ctrl + B`: إخفاء/إظهار القائمة

## أخرى:
- `?` أو `Ctrl + /`: عرض المساعدة
- `Escape`: إغلاق/إلغاء
"""

FEATURES_GUIDE = """
# دليل المميزات

## 1. الوضع الداكن 🌙
**التفعيل**: اضغط أيقونة القمر في النافبار
**المميزات**:
- انتقال سلس
- يحفظ التفضيل
- تصميم داكن كامل

## 2. الإشعارات الذكية 🔔
**التلقائية**:
- حفظ ناجح
- أخطاء
- تحذيرات
**المميزات**:
- صوت + اهتزاز
- إغلاق تلقائي
- أنيقة ومرنة

## 3. البحث الذكي 🔍
**للزبائن**:
- بحث بالاسم
- بحث بالهاتف
- بحث بالإيميل
- نتائج فورية

**للمنتجات**:
- بحث بالاسم
- بحث بـ SKU
- بحث بـ Barcode
- عرض المخزون والأسعار

## 4. الأزرار السريعة ⚡
**في صفحة الزبائن**:
- دفع: سند قبض مباشر
- بيع: فاتورة جديدة

**في صفحة المنتجات**:
- بيع: فاتورة مباشرة
- إضافة كمية: تعديل المخزون

## 5. التصدير والطباعة 📊
**كل الجداول**:
- Excel
- CSV
- Copy
- Print
- Column visibility
"""

TROUBLESHOOTING = """
# حل المشاكل الشائعة

## 1. لا يظهر الزبون في قائمة الاختيار:
**الحل**: 
- تأكد أن الزبون نشط (is_active = True)
- جرب البحث بالاسم أو الهاتف
- اضغط على القائمة - ستظهر جميع الزبائن

## 2. المنتج غير متاح في الفاتورة:
**الحل**:
- تأكد أن المنتج نشط
- تأكد من وجود كمية في المخزون
- تأكد من وجود سعر

## 3. خطأ في حساب الإجمالي:
**السبب**: خلط العملات
**الحل**: النظام يحول كل شيء لـ AED تلقائياً

## 4. لا يمكن حفظ الفاتورة:
**الأسباب المحتملة**:
- لم تختر زبون
- لم تضف منتجات
- الكمية أكبر من المخزون
- حقول إجبارية فارغة

## 5. سعر الصرف خطأ:
**الحل**:
- انتظر تحميل السعر من API
- يمكنك التعديل يدوياً
- سيتم تسجيل التعديل في الملاحظات
"""

OWNER_MODE = """
# وحدة المالك (Owner Mode)

## الوصول:
**فقط للمستخدم الذي** `is_owner = True`

## الأدوات المتاحة:

### 1. لوحة المالك:
- إحصائيات شاملة
- الربح الحقيقي
- قيمة المخزون
- الذمم المدينة

### 2. إدارة قاعدة البيانات:
- SQL Console
- Browse Tables
- Backup & Restore
- تحويل لـ MySQL

### 3. خزينة البطاقات:
- عرض البطاقات المشفرة
- إضافة بطاقة جديدة
- تشفير AES-256
- حذف آمن

### 4. إعدادات الشركة:
- معلومات الشركة/الكراج
- الشعارات والألوان
- المعلومات القانونية
- العلامة التجارية

### 5. إعدادات النظام:
- تفعيل/تعطيل الوحدات
- تفعيل/تعطيل المميزات
- إعدادات عامة

### 6. ترويسات الفواتير:
- تخصيص كامل
- 4 قوالب احترافية
- معاينة حية

### 7. سجل التدقيق:
- كل العمليات مسجلة
- من؟ متى؟ ماذا؟
- لا يمكن حذفها

### 8. الأرشيف:
- عرض المحذوفات
- استعادة
- حذف نهائي (خطير!)
"""

RECENT_UPDATES_OCT_2025 = """
# 🔄 التحديثات الأخيرة - أكتوبر 2025

## 📊 تحديثات النظام (2025-10-19)

### 1. ✅ إصلاح وحدة الموردين (Suppliers)
**المشكلة:** خطأ في API البحث عن الموردين
**الإصلاح:**
- تصحيح دالة `get_balance()` → `get_balance_aed()` في `routes/suppliers.py`
- إزالة `@login_required` من API endpoint
- إضافة معالجة أخطاء شاملة (try-except)

**النتيجة:**
✅ API البحث عن الموردين يعمل بنجاح 100%
✅ فلتر الموردين في فواتير الشراء يعمل بشكل صحيح

### 2. ✅ تحسين نظام الطباعة (Print System)
**تم إصلاح 11 قالب طباعة**

**التحسينات:**
✅ تكيف كامل مع أحجام الورق (A4, A5, Letter)
✅ تكيف مع الاتجاه (Portrait/Landscape)
✅ هوامش قابلة للتخصيص
✅ منع تقطيع الجداول

### 3. ✅ تحسين روابط AJAX
**تم إصلاح 6 ملفات** - تحويل روابط ثابتة إلى `url_for()`

### 4. ✅ الفحص الشامل
**النتيجة:**
- 103 قالب ✅
- 504 عنصر تفاعلي ✅
- 0 أخطاء ✅
- 100% تكامل ✅
"""

# دليل سريع لكل الوحدات
ALL_MODULES = {
    'sales': SALES_MODULE,
    'customers': CUSTOMERS_MODULE,
    'products': PRODUCTS_MODULE,
    'payments': PAYMENTS_MODULE,
    'reports': REPORTS_MODULE,
    'warehouse': WAREHOUSE_MODULE,
    'gl': GL_MODULE,
    'permissions': PERMISSIONS_SYSTEM,
    'currency': CURRENCY_SYSTEM,
    'shortcuts': KEYBOARD_SHORTCUTS,
    'features': FEATURES_GUIDE,
    'troubleshooting': TROUBLESHOOTING,
    'owner': OWNER_MODE,
    'recent_updates': RECENT_UPDATES_OCT_2025,  # ✅ التحديثات الأخيرة أكتوبر 2025
}

def get_module_help(module_name):
    """الحصول على مساعدة وحدة معينة"""
    return ALL_MODULES.get(module_name.lower(), "الوحدة غير موجودة")

def search_knowledge(query):
    """البحث في قاعدة المعرفة"""
    query = query.lower()
    results = []
    
    for module, content in ALL_MODULES.items():
        if query in content.lower():
            results.append({
                'module': module,
                'content': content[:500] + '...'
            })
    
    return results

