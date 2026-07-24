# API Reference — Azadexa ERP

## 1. Base URL

| Environment | URL |
|-------------|-----|
| Production | `https://<tenant-slug>.azadsystems.com` |
| API root | `https://<tenant-slug>.azadsystems.com/api/v2` |

## 2. Authentication

### 2.1 API Key (External Systems)

External POS systems and integrations authenticate via API key.

| Header | Value |
|--------|-------|
| `X-API-Key` | `{key}` |
| `X-API-Secret` | `{secret}` |

The key is scoped to a `tenant_id`. The `@api_key_required` decorator sets `g.active_tenant_id`, enabling automatic ORM tenant scoping.

### 2.2 Session (Internal Users)

Authenticated users use session cookies (Flask-Login + CSRF).

| Header | Value |
|--------|-------|
| `Cookie` | `session={value}` |

## 3. External POS Stock Sync

### 3.1 Submit Sync Batch

```
POST /api/v2/stock/sync
```

**Headers:**
```
Content-Type: application/json
X-API-Key: {key}
X-API-Secret: {secret}
```

**Body:**
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

**Response 202 Accepted:**
```json
{
  "batch_id": "pos-2026-07-24-001",
  "status": "accepted",
  "records_received": 1,
  "sync_url": "/api/v2/stock/sync/status/pos-2026-07-24-001"
}
```

**Response 400 Bad Request:**
```json
{
  "error": "Invalid SKU: SKU-12345 not found in tenant scope"
}
```

**Response 401 Unauthorized:**
```json
{
  "error": "Invalid or expired API key"
}
```

### 3.2 Check Sync Status

```
GET /api/v2/stock/sync/status/{batch_id}
```

**Response 200:**
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

**Response 404:**
```json
{
  "error": "Batch not found"
}
```

### 3.3 Idempotency

The `batch_id` is idempotent. Re-submitting the same `batch_id` with identical payload returns the cached result without reprocessing.

## 4. Core API Endpoints

### 4.1 Products

```
GET /api/products
GET /api/products/{id}/info
GET /api/products/barcode/{code}
GET /api/warehouses/{wid}/products
```

### 4.2 Sales

```
POST /api/sales
GET /api/sales/{id}
```

### 4.3 Customers

```
GET /api/customers
GET /api/customers/{id}/balance
GET /api/customers/{id}/sales
```

### 4.4 Exchange Rates

```
GET /api/exchange-rates/display?base=AED
GET /api/currency-rate/{from}/{to}
```

### 4.5 Health & System

```
GET /health
GET /version
```

## 5. Webhooks

### 5.1 Events

| Event | Payload | Trigger |
|-------|---------|---------|
| `sale.created` | Sale object | New sale finalized |
| `payment.received` | Payment object | Payment recorded |
| `stock.moved` | Movement object | Stock movement created |
| `cheque.bounced` | Cheque object | Cheque bounce processed |
| `invoice.issued` | Invoice object | Invoice printed/emailed |

### 5.2 Subscription

```
POST /api/webhooks/subscribe
```

**Body:**
```json
{
  "url": "https://partner.com/webhook",
  "events": ["sale.created", "payment.received"],
  "secret": "whsec_xxxxxxxx"
}
```

### 5.3 Signature Verification

Payloads are signed with HMAC-SHA256:

```
X-Webhook-Signature: t={timestamp},v1={signature}
```

Verify using the shared secret:

```python
import hmac, hashlib

expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
```

## 6. Rate Limiting

| Plan | Requests / Minute | Burst |
|------|-------------------|-------|
| Starter | 60 | 10 |
| Professional | 300 | 30 |
| Enterprise | 2,000 | 200 |

Rate limit headers:

```
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 245
X-RateLimit-Reset: 1721823600
```

## 7. Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| 400 | Bad Request | Check request body and validation rules |
| 401 | Unauthorized | Verify API key or session |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource does not exist in tenant scope |
| 409 | Conflict | Idempotency key already used |
| 422 | Unprocessable Entity | Business rule violation (e.g., negative stock) |
| 429 | Too Many Requests | Wait and retry |
| 500 | Internal Server Error | Contact support with request ID |

## 8. Pagination

List endpoints return paginated results:

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

Query parameters: `?page=1&per_page=50`

## 9. OpenAPI Documentation

Interactive docs available at:

```
/openapi.json
/redoc
```

## 10. SDKs and Libraries

| Language | Status | Repository |
|----------|--------|------------|
| Python | Available | `pip install azadexa-sdk` |
| JavaScript | Roadmap Q4 2026 | — |
| PHP | Roadmap Q1 2027 | — |

## 11. Support

API support: api-support@azadsystems.com
Emergency: +972 56 215 0193
