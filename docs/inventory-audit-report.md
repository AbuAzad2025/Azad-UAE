# تقرير تدقيق المخزون والمنتجات والمستودعات — Azad ERP Inventory Audit

تاريخ: 2026-06-10

## ملخص تنفيذي

اكتشفت **9 ثغرات حرجة** في نظام المخزون: تناقضات تصميمية، تسريبات عزل، وقصور في تتبع المخزون حسب المستودع. النظام يستخدم `Product.current_stock` كحقل عالمي بينما `StockMovement` يتتبع حسب المستودع — وهذا تناقض أساسي.

---

## 1. تناقض تصميمي حرج — Product.current_stock vs StockMovement

### المشكلة

`Product.current_stock` هو **حقل واحد عالمي** على مستوى المنتج:

```python
# models/product.py:103
current_stock = db.Column(db.Numeric(15, 3), default=0, nullable=False)
```

لكن `StockMovement` يتتبع حركات **حسب المستودع**:

```python
# models/warehouse.py:55-57
product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
quantity = db.Column(db.Numeric(15, 3), nullable=False)
```

### التأثير

| السيناريو | النتيجة |
|---|---|
| مستودع A: 100، مستودع B: 50 | `current_stock = 150` (صحيح) |
| تحويل 30 من A إلى B | `current_stock` لا يتغير (صحيح) |
| بيع 120 من A فقط | `current_stock = 30` لكن A = -20 (خاطئ) |
| تعديل يدوي لـ `current_stock` | لا علاقة له بـ `StockMovement` (خاطئ) |

**لا يوجد جدول `ProductWarehouseStock`** — لا يمكن معرفة المخزون الفعلي حسب المستودع إلا بحساب تراكمي من `StockMovement`.

### الدليل

```python
# services/stock_service.py:149
product.current_stock += Decimal(str(quantity))
```

كل حركة تُعدّل `current_stock` المجمع — لا تُعدّل مخزون مستودع محدد.

---

## 2. تسريب Tenant — إنشاء مستودع افتراضي بدون tenant_id

```python
# services/stock_service.py:113-116
if not warehouse:
    warehouse = Warehouse(name='Main Warehouse', name_ar='المستودع الرئيسي', is_active=True, is_main=True)
    db.session.add(warehouse)
    db.session.flush()
```

**المستودع يُنشأ بدون `tenant_id`** — ثم يُعيّن لاحقاً:

```python
# services/stock_service.py:132-133
if getattr(warehouse, "tenant_id", None) is None and tenant_id is not None:
    warehouse.tenant_id = tenant_id
```

**التأثير**: مستودع "Main Warehouse" بلا tenant يمكن أن يُستخدم عبر tenants.

---

## 3. تناقض تسمية — get_price_for_customer

```python
# models/product.py:157-164
def get_price_for_customer(self, customer_type='regular'):
    if customer_type == 'partner' and self.partner_price:
        return self.regular_price * (1 - (self.partner_price / 100))
    elif customer_type == 'merchant' and self.merchant_price:
        return self.regular_price * (1 - (self.merchant_price / 100))
```

| الاسم | المعنى الظاهر | المعنى الفعلي |
|---|---|---|
| `merchant_price` | سعر تاجر | **نسبة خصم** |
| `partner_price` | سعر شريك | **نسبة خصم** |
| `merchant_share` | نصيب التاجر | **نسبة مئوية** (صحيح) |

**التأثير**: واجهة المستخدم تُظهر "merchant price" كسعر مطلق لكن الكود يعامله كنسبة خصم.

---

## 4. ProductPartner — لا تحقق من مجموع النسب 100%

```python
# models/product.py:35-53 (ProductPartner)
percentage = db.Column(db.Numeric(5, 2), nullable=False, default=0)
```

`routes/products.py` يتحقق من عدم التكرار لكن **لا يتحقق من مجموع النسب**:

```python
# routes/products.py:95-96
if partner_id in seen_partner_ids:
    return None, 'لا يمكن تكرار نفس الشريك'
# لا يوجد: if total > 100: error
```

**التأثير**: شريك 60% + شريك 50% = 110% — مقبول في النظام.

---

## 5. GL accounts hardcoded — لا مرونة

```python
# services/stock_service.py:48-56
lines = [
    {'account': '5150', 'concept_code': 'INVENTORY_ADJUSTMENT_LOSS', ...},
    {'account': '1140', 'concept_code': 'INVENTORY_ASSET', ...},
]
```

**التأثير**: إذا غيّر المستخدم أرقام الحسابات في COA، تفشل القيود المحاسبية للمخزون.

---

## 6. Product.cost_price عالمي — لا يوجد per-warehouse cost

```python
# models/product.py:97
cost_price = db.Column(db.Numeric(15, 3), default=0)
```

`ProductWarehouseCost` موجود لكن يُستخدم فقط لـ MWAC:

```python
# services/stock_service.py:243-247
pwc = ProductWarehouseCost.query.filter_by(
    tenant_id=tenant_id,
    product_id=line.product_id,
    warehouse_id=warehouse_id,
).first()
```

**التأثير**: إذا اشترى المنتج بـ 10 في دبي و 15 في أبوظبي — `cost_price` واحد فقط.

---

## 7. عدم تطابق Branch Scope — تعديل المنتج لا يتحقق من الفرع

```python
# routes/products.py:52-58
def _ensure_product_scope(product):
    """Tenant isolation is enforced by tenant_get_or_404 on CRUD routes.
    Branch stock visibility applies to listings, POS, and warehouse pickers
    — not to product master view/edit/delete."""
    return product
```

**التأثير**: مستخدم فرعي يمكنه تعديل منتج حتى لو الفرع لا يملكه (مع العلم أن tenant isolation يحمي).

---

## 8. current_stock يمكن أن يتعارض مع sum(StockMovement)

لا يوجد:
- إجراء مخزني دوري (reconciliation)
- trigger يتحقق من تطابق `current_stock` مع مجموع الحركات
- فحص عند startup

```python
# models/events.py — لا يوجد مستمع لـ StockMovement
```

**التأثير**: تعديل يدوي لـ `current_stock` أو خطأ في الكود يُفقد التزامن.

---

## 9. StockService.get_product_stock — يحتاج فحص

```python
# services/stock_service.py (لم يُفحص بالكامل)
def get_product_stock(product_id, warehouse_id=None):
    ...
```

بحاجة للتأكد هل يحسب من `StockMovement` أم يقرأ `current_stock`.

---

## القوالب المتأثرة

| القالب | المشكلة |
|---|---|
| `templates/warehouse/index.html` | يعرض `visible_stock` محسوب من `_annotate_visible_stock` — يعتمد على `get_branch_stock_map` |
| `templates/products/index.html` | يعرض `current_stock` المجمع — يُضلل مستخدمي الفرع |
| `templates/pos/index.html` | يبحث في المنتجات بدون filter حسب مستودع الفرع |

---

## الملفات المتأثرة

| الملف | المشكلة |
|---|---|
| `models/product.py` | current_stock عالمي، تناقض تسمية الأسعار |
| `models/warehouse.py` | لا يوجد ProductWarehouseStock |
| `services/stock_service.py` | مستودع افتراضي بدون tenant، GL hardcoded |
| `routes/products.py` | لا تحقق من مجموع نسب الشركاء |
| `routes/warehouse.py` | `visible_stock` يعتمد على `_annotate_visible_stock` |
| `utils/branching.py` | branch_scope موجود لكن لا يُطبق على تعديل المنتج |

---

## التوصيات العاجلة

### Priority 1: Architecture (تصميم)

| # | المهمة | الملفات |
|---|---|---|
| 1 | **إنشاء `ProductWarehouseStock`** | `models/warehouse.py` — جدول جديد: product_id, warehouse_id, quantity |
| 2 | **إزالة Product.current_stock** | `models/product.py` — استبدال بـ @property تحسب من ProductWarehouseStock |
| 3 | **تعديل StockService.create_movement** | `services/stock_service.py` — تحديث ProductWarehouseStock بدلاً من current_stock |
| 4 | **إضافة reconciliation** | `services/stock_service.py` — دالة تُطابق ProductWarehouseStock مع StockMovement |
| 5 | **إصلاح مستودع افتراضي** | `services/stock_service.py` — tenant_id إلزامي عند الإنشاء |

### Priority 2: Logic (منطق)

| # | المهمة | الملفات |
|---|---|---|
| 6 | **إصلاح تسمية الأسعار** | `models/product.py` — إعادة تسمية إلى merchant_discount, partner_discount |
| 7 | **تحقق من مجموع الشركاء** | `routes/products.py` — reject if total > 100% |
| 8 | **GL accounts ديناميكية** | `services/stock_service.py` — قراءة من GLAccount حسب concept_code |
| 9 | **Branch scope على تعديل المنتج** | `routes/products.py` — _ensure_product_scope يتحقق من branch |
