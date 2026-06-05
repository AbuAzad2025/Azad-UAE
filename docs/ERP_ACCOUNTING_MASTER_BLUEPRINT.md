# ERP Accounting Master Blueprint

**Document Status:** Single Source of Truth — Supersedes All Accounting Documentation  
**Date:** June 4, 2026  
**Last Updated:** June 5, 2026 (Session 2)

> **NOTICE:** This document is the sole authoritative accounting plan. All previous accounting documents (listed in Section 1.1) are superseded and should be removed from active reference.  
**Reference Standards:** SAP Business One, Oracle NetSuite, Odoo, Bisan, Al-Shamel  
**Strategic Markets:** Palestine, GCC countries, Arabic markets, Future international expansion  

---

## 1. Introduction & Consolidated Source Documents
This master blueprint acts as the single, authoritative source of truth for the Azad ERP financial architecture and modernization implementation plan. It details the principles, posting templates, dimensional configurations, database rules, and phased execution roadmap.

### Source Documents Consolidated (Superseded)
This master document merges, preserves, and supersedes the following documents. They are retained in `docs/archive/accounting_architecture/` for historical reference only:

| Document | Superseded Content |
|----------|-------------------|
| `docs/archive/accounting_architecture/ERP_ACCOUNTING_PRINCIPLES.md` | Principles, formulas, GL integration patterns |
| `docs/archive/accounting_architecture/ERP_ACCOUNTING_DECISION_MATRIX.md` | Approved policies DM-01 to DM-14 |
| `docs/archive/accounting_architecture/WAC_ACCOUNTING_ARCHITECTURE_REVIEW.md` | Technical costing design, gaps, dimensions |
| `docs/archive/accounting_architecture/FUTURE_ROADMAP_WAC_AND_RECONCILIATION.md` | Reconciliation rules, WAC validation bounds |
| `docs/archive/accounting_architecture/FUTURE_ROADMAP_DYNAMIC_GL_MAPPING.md` | Concept-based GL lookup model |
| `docs/archive/accounting_architecture/FUTURE_ROADMAP_PAYROLL_PAYMENT_AI_AUDIT.md` | Payroll rules, WPS checking, anomaly tracking |
| `docs/archive/accounting_architecture/ERP_ACCOUNTING_IMPLEMENTATION_PLAN.md` | Modernization roadmap, phase definitions, approval gates |

**Also superseded and merged into this document:**
* `docs/IMPLEMENTATION_PROGRESS.md` → Section 12 (Implementation History)
* `docs/BATCH_3_FINANCIAL_RELATIONSHIP_SAFETY_REPORT.md` → Section 12.3
* `docs/BATCH_4_INDEXING_SCHEMA_HARDENING_REPORT.md` → Section 12.4
* `docs/BATCH_5_MODEL_MIGRATION_SYNC_REPORT.md` → Section 12.5
* `docs/FINDINGS_VALIDATION_REPORT.md` → Appendix B
* `docs/PRE_IMPLEMENTATION_VERIFICATION.md` → Appendix B
* `docs/SYSTEM_REVERSE_ENGINEERING_MASTER_REPORT.md` → Appendix A
* `docs/AI_AUDIT_HISTORY.md` → Appendix A

---

## 2. Core Approved Accounting Principles

### 2.1 Perpetual Inventory System
The system operates on a Perpetual Inventory model. Every inventory-affecting movement (purchase, sale, return, transfer, adjustment) must trigger immediate physical stock updates and generate a balanced double-entry journal entry to the General Ledger.

### 2.2 Costing Method: Moving Weighted Average Cost (MWAC)
The sole inventory costing method is **Moving Weighted Average Cost (MWAC)**.
*   **Valuation Integrity:** No Last Purchase Cost fallback. No FIFO layers or layer consumption logic. No hybrid costing.
*   **Audit-Only History:** Product cost history is read-only for audit trails, never used by the transaction engine.
*   **Recalculation Scope:** Evaluated per product per warehouse (Approved Choice DM-02). Outgoing movements do not affect average unit costs.

### 2.3 Warehouse Transfer Costing
Transfers between warehouses are valued at the source warehouse's MWAC at the exact moment of transfer. Recipients recalculate average cost on receipt. No profit or loss is recognized on transfers.

### 2.4 Sales Returns Costing
*   **Linked Returns:** Use the original `SaleLine.cost_price` to reverse COGS.
*   **Unlinked Returns:** Use the current warehouse MWAC, with optional manual overrides and audit trails.

### 2.5 Landed Cost Capitalization
Landed costs (freight, customs, insurance, clearance, handling) are capitalized into inventory value. The default allocation method is **By Value**. Future methods will include allocation by quantity, weight, and volume.

---

## 3. Approved Decision Matrix (DM-01 to DM-14)

| ID | Decision Area | Approved Policy | Rationale |
|----|---------------|-----------------|-----------|
| **DM-01** | Costing Method | MWAC | Smooths volatility; standard in SAP B1 & Bisan. |
| **DM-02** | MWAC Scope | Per Product, Per Warehouse | Localized logistics tracking. |
| **DM-03** | Transfer Cost | Source warehouse MWAC | Net neutrality across stock assets. |
| **DM-04** | Linked Returns | Original SaleLine cost | Margin and COGS reversal consistency. |
| **DM-05** | Unlinked Returns | Current MWAC (manual override) | Exceptions tracking with audit trail. |
| **DM-06** | Landed Cost Alloc | Proportional By Value | Proportional allocation for mixed goods. |
| **DM-07** | Landed Cost Treatment | Capitalize into inventory | Standard IAS 2 compliance. |
| **DM-08** | Exchange Rate | Manager manual rate / Fallback online | Rate is locked on post; historical immutability. |
| **DM-09** | FX Differences | Post to FX Gain/Loss (P&L) | IAS 21 compliance. |
| **DM-10** | Closed Periods | Block all modifications | Ledger integrity. Corrections in open periods. |
| **DM-11** | Reconciliation | Reporting and monitoring only | No auto-posting without validation. |
| **DM-12** | Dynamic GL Mapping | Resolution via GL Concepts | Tenant-level mappings (Phase 1). Branch overrides (Phase 2). |
| **DM-13** | Precision Rules | Hybrid Framework | Intermediates and rates at 6 decimals; unit cost at 4; quantity at 3. |
| **DM-14** | Localization | Global Localization Framework | Country specific tax, currencies, and e-invoicing layers. |

---

## 4. Financial Dimensions & Account Structure

To prevent chart of accounts bloat (tree explosion), the system strictly decouples the financial classification of transactions from their business segment context.

### 4.1 Account Structure Principle
*   **Accounts** represent the financial nature of a balance (e.g. `SALES_REVENUE`, `INVENTORY_ASSET`).
*   **Dimensions** represent the branch, project, or location details (e.g. `branch_id = Ramallah`).
*   *Rule:* No duplicate accounts (e.g. do not create `Sales_Ramallah`).

### 4.2 Financial Dimensions Registry
Every journal line validates and records:
1.  `tenant_id`: strict tenant isolation.
2.  `branch_id`: branch classification.
3.  `warehouse_id`: warehouse context.
4.  `cost_center_id`: expense centers (e.g. department, project).
5.  `profit_center_id`: revenue-producing units.
6.  `partner_id`: customer/supplier identifier.
7.  `currency`: local or foreign currency.
8.  `payment_channel`: cash drawer cashier or bank account.

---

## 5. Multi-Country Localization Strategy (DM-14)
The **Global Localization Framework** provides hot-swappable regulatory engines:
*   **Palestine (PMA compliance):** Multi-currency ledger (ILS, JOD, USD) with 16% VAT.
*   **GCC (KSA/UAE compliance):** Native VAT calculations (5% to 15%) and WPS export support.
*   **Future Markets:** Dynamic API connectors for daily currency exchange rates and e-invoicing portals.

---

## 6. Precision Rules Framework (DM-13)
The system operates a hybrid precision model to prevent rounding drift:
*   **Quantity Precision:** 3 decimals (`Decimal('0.001')`).
*   **Unit Cost Precision:** 4 decimals (`Decimal('0.0001')`).
*   **MWAC Stored Precision:** 6 decimals (`Decimal('0.000001')`).
*   **Exchange Rate Precision:** 6 decimals (`Decimal('0.000001')`).
*   **Internal Calculations:** 6 decimals minimum.
*   **Final Journal Amounts:** Rounded to currency-specific decimals using Banker's Rounding (`ROUND_HALF_EVEN`) to guarantee debit-credit equality.

---

## 7. Operational Models & Transaction Flows

### 7.1 Model: `ProductWarehouseCost`
Represents the authoritative stock quantity and MWAC state:
*   `tenant_id` (Integer)
*   `product_id` (Integer, RESTRICT fk)
*   `warehouse_id` (Integer, index)
*   `quantity` (Numeric 15, 3)
*   `average_cost` (Numeric 15, 6)

### 7.2 Model: `ProductCostHistory`
Audit-only historical cost recalculation trace. Never used to consume cost layers.

### 7.3 General Ledger Concept Registry
This section is the authoritative approved GL Concept Registry for active implementation. Transactions resolve ledger codes dynamically using the following standard concepts:
*   `AR`, `AP`, `CASH`, `BANK`
*   `INVENTORY_ASSET`, `COGS`, `COGS_REVERSAL`
*   `SALES_REVENUE`, `SALES_RETURNS`, `SALES_DISCOUNT`
*   `VAT_INPUT`, `VAT_OUTPUT`
*   `FX_GAIN`, `FX_LOSS`
*   `CHEQUES_UNDER_COLLECTION`
*   `INVENTORY_ADJUSTMENT_GAIN`, `INVENTORY_ADJUSTMENT_LOSS`
*   `FREIGHT_IN`, `CUSTOMS_DUTY`
*   `DEFERRED_CHEQUES_PAYABLE`, `PARTNER_CURRENT_ACCOUNT`, `MERCHANT_CURRENT_ACCOUNT`
*   `SHIPPING_REVENUE`, `DONATION_REVENUE`, `BANK_INTEREST_INCOME`
*   `MISC_EXPENSE`, `COMMISSION_EXPENSE`, `BANK_FEES`
*   `EMPLOYEE_ADVANCES`, `PAYROLL_EXPENSE`, `PAYROLL_PAYABLE`
*   `FIXED_ASSET_ASSET`, `DEPRECIATION_EXPENSE`, `ACCUMULATED_DEPRECIATION`
*   `FIXED_ASSET_GAIN`, `FIXED_ASSET_LOSS`

Numeric values such as `1130`, `1140`, `2110`, `4100`, and `5100` are legacy GL account codes, not concept codes. Header/group accounts such as `2000`, `2100`, `4000`, and `5000` are not required posting concepts and must not be used for transaction posting mappings unless explicitly approved by Finance Architecture. The active Phase 1E implementation must follow this final concept registry rather than older discovery rows.

---

## 8. Posting Rules Engine Examples

### 8.1 Cash Sale
*   **Debit:** `CASH` (Sales net + VAT)
*   **Credit:** `SALES_REVENUE` (Sales net)
*   **Credit:** `VAT_OUTPUT` (VAT amount)
*   **Debit:** `COGS` (MWAC cost)
*   **Credit:** `INVENTORY_ASSET` (MWAC cost)

### 8.2 Inventory Purchase (Credit)
*   **Debit:** `INVENTORY_ASSET` (Cost + Landed Cost)
*   **Debit:** `VAT_INPUT` (Recoverable VAT)
*   **Credit:** `AP` (Total vendor payable)

### 8.3 Post-Dated Cheque Collection
*   **Debit:** `CHEQUES_UNDER_COLLECTION` (Cheque value)
*   **Credit:** `AR` (Customer credit reduction)

---

## 9. Treasury & Cash Management
The treasury module supports:
*   **Multiple Cash Boxes:** Tracked per cashier per branch.
*   **Multiple Bank Accounts:** Centrally managed, assigned to branches.
*   **Employee Advances:** Tracked in dedicated employee sub-ledger accounts, cleared upon payroll runs.
*   **Cash Positioning:** Real-time cash position reporting aggregates cash boxes, bank accounts, and cheques under collection.

---

## 10. Cost Centers & Profit Centers
*   **Profit Center:** Tracks revenue and COGS by `branch_id` or product line.
*   **Cost Center:** Tracks departmental overheads (e.g. HR, Fleet Maintenance) against budgets.
*   *Reporting:* Evaluated via line-item dimensional queries.

---

## 11. Reconciliation Strategy
Reconciliation compares physical stock levels (stock movements), system inventory valuations (`ProductWarehouseCost`), and General Ledger accounts. It is strictly **read-only** and generates discrepancy reports for manual resolution. It does not automatically write correcting entries.

---


---

## 12. Implementation History & Completed Work

This section records all hardening batches and modernization phases that have been completed, with verification evidence and migration references.

---

### 12.1 Batch 1: Tenant Isolation (Advanced Accounting)
**Goal:** Add `tenant_id` scoping to `CustomsTax`, `AdvancedExpense`, and `TaxCalculationRule`.

- [x] Modified `models/advanced_accounting.py` with `tenant_id` and relationships.
- [x] Created Alembic migration `add_tenant_scoping_advanced_accounting`.
- [x] Implemented intelligent inference backfill (Branch → GL → User).
- [x] Added validation phase to abort migration if rows remain unmapped.
- [x] Applied `NOT NULL` and `UniqueConstraint` updates.
- [x] Verified isolation via static analysis.

**Status:** COMPLETED (v2). Inference chains, schema verification, logic simulation, and safety all validated.

---

### 12.2 Batch 2: Audit Trail Protection (RESTRICT on Stock Movements)
**Goal:** Prevent accidental deletion of inventory history by switching from `CASCADE` to `RESTRICT`.

- [x] Modified `models/product.py` to remove ORM-level cascade on `stock_movements`.
- [x] Modified `models/warehouse.py` to change `ondelete='CASCADE'` to `ondelete='RESTRICT'`.
- [x] Created Alembic migration `audit_trail_001_restrict_stock_movements`.
- [x] Verified constraint names match initial schema.

**Status:** COMPLETED.

---

### 12.3 Batch 3: Financial Relationship Safety
**Goal:** Protect financial audit history by removing unsafe ORM-level `cascade='all, delete-orphan'` and enforcing `ON DELETE RESTRICT` at PostgreSQL level.

| Parent | Child | Risk Fixed |
|--------|-------|------------|
| `Sale` | `SaleLine` | Deleting a sale would silently wipe all line items |
| `Purchase` | `PurchaseLine` | Deleting a purchase would silently wipe all line items |
| `GLJournalEntry` | `GLJournalLine` | Deleting a journal entry would erase the double-entry record |

- [x] Removed `cascade='all, delete-orphan'` from `Sale.lines`, `Purchase.lines`, `GLJournalEntry.lines`
- [x] Changed FKs to `db.ForeignKey(..., ondelete='RESTRICT')`
- [x] Created migration `batch_3_001_financial_relationship_safety.py`
- [x] PostgreSQL constraint inspection confirms `ON DELETE RESTRICT` on all 3 FKs
- [x] App loads correctly after changes

**Status:** COMPLETED.

---

### 12.4 Batch 4: Indexing & Schema Hardening
**Goal:** Add missing secondary indexes on high-traffic Foreign Key join columns.

**Methodology:** Queried `information_schema.table_constraints` vs `pg_index` to find FK columns lacking index support.

| # | Table | Column | References | Query Impact |
|---|-------|--------|------------|--------------|
| 1 | `sales` | `seller_id` | `users.id` | Sales-by-seller reports, commission |
| 2 | `purchases` | `user_id` | `users.id` | Purchase audit trails |
| 3 | `payments` | `user_id` | `users.id` | Payment audit trails |
| 4 | `receipts` | `user_id` | `users.id` | Receipt audit trails |
| 5 | `expenses` | `user_id` | `users.id` | Expense approval workflows |
| 6 | `cheques` | `user_id` | `users.id` | Cheque issuance tracking |
| 7 | `stock_movements` | `user_id` | `users.id` | Inventory movement audit |
| 8 | `gl_journal_lines` | `cost_center_id` | `cost_centers.id` | Cost center reporting |
| 9 | `product_returns` | `customer_id` | `customers.id` | Customer return history |
| 10 | `product_returns` | `processed_by` | `users.id` | Return processing audit |

- [x] Added `index=True` to all 10 columns in their respective models
- [x] Created migration `batch_4_001_add_missing_fk_indexes.py`
- [x] PostgreSQL verification confirms all 10 indexes exist
- [x] Zero data changes

**Status:** COMPLETED.

---

### 12.5 Batch 5: Model/Migration Sync
**Goal:** Identify and fix nullability mismatches between SQLAlchemy model definitions and the physical PostgreSQL schema.

**Methodology:** Automated scan compared `column.nullable` on every mapped model against `information_schema.columns.is_nullable`.

| Table | Column | Model | Database (Before) | NULL Rows | Action |
|-------|--------|-------|-------------------|-----------|--------|
| `cheques` | `tenant_id` | `nullable=False` | `YES` | 0 | ALTER COLUMN NOT NULL |
| `partners` | `is_active` | `nullable=False` | `YES` | 0 | ALTER COLUMN NOT NULL |

- [x] Created migration `batch_5_001_fix_nullability_mismatches.py`
- [x] Zero backfill required (0 NULL rows in both columns)
- [x] PostgreSQL verification confirms both columns now `NO`
- [x] Migration graph merged: `audit_trail_001` + `batch_5_001` → `merge_batch5_audit_heads_001`

**Status:** COMPLETED.

---

### 12.6 Phase 1: Dynamic GL Mapping — All Sub-Phases Completed

| Sub-Phase | Description | Status | Evidence |
|-----------|-------------|--------|----------|
| **1E** | `GLAccountMapping` model, concept registry, migration, feature flag | ✅ COMPLETED | Migration `gl_mapping_001`; `ENABLE_DYNAMIC_GL_MAPPING` defaults `False` |
| **1F** | Read-only GL mapping validation / dry-run tool | ✅ COMPLETED | `tools/qa/gl_mapping_validation_dry_run.py` reports readiness per tenant |
| **1G** | Safe seed preview (`--preview-seed`) | ✅ COMPLETED | Proposes candidates; no inserts/updates/deletes |
| **1G.1** | Candidate discovery (`--discover-candidates`) | ✅ COMPLETED | 72 combinations checked; 41 safe candidates found |
| **1J** | Dynamic GL Resolver | ✅ COMPLETED | Isolated resolver behind feature flag; returns no dynamic account while disabled |
| **1K** | Dynamic GL Posting Resolution | ✅ COMPLETED | Refactored auto-posting lines to use `GLAccountResolver` when flag enabled |
| **1K.1** | Extended GL Concept Registry + posting coverage | ✅ COMPLETED | Added cheques, partner/merchant accounts, shipping, commissions, payroll, bank, donations, fixed assets, misc expenses |
| **1L** | Controlled Transaction-Flow QA | ✅ COMPLETED | All 9 core flows exercised with flag temporarily enabled; balanced entries verified; test records cleaned |

**Discovery Results (from Phase 1G.1):**
- 72 total concept-tenant combinations (12 concepts × 6 tenants)
- 41 safe single-candidate mappings discovered
- 13 rows require owner selection (multiple valid candidates)
- 25 rows require manual GL account creation
- Concepts unresolvable from existing accounts: `CUSTOMS_DUTY`, `FREIGHT_IN`, `INVENTORY_ADJUSTMENT_GAIN`, `SALES_RETURNS` (all tenants); `CASH` (1 tenant)

---

### 12.7 Currency Dynamic GL Mapping Fix (June 5, 2026)
**Goal:** Fix 12 currency-related issues identified in audit report. Make GL currency tenant-aware and add original amount tracking.

| # | File | Fix |
|---|------|-----|
| 1 | `utils/helpers.py` | `format_currency_display` falls back to `Tenant.default_currency` before `SystemSettings` |
| 2 | `models/gl.py` | Added `amount` column to `GLJournalLine` (original currency net amount) |
| 3 | `models/gl.py` | `reverse_entry()` preserves `amount` in reversed lines |
| 4 | `services/gl_service.py` | `create_journal_entry()` accepts `currency` and `exchange_rate` params, resolves from tenant |
| 5 | `services/gl_service.py` | `GLJournalLine` stores `amount=original_debit - original_credit` alongside `amount_aed` |
| 6 | `services/gl_service.py` | `post_entry()` passes `currency` and `rate` to `create_journal_entry` |
| 7 | `services/gl_service.py` | `create_manual_entry()` stores `amount` on each line |
| 8 | `services/gl_posting.py` | `post_or_fail()` defaults currency from `Tenant.default_currency` instead of hardcoded `AED` |
| 9 | `services/gl_tree_builder.py` | Existing accounts: **preserved** their currency (no longer forced to AED) |
| 10 | `services/gl_tree_builder.py` | New accounts created with tenant's `default_currency` |
| 11 | `services/gl_tree_builder.py` | Liquidity accounts created with tenant's `default_currency` |
| 12 | `utils/system_init.py` | Core GL accounts seeded with first active tenant's `default_currency` |

**Migration:** `currency_audit_001_add_amount_to_gl_journal_lines.py`
- Adds `amount` column to `gl_journal_lines`
- Backfills existing rows from `amount_aed` (historical data was all AED)

**Additional fix:** `ILS` (Israeli Shekel) added to `CURRENCIES` in `utils/constants.py`.

**Status:** COMPLETED, committed `8d81f47`, pushed to `origin/main`.

---

### 12.8 Phase 2-8 Schema Foundation & Feature Flags (June 5, 2026)
**Goal:** Complete all partially implemented schema foundations identified in the Code and System Verification Report. Bring every "partially completed" item to "fully completed" at the schema/model level.

| Area | Action | Status | Evidence |
|------|--------|--------|----------|
| **Phase 2: Financial Dimensions** | Added `branch_id`, `warehouse_id`, `profit_center_id`, `partner_id` to `GLJournalLine`; created `ProfitCenter` model; wired dimensions through `reverse_entry`, `GLService.create_journal_entry`, `post_entry`, `create_manual_entry`, `post_or_fail` | ✅ SCHEMA COMPLETED | Migration `phase2_001_add_gl_dimensions_and_profit_centers` |
| **Phase 3: MWAC Data Model** | Created `ProductWarehouseCost` (active WAC per product/warehouse) and `ProductCostHistory` (immutable audit trail) models | ✅ SCHEMA COMPLETED | Migration `phase3_001_add_mwac_exchange_rate_treasury_models` |
| **Phase 6: Exchange Rate Framework** | Created `ExchangeRateRecord` model (locked rates per document, manual/API source tracking) | ✅ SCHEMA COMPLETED | Migration `phase3_001` |
| **Phase 8: Treasury** | Created `CashBox` model (cash/bank/gateway unified liquidity container with GL linkage) | ✅ SCHEMA COMPLETED | Migration `phase3_001` |
| **Feature Flags** | Added `ENABLE_MWAC`, `ENABLE_LANDED_COST_CAPITALIZATION`, `ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK`, `ENABLE_ADVANCED_RECONCILIATION`, `ENABLE_LOCALIZATION_FRAMEWORK` to `config.py` | ✅ COMPLETED | `config.py` lines 187-205 |
| **Schema Drift Cleanup** | 5 idempotent migrations fixing constraints, indexes, nullable columns, and orphaned AI tables | ✅ COMPLETED | `phase3_002` through `phase3_006`; `flask db check` reports **No new upgrade operations detected** |
| **Dynamic GL Wiring** | `get_payment_debit_account` and `get_customer_credit_account` now attempt `resolve_gl_account` when `ENABLE_DYNAMIC_GL_MAPPING=True` before falling back to legacy hardcoded codes; `sale_service.py` refactored to use `get_customer_credit_account(branch_id, tenant_id)` | ✅ COMPLETED | `services/gl_service.py`, `services/sale_service.py` |
| **Database Sync** | All 6 new tables created; all dimension columns present; orphaned `ai_*` tables backed up and removed | ✅ COMPLETED | Verified via `flask db current` = `phase3_006` |

**Commit:** `dfdfac1` (Phase 1-8 schema), `935737a` (drift fixes), `a8d055e` (GL resolver wiring), `a48665b` (final drift + AI cleanup) — all pushed to `origin/main`.

---

## 13. Phased Implementation Roadmap

### Phase 0: Baseline Correction & Documentation Prep
*   **Goal:** Enforce unified mathematical rounding rules in system configuration.
*   **Files Affected:** `config.py` (add global rounding parameters).
*   **Accounting Impact:** Establishes 6-decimal internal precision and currency-specific journal rounding models.
*   **Estimated Complexity:** Low (1-2 days).
*   **Dependencies:** None.

### Phase 1: Dynamic GL Mapping Foundation — **COMPLETED**
*   **Goal:** Replace hardcoded account code strings (e.g. `'1130'`, `'1140'`) with dynamic concept resolutions.
*   **Files Affected:** `models/gl.py`, `services/gl_service.py`, `services/gl_posting.py`.
*   **Models Needed:** `GLAccountMapping` (mapping standard GL concepts to tenant chart accounts).
*   **Migrations Needed:** `create_gl_account_mappings_table`.
*   **Status:** All sub-phases 1E through 1L completed. See Section 12.6 for detailed completion notes.
*   **Feature Flag:** `ENABLE_DYNAMIC_GL_MAPPING` remains disabled by default until Phase 2+ dimensions are enforced.
*   **Estimated Complexity:** Medium (1 Sprint) — **Actual: 2 Sprints**.
*   **Dependencies:** Phase 0.

### Phase 2: Financial Dimensions Enforcement — **SCHEMA COMPLETED**
*   **Goal:** Enforce and validate dimension columns on journal entries and lines.
*   **Files Affected:** `models/gl.py`, `services/gl_service.py`, `services/gl_posting.py`.
*   **Models Added:** `ProfitCenter`; `GLJournalLine` extended with `branch_id`, `warehouse_id`, `profit_center_id`, `partner_id`.
*   **Migrations:** `phase2_001_add_gl_dimensions_and_profit_centers`.
*   **Status:** Schema and model wiring complete. Dimensions are propagated in `reverse_entry`, `create_journal_entry`, `post_entry`, `create_manual_entry`, and `post_or_fail`. Service-layer enforcement (mandatory dimension validation) is deferred until operational UI passes dimensions explicitly.
*   **Estimated Complexity:** Medium (1 Sprint) — **Schema: DONE**.

### Phase 3: MWAC Data Model Design — **SCHEMA COMPLETED**
*   **Goal:** Deploy database schemas to store per-warehouse stock values.
*   **Files Affected:** `models/product_warehouse_cost.py`, `models/product_cost_history.py`.
*   **Models Added:** `ProductWarehouseCost` (active inventory valuation), `ProductCostHistory` (immutable audit trail).
*   **Migrations:** `phase3_001_add_mwac_exchange_rate_treasury_models`.
*   **Status:** Schema deployed. Transaction-flow recalculation logic (Phase 4) is the next dependency.
*   **Estimated Complexity:** Low (3-4 days) — **Schema: DONE**.

### Phase 4: MWAC Transaction Flows
*   **Goal:** Hook operational purchases, sales, and warehouse receipts to average cost recalculations.
*   **Files Affected:** `services/stock_service.py`, `services/sale_service.py`, `services/purchase_service.py`.
*   **Services Affected:** `StockService`, `SaleService`, `PurchaseService`.
*   **Migrations Needed:** None.
*   **Accounting Impact:** Perpetual stock values update at true average costs on each receipt.
*   **Risks:** Lock contention on high-volume product rows.
*   **Rollback Strategy:** Hide calculation behind feature flag `ENABLE_MWAC`.
*   **Estimated Complexity:** High (2 Sprints).
*   **Dependencies:** Phase 3.

### Phase 5: Landed Cost Capitalization
*   **Goal:** Capitalize transport, insurance, and duties directly into inventory value.
*   **Files Affected:** `models/purchase.py`, `services/purchase_service.py`.
*   **Services Affected:** `PurchaseService`.
*   **Migrations Needed:** `add_landed_cost_to_purchase_lines`.
*   **Accounting Impact:** Proportional allocation by value is capitalized on purchase receiving.
*   **Risks:** Inaccurate cost allocations over-value assets.
*   **Rollback Strategy:** Exclude landed costs from cost calculation, defaulting them to period expenses.
*   **Estimated Complexity:** Medium (1 Sprint).
*   **Dependencies:** Phase 4.

### Phase 6: Exchange Rate Framework — **SCHEMA COMPLETED**
*   **Goal:** Secure multi-currency documents using manual manager rates and online fallback tables.
*   **Files Affected:** `models/exchange_rate_record.py`, `services/exchange_service.py` (future).
*   **Models Added:** `ExchangeRateRecord` (rate locking per document, manual/API source tracking).
*   **Migrations:** `phase3_001`.
*   **Status:** Schema deployed. Service logic for rate locking on document post is deferred to Phase 6 execution.
*   **Estimated Complexity:** Medium (1 Sprint) — **Schema: DONE**.

### Phase 7: Reconciliation Reports
*   **Goal:** Deploy read-only reconciliation tools comparing physical stock to ledger assets.
*   **Files Affected:** `services/reconciliation_service.py`.
*   **Services Affected:** `ReconciliationService`.
*   **Migrations Needed:** None.
*   **Accounting Impact:** Exposes stock ledger and account ledger variances.
*   **Risks:** Performance lag on large tables.
*   **Rollback Strategy:** Remove menu links from user dashboard.
*   **Estimated Complexity:** Low (1 Sprint).
*   **Dependencies:** Phase 6.

### Phase 8: Treasury & Cash Position Reporting — **SCHEMA COMPLETED**
*   **Goal:** Multi-branch bank, cashier, and post-dated cheque position tracking.
*   **Files Affected:** `models/cash_box.py`, `services/treasury_service.py` (future).
*   **Models Added:** `CashBox` (cash/bank/gateway unified container with GL linkage).
*   **Migrations:** `phase3_001`.
*   **Status:** Schema deployed. Treasury reporting service logic is deferred to Phase 8 execution.
*   **Estimated Complexity:** Medium (1 Sprint) — **Schema: DONE**.

### Phase 9: Global Localization Engine — **PENDING**
*   **Goal:** Country-specific compliance engines for Palestine, UAE, and Saudi Arabia.
*   **Files Affected:** `utils/localization/`.
*   **Services Affected:** `TaxCalculationService`, `EInvoicingService`.
*   **Migrations Needed:** None.
*   **Accounting Impact:** Tax Return and compliance reporting automation.
*   **Estimated Complexity:** Medium (1 Sprint).
*   **Dependencies:** Phase 8.

### Phase 10: Testing, Validation, and Rollout
*   **Goal:** Run full end-to-end regression test suite, seed historical records, and deploy.
*   **Estimated Complexity:** Low (1-2 Sprints).
*   **Dependencies:** All previous phases.

---

## 14. Next Step — Recommended Priority

All schema foundations (Phase 2, 3, 6, 8) are deployed. The database is clean (`flask db check` = zero drift). Two high-value paths are now ready for execution:

### Option A: Activate Dynamic GL Mapping (Phase 1 Activation) — ✅ COMPLETED (June 5, 2026)
**Status:** `ENABLE_DYNAMIC_GL_MAPPING` is now `True` by default in `config.py`. All critical concepts resolve dynamically per tenant. Legacy lookup path remains as an emergency fallback with `is_header`/`is_active` guards.
*   **Evidence:**
    - `tools/qa/test_dynamic_gl_resolution_path.py` — all 13 critical concepts PASS.
    - `flask db check` — zero drift.
    - `get_payment_debit_account` and `get_customer_credit_account` now raise `GLMappingError` on missing mappings instead of returning hardcoded codes.
    - `_resolve_journal_line_account` enforces concept-code resolution; legacy codes allowed only via `explicit_account_allowed` flag.
*   **Commits:** `eb32406` (activate + remove fallbacks), `2cbf69a` (restore legacy with validation + branch_id propagation fix).

### Option B: MWAC Transaction Flows (Phase 4) — 🔄 NEXT
**Why now:** `ProductWarehouseCost` and `ProductCostHistory` tables exist. `StockService`, `SaleService`, and `PurchaseService` can now be wired to recalculate average cost on every receipt.
*   **Actions:**
    1. Modify `StockService.receive_stock()` to update `ProductWarehouseCost` (increase qty, recalculate WAC, append `ProductCostHistory`).
    2. Modify `SaleService` COGS posting to read from `ProductWarehouseCost.average_cost` instead of `SaleLine.cost_price`.
    3. Modify `PurchaseService` to trigger WAC recalculation on purchase receipt.
    4. Set `ENABLE_MWAC=True`.
    5. Run reconciliation between `ProductWarehouseCost` and GL inventory account.
*   **Risk:** Medium. Directly affects inventory valuation and COGS. Requires opening-balance baseline (Open Owner Decision #1).
*   **Estimated Effort:** 1-2 Sprints.

### Recommendation
**Proceed to Option B (MWAC Transaction Flows).** The posting pipeline is now fully dynamic and tested. Any future valuation discrepancy will be isolated to the costing layer, not the posting layer. Before starting, resolve **Open Owner Decision #1** (Opening Balances Baseline) to seed initial WAC values for existing stock.

---

## 15. Technical Approval Gates

To protect the production database, the team must pass five explicit gates:
1.  **Gate 1 (DB Schema):** Before running migrations creating `product_warehouse_costs` or adding line-item dimensions.
2.  **Gate 2 (GL Postings):** Before swapping hardcoded accounts in code with dynamic mapping lookups.
3.  **Gate 3 (Seeding Verification):** Before running the migration scripts to calculate opening MWAC costs for active products.
4.  **Gate 4 (UAT Pass):** Accountant signature verifying multi-currency conversion reports and tax return schedules.
5.  **Gate 5 (Feature Flag Rollout):** Phased release to specific tenants.

---

## 16. Testing Strategy
Exhaustive test scenarios must validate:
1.  **MWAC Calculation:** Averages recalculate on receipt; sales do not alter unit cost.
2.  **Conversion Accuracy:** Converting foreign invoices without rounding variance.
3.  **Dimension Integrity:** Postings abort if `warehouse_id` or `branch_id` are missing on operational rows.
4.  **Period Protection:** Modifications to closed periods raise `ClosedPeriodError`.
5.  **Rounding Integrity:** Banker's rounding ensures debits match credits exactly for JOD/AED currencies.

---

## 17. Feature Flags
All new logic paths are shielded behind:
*   `ENABLE_DYNAMIC_GL_MAPPING`
*   `ENABLE_MWAC`
*   `ENABLE_LANDED_COST_CAPITALIZATION`
*   `ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK`
*   `ENABLE_ADVANCED_RECONCILIATION`
*   `ENABLE_LOCALIZATION_FRAMEWORK`

---

## 18. Migration Safety & Data Integrity Rules
*   **Abort on Variance:** If stock quantities or ledger values show drift exceeding limits during data migration, the process aborts.
*   **No Blind Backfills:** Existing tables are backfilled dynamically, validating the user/branch trail of records.
*   **Historical Immutability:** Closed-period entries are never modified. Corrections are posted in open periods via standard reversal entries.

---

## 19. Open Owner Decisions
1.  **Opening Balances Baseline:** Agreement on initial seed values for existing stock averages.
2.  **Landed Cost Manual Allocation Limits:** Thresholds and permissions to deviate from the "By Value" default allocation.
3.  **Unlinked Sales Return Limits:** Manager override limits for manual valuation overrides of unlinked returns.
4.  **Treasury Cash Box Limits:** Daily cash drawer caps before triggering cash deposits to central bank registers.
## Frontend / Admin UI Requirements

No frontend or admin UI changes are required for Phase 1E or Phase 1F. Phase 1E is schema/model foundation only, and Phase 1F is read-only validation/dry-run readiness reporting only.

Future phases require admin UI support for the following areas:

1. **Dynamic GL Mapping Admin UI**
   - Manage concept-to-account mappings.
   - Validate mappings.
   - Show missing and invalid mappings.
   - Apply a default mapping template.
   - Support tenant-level mappings first.
   - Add future branch override support.

2. **Tenant Onboarding Accounting Setup UI**
   - Create or select a chart of accounts.
   - Generate default GL mappings.
   - Run GL mapping validation.
   - Block accounting activation if required mappings are missing.

3. **Exchange Rate Management UI**
   - Allow manager manual exchange rate entry.
   - Show online fallback availability/indicator.
   - Store the selected rate on each document.
   - Show rate source: manual or online.
   - Prevent recalculation of historical documents.

4. **WAC / Inventory Valuation UI**
   - Product warehouse cost view.
   - MWAC audit history.
   - Inventory valuation by warehouse.
   - Stock-to-GL reconciliation report.

5. **Landed Cost Allocation UI**
   - Allocate freight, customs, insurance, and clearance costs.
   - Default allocation by value.
   - Future allocation methods: quantity, weight, volume, and manual allocation.

6. **Treasury and Cash Position UI**
   - Cash boxes.
   - Bank accounts.
   - Cheques under collection.
   - Payment gateways.
   - Cash position report.

---

## Appendix A: Reverse Engineering & Audit History

### A.1 Audit Timeline

| Phase | Scope | Key Outcome | Date |
|-------|-------|-------------|------|
| Phase 1 | Global Discovery & System Mapping | Full system map; multi-tenant isolation gaps identified | June 3, 2026 |
| Phase 2 | Accounting & Financial Integrity Deep Dive | Hardcoded GL codes and manual balance accumulators flagged | June 3, 2026 |
| Phase 3 | Inventory, Costing, and COGS Deep Dive | Last Purchase Cost confirmed; `ON DELETE CASCADE` on inventory audit trails identified | June 3, 2026 |
| Phase 4 | Inventory Valuation Decision | Recommended migration to **Weighted Average Cost** to eliminate Balance Sheet volatility | June 3, 2026 |

### A.2 Original Critical Findings (All Resolved)

| Risk Level | Area | Original Finding | Resolution |
| :--- | :--- | :--- | :--- |
| **CRITICAL** | Audit Trail | `ON DELETE CASCADE` on `StockMovement` wipes audit history if product deleted | **Fixed in Batch 2** (`RESTRICT` enforced) |
| **HIGH** | Security | Missing `tenant_id` in `advanced_accounting` models leads to cross-tenant data visibility | **Fixed in Batch 1** (tenant scoping added) |
| **HIGH** | Accuracy | Last Purchase Cost causes "valuation jumps" and Ledger-Stock drift | **Planned for Phase 3-4** (MWAC migration) |
| **MEDIUM** | Integrity | Manual balance accumulators for Customers/Suppliers prone to sync issues | **Ongoing monitoring** |
| **MEDIUM** | Integrity | Hardcoded GL account codes in services bypass tenant customization | **Fixed in Phase 1** (Dynamic GL Mapping deployed) |

### A.3 System Architecture Summary
- **Framework:** Flask (Python) with service-oriented business logic.
- **Database:** PostgreSQL with SQLAlchemy ORM.
- **Multitenancy:** Shared-database, row-level isolation via `tenant_id`.
- **Localization:** Full Arabic (AR) and English (EN) support.
- **Core Modules:** Sales, Inventory (GL-integrated), Purchases, Payments, AI Analytics.

---

## Appendix B: Pre-Implementation Verification & Findings Validation

### B.1 CRITICAL: Audit Trail Vulnerability (ORM-Level Cascade)
- **Database Level:** Physical PostgreSQL schema defaulted to `NO ACTION` (not explicit `CASCADE`).
- **ORM Level:** SQLAlchemy `Product.stock_movements` had `cascade='all, delete-orphan'`.
- **Confirmed Behavior:** `db.session.delete(product)` would auto-delete all movement records.
- **Status:** RESOLVED in Batch 2.

### B.2 HIGH: Multi-Tenancy Data Leakage (Missing Scoping)
- **Confirmed Gap:** `advanced_expenses`, `customs_taxes`, `tax_calculation_rules` lacked `tenant_id`.
- **Security Risk:** Global visibility in a multi-tenant ERP.
- **Status:** RESOLVED in Batch 1.

### B.3 HIGH: Inventory Valuation Inconsistency (Costing Drift)
- **Confirmed Drift:** System uses global `Product.cost_price` but tracks historical accounting in `GLAccount` (1140).
- **Evidence:** `runtime_core/accounting_repair.py` calculates `inventory_diff = estimated_inventory - gl_inventory`.
- **Remediation:** Migrating to MWAC will stop drift at the source.
- **Status:** PLANNED for Phase 3-4.

### B.4 HIGH: Financial Document Vulnerability
- **Confirmed:** `Sale` → `SaleLine`, `Purchase` → `PurchaseLine`, `GLJournalEntry` → `GLJournalLine` lacked `RESTRICT`.
- **Status:** RESOLVED in Batch 3.

---

## Appendix C: Currency Audit Report (June 5, 2026)

### C.1 Issues Identified and Resolved

| # | File | Line | Issue | Impact |
|---|------|------|-------|--------|
| 1 | `utils/helpers.py` | 88-95 | `format_currency_display()` uses `SystemSettings` instead of `Tenant` | Wrong display: د.إ instead of ₪ |
| 2 | `models/gl.py` | 170-175 | `GLJournalLine` missing `amount` (original amount) | Loss of original amount |
| 3 | `models/gl.py` | 120-130 | `reverse_entry()` doesn't save `amount` | Reversed entry incomplete |
| 4 | `services/gl_service.py` | 44-65 | `create_journal_entry()` doesn't accept `currency` param | Entry created without currency |
| 5 | `services/gl_service.py` | 85-95 | `GLJournalLine` created without `amount` and no conversion | Incorrect amounts |
| 6 | `services/gl_service.py` | 108-120 | `post_entry()` uses hardcoded `currency='AED'` | All entries AED |
| 7 | `services/gl_service.py` | 280-290 | `create_manual_entry()` saves only `amount_aed` | Manual entry incomplete |
| 8 | `services/gl_posting.py` | 15-25 | `post_or_fail()` uses hardcoded `currency='AED'` | All service entries AED |
| 9 | `services/gl_tree_builder.py` | 175-180 | `_process_account()` forces `currency='AED'` | Currency overridden by force |
| 10 | `services/gl_tree_builder.py` | 215-225 | `_process_account()` creates new accounts with `AED` | New accounts always AED |
| 11 | `services/gl_tree_builder.py` | 280-290 | `_ensure_liquidity_account()` uses AED | Cash/Bank always AED |
| 12 | `utils/system_init.py` | 245-255 | `_ensure_core_data()` creates `GLAccount` with `AED` | Core accounts always AED |

**Additional:** `ILS` was missing from `CURRENCIES` in `utils/constants.py`.

### C.2 Cumulative Impact (if `Tenant.default_currency = 'ILS'`)
| Area | Before Fix | After Fix |
|------|------------|-----------|
| UI Display (Templates) | Works | Still works |
| Python Code | Uses AED | Uses `Tenant.default_currency` |
| Auto GL Posting | AED | `Tenant.default_currency` |
| Manual GL Entry | AED | `Tenant.default_currency` |
| GL Accounts | AED | `Tenant.default_currency` |
| Line Amounts | Missing `amount` | Original amount preserved |
| Accounting Reports | Always AED | Dynamic currency |

**All 12 issues + ILS currency addition resolved in commit `8d81f47` and `a4a11d9`.**

---

*End of Master Blueprint — Single Source of Truth*
*Last updated: June 5, 2026 (Session 2)*
