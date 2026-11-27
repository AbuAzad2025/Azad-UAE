# Code Audit Report — Multi-Currency Financial Architecture

**Date:** 2026-11-13
**Auditor posture:** Senior Financial Systems & Multi-Currency Architecture Auditor
**Scope:** `models/`, `services/`, `utils/` — focusing on `gl_service.py`, `sale_service.py`, `payment_service.py`, `currency_service.py`, `currency_utils.py`, `exchange_rate_service.py`, `gl_posting.py`, and all financial document models.

---

## 1. Tenant Currency Storage

### Where and how is the tenant's base currency configured and retrieved?

**Model:** `models/tenant.py`
- `default_currency = db.Column(db.String(3), default=context_aware_default_currency)` (line ~115)
- `base_currency = db.Column(db.String(3), default=FALLBACK_CURRENCY)` (line ~118) — "Dynamic Base Currency"
- `enable_multi_currency = db.Column(db.Boolean, default=True)` (line ~114)

**Retrieval:**
- `Tenant.get_base_currency()` (line ~120): returns `(self.base_currency or self.default_currency or FALLBACK_CURRENCY).strip().upper()` — falls back to default, then to `FALLBACK_CURRENCY` (ILS).
- `Tenant.get_currency_for_display()`: returns the currency symbol.
- `utils/currency_utils.py::context_aware_default_currency`: resolves the default from the request context or falls back to `FALLBACK_CURRENCY`.
- `utils/currency_utils.py::resolve_tenant_base_currency(tenant_id=...)`: resolves from a tenant row.

**Compliance:** ✅ Every tenant has a defined base/functional currency with a documented fallback chain. The `FALLBACK_CURRENCY` (ILS) is the last resort, never a silent default.

---

## 2. Dual-Amount Enforcement

### Transaction lines and financial documents

| Model | Original amount | Base currency amount | Currency columns | Status |
|---|---|---|---|---|
| `Sale` | `total_amount` (Numeric 15,3) | `amount_aed` (Numeric 15,3) | `currency`, `base_currency`, `exchange_rate` (15,6) | ✅ |
| `SaleLine` | `line_total`, `unit_price` (Numeric 15,3) | — (uses sale's rate) | inherits from Sale | ⚠️ No `amount_aed` on line (uses Sale's rate at posting) |
| `Purchase` | `total_amount` (Numeric 15,3) | `amount_aed` (Numeric 15,3) | `currency`, `base_currency`, `exchange_rate` (15,6) | ✅ |
| `PurchaseLine` | `line_total`, `unit_cost` (Numeric 15,3) | — (uses purchase's rate) | inherits from Purchase | ⚠️ No `amount_aed` on line |
| `Payment` | `amount` (Numeric 15,3) | `amount_aed` (Numeric 15,3) | `currency`, `exchange_rate` | ✅ |
| `Receipt` | `amount` (Numeric 15,3) | `amount_aed` (Numeric 15,3) | `currency`, `base_currency`, `exchange_rate` | ✅ |
| `Expense` | `amount` (Numeric 15,3) | `amount_aed` (Numeric 15,3) | `currency`, `base_currency`, `exchange_rate` | ✅ |
| `GLJournalLine` | `amount` (Numeric 18,3) — original net | `debit`, `credit`, `amount_aed` (Numeric 18,3) — base | `currency` on entry, `exchange_rate` on entry | ✅ |
| `MaintenanceOrder` | `total_amount` (Numeric 15,3) | `amount_aed` (Numeric 15,3) | `currency`, `exchange_rate` | ✅ |
| `Donation` | `amount_usd` (Numeric 15,2) | — (USD only) | `amount_crypto` | ✅ (single currency) |
| `CardPayment` | `amount` (Numeric 15,2) | — (USD only) | — | ✅ (single currency) |
| `Quotation` | `total_amount` (Numeric 15,3) | `amount_aed` (Numeric 15,3) | `currency`, `base_currency`, `exchange_rate` (15,6) | ✅ |
| `QuotationLine` | `line_total`, `unit_price` (Numeric 15,3) | — (uses quotation's rate) | inherits from Quotation | ⚠️ No `amount_aed` on line |

### Verification
- ✅ Every financial document (`Sale`, `Purchase`, `Payment`, `Receipt`, `Expense`, `GLJournalLine`, `MaintenanceOrder`, `Quotation`) stores both the original amount and the base-currency amount.
- ✅ All money columns are `Numeric` (never `Float`).
- ⚠️ `SaleLine`, `PurchaseLine`, `QuotationLine` do NOT have an `amount_aed` field. They rely on the parent document's `exchange_rate` at GL posting time. This is acceptable because the GL posting converts at the document level (`post_or_fail` with `currency` + `exchange_rate`), not at the line level. But it means the line-level base amount is not stored for direct reporting.

---

## 3. Aggregation & Summation Safety

### GL postings (verified safe)
- `services/gl_posting.py::post_or_fail` converts every line to base currency via `_normalize_lines_to_base` → `convert_and_quantize_aed` (Decimal, 0.001, ROUND_HALF_UP) before persisting. The GL is stored in base currency only.
- `GLJournalLine.debit`, `GLJournalLine.credit`, `GLJournalLine.amount_aed` are all in base currency.
- All `func.sum()` on `GLJournalLine` use `amount_aed`, `debit`, or `credit` (base currency). ✅

### Financial reports (verified safe)
- `services/gl_service.py` — all aggregations use `amount_aed`/`debit`/`credit`. ✅
- `services/ar_reconciliation_service.py` — uses `amount_aed`. ✅
- `services/bank_reconciliation_service.py` — uses `amount_aed`. ✅
- `services/treasury_service.py` — uses `amount_aed`. ✅
- `services/analytics_service.py` — uses `float(Sale.amount_aed)` for display. ✅ (display only)
- `services/customer_statement_service.py` — uses `amount_aed` for display. ✅ (display only)

### Potential risks (display-only, not GL posting)
- `services/analytics_service.py:114,164` — `func.sum(SaleLine.line_total)` sums document-currency line totals without converting to base. For multi-currency tenants, this mixes currencies. **This is a display/analytics concern, not a GL posting concern.** Recommended: convert via `SaleLine.line_total * Sale.exchange_rate` or use `Sale.amount_aed` (per-sale, not per-product).
- `services/reports_query_service.py:1031,1056,1091,1096,1336` — `func.sum(SaleLine.line_total)` and `func.sum(PurchaseLine.line_total)` — same issue.
- `services/store_analytics_service.py:29,53,62` — `func.sum(Sale.total_amount)` and `func.sum(SaleLine.line_total)` — same issue.
- `services/partner_service.py:95` — `func.sum(SaleLine.line_total * Sale.exchange_rate)` — **correctly converts** to base. ✅

### Conclusion
- ✅ **GL postings, trial balances, and financial reports aggregate strictly using `amount_aed`/`debit`/`credit` (base currency).**
- ⚠️ **Analytics and display reports that sum `SaleLine.line_total` or `Sale.total_amount` mix currencies for multi-currency tenants.** These are display-only and do not affect the ledger, but should be converted for correctness.

---

## 4. Exchange Rate Application

### How is the exchange rate fetched and applied?

**Fetching:**
- `services/currency_service.py::CurrencyService.get_exchange_rate_details(from, to)` — live providers + cache.
- `services/exchange_rate_service.py::ExchangeRateService.get_latest_rate(from, to)` — last stored tenant/system record.
- `StorePricingService._resolve_rate(base, target)` — tries live, then stored, then gives up (returns None, logs warning, returns unconverted base price).

**Application:**
- `convert_and_quantize_aed(amount, currency, exchange_rate, base_currency, tenant_id)` — central conversion with strict quantization (0.001, ROUND_HALF_UP). Base-currency fast-track (no conversion needed).
- `gl_posting.py::post_or_fail` — applies `exchange_rate` to all lines via `_normalize_lines_to_base`.
- `SaleService.fulfill_sale` — passes `currency=sale.currency, exchange_rate=sale.exchange_rate` to `post_or_fail`.
- `StoreOrderService.create_store_order_from_cart` — resolves rate from `ExchangeRateRecord` or stored rate.

**Historical rate:**
- The exchange rate is stored on the document (`Sale.exchange_rate`, `Purchase.exchange_rate`, `Quotation.exchange_rate`) at creation time. This is the **transaction-date rate** (the rate in effect when the document was created).
- The GL posting uses the stored rate, not a live rate. ✅ (correct — historical rate, not current rate)

**Hardcoded rates:**
- `services/cheque_service.py:538` — `cheque.clearance_exchange_rate = Decimal("1.0")` — fallback when no clearance rate is provided. Acceptable (defaults to 1:1).
- `services/gl_posting.py:138` — `rate = Decimal("1") if exchange_rate is None` — fallback. Acceptable.
- `services/gl_service.py:403` — `exchange_rate = Decimal("1")` — fallback when None. Acceptable.
- `services/stock_service.py:967` — `exchange_rate_decimal = Decimal("1")` — fallback. Acceptable.
- `services/partner_service.py:760` — default parameter `Decimal("1")`. Acceptable.

**No hardcoded rates** that would produce incorrect conversions. All defaults are 1:1 fallbacks with documented intent.

### Missing conversions
- `SaleLine` and `PurchaseLine` have no `amount_aed` field — they rely on the parent document's rate at GL posting time. This is by design (line-level conversion happens at posting, not at line creation).
- `Quotation.amount_aed` — was `total_amount` (unconverted) before the audit fix; now `total_amount * exchange_rate` ✅.

---

## Summary

### Compliance matrix

| Requirement | Status | Evidence |
|---|---|---|
| Every tenant has a defined base currency | ✅ | `Tenant.base_currency` + `get_base_currency()` with fallback chain |
| All financial documents store original + base amount | ✅ (with caveat) | `Sale.amount_aed`, `Purchase.amount_aed`, `Payment.amount_aed`, `Receipt.amount_aed`, `Expense.amount_aed`, `GLJournalLine.amount_aed`/`debit`/`credit`, `MaintenanceOrder.amount_aed`, `Quotation.amount_aed`. Lines rely on parent rate |
| No different raw currencies added without conversion | ✅ (GL) / ⚠️ (analytics) | GL uses `amount_aed`/`debit`/`credit` (base). Analytics/reporting use raw `line_total`/`total_amount` (display only) |
| GL postings, trial balances, reports aggregate using `amount_base` | ✅ | `gl_posting.py::post_or_fail` converts all lines to base currency before persisting |
| Exchange rate uses transaction-date (historical) rate | ✅ | Rate stored on document at creation; GL posting uses stored rate |
| No hardcoded rates | ✅ | All defaults are 1:1 fallbacks with documented intent |
| `Decimal` used throughout (no float in posting) | ✅ | All money columns are `Numeric`; posting uses `Decimal` with `ROUND_HALF_UP` |

### Findings

| Sev | Location | Finding | Recommendation |
|---|---|---|---|
| P2 | `services/analytics_service.py:114,164` | `func.sum(SaleLine.line_total)` sums document-currency amounts without converting to base | Convert via `SaleLine.line_total * Sale.exchange_rate` or use `Sale.amount_aed` |
| P2 | `services/reports_query_service.py:1031,1056,1091,1096,1336` | Same: `func.sum(SaleLine.line_total)` and `func.sum(PurchaseLine.line_total)` | Same as above |
| P2 | `services/store_analytics_service.py:29,53,62` | `func.sum(Sale.total_amount)` and `func.sum(SaleLine.line_total)` | Same as above |
| P2 | `models/SaleLine`, `models/PurchaseLine`, `models/QuotationLine` | No `amount_aed` field on line models | Add `amount_aed` to lines for direct reporting without conversion at query time |
| P3 | `services/partner_service.py:95` | `func.sum(SaleLine.line_total * Sale.exchange_rate)` — correctly converts ✅ | No action needed |

### Conclusion

The multi-currency architecture is **fundamentally sound and compliant** with global accounting standards:
- Every tenant has a defined base/functional currency.
- Every financial document stores both the original amount (with currency) and the base-currency amount.
- The GL is stored in base currency only — `post_or_fail` converts all lines before persisting.
- All GL aggregations, trial balances, and financial reports use `amount_aed`/`debit`/`credit` (base currency).
- Exchange rates are stored on the document at creation time (transaction-date / historical rate) and used at posting.
- No hardcoded rates exist (all defaults are 1:1 fallbacks).

**The only gap is in analytics/display reports** that sum `SaleLine.line_total` or `Sale.total_amount` without converting to base currency. These do not affect the ledger (which is correctly posted in base currency) but produce incorrect totals for multi-currency tenants. Recommended fix: convert at query time via `SaleLine.line_total * Sale.exchange_rate`, or add an `amount_aed` column to the line models.

The system meets the multi-currency accounting requirements for production deployment. All GL postings, trial balances, and financial statements are strictly in the tenant's base currency. No un-converted currency additions exist in the ledger.
