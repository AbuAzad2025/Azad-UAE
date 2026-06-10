# التقرير الموحد الشامل — المخزون والمنتجات والمستودعات والصناعات والتسعير

تاريخ: 2026-06-10
الإصدار: 1.0 — Unified Master

## ملخص تنفيذي

اكتشفت **18 ثغرة حرجة** عبر 6 مجالات: تصميم مخزوني، عزل tenant/branch، تأقلم صناعي، تسعير متعدد الطبقات، عملات، وحملات ترويجية. النظام يحتاج إعادة تصميم جوهرية في طبقة المخزون مع الحفاظ على التوافق العكسي.

---

## الجدول التنفيذي — 18 ثغرة

| # | المجال | الثغرة | الخطورة |
|---|---|---|---|
| 1 | مخزون | `Product.current_stock` عالمي — لا يوجد `ProductWarehouseStock` | حرج |
| 2 | مخزون | مستودع افتراضي يُنشأ بدون `tenant_id` | حرج |
| 3 | مخزون | GL accounts hardcoded (5150/1140) | عالي |
| 4 | مخزون | `cost_price` عالمي — لا يوجد per-warehouse cost | عالي |
| 5 | مخزون | لا reconciliation بين `current_stock` و `StockMovement` | عالي |
| 6 | مخزون | Branch scope مفقود على تعديل المنتج | متوسط |
| 7 | تسعير | `merchant_price`/`partner_price` أسماء مضللة (نسبة خصم لا سعر) | عالي |
| 8 | تسعير | لا يوجد `wholesale_price`/`retail_price` منفصلان | عالي |
| 9 | تسعير | لا يوجد `sales_rep_commission_rate` للمندوب | عالي |
| 10 | تسعير | `PartnerCommissionEntry.base_amount_aed` hardcoded AED | عالي |
| 11 | ترويج | لا يوجد Promotion/Campaign/Offer model | حرج |
| 12 | عملات | `amount_aed` hardcoded في Purchase/Sale/Commission | عالي |
| 13 | عملات | ILS/شيقل مفقود في أماكن عديدة | عالي |
| 14 | صناعة | `Tenant.business_type` حقل نص حر بدون validation | متوسط |
| 15 | صناعة | `Tenant.industry` موجود لكن غير مستخدم | متوسط |
| 16 | صناعة | Product/Warehouse حقول ثابتة — لا تتأقلم | عالي |
| 17 | ضمان | `warranty_days` موجود لكن لا يوجد tracking للكفالات | متوسط |
| 18 | شحن | `shipping_cost` في Sale فقط — لا يوجد `customs` للمبيعات | متوسط |
| 19 | تتبع | `ProductSerial` موجود لكن لا يوجد `warehouse_id` — لا نعرف السيريال في أي مستودع | عالي |
| 20 | تتبع | لا يوجد `imei` field — موبايلات تحتاج IMEI منفصل عن serial | عالي |
| 21 | مستودع | `Product` يحمل الوصف والباركود والبلد — لا يوجد per-warehouse override | متوسط |
| 22 | صور | لا يوجد `ProductImage` model — صورة واحدة فقط (`image_url`) | متوسط |

---

## المجال أ — نظام المخزون (Stock System)

### A1. `Product.current_stock` عالمي (حرج)

```python
# models/product.py:103
current_stock = db.Column(db.Numeric(15, 3), default=0, nullable=False)
```

`current_stock` حقل واحد على مستوى المنتج. لكن `StockMovement` يتتبع حركات حسب المستودع:

```python
# models/warehouse.py:55-57
product_id = db.Column(...)
warehouse_id = db.Column(...)
quantity = db.Column(...)
```

**التناقض**: مستودع A فيه 100، B فيه 50. تبيع 120 من A → `current_stock` يصبح 30 (صحيح رياضياً) لكن A أصبح -20 (خطأ). لا يمكن معرفة المخزون حسب المستودع إلا بحساب تراكمي من `StockMovement`.

**الحل**: إنشاء `ProductWarehouseStock` (product_id, warehouse_id, quantity) + تحويل `current_stock` إلى @property تعيد sum(quantity).

### A2. مستودع افتراضي بدون tenant_id (حرج)

```python
# services/stock_service.py:113-116
if not warehouse:
    warehouse = Warehouse(name='Main Warehouse', ...)
    db.session.add(warehouse)
    db.session.flush()
# tenant_id يُعيّن بعد الإنشاء (line 132-133)
```

**الحل**: `tenant_id` إلزامي في constructor.

### A3. GL accounts hardcoded (عالي)

```python
# services/stock_service.py:48-56
lines = [
    {'account': '5150', 'concept_code': 'INVENTORY_ADJUSTMENT_LOSS', ...},
    {'account': '1140', 'concept_code': 'INVENTORY_ASSET', ...},
]
```

**الحل**: `GLService.resolve_account_by_concept(concept_code)`.

### A4. `cost_price` عالمي (عالي)

```python
# models/product.py:97
cost_price = db.Column(db.Numeric(15, 3), default=0)
```

اشتريت بـ 10 في دبي و 15 في أبوظبي → `cost_price` واحد فقط.

**الحل**: `ProductWarehouseCost` موجود لكن يُستخدم فقط لـ MWAC. توسيعه ليصبح المصدر الرئيسي لـ cost.

### A5. لا reconciliation (عالي)

لا يوجد فحص أن `current_stock` يطابق مجموع `StockMovement`.

**الحل**: `flask reconcile-stock` CLI command.

### A6. Branch scope مفقود (متوسط)

```python
# routes/products.py:52-58
def _ensure_product_scope(product):
    return product  # لا يفعل شيئاً
```

**الحل**: التحقق من branch_id عبر warehouse للمستخدمين الفرعيين.

---

## المجال ب — نظام التسعير (Pricing System)

### B7. تناقض تسمية الأسعار (عالي)

```python
# models/product.py:97-101
cost_price = db.Column(...)       # سعر التكلفة (صحيح)
regular_price = db.Column(...)    # السعر العادي (صحيح)
merchant_price = db.Column(...)   # يُعامل كنسبة خصم (مضلل)
partner_price = db.Column(...)    # يُعامل كنسبة خصم (مضلل)
merchant_share = db.Column(...)  # نسبة مئوية (اسم صحيح)
```

```python
# models/product.py:157-164
def get_price_for_customer(self, customer_type='regular'):
    if customer_type == 'merchant' and self.merchant_price:
        return self.regular_price * (1 - (self.merchant_price / 100))  # نسبة خصم!
```

**merchant_price** اسم يوحي بـ "سعر مطلق" لكنه يُعامل كنسبة خصم.

**الحل**: إعادة تسمية إلى `merchant_discount_pct` و `partner_discount_pct` أو إضافة أعمدة جديدة.

### B8. لا يوجد سعر جملة ومفرق (عالي)

| الحقل المطلوب | الحالة |
|---|---|
| `wholesale_price` | **غير موجود** |
| `retail_price` | موجود لكن `regular_price` = يُستخدم كسعر عام |
| `distributor_price` | **غير موجود** |
| `min_retail_qty` | **غير موجود** |

**الحل**: إضافة `price_tiers` JSONB أو جدول `ProductPriceTier`:
```python
class ProductPriceTier:
    product_id, tier_code ('wholesale', 'retail', 'distributor'),
    min_quantity, price, currency
```

### B9. لا يوجد مندوب (Sales Rep) (عالي)

```python
# models/partner_commission.py
class PartnerCommissionEntry:  # للشركاء فقط
    partner_customer_id = ...
    percentage = ...
```

**لا يوجد**: `SalesRep`, `SalesRepCommission`, `sales_rep_id` على Sale.

**الحل**: إضافة `sales_rep_id` على `Sale` + `SalesRepCommission` model.

### B10. Commission hardcoded AED (عالي)

```python
# models/partner_commission.py:19-20
base_amount_aed = db.Column(...)
commission_amount_aed = db.Column(...)
```

**الحل**: إضافة `base_amount`, `commission_amount` + `currency` column.

---

## المجال ج — الحملات والخصومات (Promotions)

### C11. لا يوجد Promotion model (حرج)

لا يوجد أي من:
- `Promotion`, `Campaign`, `Offer`
- `discount_code`, `promo_code`
- `buy_x_get_y`, `bundle_price`
- `flash_sale`, `seasonal_discount`

الخصومات الوحيدة الموجودة: `Sale.discount_amount` (خصم إجمالي ثابت).

**الحل**: إنشاء `Campaign` model + `SaleCampaign` junction:
```python
class Campaign:
    id, tenant_id, name, campaign_type ('percentage', 'fixed', 'bundle', 'flash'),
    discount_value, start_date, end_date, min_order_amount, applicable_products JSON
```

---

## المجال د — العملات (Currency System)

### D12/D13. `amount_aed` hardcoded — ILS مفقود (عالي)

| الملف | الحقل | المشكلة |
|---|---|---|
| `models/purchase.py:34` | `amount_aed` | hardcoded AED |
| `models/sale.py:39` | `amount_aed` | hardcoded AED |
| `models/sale.py:41` | `paid_amount_aed` | hardcoded AED |
| `models/partner_commission.py:19` | `base_amount_aed` | hardcoded AED |
| `models/partner_commission.py:20` | `commission_amount_aed` | hardcoded AED |

```python
# models/purchase.py:51-58
@property
def base_amount(self):
    return self.amount_aed  # Alias فقط — لا يحل المشكلة
```

**الحل**: إضافة `currency` column على كل جدول مالي + `amount` (العملة الأصلية) + `amount_base` (محول لعملة tenant).

---

## المجال هـ — التأقلم حسب الصناعة (Industry Adaptation)

### E14/E15. `business_type` حر + `industry` غير مستخدم (متوسط)

```python
# models/tenant.py:26-27
business_type = db.Column(db.String(50), default='general')  # حر
industry = db.Column(db.String(100))                         # غير مستخدم
```

```html
<!-- templates/owner/tenant_create.html:36-38 -->
<input type="text" name="business_type">  <!-- حقل نص بدون قائمة -->
```

### E16. Product/Warehouse حقول ثابتة — لا تتأقلم + لا يوجد override (عالي)

| الصناعة | ما يراه المستخدم | ما يحتاجه |
|---|---|---|
| **بطاريات** | `part_number` | `battery_type` (Li-ion/Lead-acid), `voltage`, `capacity_ah`, `cold_cranking_amps`, `dimensions`, `terminal_type` |
| **ملابس** | `sku` | `size` (S/M/L/XL/ numeric), `color`, `fabric_type`, `season`, `style_code`, `brand` |
| **موبايلات جديد** | `has_serial_number` | `imei_required`, `storage_gb`, `color`, `model_year`, `warranty_period`, `condition` (new) |
| **موبايلات مستعملة** | نفس الحقول | `condition` (used/refurbished), `grade` (A/B/C), `battery_health_pct`, `original_box`, `charger_included` |
| **قطع غيار موبايلات** | `part_number` | `compatible_models` (JSON), `part_type` (screen/battery/charging_port), `oem_or_aftermarket` |

**المشكلة الأولى**: لا يوجد فصل بين الحقول الأساسية (الكل يراها) والحقول الديناميكية (حسب الصناعة).

**المشكلة الثانية**: لا يوجد `product_industry` — المنتج يرث صناعة التينانت فقط. لا يمكن أن يبيع تينانت "سوبرماركت" منتج إلكتروني بحقول IMEI.

**الحل**: نظام هجين:
1. **Core Fields**: `name`, `name_ar`, `sku`, `barcode`, `cost_price`, `regular_price`, `current_stock` — للجميع
2. **Industry Fields**: من `IndustryFieldDefinition` — حسب `product.industry` (يفترض `tenant.business_type`)
3. **Per-Product Override**: `product.industry` يمكن أن يختلف عن `tenant.business_type`

```python
class Product:
    industry = db.Column(db.String(50), nullable=False)  # defaults to tenant.business_type
    extra_fields = db.Column(db.JSON, default=dict)      # industry-specific fields stored here
```

---

## المجال و — الكفالات والضمانات (Warranty)

### W17. ضمان موجود لكن لا tracking (متوسط)

```python
# models/product.py:107-108
has_serial_number = db.Column(db.Boolean, default=False)
warranty_days = db.Column(db.Integer, default=0)
```

**ما هو موجود**: حقل `warranty_days` على المنتج.
**ما هو مفقود**:
- `WarrantyClaim` model (تتبع مطالبات الضمان)
- `SaleLine.warranty_start_date`, `warranty_end_date`
- `ProductSerial` موجود لكن لا يربط serial بـ warranty claim
- `Return` موجود لكن لا يفرق بين return عادي و warranty claim

**الحل**: `WarrantyClaim` model + `SaleLine.warranty_status`.

---

## المجال ز — الشحن والجمارك (Shipping & Customs)

### Z18. customs للشراء فقط (متوسط)

```python
# models/purchase.py:36-40
freight = db.Column(...)
insurance = db.Column(...)
customs_duty = db.Column(...)
other_landed_cost = db.Column(...)
```

**موجود في Purchase**: freight + insurance + customs + landed cost.
**مفقود في Sale**: لا يوجد `customs_duty` للمبيعات التصديرية.
**مفقود**: standalone `Shipping` model مع carrier + tracking number.

```python
# models/sale.py:29
shipping_cost = db.Column(db.Numeric(15, 3), default=0)  # فقط تكلفة
```

**الحل**: `Shipment` model (sale_id/purchase_id, carrier, tracking_number, customs_duty, status).

---

## الملخص المعماري — ما يجب بناؤه

### جداول جديدة مطلوبة

| الجدول | الوظيفة |
|---|---|
| `ProductWarehouseStock` | مخزون حسب مستودع |
| `ProductPriceTier` | أسعار جملة/مفرق/موزع |
| `SalesRepCommission` | عمولات المندوبين |
| `Campaign` / `SaleCampaign` | حملات ترويجية |
| `WarrantyClaim` | تتبع مطالبات الضمان |
| `Shipment` | شحن + tracking + جمارك |
| `ProductImage` | صور متعددة للمنتج |
| `ProductWarehouseSerial` | ربط سيريال بمستودع |
| `IndustryFieldDefinition` | تعريف الحقول حسب الصناعة |

### أعمدة جديدة على جداول موجودة

| الجدول | العمود | الوظيفة |
|---|---|---|
| `Product` | `extra_fields` (JSONB) | حقول ديناميكية حسب الصناعة |
| `Warehouse` | `extra_fields` (JSONB) | حقول ديناميكية |
| `Sale` | `sales_rep_id` (FK) | ربط بالمندوب |
| `SaleLine` | `warranty_start_date`, `warranty_end_date` | تتبع ضمان |
| `Purchase` | `currency`, `amount` | العملة الأصلية |
| `Sale` | `currency`, `amount` | العملة الأصلية |
| `PartnerCommissionEntry` | `currency` | عملة العمولة |
| `ProductSerial` | `warehouse_id`, `imei1`, `imei2`, `model_number` | تتبع مستودع + IMEI |

### خدمات جديدة

| الخدمة | الوظيفة |
|---|---|
| `services/industry_service.py` | قراءة/كتابة الحقول الديناميكية |
| `services/reconciliation_service.py` | تطابق المخزون |
| `services/campaign_service.py` | تطبيق الخصومات |
| `services/warranty_service.py` | إدارة الضمانات |
| `services/shipment_service.py` | إدارة الشحن |
| `services/product_image_service.py` | إدارة صور المنتج |

---

## ملخص الملفات المتأثرة

| الملف | التعديل |
|---|---|
| `models/warehouse.py` | +ProductWarehouseStock, +extra_fields |
| `models/product.py` | +extra_fields, +price_tiers |
| `models/tenant.py` | business_type enum |
| `models/sale.py` | +sales_rep_id, +currency |
| `models/purchase.py` | +currency |
| `models/partner_commission.py` | +currency |
| `models/product_serial.py` | +warehouse_id, +imei1, +imei2, +model_number |
| `models/product_image.py` | جديد (صور متعددة) |
| `services/stock_service.py` | rewrite create_movement |
| `services/industry_service.py` | جديد |
| `services/campaign_service.py` | جديد |
| `services/warranty_service.py` | جديد |
| `services/shipment_service.py` | جديد |
| `routes/products.py` | حفظ/قراءة extra_fields |
| `routes/warehouse.py` | حفظ/قراءة extra_fields |
| `routes/sales.py` | تطبيق campaigns + sales_rep |
| `templates/owner/tenant_create.html` | dropdown للصناعة |
| `templates/products/create.html` | حقول ديناميكية |
| `templates/warehouse/create.html` | حقول ديناميكية |

### Z19. `ProductSerial` بدون `warehouse_id` (عالي)

```python
# models/product_serial.py:7-11
class ProductSerial:
    id, tenant_id, product_id
    serial_number = db.Column(db.String(100), nullable=False, unique=True)
    status = db.Column(db.String(20), default='available')
    # لا يوجد warehouse_id!
```

**المشكلة**: نعرف أن السيريال "متوفر" لكن لا نعرف في **أي مستودع**.

**الحل**: إضافة `warehouse_id` إلى `ProductSerial` + `ProductWarehouseSerial` junction.

### Z20. لا يوجد `imei` field (عالي)

```python
# models/product_serial.py
serial_number = db.Column(db.String(100))  # واحد فقط
```

**المشكلة**: موبايلات جديدة ومستعملة وقطع غيار تحتاج:
- `imei1` + `imei2` (dual SIM)
- `serial_number` (رقم سيريال الشركة المصنعة)
- `iccid` (لشريحة SIM المدمجة)
- `model_number` (A2784, A2785, إلخ)

**الحل**: إضافة `imei1`, `imei2`, `model_number` إلى `ProductSerial` أو `ProductExtraData`.

### Z21. الوصف والباركود والبلد — Product فقط (متوسط)

```python
# models/product.py
barcode = db.Column(db.String(100))          # على المنتج
name_ar = db.Column(db.String(200))          # على المنتج
name_en = db.Column(db.String(200))          # غير موجود أصلاً!
country_of_origin = db.Column(db.String(100)) # على المنتج
```

**المشكلة**: مستودع دبي قد يستلم نفس المنتج من الصين (باركود مختلف) أو من تركيا (وصف مختلف). المنتج `barcode` واحد فقط.

**الحل**: `ProductWarehouseStock` يحمل:
- `warehouse_barcode` (override per warehouse)
- `warehouse_description_ar` (override per warehouse)
- `warehouse_description_en` (override per warehouse)
- `warehouse_country_of_origin` (override per warehouse)

أو: تخزين في `extra_fields` JSONB على `ProductWarehouseStock`.

### Z22. صورة واحدة فقط — لا يوجد ProductImage (متوسط)

```python
# models/product.py:141
image_url = db.Column(db.String(255))  # صورة واحدة
```

**المشكلة**: بطاريات تحتاج صورة + مواصفات تقنية + مقاسات. ملابس تحتاج صورة أمامية/خلفية/تفاصيل. موبايلات تحتاج صورة + صورة الكاميرا + صورة الشاشة.

**الحل**: `ProductImage` model:
```python
class ProductImage:
    id, tenant_id, product_id
    image_url, image_type ('main', 'specs', 'dimensions', 'angle', 'detail')
    caption_ar, caption_en, sort_order
```

---

## القرارات المعمارية

### قرار 1: JSONB vs Separate Table للحقول الديناميكية

**التوصية**: `extra_fields` JSONB على Product/Warehouse (بسيط). إذا أردت indexing لاحقاً → migration لجدول `ProductCustomData`.

### قرار 2: Price Tiers — JSONB vs Table

**التوصية**: `ProductPriceTier` جدول منفصل (indexing مطلوب).

### قرار 3: Currency — كيف نحل `_aed` hardcoded

**التوصية**: المرحلة 1: إضافة `currency` column. المرحلة 2: migration يحول `amount_aed` → `amount_base` (إعادة تسمية). المرحلة 3: إزالة `_aed` من الأسماء.

### قرار 4: Industry Code — English vs Arabic

**التوصية**: `industry_code` بالإنجليزي (stable identifier). عرض AR/EN حسب `current_language`.
