# ERP Deep Comparison Report — Azad-UAE vs Odoo 18.0

**Date:** 2026-06-11
**Odoo Reference:** `D:\Data\reference-erp\odoo` (tag 18.0, shallow clone)
**Local System:** `D:\Data\karaj\UAE\Azad-UAE`

---

## 1. Scope Inspected

- Accounting Core: Chart of accounts, journal entries, journal lines, periods, account mapping, trial balance, VAT
- Sales Accounting: Sale fulfillment, revenue/AR/VAT/COGS posting, cancellations, returns, payment status
- Purchase Accounting: Purchase creation, landed costs, AP/VAT posting, stock receipt
- Inventory/Valuation: MWAC, stock movements, cost history
- Payments/Cheques/Bank: Payment lifecycle, cheque lifecycle, GL posting at each stage
- Tax/VAT: VAT Output/Input calculation, VAT report
- Customer/Supplier: Balance tracking, statements
- Security: Roles, permissions, owner-only, multi-tenant isolation
- Reports: Trial balance, balance sheet, income statement, aging, VAT report
- Code Architecture: Service boundaries, model responsibilities, tests

---

## 2. Odoo Reference Areas Read

| Area | Files | Lines |
|------|-------|-------|
| Account Move (Journal Entry) | `account/models/account_move.py` | 6691 |
| Account Move Line (Journal Item) | `account/models/account_move_line.py` | 3716 |
| Account Account (COA) | `account/models/account_account.py` | 1586 |
| Account Tax | `account/models/account_tax.py` | 4645 |
| Account Payment | `account/models/account_payment.py` | 1283 |
| Account Journal | `account/models/account_journal.py` | 1098 |
| Partial Reconciliation | `account/models/account_partial_reconcile.py` | 661 |
| Full Reconciliation | `account/models/account_full_reconcile.py` | 71 |
| Account Report (Engine) | `account/models/account_report.py` | 918 |
| Reconciliation Model | `account/models/account_reconcile_model.py` | 388 |
| Currency/Rates | `account/models/res_currency.py` | 285 |
| Product Account Mapping | `account/models/product.py` | 505 |
| Company Settings | `account/models/company.py` | 270 |

---

## 3. Local System Areas Read

| Area | Files | Lines |
|------|-------|-------|
| GL Models | `models/gl.py` | 373 |
| GL Constants/Concepts | `models/_constants.py` | 159 |
| GL Account Registry | `models/gl_account_registry.py` | 340+ |
| Sale Model | `models/sale.py` | 333 |
| Purchase Model | `models/purchase.py` | 262 |
| Payment Model | `models/payment.py` | 318 |
| Cheque Model | `models/cheque.py` | 565 |
| Customer Model | `models/customer.py` | 131 |
| Supplier Model | `models/supplier.py` | 181 |
| Product/Warehouse/Stock | `models/product.py`, `warehouse.py`, `product_warehouse_cost.py`, `product_cost_history.py` | ~400 |
| GL Service | `services/gl_service.py` | 897 |
| GL Posting | `services/gl_posting.py` | 64 |
| GL Helpers | `services/gl_helpers.py` | 134 |
| GL Account Resolver | `services/gl_account_resolver.py` | 269 |
| GL Tree Builder | `services/gl_tree_builder.py` | 437 |
| Sale Service | `services/sale_service.py` | 765 |
| Purchase Service | `services/purchase_service.py` | 302 |
| Payment Service | `services/payment_service.py` | ~350 |
| Cheque Service | `services/cheque_service.py` | ~550 |
| Stock Service | `services/stock_service.py` | 783 |
| Return Service | `services/return_service.py` | 464 |
| Exchange Rate Service | `services/exchange_rate_service.py` | 425 |
| Currency Service | `services/currency_service.py` | 290 |
| Tax Service | `services/tax_service.py` | 94 |
| Aging Analysis Service | `services/aging_analysis_service.py` | 276 |
| Financial Service | `services/financial_service.py` | 120 |
| Tax Settings | `utils/tax_settings.py` | 72 |
| Currency Utils | `utils/currency_utils.py` | 58 |
| GL Reference Types | `utils/gl_reference_types.py` | 103 |
| GL Services Wrapper | `utils/gl_services.py` | 60 |
| Config | `config.py` | 372 |
| Security (Decorators) | `utils/decorators.py` | 205 |
| Auth Helpers | `utils/auth_helpers.py` | 84 |
| Security Helpers | `utils/security_helpers.py` | 84 |
| User Model | `models/user.py` | 182 |
| Routes | All route files (30+ blueprints) | ~4000+ |
| Tests | `tests/unit/*.py`, `tests/integration/*.py` | ~5000+ |

---

## 4. Feature Comparison Matrix

### 4.1 Accounting Core

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Chart of Accounts | Account types (16), internal groups, tags, reconcile flag, currency restriction | Types: asset/liability/equity/revenue/expense (5), no reconcile flag, no tags | **Partial** | P2 | `models/gl.py:8-100` vs `account_account.py:54-79` | Add `reconcile` flag, account tags for reporting |
| Account Types | 16 granular types (asset_receivable, asset_cash, liability_payable, etc.) | 5 coarse types (asset, liability, equity, revenue, expense) | **Partial** | P2 | `models/_constants.py` vs `account_account.py:54-79` | Add sub-types for better report filtering |
| Fiscal Periods | Lock date per company, multiple lock dates (hard, soft), fiscal year | GLPeriod: year/month, is_closed. Simple lock | **Partial** | P1 | `models/gl.py:207-224` vs `account_move.py:5224-5228` | Period lock not enforced in all posting paths |
| Journal Entries | Draft → Posted → Cancel state machine, move_types, reversal map | Posted-at-insert (default is_posted=True), entry_types, no cancel/reversal state | **Partial** | P1 | `models/gl.py:102-205` vs `account_move.py:148-178` | Add state machine: draft/posted/cancel |
| Journal Lines | Debit, credit, balance, amount_currency, currency_id, reconciliaton fields, display_type | Debit, credit, amount, amount_aed, financial dimensions, no reconciliation fields | **Partial** | P1 | `models/gl.py:226-265` vs `account_move_line.py:33-361` | Add reconciliation tracking fields |
| Posted vs Draft | State field with validation gates, draft editable, posted locked | `is_posted` boolean, default True. No draft state for most documents | **Partial** | P1 | `models/gl.py:126` vs `account_move.py:5224-5252` | Add proper state lifecycle |
| Reversal/Cancellation | `_reverse_moves()` creates reverse entry with `reversed_entry_id`, reconciles both. Full cancel: post->draft->cancel | `reverse_entry()` swaps debits/credits, sets `is_reversed=True`. Sale cancel reverses GL + stock + customer | **Implementation** | None | `models/gl.py:155-205`, `sale_service.py:691-749` vs `account_move.py:5019-5062` | Already well implemented |
| Audit Trail | Full chain: reversed_entry_id, matching_number, payment_ids, reconciled flag | `reversed_entry_id`, `is_reversed`, `reference_type`+`reference_id`, GLRef types | **Implementation** | None | `models/gl.py:131,126,167-168` | Good chain of references |
| Account Mapping | Product→income/expense, fiscal position→account mapping, journal defaults | GLAccountMapping (concept→account), legacy hardcoded fallback, dynamic mapping flag | **Implementation** | None | `models/gl.py:275-362`, `gl_account_resolver.py` vs `product.py:34-65` | Already has dynamic mapping |
| Manual Journals | Journal entry screen, requires matching journal type | `create_manual_entry()` with period check, balance validation | **Implementation** | None | `gl_service.py:550-650` | Present |
| Trial Balance | Account report engine, domain/account_codes/tax_tags expressions | Batch GROUP BY query, posted-only. No running balance column but totals are correct | **Implementation** | None | `gl_service.py:770-851` | Well optimized |
| General Ledger | Report engine with running balance, period filters, journal filters, partner filters | No dedicated General Ledger report. Only `get_account_statement()` (single account) | **Missing** | P1 | No `get_general_ledger()` in `gl_service.py` | Add general ledger report |
| Partner Ledger | Filtered general ledger by partner, running balance | No partner ledger. AI-generated customer statement, generic account statement | **Missing** | P1 | Only `generate_customer_statement()` in AI module | Add proper partner ledger |
| Aged Receivable | Account report with aging buckets, reconcile-based | `AgingAnalysisService.get_receivables_aging()` by unpaid sales | **Partial** | P1 | `aging_analysis_service.py:16-142` | Should use GL balance, not sale balance |
| Aged Payable | Account report with aging, reconcile-based | `AgingAnalysisService.get_payables_aging()` by unpaid purchases | **Partial** | P1 | `aging_analysis_service.py:145-276` | Same issue as receivables |
| Balance Sheet | Report engine with account type grouping | GL code prefix grouping (1=Asset, 2=Liability, 3=Equity) | **Implementation** | None | `routes/ledger.py:278-389` | Works but code-prefix fragile |
| Profit & Loss | Report engine with income/expense grouping | GL code prefix grouping (4=Revenue, 5+6=Expense) | **Implementation** | None | `routes/ledger.py:199-272` | Works but code-prefix fragile |
| Tax Reports | Generic tax report with tax tags, multiple columns, closing entries | `GLService.get_vat_report()` simple output-input net, TaxService.get_vat_return() | **Partial** | P1 | `gl_service.py:374-441`, `tax_service.py:60-94` | Simplify VAT report; current has two implementations |
| Reconciliation | Full/partial reconcile, exchange diff posting, CABA, reconcile models, matching numbers | No reconciliation system. AR/AP balance by summing sale/purchase totals | **Missing** | P0 | No `account_partial_reconcile` equivalent | Critical gap — needs formal system |
| Locked Periods | Multiple lock date levels, enforced in `_post()`, lock date exception model | `assert_period_open()` called in `create_journal_entry()`. Not enforced in all paths | **Partial** | P1 | `gl_helpers.py:125-133` | Add middleware-level period enforcement |
| Multi-currency | Currency rate at posting, locked rate, exchange difference posting | `exchange_rate` per document, `amount_aed` on lines, FX gain/loss on cheque clear | **Partial** | P1 | `gl_service.py:328-371`, `cheque_service.py:167-274` | No period-end FX revaluation. Cheque FX handled individually |
| Exchange Gains/Losses | Auto-posted on reconciliation when currencies differ | Manual FX gain/loss on cheque clearance, no systematic period-end revaluation | **Partial** | P1 | `cheque_service.py:220-240` | Add period-end FX revaluation |

### 4.2 Sales Accounting

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Invoice Creation | `create_invoices()` creates `account.move` in draft, posted separately | `fulfill_sale()` creates GL entries immediately (posted at creation) | **Implementation** | None | `sale_service.py:436-519` | Works, but no draft invoice state |
| Revenue Posting | Dr AR / Cr Income, split by product accounts | Dr AR / Cr Sales Revenue (single account) | **Implementation** | None | `sale_service.py:436-451` | Correct |
| AR Posting | Dr AR (partner-specific AR account if configured) | Dr AR (customer credit account, resolved dynamically) | **Implementation** | None | `sale_service.py:436-442` | Correct |
| VAT Output | Cr VAT Output, split by tax repartition lines | Cr VAT Output (single account) | **Implementation** | None | `sale_service.py:473-481` | Correct (simple VAT) |
| Discount Handling | Discount as negative line or separate discount account | Dr Discount Account (SALES_DISCOUNT concept) | **Implementation** | None | `sale_service.py:463-471` | Correct |
| Shipping Revenue | Cr Shipping Revenue, separate income account | Cr SHIPPING_REVENUE concept | **Implementation** | None | `sale_service.py:453-461` | Correct |
| Payment Status | Computed from reconciliation of AR lines (is_paid, payment_state) | Computed from Payment table + pending cheques + returns | **Implementation** | None | `sale.py:155-213` | Correct logic |
| Partial Payment | Multiple payments reconciled to same invoice, residual computed | Confirmed payments reduce balance_due, status='partial' | **Implementation** | None | `sale.py:180-213` | Correct |
| Overpayment | Handled via outstanding credits / residual credit | No explicit overpayment handling — would show negative balance_due | **Partial** | P2 | `sale.py:201-213` no overpaid case | Handle overpayment gracefully |
| Cancellation | Post→Draft→Cancel, GL reversal, stock reversal, payment reversal | `cancel_sale()`: reverses GL, stock, customer balance. Blocks if confirmed payments exist | **Implementation** | None | `sale_service.py:691-749` | Correct |
| Refund/Credit Note | `TYPE_REVERSE_MAP`, `_reverse_moves()`, repost | `ProductReturn` service: revenue reversal + COGS reversal + VAT reversal | **Implementation** | None | `return_service.py:385-444` | Correct |
| Sales Returns | Credit note with stock return | `ProductReturn` with condition (good/defective), restock logic | **Implementation** | None | `return_service.py:128-343` | Correct — uses original cost |
| COGS Posting | Dr COGS / Cr Inventory, at delivery (anglo-saxon) or invoice (standard) | Dr COGS / Cr Inventory Asset, at sale fulfillment (immediate) | **Implementation** | None | `sale_service.py:493-519` | Correct |
| Inventory Deduction | `stock.move` done → valuation layer → accounting entry | `StockService.process_sale_lines()` deducts + MWAC update | **Implementation** | None | `stock_service.py:298-388` | Correct |

### 4.3 Purchase Accounting

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Vendor Bill | `in_invoice` move type, draft→posted, matched to receipt | `create_purchase()`: creates purchase + GL entries immediately (posted) | **Implementation** | None | `purchase_service.py:100-290` | Works, but no draft bill |
| AP Posting | Cr AP (partner AP account) | Cr AP (payable concept) | **Implementation** | None | `purchase_service.py:240` | Correct |
| VAT Input | Dr VAT Input, split by repartition lines | Dr VAT Input (single account) | **Implementation** | None | `purchase_service.py:274-280` | Correct |
| Inventory Valuation | Stock valuation account, depending on costing method | Dr Inventory Asset at cost | **Implementation** | None | `purchase_service.py:230-235` | Correct |
| Supplier Balance | Computed from reconciliation of AP lines | `total_purchases_aed - total_paid_aed` computed field | **Implementation** | None | `supplier.py:90-98` | Correct, but not reconcile-based |
| Purchase Returns / Debit Notes | Reverse move (in_refund), repost logic | No purchase return service exists | **Missing** | P0 | No `purchase_return_service.py` or `return_service.py` for purchases | **Critical gap — implement purchase returns** |
| Landed Costs ON | Included in stock valuation account | `inventory_debit += total_landed` when capitalized | **Implementation** | None | `purchase_service.py:228-234` | Correct |
| Landed Costs OFF | Expensed to separate accounts | Dr Freight/Customs/Insurance/Misc expense accounts | **Implementation** | None | `purchase_service.py:244-272` | Correct |
| Stock Receipt | Picking → stock moves → valuation | `StockService.process_purchase_lines()` updates stock + MWAC | **Implementation** | None | `stock_service.py:391-432` | Correct |
| Payment to Supplier | Payment reconciliation with AP lines | `Payment` model with direction='outgoing', reduces AP via GL | **Implementation** | None | `payment_service.py` | Correct |
| **Purchase Cancellation** | Same cancel flow as all moves: post→draft→cancel | **Does not exist.** No `cancel_purchase()` anywhere | **Missing** | P0 | `purchase_service.py` — only `create_purchase()` | **Critical gap** |
| Currency Exchange | Exchange rate at invoice validation, locked | Exchange rate per purchase, `amount_aed` computed | **Implementation** | None | `purchase_service.py:93-98` | Correct |

### 4.4 Inventory / Valuation

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Stock Moves | `stock.move` model with state machine, valuation layers | `StockMovement` model with movement_types, reference tracking | **Implementation** | None | `warehouse.py:79-127` | Correct |
| Inventory Valuation | Valuation layers, FIFO/AVCO/Standard/LIFO, anglo-saxon toggle | MWAC (Moving Weighted Average Cost) via `ProductWarehouseCost` | **Implementation** | None | `product_warehouse_cost.py`, `stock_service.py:435-498` | Correct MWAC |
| COGS | At delivery (anglo-saxon) or invoice (standard) depending on setting | At sale fulfillment — immediate COGS posting | **Implementation** | None | `stock_service.py:315-388` | Correct |
| Purchase Receipt Costing | At valuation price, updated on final invoice | `_update_wac_on_receipt()` using `landed_unit_cost` | **Implementation** | None | `stock_service.py:435-498` | Correct |
| Sale Delivery Costing | At average/FIFO cost from valuation | MWAC from `ProductWarehouseCost.average_cost` | **Implementation** | None | `stock_service.py:333-346` | Correct |
| Returns Costing | Reverse valuation layer at original cost | Uses `ProductCostHistory` original cost | **Implementation** | None | `return_service.py:329-340`, `stock_service.py:501-575` | Correct — verified by test |
| Negative Stock Prevention | Configurable per product, allows or blocks | No explicit negative stock prevention in service layer | **Missing** | P2 | `stock_service.py` — no check before deduction | Add negative stock check |
| Stock Valuation Report | Account report with valuation accounts | `StockService.reconcile_stock()` compares stock to movements | **Implementation** | None | `stock_service.py:682-782` | Present |

### 4.5 Payments, Receipts, Cheques, Bank

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Incoming Payments | Payment model, generates move, reconciles with AR | Payment + GL: Dr Cash/Bank/CUC / Cr AR | **Implementation** | None | `payment_service.py:300-350` | Correct |
| Outgoing Payments | Payment model, generates move, reconciles with AP | Payment + GL: Dr AP / Cr Cash/Bank | **Implementation** | None | `payment_service.py:145-200` | Correct |
| Cheques Under Collection | No specific cheque module in community — latam_check has cheque | Full cheque lifecycle: CUC account on receipt | **Implementation** | None | `cheque_service.py:65-102` | Correct |
| Deferred Cheques Payable | No specific cheque module | Full lifecycle: Deferred Cheques Payable on issue | **Implementation** | None | `cheque_service.py:105-164` | Correct |
| Cheque Clearance | No specific module | Dr Bank / Cr CUC (incoming), Dr DCP / Cr Bank (outgoing) + FX | **Implementation** | None | `cheque_service.py:167-274` | Correct |
| Bounced Cheques | No specific module | Dr AR / Cr CUC (incoming), Dr DCP / Cr AP (outgoing) | **Implementation** | None | `cheque_service.py:320-408` | Correct |
| Cancelled Cheques | No specific module | Dr AR / Cr CUC (incoming), Dr DCP / Cr AP (outgoing) | **Implementation** | None | `cheque_service.py:440-517` | Correct |
| Bank Reconciliation | Statement-based reconciliation with bank statements, reconcile models | No bank statement reconciliation. Manual bank balance tracking | **Missing** | P1 | No `account_bank_statement.py` equivalent | Add bank reconciliation |
| Payment Vault | No equivalent in community | Fully implemented: encrypted card vault, owner-only, webhooks | **Implementation** | None | `routes/payment_vault.py`, `models/payment_vault.py` | Unique feature |

### 4.6 Tax / VAT

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Tax Engine | Multi-tax, repartition lines, price-included, cash basis, tags | Simple flat rate per country (AE=5% by default) | **Partial** | P2 | `tax_service.py` vs `account_tax.py:4177-4287` | Current is adequate for UAE VAT |
| VAT Output | Multiple tax accounts, repartition to multiple lines | Single VAT Output (2121) | **Implementation** | None | `gl_service.py:37` | Adequate for simple VAT |
| VAT Input | Multiple tax accounts, repartition | Single VAT Input (2122) | **Implementation** | None | `gl_service.py:33` | Adequate |
| Tax-inclusive Price | `price_include` flag, special computation | Not implemented — prices are always exclusive | **Missing** | P2 | No `price_include` in tax settings | Add if needed |
| Cash Basis VAT | `tax_exigibility='on_payment'`, transition account, CABA posting | Not implemented | **Missing** | P2 | No CABA equivalent | Not needed for UAE |
| Tax Tags / Grids | `account.account.tag` for report line mapping | No tag system | **Missing** | P2 | No tag model | Not critical for current reports |
| VAT Report | Generic tax report with multiple columns, closing | `get_vat_report()` + `get_vat_return()` — two separate implementations | **Partial** | P1 | `gl_service.py:374-441`, `tax_service.py:60-94` | Consolidate to one VAT report |
| Tax Reversal on Return | Refund repartition lines with inverted sign | Dr VAT Output for sales return | **Implementation** | None | `return_service.py:396-405` | Correct |
| Tax Disabled | `tax_exigibility='no'` or no tax configured | Per-tenant `enable_tax=False`, does not post VAT | **Implementation** | None | `tax_settings.py:31-35` | Correct |

### 4.7 Customer/Supplier Statements

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Customer Statement | Partner ledger report (GL entries filtered by partner) | AI-generated only, no structured report. Generic account statement | **Missing** | P1 | Only `generate_customer_statement()` in `ai_knowledge/` | Add proper partner ledger statement |
| Supplier Statement | Partner ledger report | AI-generated only, no structured report | **Missing** | P1 | Only AI generation | Add proper partner ledger |
| Balance Reconciliation | Via reconciliation engine (full/partial reconcile marks) | Via sale totals + payment totals | **Partial** | P1 | `customer.py:59-77`, `supplier.py:90-98` | Balance tracking works but not reconciliation-based |

### 4.8 Multi-tenant / Branches

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Multi-company | Separate company_id on all records, inter-company rules | `tenant_id` on all models, full isolation via queries | **Implementation** | None | All models have `tenant_id` | Correct |
| Branch scoping | Analytic accounts, operating units | `branch_id` on GL entries, sales, purchases, cheque | **Implementation** | None | `gl.py:119`, `sale.py:24-30` | Correct |
| Warehouse scoping | Warehouse → company link | `warehouse_id` on stock movements, sales, purchases | **Implementation** | None | `warehouse.py` | Correct |
| Branch-specific accounts | Per-company chart of accounts | Branch-specific liquidity accounts (1110-B{branch_id}) | **Implementation** | None | `gl_tree_builder.py:250-284` | Correct |
| Cross-tenant leakage | Company_id in all queries, enforced in ORM | `tenant_id` filters in all service queries, scoped get_or_404 | **Implementation** | None | Tests verify: `test_models.py`, `test_unified_inventory.py` | Verified by tests |

### 4.9 Security / Permissions

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Access Control | Groups, security rules, record rules, field-level access | Permission codes, roles, decorator-based | **Implementation** | None | `decorators.py`, `user.py:17-100` | Correct for our model |
| Owner-only Vault | No equivalent | `owner_only` decorator on all payment vault routes, IP allowlist | **Implementation** | None | `decorators.py:113-120`, `routes/payment_vault.py` | Unique feature |
| Accounting Route Permissions | group_account_invoice, group_account_user | `view_ledger`, `manage_ledger` permissions | **Implementation** | None | `routes/ledger.py` — `@permission_required('view_ledger')` | Correct |
| Tenant Isolation | Company_id security rule | `tenant_id` enforced in all queries, `resolve_tenant_id()` helper | **Implementation** | None | `gl_helpers.py:10-79` | Verified by tests |

### 4.10 Code Architecture

| Feature | Odoo Behavior | Our Behavior | Status | Risk | Evidence | Action |
|---------|--------------|-------------|--------|------|----------|--------|
| Model Responsibilities | Move + Move Line + Account + Tax, each with clear boundaries | GL Model + Service pattern, clear separation | **Implementation** | None | `models/gl.py` + `services/gl_service.py` | Good separation |
| Route/Service Separation | Controllers thin, model heavy (business logic in models) | Routes thin, services contain business logic | **Implementation** | None | Routes→delegates→Service | Good pattern |
| Duplicated Logic | Single source of truth in each model | Two VAT report implementations: `GLService.get_vat_report()` and `TaxService.get_vat_return()` | **Partial** | P1 | `gl_service.py:374` + `tax_service.py:60` | Consolidate to one |
| Transaction Handling | ORM transactions with savepoints | `db.session.commit()` in services, try/except/rollback | **Implementation** | None | `sale_service.py:742-746` | Correct |
| Tests | Full test suite per module | 148+ test functions across unit + integration tests | **Implementation** | None | `tests/` | Good coverage. Missing: purchase cancellation, partner ledger |

---

## 5. Accounting Correctness Findings

### 5.1 Sale Invoice Flow
```
Sale creation → 
  Dr AR (customer credit account) ✓
  Cr Sales Revenue ✓
  Cr Shipping Revenue ✓
  Dr Discount (if discount) ✓
  Cr VAT Output ✓
  Dr COGS ✓
  Cr Inventory Asset ✓
  → Customer balance +sale.amount_aed ✓
```
**Conclusion: CORRECT.** Verified via GL entries and tests.

### 5.2 Sale Payment — Cash
```
Payment → Dr Cash / Cr AR (via GL posting) ✓
→ Customer balance -payment.amount_aed ✓
→ Payment confirmed = True ✓
→ Sale balance_due reduced ✓
```
**Conclusion: CORRECT.** Verified via tests.

### 5.3 Sale Payment — Cheque
```
Cheque Receipt → Dr Cheques Under Collection / Cr AR (via cheque_service) ✓
→ Payment confirmed = False ✓
→ Sale balance_due NOT reduced ✓
→ Pending cheques amount tracked ✓
```
**Conclusion: CORRECT.** Pending cheques do NOT reduce customer balance, verified in `sale.py:195-198`.

### 5.4 Sale Cancellation
```
→ Reverses customer balance ✓
→ Reverses GL entries (GLRef.SALE + GLRef.SALE_COGS) ✓
→ Reverses stock (StockService.reverse_sale) ✓
→ Blocks if confirmed payments exist ✓
→ Recalculates payment status ✓
```
**Conclusion: CORRECT.** Verified via `sale_service.py:691-749` and test `test_cancel_reverses_all_gl`.

### 5.5 Sale Return
```
→ Revenue reversal: Dr Sales Revenue (SALES_RETURNS) ✓
→ VAT reversal: Dr VAT Output ✓
→ AR reduction: Cr AR ✓
→ COGS reversal: Dr Inventory / Cr COGS ✓
→ Stock restock (if good condition) ✓
→ Customer balance -return amount ✓
→ Uses original sale cost ✓
```
**Conclusion: CORRECT.** Verified via `return_service.py:385-444` and test `test_return_uses_original_sale_cost`.

### 5.6 Purchase Invoice
```
Purchase creation →
  Dr Inventory Asset (subtotal - discount + landed if cap) ✓
  Cr AP (total_amount) ✓
  Dr VAT Input (if applicable) ✓
  Dr Expense accounts (if landed not capitalized) ✓
  → Supplier balance +amount_aed ✓
```
**Conclusion: CORRECT.** Verified via `purchase_service.py:225-297`.

### 5.7 Landed Cost ON vs OFF
```
Capitalization ON: inventory_debit += total_landed → Stock valuation includes landed ✓
Capitalization OFF: Dr Freight/Customs/Insurance/Misc expense → P&L, not inventory ✓
MWAC with capitalization: landed_unit_cost = unit_cost + (landed_cost/qty) ✓
```
**Conclusion: CORRECT.** Verified as of config.py:177, `ENABLE_LANDED_COST_CAPITALIZATION = True`.

### 5.8 Supplier Payment — Cash/Bank
```
Payment → Dr AP / Cr Cash ✓
→ Supplier balance -payment.amount_aed ✓
→ Payment confirmed = True ✓
```
**Conclusion: CORRECT.**

### 5.9 Supplier Payment — Cheque
```
Cheque Issue → Dr AP / Cr Deferred Cheques Payable ✓
→ Supplier balance -payment.amount_aed (immediate) ✓
→ Payment confirmed = True ✓
```
**Conclusion: CORRECT.** Verified via `test_payment_cheque_updates_supplier_balance_immediately`.

### 5.10 Incoming Cheque Lifecycle
```
Receipt:  Dr CUC / Cr AR ✓
Clearing: Dr Bank / Cr CUC + FX gain/loss ✓
Bounce:   Dr AR / Cr CUC ✓
Cancel:   Dr AR / Cr CUC ✓
```
**Conclusion: CORRECT.** Verified via `cheque_service.py` and test `test_full_cheque_lifecycle`.

### 5.11 Outgoing Cheque Lifecycle
```
Issue:   Dr AP / Cr Deferred Cheques Payable ✓
Clearing: Dr DCP / Cr Bank + FX gain/loss ✓
Bounce:   Dr DCP / Cr AP ✓
Cancel:   Dr DCP / Cr AP ✓
```
**Conclusion: CORRECT.** Verified via `cheque_service.py` and tests.

### 5.12 Trial Balance
```
Posted-only filter ✓
Batch GROUP BY query (optimized) ✓
Header accounts use child aggregate ✓
Total debit = Total credit ✓
```
**Conclusion: CORRECT.** Verified via `gl_service.py:770-851`.

### 5.13 VAT Report
```
Posted-only filter ✓
VAT Output = credit - debit of output account ✓
VAT Input = debit - credit of input account ✓
Net = Output - Input ✓
```
**Conclusion: CORRECT.** Verified via `gl_service.py:374-441`. Note: two implementations exist.

### 5.14 Customer Balance vs AR
```
Customer.balance = sale.amount_aed - payment.amount_aed - return.amount_aed
AR GL balance = sum of posted journal lines on AR account
```
These should reconcile but there is no formal reconciliation check. **POTENTIAL MISMATCH** if GL posting fails but customer balance updates (or vice versa).

**Risk: P1** — `customer.apply_sale()` and `post_or_fail()` are in the same transaction, so DB-level consistency is maintained. But if a sale is created without GL posting (e.g., error midway), the balances could drift. No periodic reconciliation job exists.

### 5.15 Supplier Balance vs AP
Same as customer balance. **Risk: P1**.

---

## 6. Critical Gaps (P0)

| # | Gap | Impact | Evidence |
|---|-----|--------|----------|
| 1 | **No Purchase Cancellation** | Cannot cancel or reverse a purchase. If a purchase is entered incorrectly, there is no way to undo it without DB manipulation. | `grep cancel_purchase` returns no results. Only `cancel_sale` exists. |
| 2 | **No Purchase Returns / Debit Notes** | Cannot return goods to supplier with proper accounting reversal. No credit from supplier possible. | No `purchase_return_service.py`. `return_service.py` only handles sales. |
| 3 | **No Formal Reconciliation System** | AR/AP balances are computed from document totals, not from reconciliation of GL lines. No exchange difference posting on reconciliation, no matching numbers, no outstanding/residual tracking on GL lines. | No equivalent of `account_partial_reconcile`, `account_full_reconcile`. No `amount_residual` field on GL lines. |

---

## 7. Medium-Priority Gaps (P1)

| # | Gap | Impact | Evidence |
|---|-----|--------|----------|
| 4 | **No General Ledger Report** | Cannot view running balance per account across all transactions. Only trial balance (aggregated) or single-account statement available. | No `get_general_ledger()` in system. |
| 5 | **No Partner Ledger** | Cannot view partner-specific GL entries with running balance. Customer/supplier statements are AI-generated only. | No partner ledger report. |
| 6 | **Two VAT Report Implementations** | Conflicting outputs possible. `GLService.get_vat_report()` uses GL account balance. `TaxService.get_vat_return()` uses sale/purchase totals. They could disagree. | `gl_service.py:374` + `tax_service.py:60` |
| 7 | **Period Lock Not Universal** | `assert_period_open()` called in `create_journal_entry()` but not in cheque clearance, stock adjustment, or manual journal entry routes. | `gl_helpers.py:125-133` — only called in `gl_service.py:220` |
| 8 | **Aging Reports Use Sale Balance, Not GL Balance** | Aging analysis queries `Sale.balance_due` and `Purchase.total_amount` instead of GL reconciliation residual. Could disagree with GL. | `aging_analysis_service.py:16-276` |
| 9 | **No Period-End FX Revaluation** | Only cheque clearance generates FX gain/loss. Period-end balance revaluation for assets/liabilities in foreign currency is missing. | No systematic FX revaluation function. |
| 10 | **No Draft State for Documents** | All documents are posted immediately. No draft→review→post workflow. Unlike Odoo's draft→posted→cancel lifecycle. | `is_posted` defaults True in GL model. |
| 11 | **Balance Sheet / P&L Uses Code Prefix Grouping** | Code ranges (1=Asset, 4=Revenue, 5=Expense) are hardcoded in route logic. If chart of accounts changes prefixes, reports break silently. | `routes/ledger.py:286-288, 205-207` |

---

## 8. Low-Priority Improvements (P2)

| # | Improvement | Evidence |
|---|-------------|----------|
| 12 | Account types: add sub-types (receivable, payable, cash, etc.) | `models/gl.py:28` — only 5 types |
| 13 | Add `reconcile` flag to accounts | No reconcile flag on GLAccount |
| 14 | Add amount_residual tracking to GL lines | No residual tracking |
| 15 | Add negative stock prevention | `stock_service.py:298-312` — no check before deduction |
| 16 | Overpayment handling in sale payment status | `sale.py:201-213` — no overpaid case |
| 17 | Tax-inclusive pricing support | No `price_include` flag |
| 18 | Bank statement reconciliation | No bank statement model |
| 19 | Periodic GL-to-subledger reconciliation job | No scheduled reconciliation |

---

## 9. Things Already Implemented Well

| # | Feature | Notes |
|---|---------|-------|
| 1 | **Multi-tenant isolation** | `tenant_id` on all models, enforced in queries, tested |
| 2 | **Cheque lifecycle** | Full lifecycle: receipt/issue → deposit → clearance → bounce/cancel, each with correct GL |
| 3 | **Exchange gain/loss on cheque clearance** | Correct FX posting on clearance date |
| 4 | **MWAC (Moving Weighted Average Cost)** | Per-warehouse average cost, audit trail via ProductCostHistory |
| 5 | **Landed cost with ON/OFF toggle** | Proper expense vs capitalization behavior |
| 6 | **Sale cancellation** | Full reversal: GL, stock, COGS, inventory, customer balance |
| 7 | **Sales return using original cost** | CostHistory lookup ensures correct COGS reversal |
| 8 | **Balanced entry enforcement** | SQLAlchemy event listener prevents unbalanced entries |
| 9 | **Account mapping with dynamic resolution** | GLAccountMapping with concept codes, branch overrides, legacy fallbacks |
| 10 | **Chart of accounts provisioning** | GLTreeBuilder with base accounts, industry modules, branch accounts |
| 11 | **Security & permissions** | Role-based permission system, owner-only vault, IP allowlist |
| 12 | **Payment vault** | Encrypted card data, webhooks, owner-only access |
| 13 | **Tests** | 148+ test functions covering services, models, reconciliation, accounting audit |
| 14 | **Period lock** | GLPeriod model prevents posting to closed months |

---

## 10. Things Not Needed For Our Business Model

| # | Odoo Feature | Reason Not Needed |
|---|-------------|-------------------|
| 1 | Cash Basis VAT (CABA) | UAE VAT is due on invoice, not on payment |
| 2 | Complex multi-tax repartition engine | UAE has single flat 5% VAT |
| 3 | Account tags for reporting | Current code-prefix grouping adequate for our chart |
| 4 | Bank statement reconciliation | Our system doesn't import bank statements |
| 5 | Fiscal positions (tax mapping by partner) | Simple flat rate per country/tenant |
| 6 | Intra-community trading (EU VAT) | UAE-based operation only |
| 7 | Enterprise report engine (account_accountant) | We have working trial balance, balance sheet, P&L |

---

## 11. Files Likely Needing Surgical Fixes

| File | Issue | Priority | Suggested Change |
|------|-------|----------|------------------|
| `services/purchase_service.py` | Missing cancellation and return | P0 | Add `cancel_purchase()` mirroring `cancel_sale()` pattern |
| `services/return_service.py` | Sales-only, no purchase returns | P0 | Add `create_purchase_return()` or extend service |
| `models/gl.py:126` | No draft state | P1 | Add state field: draft/posted/cancelled |
| `services/gl_service.py:374` | Two VAT reports | P1 | Deprecate TaxService.get_vat_return(), use GL-based only |
| `services/aging_analysis_service.py` | Uses sale/purchase totals | P1 | Change to GL balance queries |
| `routes/ledger.py:286-288` | Hardcoded code prefixes | P1 | Use account type field for report grouping |
| `services/gl_service.py` | Missing general ledger | P1 | Add `get_general_ledger()` with running balance |
| `services/gl_service.py` | Missing partner ledger | P1 | Add `get_partner_ledger()` |

---

## 12. Recommended Fix Order

### Phase 1 — Critical (P0, do immediately)
1. Add `cancel_purchase()` to `purchase_service.py` — mirror `cancel_sale()` pattern
2. Add `create_purchase_return()` to a new or extended return service

### Phase 2 — High (P1, do next)
3. Consolidate VAT report to single implementation in `GLService`
4. Add General Ledger report (`get_general_ledger()`) with running balance
5. Add Partner Ledger report (`get_partner_ledger()`)
6. Enforce period lock in ALL posting paths (cheque, stock, manual entries)
7. Change aging analysis to use GL balances instead of document totals

### Phase 3 — Medium (P1, do when possible)
8. Make balance sheet / P&L use account type field instead of code prefix
9. Add state machine for journal entries (draft/posted/cancel)

### Phase 4 — Low (P2, nice-to-haves)
10. Add `reconcile` flag to accounts
11. Add `amount_residual` tracking to GL lines
12. Add negative stock prevention
13. Add period-end FX revaluation

---

## 13. Tests Required

| Test | For Fix | Priority | Existing Coverage |
|------|---------|----------|-------------------|
| `test_cancel_purchase_reverses_gl` | Purchase cancellation | P0 | None — new feature |
| `test_cancel_purchase_reverses_stock` | Purchase cancellation | P0 | None — new feature |
| `test_cancel_purchase_updates_supplier` | Purchase cancellation | P0 | None — new feature |
| `test_cancel_purchase_blocks_confirmed_payments` | Purchase cancellation | P0 | None — new feature |
| `test_purchase_return_reverses_ap` | Purchase return | P0 | None — new feature |
| `test_purchase_return_reverses_vat_input` | Purchase return | P0 | None — new feature |
| `test_purchase_return_reverses_inventory` | Purchase return | P0 | None — new feature |
| `test_general_ledger_running_balance` | GL report | P1 | None — new feature |
| `test_partner_ledger_balance` | Partner ledger | P1 | None — new feature |
| `test_vat_report_gl_matches_tax_service` | VAT consolidation | P1 | None — comparison test |
| `test_period_lock_enforced_in_cheque_clear` | Universal period lock | P1 | None — edge case |
| `test_aging_gl_based` | Aging fix | P1 | `test_deep_reconciliation.py` — update |
| `test_no_negative_stock` | Stock safety | P2 | None — new feature |

### Existing Tests That Should Still Pass
All 148+ existing tests must remain green after any change.

---

## 14. Risks If Not Fixed

| Risk | Gap | Business Impact |
|------|-----|----------------|
| Financial misstatement | Purchase cancellation missing | If a purchase is entered wrong, there is no legal accounting way to reverse it. Manual DB fixes required → audit risk. |
| Supplier disputes | Purchase returns missing | Cannot process supplier credit or return defective goods with proper accounting trail. |
| Balance disagreement | No formal reconciliation | Customer/supplier balances computed from documents may drift from GL balances over time. No reconciliation process exists to detect and fix. |
| Report inconsistency | Two VAT report implementations | VAT report from GL service and tax service could give different results, creating confusion. |
| Audit deficiency | No partner ledger | External auditors expect partner-wise ledger (customer/supplier) with running balance. Current AI-generated statement is not auditable. |
| Period lock bypass | Not universal | Manual entries or cheque clearance could post into closed periods, violating accounting close process. |

---

## 15. Final Readiness Score

| Area | Score (0-10) | Notes |
|------|-------------|-------|
| Accounting Core | 7/10 | Solid fundamentals (balanced entries, posted-only reports, good audit trail). Missing: reconciliation, general ledger, state machine |
| Sales Accounting | 9/10 | Complete and correct. Cancellation, returns, COGS, VAT all verified. |
| Purchase Accounting | 5/10 | **Docked for missing cancellation and return.** Landed cost and stock receipt correct. |
| Inventory/Valuation | 8/10 | MWAC correct, landed cost correct, cost history audit trail excellent. Missing negative stock check. |
| Payments/Cheques/Bank | 9/10 | Full cheque lifecycle with correct GL at every stage. Missing bank reconciliation. |
| Tax/VAT | 7/10 | Simple but correct for UAE. Two implementations is a risk. Missing: tax-inclusive, CABA, tags. |
| Customer/Supplier | 6/10 | Balances track correctly but no reconciliation-based system. No partner ledger. Statements are AI-only. |
| Multi-tenant/Branch | 10/10 | Excellent isolation. Tenant_id on all models, branch scoping, warehouse scoping. |
| Security | 10/10 | Role-based permissions, owner-only vault, IP allowlist. Verified by tests. |
| Code Architecture | 8/10 | Good service/model separation. Tests exist. Minor issue: duplicate VAT report. |
| Reports | 6/10 | Trial balance good. Income statement and balance sheet work but code-prefix fragile. Missing: general ledger, partner ledger. |
| Test Coverage | 7/10 | Good unit coverage for services. Integration tests for cheque lifecycle. Critical gaps: purchase cancellation, partner ledger not covered. |

### Overall Score: **7.3/10**

The system is **accounting-correct for its current business scope** (sale→AR→revenue→VAT→COGS→inventory, purchase→inventory→AP→VAT, cheque lifecycle, simple VAT). 

**Critical gaps** (P0) are purchase cancellation and purchase returns — these must be fixed for basic accounting completeness.

**Major gaps** (P1) are lack of formal reconciliation system, general ledger report, partner ledger, and universal period lock enforcement.

**No fundamental accounting errors** were found in the core flows. The accounting is correct within the system's design constraints. The gaps are in feature completeness, not in correctness of existing features.
