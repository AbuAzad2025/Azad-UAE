# Integration Guide — Azadexa ERP

## 1. External POS Stock Sync

### 1.1 Overview

External POS systems (e.g., Shopify POS, custom Android POS, legacy systems) can sync stock movements into Azadexa in real time via authenticated API.

### 1.2 Authentication

1. Create an API key in `routes/owner/settings.py` → API Keys.
2. Assign `tenant_id` to the key.
3. Use `X-API-Key` and `X-API-Secret` headers.

### 1.3 Endpoint

```
POST /api/v2/stock/sync
```

### 1.4 Payload

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

### 1.5 Idempotency

Submitting the same `batch_id` with identical payload returns cached result. Use UUIDs or `{date}-{counter}` for `batch_id`.

### 1.6 Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| 400 Invalid SKU | SKU not found in tenant scope | Verify SKU exists in `products` table |
| 400 Invalid warehouse | Warehouse code not found | Verify `warehouse.code` matches |
| 422 Negative stock | Resulting quantity < 0 and negative stock disabled | Enable negative stock in settings or adjust quantity |
| 429 Rate limited | Exceeded plan limit | Retry with exponential backoff |

### 1.7 Webhook Confirmation

Azadexa can send a webhook to your POS when the sync is complete:

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

## 2. Payment Gateway Integration

### 2.1 Stripe

- Webhook endpoint: `/stripe`
- Events handled: `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.updated`
- Configure in `routes/owner/settings.py` → Payment Gateways.

### 2.2 NOWPayments (Cryptocurrency)

- Supported: BTC, ETH, USDT, and 50+ cryptocurrencies.
- Webhook endpoint: `/payment/callback`
- Configure API key in `config.py` or environment variable.

### 2.3 Custom Payment Gateway

1. Implement `StoreOnlinePaymentService` interface.
2. Add webhook handler in `routes/billing_webhooks.py`.
3. Register in `utils/decorators.py` if authentication is needed.

## 3. WhatsApp Business API

### 3.1 Use Cases

- Payment reminders.
- Invoice delivery.
- Support ticket updates.
- Abandoned cart recovery.

### 3.2 Configuration

1. Obtain WhatsApp Business API credentials from Meta.
2. Configure in `routes/owner/settings.py` → WhatsApp Settings.
3. Set `WHATSAPP_API_KEY` and `WHATSAPP_PHONE_NUMBER_ID` in environment.

### 3.3 Message Templates

Templates must be pre-approved by Meta. Supported languages: Arabic, English.

## 4. Accounting Software Integration

### 4.1 QuickBooks (Roadmap Q4 2026)

Planned sync: Chart of accounts, journal entries, invoices.

### 4.2 Xero (Roadmap Q1 2027)

Planned sync: Contacts, invoices, bank transactions.

## 5. E-commerce Platform Integration

### 5.1 Shopify (Roadmap Q4 2026)

Planned: Product sync, order import, inventory sync.

### 5.2 WooCommerce (Roadmap Q1 2027)

Planned: Product sync, order import, customer sync.

## 6. Custom Webhook Setup

### 6.1 Subscribe

```
POST /api/webhooks/subscribe
```

Body:
```json
{
  "url": "https://partner.com/webhook",
  "events": ["sale.created", "payment.received"],
  "secret": "whsec_your_secret"
}
```

### 6.2 Verify Signature

```python
import hmac, hashlib

expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
assert signature == expected
```

## 7. Support

Integration support: integration-support@azadsystems.com
Emergency: +972 56 215 0193
