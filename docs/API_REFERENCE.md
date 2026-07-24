# API Reference | مرجع API

## 1. Base URL | عنوان الأساس

| Environment | البيئة | URL |
|-------------|--------|-----|
| Production | الإنتاج | `https://<tenant-slug>.azadsystems.com` |
| API root | جذر API | `https://<tenant-slug>.azadsystems.com/api/v2` |

## 2. Authentication | الاستيثاق

### 2.1 API Key (External Systems) | مفتاح API (الأنظمة الخارجية)

**EN:** External POS systems and integrations authenticate via API key.
**AR:** تُوثّق أنظمة POS الخارجية والتكاملات عبر مفتاح API.

| Header | الرأس | Value | القيمة |
|--------|-------|-------|--------|
| `X-API-Key` | `X-API-Key` | `{key}` | `{المفتاح}` |
| `X-API-Secret` | `X-API-Secret` | `{secret}` | `{السر}` |

**EN:** The key is scoped to a `tenant_id`. The `@api_key_required` decorator sets `g.active_tenant_id`, enabling automatic ORM tenant scoping.
**AR:** المفتاح مُحدّد النطاق لـ `tenant_id`. يضبط الديكور `@api_key_required` `g.active_tenant_id`، مما يُفعّل نطاق ORM التلقائي للمستأجر.

### 2.2 Session (Internal Users) | الجلسة (المستخدمون الداخليون)

**EN:** Authenticated users use session cookies (Flask-Login + CSRF).
**AR:** يستخدم المستخدمون المُوثّقون كوكيز الجلسة (Flask-Login + CSRF).

| Header | الرأس | Value | القيمة |
|--------|-------|-------|--------|
| `Cookie` | `Cookie` | `session={value}` | `session={القيمة}` |

## 3. External POS Stock Sync | مزامنة مخزون POS الخارجي

### 3.1 Submit Sync Batch | إرسال دفعة المزامنة

```
POST /api/v2/stock/sync
```

**Headers | الرؤوس:**
```
Content-Type: application/json
X-API-Key: {key}
X-API-Secret: {secret}
```

**Body | الجسم:**
```json
{
  "batch_id": "pos-2026-07-24-001",
  "movements": [
    {
      "product_sku": "SKU-12345",
      "warehouse_code": "WH-MAIN",
      "quantity_delta": -3,
      "movement_type": "sale",
      "reference": "POS-REC-8842",
      "timestamp": "2026-07-24T14:30:00Z"
    }
  ]
}
```

**Response 202 Accepted | استجابة 202 مقبول:**
```json
{
  "batch_id": "pos-2026-07-24-001",
  "status": "accepted",
  "records_received": 1,
  "sync_url": "/api/v2/stock/sync/status/pos-2026-07-24-001"
}
```

**Response 400 Bad Request | استجابة 400 طلب سيء:**
```json
{
  "error": "Invalid SKU: SKU-12345 not found in tenant scope"
}
```

**Response 401 Unauthorized | استجابة 401 غير مصرّح:**
```json
{
  "error": "Invalid or expired API key"
}
```

### 3.2 Check Sync Status | التحقق من حالة المزامنة

```
GET /api/v2/stock/sync/status/{batch_id}
```

**Response 200 | استجابة 200:**
```json
{
  "batch_id": "pos-2026-07-24-001",
  "status": "completed",
  "records_total": 1,
  "records_processed": 1,
  "records_failed": 0,
  "started_at": "2026-07-24T14:30:01Z",
  "completed_at": "2026-07-24T14:30:03Z",
  "errors": []
}
```

**Response 404 | استجابة 404:**
```json
{
  "error": "Batch not found"
}
```

### 3.3 Idempotency | تكرارية الطلب

**EN:** The `batch_id` is idempotent. Re-submitting the same `batch_id` with identical payload returns the cached result without reprocessing.
**AR:** `batch_id` هو إيدمبوتنت (تكراري). إعادة إرسال نفس `batch_id` مع حمولة مطابقة تُرجع النتيجة المخبأة دون إعادة المعالجة.

## 4. Core API Endpoints | نقاط نهاية API الأساسية

| Endpoint (EN) | نقطة النهاية | Methods | الطرق |
|---------------|-------------|---------|-------|
| Products | المنتجات | `GET /api/products`, `GET /api/products/{id}/info`, `GET /api/products/barcode/{code}`, `GET /api/warehouses/{wid}/products` | `GET` |
| Sales | المبيعات | `POST /api/sales`, `GET /api/sales/{id}` | `POST`, `GET` |
| Customers | العملاء | `GET /api/customers`, `GET /api/customers/{id}/balance`, `GET /api/customers/{id}/sales` | `GET` |
| Exchange Rates | أسعار الصرف | `GET /api/exchange-rates/display?base=AED`, `GET /api/currency-rate/{from}/{to}` | `GET` |
| Health & System | الصحة والنظام | `GET /health`, `GET /version` | `GET` |

## 5. Webhooks | Webhooks

### 5.1 Events | الأحداث

| Event (EN) | الحدث (AR) | Payload | الحمولة | Trigger | المُشغّل |
|------------|-----------|---------|---------|---------|---------|
| `sale.created` | `sale.created` | Sale object | كائن المبيعة | New sale finalized | المبيعة الجديدة المُنهية |
| `payment.received` | `payment.received` | Payment object | كائن الدفع | Payment recorded | الدفع المُسجّل |
| `stock.moved` | `stock.moved` | Movement object | كائن الحركة | Stock movement created | حركة المخزون المُنشأة |
| `cheque.bounced` | `cheque.bounced` | Cheque object | كائن الشيك | Cheque bounce processed | معالجة رد الشيك |
| `invoice.issued` | `invoice.issued` | Invoice object | كائن الفاتورة | Invoice printed/emailed | الفاتورة المطبوعة/المُرسلة |

### 5.2 Subscription | الاشتراك

```
POST /api/webhooks/subscribe
```

**Body | الجسم:**
```json
{
  "url": "https://partner.com/webhook",
  "events": ["sale.created", "payment.received"],
  "secret": "whsec_xxxxxxxx"
}
```

### 5.3 Signature Verification | التحقق من التوقيع

**EN:** Payloads are signed with HMAC-SHA256:
```
X-Webhook-Signature: t={timestamp},v1={signature}
```

**AR:** تُوقّع الحمولات بـ HMAC-SHA256:
```
X-Webhook-Signature: t={الطابع الزمني},v1={التوقيع}
```

**EN:** Verify using the shared secret:
```python
import hmac, hashlib
expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
```

**AR:** تحقق باستخدام السر المشترك:
```python
import hmac, hashlib
expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
```

## 6. Rate Limiting | تحديد المعدل

| Plan (EN) | الباقة (AR) | Requests / Minute | الطلبات/الدقيقة | Burst | الانفجار |
|-----------|-------------|-------------------|-------------------|-------|----------|
| Starter | البداية | 60 | 60 | 10 | 10 |
| Professional | الاحترافية | 300 | 300 | 30 | 30 |
| Enterprise | المؤسسات | 2,000 | 2,000 | 200 | 200 |

**EN:** Rate limit headers:
```
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 245
X-RateLimit-Reset: 1721823600
```

**AR:** رؤوس تحديد المعدل:
```
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 245
X-RateLimit-Reset: 1721823600
```

## 7. Error Codes | رموز الخطأ

| Code | الرمز | Meaning (EN) | المعنى | Resolution | الحل |
|------|-------|--------------|--------|------------|------|
| 400 | 400 | Bad Request | طلب سيء | Check request body and validation rules | تحقق من جسم الطلب وقواعد التحقق |
| 401 | 401 | Unauthorized | غير مصرّح | Verify API key or session | تحقق من مفتاح API أو الجلسة |
| 403 | 403 | Forbidden | ممنوع | Insufficient permissions | أذونات غير كافية |
| 404 | 404 | Not Found | غير موجود | Resource does not exist in tenant scope | المورد غير موجود في نطاق المستأجر |
| 409 | 409 | Conflict | تعارض | Idempotency key already used | مفتاح الإيدمبوتنسي مستخدم بالفعل |
| 422 | 422 | Unprocessable Entity | كيان غير قابل للمعالجة | Business rule violation (e.g., negative stock) | انتهاك قاعدة الأعمال (مثل مخزون سالب) |
| 429 | 429 | Too Many Requests | طلبات كثيرة جداً | Wait and retry | انتظر وأعد المحاولة |
| 500 | 500 | Internal Server Error | خطأ خادم داخلي | Contact support with request ID | اتصل بالدعم مع معرف الطلب |

## 8. Pagination | الترقيم

**EN:** List endpoints return paginated results:
```json
{
  "data": [...],
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 147,
    "total_pages": 8
  }
}
```

**AR:** تُرجع نقاط النهاية القائمة نتائج مُرقّمة:
```json
{
  "data": [...],
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 147,
    "total_pages": 8
  }
}
```

**EN:** Query parameters: `?page=1&per_page=50`
**AR:** معاملات الاستعلام: `?page=1&per_page=50`

## 9. OpenAPI Documentation | مستندات OpenAPI

**EN:** Interactive docs available at:
```
/openapi.json
/redoc
```

**AR:** المستندات التفاعلية متاحة على:
```
/openapi.json
/redoc
```

## 10. SDKs and Libraries | SDKs والمكتبات

| Language | اللغة | Status | الحالة | Repository | المستودع |
|----------|--------|--------|--------|------------|----------|
| Python | بايثون | Available | متاح | `pip install azadexa-sdk` | `pip install azadexa-sdk` |
| JavaScript | جافاسكريبت | Roadmap Q4 2026 | خارطة الطريق Q4 2026 | — | — |
| PHP | PHP | Roadmap Q1 2027 | خارطة الطريق Q1 2027 | — | — |

## 11. Support | الدعم

**EN:** API support: api-support@azadsystems.com | Emergency: +972 56 215 0193
**AR:** دعم API: api-support@azadsystems.com | طارئ: +972 56 215 0193
