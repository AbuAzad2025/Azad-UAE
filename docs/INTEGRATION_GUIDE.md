# Integration Guide | دليل التكامل

## 1. External POS Stock Sync | مزامنة مخزون POS الخارجي

### 1.1 Overview | نظرة عامة

**EN:** External POS systems (e.g., Shopify POS, custom Android POS, legacy systems) can sync stock movements into Azadexa in real time via authenticated API.
**AR:** يمكن لأنظمة POS الخارجية (مثل Shopify POS، Android POS مخصص، الأنظمة القديمة) مزامنة حركات المخزون إلى أزادكسا في الوقت الفعلي عبر API موثّق.

### 1.2 Authentication | الاستيثاق

**EN:**
1. Create an API key in `routes/owner/settings.py` → API Keys.
2. Assign `tenant_id` to the key.
3. Use `X-API-Key` and `X-API-Secret` headers.

**AR:**
1. أنشئ مفتاح API في `routes/owner/settings.py` → API Keys.
2. اربط `tenant_id` بالمفتاح.
3. استخدم رؤوس `X-API-Key` و `X-API-Secret`.

### 1.3 Endpoint | نقطة النهاية

```
POST /api/v2/stock/sync
```

### 1.4 Payload | الحمولة

```json
{
  "batch_id": "{unique-batch-id}",
  "movements": [
    {
      "product_sku": "SKU-12345",
      "warehouse_code": "WH-MAIN",
      "quantity_delta": -2,
      "movement_type": "sale",
      "reference": "POS-REC-9912",
      "timestamp": "2026-07-24T16:00:00Z"
    }
  ]
}
```

### 1.5 Idempotency | الإيدمبوتنسي

**EN:** The `batch_id` is idempotent. Re-submitting the same `batch_id` with identical payload returns cached result. Use UUIDs or `{date}-{counter}` for `batch_id`.
**AR:** `batch_id` هو إيدمبوتنت. إعادة إرسال نفس `batch_id` مع حمولة مطابقة تُرجع النتيجة المخبأة. استخدم UUIDs أو `{date}-{counter}` لـ `batch_id`.

### 1.6 Error Handling | معالجة الأخطاء

| Error (EN) | الخطأ (AR) | Cause | السبب | Fix | الحل |
|------------|-----------|-------|-------|-----|------|
| 400 Invalid SKU | 400 SKU غير صالح | SKU not found in tenant scope | SKU غير موجود في نطاق المستأجر | Verify SKU exists in `products` table | تحقق من وجود SKU في جدول `products` |
| 400 Invalid warehouse | 400 مستودع غير صالح | Warehouse code not found | كود المستودع غير موجود | Verify `warehouse.code` matches | تحقق من تطابق `warehouse.code` |
| 422 Negative stock | 422 مخزون سالب | Resulting quantity < 0 and negative stock disabled | الكمية الناتجة < 0 والمخزون السالب معطل | Enable negative stock in settings or adjust quantity | فعّل المخزون السالب في الإعدادات أو اضبط الكمية |
| 429 Rate limited | 429 معدل مقيّد | Exceeded plan limit | تجاوز حد الباقة | Retry with exponential backoff | أعد المحاولة مع تراجع أسي |

### 1.7 Webhook Confirmation | تأكيد Webhook

**EN:** Azadexa can send a webhook to your POS when the sync is complete:
```
POST /your-webhook-endpoint
```
Body:
```json
{
  "event": "stock.sync.completed",
  "batch_id": "pos-2026-07-24-001",
  "tenant_id": 42,
  "status": "completed",
  "records_processed": 1,
  "records_failed": 0
}
```
Configure webhook URL in `routes/owner/settings.py` → Integrations.

**AR:** يمكن لأزادكسا إرسال webhook إلى POS عند اكتمال المزامنة:
```
POST /your-webhook-endpoint
```
الجسم:
```json
{
  "event": "stock.sync.completed",
  "batch_id": "pos-2026-07-24-001",
  "tenant_id": 42,
  "status": "completed",
  "records_processed": 1,
  "records_failed": 0
}
```
اضبط URL webhook في `routes/owner/settings.py` → Integrations.

## 2. Payment Gateway Integration | تكامل بوابة الدفع

### 2.1 Stripe

**EN:** Webhook endpoint: `/stripe`. Events handled: `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.updated`. Configure in `routes/owner/settings.py` → Payment Gateways.
**AR:** نقطة نهاية webhook: `/stripe`. الأحداث المُعالجة: `invoice.payment_succeeded`، `invoice.payment_failed`، `customer.subscription.updated`. اضبط في `routes/owner/settings.py` → بوابات الدفع.

### 2.2 NOWPayments (Cryptocurrency) | NOWPayments (العملات المشفرة)

**EN:** Supported: BTC, ETH, USDT, and 50+ cryptocurrencies. Webhook endpoint: `/payment/callback`. Configure API key in `config.py` or environment variable.
**AR:** مدعوم: BTC، ETH، USDT، وأكثر من 50 عملة مشفرة. نقطة نهاية webhook: `/payment/callback`. اضبط مفتاح API في `config.py` أو متغير البيئة.

### 2.3 Custom Payment Gateway | بوابة دفع مخصصة

**EN:**
1. Implement `StoreOnlinePaymentService` interface.
2. Add webhook handler in `routes/billing_webhooks.py`.
3. Register in `utils/decorators.py` if authentication is needed.

**AR:**
1. نفّذ واجهة `StoreOnlinePaymentService`.
2. أضف معالج webhook في `routes/billing_webhooks.py`.
3. سجّل في `utils/decorators.py` إذا كان الاستيثاق مطلوباً.

## 3. WhatsApp Business API | واجهة WhatsApp Business

### 3.1 Use Cases | حالات الاستخدام

**EN:** Payment reminders. Invoice delivery. Support ticket updates. Abandoned cart recovery.
**AR:** تذكيرات الدفع. تسليم الفاتورة. تحديثات تذكرة الدعم. استرداد السلة المهجورة.

### 3.2 Configuration | الإعداد

**EN:**
1. Obtain WhatsApp Business API credentials from Meta.
2. Configure in `routes/owner/settings.py` → WhatsApp Settings.
3. Set `WHATSAPP_API_KEY` and `WHATSAPP_PHONE_NUMBER_ID` in environment.

**AR:**
1. احصل على بيانات اعتماد WhatsApp Business API من Meta.
2. اضبط في `routes/owner/settings.py` → إعدادات WhatsApp.
3. اضبط `WHATSAPP_API_KEY` و `WHATSAPP_PHONE_NUMBER_ID` في البيئة.

### 3.3 Message Templates | قوالب الرسائل

**EN:** Templates must be pre-approved by Meta. Supported languages: Arabic, English.
**AR:** يجب أن تكون القوالب مُسبقة الموافقة من Meta. اللغات المدعومة: العربية، الإنجليزية.

## 4. Accounting Software Integration | تكامل برامج المحاسبة

### 4.1 QuickBooks (Roadmap Q4 2026)

**EN:** Planned sync: Chart of accounts, journal entries, invoices.
**AR:** المزامنة المخططة: شجرة الحسابات، القيود اليومية، الفواتير.

### 4.2 Xero (Roadmap Q1 2027)

**EN:** Planned sync: Contacts, invoices, bank transactions.
**AR:** المزامنة المخططة: جهات الاتصال، الفواتير، معاملات البنك.

## 5. E-commerce Platform Integration | تكامل منصة التجارة الإلكترونية

### 5.1 Shopify (Roadmap Q4 2026)

**EN:** Planned: Product sync, order import, inventory sync.
**AR:** المخطط: مزامنة المنتجات، استيراد الطلبات، مزامنة المخزون.

### 5.2 WooCommerce (Roadmap Q1 2027)

**EN:** Planned: Product sync, order import, customer sync.
**AR:** المخطط: مزامنة المنتجات، استيراد الطلبات، مزامنة العملاء.

## 6. Custom Webhook Setup | إعداد Webhook مخصص

### 6.1 Subscribe | الاشتراك

```
POST /api/webhooks/subscribe
```

**Body | الجسم:**
```json
{
  "url": "https://partner.com/webhook",
  "events": ["sale.created", "payment.received"],
  "secret": "whsec_your_secret"
}
```

### 6.2 Verify Signature | التحقق من التوقيع

**EN:**
```python
import hmac, hashlib
expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
assert signature == expected
```

**AR:**
```python
import hmac, hashlib
expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
assert signature == expected
```

## 7. Support | الدعم

**EN:** Integration support: integration-support@azadsystems.com | Emergency: +972 56 215 0193
**AR:** دعم التكامل: integration-support@azadsystems.com | طارئ: +972 56 215 0193
