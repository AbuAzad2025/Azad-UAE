# قواعد المحاسبة والمخزون — AZADEXA ERP Accounting & Inventory Rules

> مستند حقيقي مبني على الكود الفعلي. آخر تحديث: يوليو 2026.

---

## 1. المحاسبة العامة (General Ledger)

### 1.1 الهيكل

- **شجرة الحسابات** (Chart of Accounts) مبنية على `GLAccount` مع `parent_id`.
- **أنواع الحسابات**: assets, liabilities, equity, revenue, expenses.
- **الفترات المحاسبية**: `GLPeriod` (period_start, period_end, is_closed).

### 1.2 القيود اليومية (Journal Entries)

- `GLJournalEntry` + `GLJournalLine` (debit, credit, account_id).
- كل قيد يجب أن يكون متوازنًا: `sum(debit) == sum(credit)`.
- الترحيل يتم عبر `GLPostingService.post_or_fail()` في `services/gl_posting.py`.
- **ممنوع** `db.session.commit()` — فقط `flush()` داخل `atomic_transaction`.

### 1.3 التعيين التلقائي

- `GLAccountMapping` يربط العمليات بحسابات GL.
- `ENABLE_DYNAMIC_GL_MAPPING` في `config.py` يُفعّل/يُعطّل.

### 1.4 إعداد المستأجر الجديد

- `GLAccountingSetup` في `services/gl_accounting_setup.py` ينشئ شجرة GL افتراضية لكل مستأجر.
- `tenant_provisioning.py` يستدعيها أثناء التوفير.

---

## 2. قواعد المخزون

### 2.1 المستودعات

- `Warehouse` — مستودع رئيسي أو فرعي أو نقطة بيع.
- `ProductWarehouseStock` — كمية المنتج في كل مستودع.
- `ProductWarehouseCost` — تكلفة المنتج في المستودع (cost_method, average_cost).

### 2.2 طرق التكلفة

| الطريقة | الملف | الوصف |
|---------|-------|-------|
| WAC (Weighted Average Cost) | `services/stock_service.py` | متوسط التكلفة المرجح |
| MWAC (Moving WAC) | `config.py: ENABLE_MWAC` | متوسط متحرك |
| Landed Cost | `config.py: ENABLE_LANDED_COST_CAPITALIZATION` | تكلفة الوصول |

### 2.3 حركة المخزون

- `StockService.create_movement()` في `services/stock_service.py`.
- كل حركة تُحدّث `ProductWarehouseStock.quantity`.
- عند البيع: `calculate_sale_cogs_and_deduct()` تحسب COGS وتخصم.
- عند الشراء: `_update_wac_on_receipt()` تحدّث المتوسط.

### 2.4 التتبع التسلسلي

- `ProductSerial` — تتبع كل قطعة فرديًا.
- `SerialTrackingService` — إدارة التتبع التسلسلي.

### 2.5 التسوية المخزونية

- `InventoryReconciliationService` — مقارنة الفعلي مع النظام.
- Celery task: `run_inventory_reconciliation`.

---

## 3. قواعد العملات المتعددة

### 3.1 التكميم (Quantization)

كل `amount_aed` **يجب** أن يُكمّم إلى `Decimal("0.001")` باستخدام `ROUND_HALF_UP`.

```python
from utils.currency_utils import convert_and_quantize_aed
amount_aed = convert_and_quantize_aed(amount, rate)
```

### 3.2 خط أنابيب FX

```
ExchangeRateService.resolve_exchange_rate_for_transaction()
  → يُرجع rate كـ string (ليس float)
  → convert_and_quantize_aed()
  → Decimal("0.001") + ROUND_HALF_UP
```

### 3.3 إعادة التقييم (Revaluation)

- `fx_revaluation_service.py` — `revaluate_open_items()`.
- تُعيد تقييم الفواتير المفتوحة والقيود بنهاية كل شهر.
- تُنشئ قيد `GLJournalEntry` للفرق (unrealized gain/loss).

---

## 4. قواعد المدفوعات

### 4.1 الميزانية العمومية

- `Customer.balance` — الرصيد المستحق من العملاء.
- `Supplier.balance` — الرصيد المستحق للموردين.
- `Payment` — المدفوعات الصادرة.
- `Receipt` — السندات الواردة.

### 4.2 الشيكات

- دورة حياة كاملة: receive → deposit → clear / bounce / cancel.
- `cheque_service.py` — كل حالة تُنشئ قيد GL تلقائيًا (عبر `cheque_accounting_integration.py`).

### 4.3 خزينة الدفع

- `PaymentVault` — إعدادات البوابة.
- `CardVault` — تخزين آمن للبطاقات.
- `PaymentTransaction` — تتبع كل معاملة.

---

## 5. قواعد الرواتب

### 5.1 المعالجة

- `PayrollService.process_payroll()` — تحسب صافي الراتب، الضريبة، التأمينات.
- `post_payroll_accruals()` — ترحيل قيود الاستحقاقات.

### 5.2 الإعدادات

- `PayrollSettings` — أيام العمل، معدل الovertime.

---

## 6. قواعد الإهلاك

- `DepreciationService` — straight-line, declining balance.
- `DepreciationSchedule` — جدول إهلاك لكل أصل.
- `FixedAsset.dispose()` — يُنشئ قيد بيع/تكهين.

---

## 7. ما يجب عدم تغييره (What NOT to Change)

| القاعدة | السبب |
|---------|-------|
| فلاتر `tenant_id` | عزل البيانات |
| حمايات `owner-only` | صلاحيات المالك |
| حدود `payment vault` | أمان المدفوعات |
| منطق `customer/supplier balance` | توازن الميزانية |
| ترحيل GL debit/credit | صحة القيود |
| حركة المخزون وتكلفة المستودع | دقة COGS |
| ملكية `public donation/package payment` | قانونية التبرعات |

---
*هذا المستند مبني على الكود الفعلي. أي تغيير في المشروع يجب أن يعكس هنا.*
