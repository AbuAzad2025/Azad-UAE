# تقرير تدقيق التأقلم حسب الصناعة — Industry-Adaptive Product & Warehouse Fields

تاريخ: 2026-06-10

## ملخص تنفيذي

النظام يملك حقلي `Tenant.business_type` و `Tenant.industry` لكنهما **غير مستخدمين** في تخصيص سلوك النظام. جميع حقول `Product` و `Warehouse` ثابتة عالمياً — سوبرماركت وكراج ومحل موبايلات ير ven نفس الحقول بالضبط. هذا يُسبب تشويشاً للمستخدم ويُضيع فرصاً لتحسين سير العمل حسب القطاع.

---

## 1. الحالة الحالية — حقول ثابتة لكل الصناعات

### Tenant Model — الحقول موجودة لكنها نص حر

```python
# models/tenant.py:26-27
business_type = db.Column(db.String(50), default='general')
industry = db.Column(db.String(100))
```

**المشكلة**: `business_type` حقل نص حر (free text) — المستخدم يكتب ما يشاء:
- "سوبرماركت" / "supermarket" / "retail" / "مجر"
- لا يوجد enum محدد
- لا يوجد validation على القيم المقبولة

### Tenant Creation Form — حقل نص بدون قائمة

```html
<!-- templates/owner/tenant_create.html:36-38 -->
<label for="input_business_type">نوع النشاط</label>
<input type="text" name="business_type" class="form-control">
```

**لا يوجد `<select>` dropdown** — المستخدم يكتب النشاط يدوياً بدون توحيد.

### Product Model — حقول "الكل يلبس الكل"

```python
# models/product.py
class Product:
    name, name_ar, commercial_name  # عام
    sku, part_number, barcode     # عام
    country_of_origin              # عام
    cost_price, regular_price      # عام
    merchant_price, partner_price  # عام (لكنها نسبة خصم فعلياً)
    current_stock                  # عام
    has_serial_number             # عام
    warranty_days                  # عام
```

**لا يوجد**:
- `car_make`, `car_model`, `year` (للكراج)
- `device_type`, `screen_size`, `storage_gb`, `color` (للموبايلات)
- `expiry_date`, `weight_kg`, `organic`, `halal_certified` (للسوبرماركت)
- `engine_cc`, `transmission_type`, `fuel_type` (للكراج)
- `batch_number`, `manufacturing_date` (للأدوية/مواد غذائية)

### Warehouse Model — نفس الحقول لكل الصناعات

```python
# models/warehouse.py
class Warehouse:
    name, code, location
    warehouse_type = physical/online
    branch_id
    manager_id
```

**لا يوجد**:
- `bay_number`, `lift_capacity` (كراج)
- `display_case_number`, `security_level` (موبايلات/مجوهرات)
- `aisle`, `shelf`, `temperature_zone`, `refrigeration_unit` (سوبرماركت)
- `shelf_racking_type`, `forklift_accessible` (مستودعات كبيرة)

---

## 2. التأثيرات السلبية

| الصناعة | المستخدم يرى | النتيجة |
|---|---|---|
| **كراج** | حقل `has_serial_number` | السيارات لا تحتاج SN للمنتج — تحتاج VIN/Chassis |
| **سوبرماركت** | حقل `part_number` | ماذا يعني "رقم القطعة" لكيس رز؟ |
| **موبايلات** | حقل `country_of_origin` | مناسب، لكن يحتاج `imei_required`, `color`, `storage` |
| **مستودع كراج** | حقل `warehouse_type` فقط | يحتاج `service_bay`, `parking_spots` |
| **مستودع أغذية** | لا يوجد `temperature_zone` | لا يمكن تمييز مستودع مبرد عن جاف |

---

## 3. البيانات المتاحة — AI Training يعرف الصناعات

من `ai_training/config.json` — 5 tenants بصناعات مختلفة:

| Tenant Slug | business_type | الصناعة |
|---|---|---|
| alhazem | garage | كراج سيارات |
| nasrallah | — | تجارة عامة |
| dubai_electronics | retail | إلكترونيات |
| abudhabi_construction | — | مقاولات |
| sharjah_trading | — | تجارة |

**المشكلة**: هذه البيانات تُستخدم فقط للذكاء الاصطناعي (AI chat) — لا تؤثر على حقول النظام.

---

## 4. التناقضات المكتشفة

### تناقض 4.1: business_type حر + industry غير مستخدم

```python
# models/tenant.py
business_type = db.Column(db.String(50), default='general')  # حر
industry = db.Column(db.String(100))                           # غير مستخدم
```

`industry` موجود لكن **لا يُقرأ في أي route** و **لا يُعرض في أي form**.

### تناقض 4.2: Product fields تحتوي على حقول متضاربة

```python
merchant_price      # تعامل كنسبة خصم (أسماء مضللة)
partner_price       # تعامل كنسبة خصم
merchant_share      # نسبة مئوية (اسم صحيح)
```

كل هذه الحقول تظهر لكل الصناعات — كراج لا يحتاج "سعر شريك".

### تناقض 4.3: Warehouse لا يميز أنواع المستودعات الوظيفية

كراج يحتاج مستودع قطع غيار + منطقة صيانة + موقف سيارات.
النظام يراهم كلهم "مستودع" بنفس الحقول.

---

## 5. الملفات المتأثرة

| الملف | المشكلة |
|---|---|
| `models/tenant.py` | `business_type` حر, `industry` غير مستخدم |
| `models/product.py` | حقول ثابتة — لا تتأقلم حسب الصناعة |
| `models/warehouse.py` | حقول ثابتة — لا تتأقلم حسب الصناعة |
| `routes/owner.py` | لا يُمرر industry للنموذج |
| `templates/owner/tenant_create.html` | حقل نص بدون قائمة صناعات |
| `templates/owner/tenant_edit.html` | حقل نص بدون قائمة صناعات |
| `templates/products/create.html` | نفس الحقول لكل المستخدمين |
| `templates/warehouse/create.html` | نفس الحقول لكل المستخدمين |
| `services/product_service.py` | لا يأخذ الصناعة بعين الاعتبار |
| `services/stock_service.py` | لا يأخذ الصناعة بعين الاعتبار |

---

## 6. التوصيات — بناء نظام تأقلم حسب الصناعة

### المرحلة A: إعداد النظام الأساسي (Foundation)

#### A1: إنشاء `IndustrySchema` — تعريف الحقول حسب الصناعة

```python
# models/industry_schema.py (NEW)
class IndustrySchema(db.Model):
    """Defines which fields are active per industry"""
    __tablename__ = 'industry_schemas'

    id = db.Column(db.Integer, primary_key=True)
    industry_code = db.Column(db.String(50), nullable=False, unique=True)  # 'automotive', 'retail', 'supermarket'
    industry_name_ar = db.Column(db.String(100), nullable=False)
    industry_name_en = db.Column(db.String(100), nullable=False)

    # Product field flags
    field_car_make = db.Column(db.Boolean, default=False)
    field_car_model = db.Column(db.Boolean, default=False)
    field_year = db.Column(db.Boolean, default=False)
    field_engine_type = db.Column(db.Boolean, default=False)
    field_device_type = db.Column(db.Boolean, default=False)
    field_storage_gb = db.Column(db.Boolean, default=False)
    field_color = db.Column(db.Boolean, default=False)
    field_expiry_date = db.Column(db.Boolean, default=False)
    field_weight_kg = db.Column(db.Boolean, default=False)
    field_batch_number = db.Column(db.Boolean, default=False)
    # ... etc for all optional fields

    # Warehouse field flags
    warehouse_field_bay_number = db.Column(db.Boolean, default=False)
    warehouse_field_temperature_zone = db.Column(db.Boolean, default=False)
    warehouse_field_aisle = db.Column(db.Boolean, default=False)
    # ... etc
```

#### A2: إنشاء `ProductCustomData` — تخزين الحقول الديناميكية

```python
# models/product_custom_data.py (NEW)
class ProductCustomData(db.Model):
    """Key-value store for industry-specific product fields"""
    __tablename__ = 'product_custom_data'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    field_code = db.Column(db.String(50), nullable=False)  # 'car_make', 'color', etc.
    field_value = db.Column(db.Text)
    field_value_ar = db.Column(db.Text)  # For Arabic values

    __table_args__ = (
        db.UniqueConstraint('product_id', 'field_code', name='uq_product_custom_field'),
    )
```

**بديل**: إضافة أعمدة nullable إلى `Product` مباشرة (أبسط لكن أقل مرونة):

```python
# models/product.py — إضافة حقول اختيارية
extra_field_1_label = db.Column(db.String(50))   # 'car_make', 'color', etc.
extra_field_1_value = db.Column(db.String(200))
extra_field_2_label = db.Column(db.String(50))
extra_field_2_value = db.Column(db.String(200))
# ... up to 5-10 fields
```

#### A3: إنشاء `IndustryFieldDefinition` — تعريف الحقول العالمية

```python
# models/industry_field_definition.py (NEW)
class IndustryFieldDefinition(db.Model):
    """Master list of available fields per industry"""
    __tablename__ = 'industry_field_definitions'

    id = db.Column(db.Integer, primary_key=True)
    industry_code = db.Column(db.String(50), nullable=False, index=True)
    field_code = db.Column(db.String(50), nullable=False)       # 'car_make'
    field_name_ar = db.Column(db.String(100), nullable=False)   # 'ماركة السيارة'
    field_name_en = db.Column(db.String(100), nullable=False)   # 'Car Make'
    field_type = db.Column(db.String(20), default='text')        # text, number, date, select, boolean
    field_options = db.Column(db.Text)                            # JSON for select options
    applies_to = db.Column(db.String(20), default='product')      # product, warehouse, both
    sort_order = db.Column(db.Integer, default=0)
    is_required = db.Column(db.Boolean, default=False)
```

### المرحلة B: تعديل النماذج الحالية

#### B1: تعديل `Tenant` — `business_type` enum

```python
# models/tenant.py
BUSINESS_TYPES = [
    ('general', 'عام', 'General'),
    ('automotive', 'كراج / قطع غيار سيارات', 'Automotive / Garage'),
    ('retail', 'تجارة Retail', 'Retail'),
    ('supermarket', 'سوبرماركت', 'Supermarket'),
    ('electronics', 'إلكترونيات / موبايلات', 'Electronics / Mobile'),
    ('pharmacy', 'صيدلية', 'Pharmacy'),
    ('restaurant', 'مطعم / كافيه', 'Restaurant / Cafe'),
    ('construction', 'مقاولات', 'Construction'),
    ('trading', 'تجارة عامة', 'General Trading'),
    ('textile', 'أقمشة / ملابس', 'Textile / Clothing'),
    ('jewelry', 'مجوهرات / ذهب', 'Jewelry / Gold'),
]

business_type = db.Column(db.String(50), default='general', nullable=False)
```

#### B2: تعديل Product — إضافة JSONB للحقول الديناميكية

```python
# models/product.py
extra_fields = db.Column(db.JSON, default=dict)
# أو:
extra_fields = db.Column(db.Text, default='{}')  # JSON string for SQLite compatibility
```

**مثال على البيانات**:
```json
{
  "car_make": "Toyota",
  "car_model": "Camry",
  "year": 2023,
  "engine_type": "V6"
}
```

#### B3: تعديل Warehouse — إضافة JSONB

```python
# models/warehouse.py
extra_fields = db.Column(db.JSON, default=dict)
```

### المرحلة C: تعديل الواجهات (UI)

#### C1: Tenant Create/Edit — قائمة منسدلة للصناعة

```html
<!-- templates/owner/tenant_create.html -->
<select name="business_type" class="form-select" required>
  <option value="">-- اختر نوع النشاط --</option>
  {% for code, name_ar, name_en in business_types %}
  <option value="{{ code }}">{{ name_ar }}</option>
  {% endfor %}
</select>
```

#### C2: Product Create/Edit — حقول ديناميكية

```html
<!-- templates/products/create.html -->
{% for field in industry_fields %}
<div class="col-md-6">
  <label class="form-label">{{ field.field_name_ar }}</label>
  {% if field.field_type == 'select' %}
  <select name="extra_{{ field.field_code }}" class="form-select">
    {% for opt in field.options %}
    <option value="{{ opt }}">{{ opt }}</option>
    {% endfor %}
  </select>
  {% else %}
  <input type="{{ field.field_type }}" name="extra_{{ field.field_code }}" class="form-control">
  {% endif %}
</div>
{% endfor %}
```

#### C3: Warehouse Create/Edit — حقول ديناميكية

نفس النمط — عرض الحقول حسب `tenant.business_type`.

### المرحلة D: تعديل Services

#### D1: `ProductService.get_industry_fields()`

```python
# services/product_service.py
def get_industry_fields(tenant):
    return IndustryFieldDefinition.query.filter_by(
        industry_code=tenant.business_type
    ).order_by(IndustryFieldDefinition.sort_order).all()
```

#### D2: `ProductService.save_extra_fields()`

```python
def save_extra_fields(product, form_data, tenant):
    fields = get_industry_fields(tenant)
    extra = {}
    for field in fields:
        key = f"extra_{field.field_code}"
        if key in form_data:
            extra[field.field_code] = form_data[key]
    product.extra_fields = extra
```

### المرحلة E: Migration Strategy

#### E1: Populate `IndustryFieldDefinition` with defaults

```python
# migrations or bootstrap script
DEFAULT_FIELDS = [
    # Automotive
    {'industry_code': 'automotive', 'field_code': 'car_make', 'field_name_ar': 'ماركة السيارة', 'field_name_en': 'Car Make', 'field_type': 'text'},
    {'industry_code': 'automotive', 'field_code': 'car_model', 'field_name_ar': 'موديل السيارة', 'field_name_en': 'Car Model', 'field_type': 'text'},
    {'industry_code': 'automotive', 'field_code': 'year', 'field_name_ar': 'سنة الصنع', 'field_name_en': 'Year', 'field_type': 'number'},
    {'industry_code': 'automotive', 'field_code': 'engine_cc', 'field_name_ar': 'سعة المحرك', 'field_name_en': 'Engine CC', 'field_type': 'text'},
    # Electronics
    {'industry_code': 'electronics', 'field_code': 'device_type', 'field_name_ar': 'نوع الجهاز', 'field_name_en': 'Device Type', 'field_type': 'select', 'field_options': '["Mobile", "Tablet", "Laptop", "Accessory"]'},
    {'industry_code': 'electronics', 'field_code': 'storage_gb', 'field_name_ar': 'سعة التخزين', 'field_name_en': 'Storage (GB)', 'field_type': 'select', 'field_options': '["64", "128", "256", "512", "1024"]'},
    {'industry_code': 'electronics', 'field_code': 'color', 'field_name_ar': 'اللون', 'field_name_en': 'Color', 'field_type': 'text'},
    # Supermarket
    {'industry_code': 'supermarket', 'field_code': 'expiry_date', 'field_name_ar': 'تاريخ الانتهاء', 'field_name_en': 'Expiry Date', 'field_type': 'date'},
    {'industry_code': 'supermarket', 'field_code': 'weight_kg', 'field_name_ar': 'الوزن (كغ)', 'field_name_en': 'Weight (KG)', 'field_type': 'number'},
    {'industry_code': 'supermarket', 'field_code': 'organic', 'field_name_ar': 'عضوي', 'field_name_en': 'Organic', 'field_type': 'boolean'},
]
```

---

## 7. ملخص الملفات الجديدة والمعدلة

### ملفات جديدة

| الملف | الوصف |
|---|---|
| `models/industry_field_definition.py` | تعريف الحقول حسب الصناعة |
| `services/industry_service.py` | منطق قراءة/كتابة الحقول الديناميكية |
| `templates/partials/industry_fields.html` | Partial لعرض الحقول الديناميكية |
| `scripts/seed_industry_fields.py` | تعبئة البيانات الافتراضية للحقول |

### ملفات تعديل

| الملف | التعديل |
|---|---|
| `models/tenant.py` | `business_type` enum + validation |
| `models/product.py` | إضافة `extra_fields` JSONB |
| `models/warehouse.py` | إضافة `extra_fields` JSONB |
| `routes/owner.py` | تمرير `business_types` للنموذج |
| `routes/products.py` | حفظ/قراءة الحقول الديناميكية |
| `routes/warehouse.py` | حفظ/قراءة الحقول الديناميكية |
| `templates/owner/tenant_create.html` | `<select>` بدلاً من `<input>` |
| `templates/owner/tenant_edit.html` | `<select>` بدلاً من `<input>` |
| `templates/products/create.html` | عرض الحقول الديناميكية |
| `templates/products/edit.html` | عرض الحقول الديناميكية |
| `templates/warehouse/create.html` | عرض الحقول الديناميكية |
| `templates/warehouse/edit.html` | عرض الحقول الديناميكية |

---

## 8. القرارات المعمارية المطلوبة

### قرار 8.1: JSONB vs Separate Table

| النهج | الإيجابيات | السلبيات |
|---|---|---|
| **JSONB** (`extra_fields`) | بسيط، لا يحتاج migration لكل حقل جديد | لا يدعم indexing مباشر، البحث بطيء |
| **جدول منفصل** (`ProductCustomData`) | indexing، validation، relationships | أكثر تعقيداً |
| **أعمدة nullable** في `Product` | أبسط، أداء ممتاز | ثابت (5-10 حقول فقط) |

**التوصية**: JSONB لـ MVP + migration لجدول منفصل عند الحاجة للبحث.

### قرار 8.2: هل يمكن للمستخدم إضافة حقول خاصة؟

- **Plan A**: حقول محددة مسبقاً حسب الصناعة — لا يمكن للمستخدم إضافة حقول جديدة
- **Plan B**: المستخدم يمكنه إضافة حقول مخصصة عبر الواجهة

**التوصية**: Plan A للمرحلة الأولى — Plan B لاحقاً.

### قرار 8.3: Industry code — English vs Arabic

```python
industry_code = 'automotive'  # English (stable, used in code)
field_name_ar = 'كراج / قطع غيار'  # Arabic (display only)
field_name_en = 'Automotive / Garage'  # English (display)
```

**التوصية**: `industry_code` بالإنجليزي (stable identifier) + `field_name_ar` للعرض.
