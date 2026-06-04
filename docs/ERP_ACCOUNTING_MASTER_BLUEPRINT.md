# ERP Accounting Master Blueprint

**Document Status:** Approved Core Design System & Implementation Roadmap  
**Date:** June 4, 2026  
**Reference Standards:** SAP Business One, Oracle NetSuite, Odoo, Bisan, Al-Shamel  
**Strategic Markets:** Palestine, GCC countries, Arabic markets, Future international expansion  

---

## 1. Introduction & Consolidated Source Documents
This master blueprint acts as the single, authoritative source of truth for the Azad ERP financial architecture and modernization implementation plan. It details the principles, posting templates, dimensional configurations, database rules, and phased execution roadmap.

### Source Documents Consolidated
This master document merges, preserves, and supersedes the following documents:
*   `docs/ERP_ACCOUNTING_PRINCIPLES.md` (principles, formulas, GL integration patterns)
*   `docs/ERP_ACCOUNTING_DECISION_MATRIX.md` (approved policies DM-01 to DM-12, DM-13, and DM-14 options)
*   `docs/WAC_ACCOUNTING_ARCHITECTURE_REVIEW.md` (technical costing design, gaps, dimensions)
*   `docs/FUTURE_ROADMAP_WAC_AND_RECONCILIATION.md` (reconciliation rules, WAC validation bounds)
*   `docs/FUTURE_ROADMAP_DYNAMIC_GL_MAPPING.md` (concept-based GL lookup model)
*   `docs/FUTURE_ROADMAP_PAYROLL_PAYMENT_AI_AUDIT.md` (payroll rules, WPS checking, anomaly tracking)
*   `docs/ERP_ACCOUNTING_IMPLEMENTATION_PLAN.md` (modernization roadmap, phase definitions, approval gates, test plans)

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

## 12. Phased Implementation Roadmap

### Phase 0: Baseline Correction & Documentation Prep
*   **Goal:** Enforce unified mathematical rounding rules in system configuration.
*   **Files Affected:** `config.py` (add global rounding parameters).
*   **Accounting Impact:** Establishes 6-decimal internal precision and currency-specific journal rounding models.
*   **Estimated Complexity:** Low (1-2 days).
*   **Dependencies:** None.

### Phase 1: Dynamic GL Mapping Foundation
*   **Goal:** Replace hardcoded account code strings (e.g. `'1130'`, `'1140'`) with dynamic concept resolutions.
*   **Files Affected:** `models/gl.py`, `services/gl_service.py`, `services/gl_posting.py`.
*   **Models Needed:** `GLAccountMapping` (mapping standard GL concepts to tenant chart accounts).
*   **Migrations Needed:** `create_gl_account_mappings_table`.
*   **Risks:** Mismatched mapping definitions fail transaction flows.
*   **Rollback Strategy:** Fallback configuration variables to legacy hardcoded accounts if database mappings are null.
*   **Estimated Complexity:** Medium (1 Sprint).
*   **Dependencies:** Phase 0.

#### Phase 1E (Completed)
GLAccountMapping foundation deployed — additive migration, feature flag `ENABLE_DYNAMIC_GL_MAPPING` disabled by default, legacy hardcoded lookups remain active.

#### Phase 1F (Completed)
Read-only GL mapping validation / dry-run tool deployed. Reports readiness status per tenant without modifying data.

#### Phase 1G (Completed)
Safe seed preview deployed. A read-only preview tool (`--preview-seed`) proposes candidate GL concept-to-account mappings by matching approved legacy codes to each tenant's existing chart of accounts. It reports:
*   **proposed** — safe candidate found (same tenant, active, not header).
*   **manual_required** — no legacy code hint or no matching GL account exists.
*   **invalid_candidate** — matched account belongs to another tenant, is inactive, or is a header/group account.

**Strict guarantees:** No inserts, updates, deletes, seeds, or backfills. Feature flag remains `False`. Posting behavior unchanged.

#### Phase 1G.1 (Completed)
Candidate discovery deployed. A read-only discovery tool (`--discover-candidates`) resolves Phase 1G gaps by searching each tenant's existing chart for postable accounts using name patterns, account types, and parent-child relationships.

**Discovery results across all tenants:**
*   **72** total concept-tenant combinations checked (12 concepts × 6 tenants).
*   **41** safe single-candidate mappings discovered.
*   **13** rows require owner selection (multiple valid candidates per concept).
*   **25** rows require manual GL account creation (no existing candidate found).
*   **Concepts unresolvable from existing accounts:** `CUSTOMS_DUTY`, `FREIGHT_IN`, `INVENTORY_ADJUSTMENT_GAIN`, `SALES_RETURNS` (all tenants); `CASH` (1 tenant).
*   **Concepts with owner-selection ambiguity:** `BANK` (multiple bank accounts per tenant), `CASH` (multiple cashboxes in some tenants).

**Strict guarantees:** No inserts, updates, deletes, seeds, or backfills. Feature flag remains `False`. Posting behavior unchanged.

### Phase 2: Financial Dimensions Enforcement
*   **Goal:** Enforce and validate dimension columns on journal entries and lines.
*   **Files Affected:** `models/gl.py`, `utils/gl_helpers.py`.
*   **Models Needed:** `gl_journal_lines` extended with dimension foreign keys (`branch_id`, `warehouse_id`, etc.).
*   **Migrations Needed:** `add_dimensions_to_gl_lines`.
*   **Accounting Impact:** Prevents ledger code explosion.
*   **Risks:** Active transactions fail if a operational parameter (like `warehouse_id`) is missing.
*   **Rollback Strategy:** Allow nullable entries for historical compatibility; log warnings instead of raising errors.
*   **Estimated Complexity:** Medium (1 Sprint).
*   **Dependencies:** Phase 1.

### Phase 3: MWAC Data Model Design
*   **Goal:** Deploy database schemas to store per-warehouse stock values.
*   **Files Affected:** `models/product.py`, `models/warehouse.py`.
*   **Models Needed:** `ProductWarehouseCost` (active inventory valuation), `ProductCostHistory` (audit trail).
*   **Migrations Needed:** `create_mwac_tables`.
*   **Accounting Impact:** Definitive asset state tracking.
*   **Risks:** Synchronization mismatches between physical movements and average records.
*   **Rollback Strategy:** Revert average queries back to standard global `Product.cost_price`.
*   **Estimated Complexity:** Low (3-4 days).
*   **Dependencies:** Phase 2.

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

### Phase 6: Exchange Rate Framework
*   **Goal:** Secure multi-currency documents using manual manager rates and online fallback tables.
*   **Files Affected:** `models/purchase.py`, `services/exchange_service.py`.
*   **Migrations Needed:** `create_exchange_rate_tables`.
*   **Accounting Impact:** Rates are permanent once documents post. Conversions lock AED/SAR/ILS values.
*   **Risks:** API disconnect on document creation.
*   **Rollback Strategy:** Standalone manual inputs required if API lookup fails.
*   **Estimated Complexity:** Medium (1 Sprint).
*   **Dependencies:** Phase 5.

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

### Phase 8: Treasury & Cash Position Reporting
*   **Goal:** Multi-branch bank, cashier, and post-dated cheque position tracking.
*   **Files Affected:** `models/payment.py`, `services/treasury_service.py`.
*   **Migrations Needed:** `create_treasury_tables`.
*   **Accounting Impact:** Cash positioning dimensions active.
*   **Estimated Complexity:** Medium (1 Sprint).
*   **Dependencies:** Phase 7.

### Phase 9: Global Localization Engine
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
## Phase 1 Dynamic GL Mapping - Discovery Checkpoint

> **Historical discovery note only:** Phase 1A, Phase 1B, and Phase 1C below preserve earlier investigation and design thinking. They are not the final approved GL Concept Registry. For implementation, validation, and posting-map readiness, section 7.3 is authoritative. Numeric legacy GL account codes are account identifiers, not concept codes.

- **Hardcoded GL codes discovered**: '1130', '1140', '1150', '2000', '2100', '2110', '2120', '2130', '4000', '4100', '4200', '5000', '5100', '1120' (debit), '4200' (credit).

- **Files/functions inspected**: `system_init.py`, `services/gl_service.py`, `services/gl_posting.py`, `models/gl.py`, `gl_helpers.py`.

- **Likely files to modify**: `models/gl.py` (add `GLAccountMapping`), `services/gl_service.py`, `services/gl_posting.py`, possibly `gl_helpers.py`.

- **Risks observed**: Hardcoded codes will break per‑tenant charts; missing mappings cause transaction failures; migrations require data back‑fill; fallback logic needed for rollback.

- **Next exact step**: Create `GLAccountMapping` model and migration, then refactor `gl_service` to resolve accounts via this mapping with fallback to legacy codes.

## Phase 1A – GL Concept Registry and Legacy Mapping

> **Discovery/design note only:** The rows in this table mix legacy account codes with conceptual meanings. They must not override the approved concept registry in section 7.3. Header/group accounts listed here, including `2000`, `2100`, `4000`, and `5000`, are legacy chart structure accounts and are not required transaction posting concepts.

| Concept Code | Meaning | Legacy Default GL Code | Required / Optional | Used by Transaction Type | Risk if Missing |
|--------------|---------|------------------------|----------------------|--------------------------|-----------------|
| 1130 | Accounts Receivable (AR) | 1130 | Required | Sales invoices, credit memos | Unposted receivables, mismatched customer balances |
| 1140 | Inventory Asset | 1140 | Required | Purchase receipts, inventory adjustments | Inventory valuation errors, stock mismatches |
| 1150 | Cheques Under Collection | 1150 | Optional | Collection of post‑dated cheques | Untracked cheques, reconciliation gaps |
| 2000 | Liabilities Header | 2000 | Required | General liability postings | Inconsistent liability hierarchy |
| 2100 | Current Liabilities | 2100 | Required | Payables, accruals | Missing liability accounts, reporting issues |
| 2110 | Accounts Payable (AP) | 2110 | Required | Vendor invoices, purchase payments | Unpaid vendor balances, audit failures |
| 2120 | PDC Payable (Post‑dated cheques) | 2120 | Optional | Payable cheques management | Missed cheque payouts, cash flow misstatement |
| 2130 | VAT Payable | 2130 | Required | VAT output on sales | VAT reporting errors, tax compliance risk |
| 4000 | Revenue Header | 4000 | Required | All revenue postings | Incomplete revenue aggregation |
| 4100 | Sales Revenue | 4100 | Required | Sale transactions | Under‑reported sales, revenue leakage |
| 4200 | Service Revenue | 4200 | Required | Service invoices, fees | Missing service income, financial distortion |
| 5000 | Cost of Sales Header | 5000 | Required | COGS entries | Inaccurate gross margin calculations |
| 5100 | Cost of Goods Sold (COGS) | 5100 | Required | Inventory cost postings | Wrong cost of goods, profit misstatement |
| 1120 | Bank – Savings Account | 1120 | Required | Cash deposits, bank payments | Untracked cash movements, reconciliation failures |

## Phase 1B – GLAccountMapping Model Design

> **Discovery/design note only:** This section predates the final Phase 1E implementation. Active model and validation work must use section 7.3 concept codes and must treat numeric values as legacy GL account codes only.

1. **Proposed fields**
   - `id` (PK, UUID)
   - `tenant_id` (FK to tenants, required)
   - `concept_code` (string, e.g., 'AR', required)
   - `gl_code` (string, legacy GL account code)
   - `branch_id` (FK to branches, nullable for optional override)
   - `is_active` (bool, default true)
   - `created_at`, `updated_at` timestamps

2. **Unique constraints**
   - (`tenant_id`, `concept_code`) must be unique.
   - (`tenant_id`, `branch_id`, `concept_code`) must be unique when `branch_id` is set.

3. **Required indexes**
   - Index on `tenant_id`.
   - Composite index on (`tenant_id`, `concept_code`).
   - Index on `branch_id` for branch‑override lookups.

4. **Tenant isolation rules**
   - All queries are automatically filtered by `tenant_id`.
   - No cross‑tenant visibility; foreign‑key constraints enforce tenancy.

5. **Optional branch override rules**
   - If a mapping exists for a specific `branch_id`, it overrides the tenant‑level mapping.
   - Fallback to tenant‑level mapping when branch mapping is absent.

6. **Validation rules**
   - `concept_code` must belong to the approved GL Concept Registry in section 7.3.
   - `gl_code` must match an existing GL account in the tenant’s chart of accounts.
   - `branch_id` must reference an existing branch belonging to the same tenant.

7. **Missing mapping behavior**
   - If no mapping is found for a required concept, transaction processing raises `GLMappingError`.
   - In batch imports, missing mappings are logged and the record is skipped.

8. **Legacy fallback behavior while feature flag disabled**
   - When `ENABLE_DYNAMIC_GL_MAPPING` flag is **off**, the system uses the hard‑coded legacy GL codes defined in Phase 1A.
   - The flag is checked at service start‑up; fallback does not require database look‑ups.

9. **Required migration safety rules**
   - Back‑fill `GLAccountMapping` with all legacy codes before enabling the feature flag.
   - Run a validation job to ensure every active concept has a mapping for each tenant.
   - Provide a reversible script to revert to legacy codes if the migration fails.

## Phase 1C – GL Mapping Migration & Backfill Design

> **Discovery/design note only:** This section describes earlier migration/backfill planning. Current approved behavior is validation-first and read-only until an explicit seeding/backfill approval is granted. Do not infer required concepts from header/group legacy accounts in this section.

1. **Migration sequence**
   - **Create mapping table** – Define `GLAccountMapping` table with tenant isolation.
   - **Seed mappings** – Populate the table with approved GL concepts mapped to each tenant's existing GL accounts using the legacy codes.
   - **Validate mappings** – Run validation jobs to ensure completeness and correctness before activating dynamic mapping.
   - **Enable feature flag later** – Flip `ENABLE_DYNAMIC_GL_MAPPING` only after successful validation.

2. **Safe backfill strategy**
   - Iterate over each tenant.
   - For every approved GL concept, locate the tenant's GL account that matches the legacy default code.
   - Insert a mapping row only if the GL account exists and is active.
   - **Do not assume** `tenant_id = 1`; query tenants dynamically.
   - Skip creation if the referenced GL account is missing; log the omission for review.
   - Abort the backfill for a tenant if any required mapping cannot be resolved, and generate a detailed report.

3. **Required validation checks**
   - Every tenant must have mappings for all **required** concepts from Phase 1A.
   - Each mapped GL account must belong to the same tenant.
   - Mapped GL accounts must be **active** (not archived or disabled).
   - Mapped GL accounts must **not be header/group** accounts.
   - No duplicate `(tenant_id, concept_code)` mappings.
   - Any branch‑override mapping must reference a branch that belongs to the same tenant.

4. **Missing mapping report format**
   ```
   tenant_id: <ID>
   tenant_name: <Name>
   concept_code: <Concept>
   expected_legacy_code: <Legacy GL code>
   severity: <required|optional>
   recommended_fix: <Create GL account / assign existing account>
   ```

5. **Rollback strategy**
   - Keep the feature flag `ENABLE_DYNAMIC_GL_MAPPING` **off** until cut‑over is confirmed.
   - The `GLAccountMapping` table remains inert; legacy hard‑coded lookups continue to function.
   - If issues arise after enabling, simply disable the flag; mappings stay harmless.

6. **Go/No‑Go criteria before code refactor**
   - All required tenant mappings are present and validated.
   - No validation errors above **warning** level.
   - Finance Architecture Committee signs off on the mapping report.
   - Security review confirms tenant isolation.
   - QA approves the migration validation test suite.
   - Feature flag can be safely toggled without breaking existing transaction flows.


10. **Owner approvals required before coding**
    - Product Owner (ERP Lead) sign‑off on the model schema.
    - Finance Architecture Committee approval of concept definitions.
    - Security review for tenant isolation.

## Phase 1D – GL Posting Refactor Plan

1. **Legacy account lookup locations already discovered:**
   - `services/gl_service.py`
   - `services/gl_posting.py`
   - `models/gl.py`
   - `gl_helpers.py`
   - `system_init.py`

2. **Refactor approach:**
   - Keep legacy lookup as fallback while feature flag is disabled.
   - Add resolver function `concept_code → GLAccount`.
   - Never hardcode GL account codes in new posting logic.
   - Raise a clear `GLMappingError` if required mapping is missing when feature flag is enabled.

3. **Posting flows to refactor later:**
   - sales
   - purchases
   - payments
   - receipts
   - cheques
   - inventory adjustments
   - COGS posting

## Phase 1E - Dynamic GL Mapping Foundation Completion

- Added the inert GL concept registry, `GLAccountMapping` model, additive mapping-table migration, and disabled-by-default `ENABLE_DYNAMIC_GL_MAPPING` flag.
- No mappings were seeded or backfilled, and no posting/account-resolution behavior was changed.
- Phase 1F must not begin until the mapping table migration is reviewed and the next approval gate is granted.

## Phase 1F - GL Mapping Validation and Dry-Run Design

**Important tenant onboarding rule:** New tenants must not require manual database migrations. After the `gl_account_mappings` table exists, every newly created tenant must receive default GL mappings automatically through tenant onboarding/setup logic, not through Alembic migrations.

### 1. Existing Tenants

- Validate existing GL mappings for every tenant.
- Report missing required and optional GL concepts.
- Do not guess or auto-fill unsafe mappings.
- Do not assume `tenant_id = 1`; enumerate tenants from the tenant table.
- Validate that each mapped GL account belongs to the same tenant, is active, and is postable rather than a header/group account.
- Produce a dry-run report only; Phase 1F must not seed, backfill, or alter tenant accounting data.

### 2. New Tenants

- Define default GL mappings as part of tenant onboarding/setup logic.
- Use a default chart/template as the source for tenant-level concept mappings.
- After tenant creation, run GL mapping validation automatically.
- If required mappings are missing, mark tenant setup incomplete or block accounting transactions until the setup is fixed.
- No Alembic migration should be needed per new tenant.
- Phase 1F may design this onboarding validation flow, but must not implement tenant creation changes yet.

### Phase 1F Dry-Run Outputs

- Tenant mapping completeness report by concept.
- Missing concept report with severity, tenant, concept code, and recommended manual fix.
- Invalid mapping report for cross-tenant accounts, inactive accounts, header accounts, duplicate defaults, and duplicate branch overrides.
- Onboarding validation checklist for future tenant setup implementation.
- Go/No-Go recommendation for enabling `ENABLE_DYNAMIC_GL_MAPPING`; the feature flag remains `False` until approved.

## Phase 1F - Completion Note

- Added a read-only GL mapping validation service and safe QA dry-run entry point.
- The validator reports readiness only; it does not seed, backfill, auto-fill, enable dynamic mapping, or change posting behavior.
- New tenant onboarding remains a future implementation step and must create default mappings from an approved chart/template before accounting transactions are allowed.

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

## Phase 1J - Dynamic GL Resolver Completion Note

- Added an isolated dynamic GL account resolver behind `ENABLE_DYNAMIC_GL_MAPPING`.
- While the feature flag remains disabled, the resolver returns no dynamic account and leaves legacy posting paths untouched.
- When enabled in a future approved phase, the resolver checks tenant-level mappings with optional branch override fallback and raises `GLMappingError` for missing, inactive, cross-tenant, or non-postable/header account mappings.
- No posting flows were refactored in Phase 1J.

## Phase 1K - Dynamic GL Posting Resolution Completion Note

- Started migrating backend auto-posting lines from hardcoded legacy GL codes to approved GL concept metadata.
- Refactored central auto journal-line account resolution so `concept_code` uses `GLAccountResolver` when `ENABLE_DYNAMIC_GL_MAPPING` is enabled, with legacy account-code fallback only while the flag remains disabled.
- Covered sales, purchases, payments, receipts, cheques, returns, VAT report account resolution, and inventory adjustments where an approved GL concept exists.
- When the flag is enabled, mapped concepts are authoritative and unresolved/missing mappings raise `GLMappingError`; auto-posting lines without an approved concept do not silently fall back to raw account codes.
- Deferred outgoing cheques, partner/merchant current-account handling, shipping/service/other revenue, commission/payroll/expense-specific accounts, and other non-registry accounts remain legacy fallback areas until Finance Architecture approves concepts and tests for those flows.
- Added read-only QA coverage for disabled legacy resolution, simulated enabled dynamic resolution, missing mapping failure, and blocked unmapped legacy fallback.
- `ENABLE_DYNAMIC_GL_MAPPING` remains disabled by default. No mappings, GL accounts, branch overrides, historical entries, or posting data were modified.

## Phase 1K.1 - Dynamic GL Posting Coverage Completion Note

- Extended the approved section 7.3 GL Concept Registry for the remaining active backend posting concepts found in cheques, partner/merchant current accounts, shipping revenue, commissions, payroll, bank reconciliation, donations, fixed assets, and miscellaneous expenses.
- Added a metadata-only Alembic migration to expand the `gl_account_mappings.concept_code` check constraint for those concepts. The migration does not seed data or modify historical postings.
- Reused `GLAccountingSetupService` to create tenant-level mappings for the newly approved concepts against existing postable tenant GL accounts. No branch overrides were created.
- Refactored active backend posting lines so numeric legacy account codes remain disabled-flag fallbacks only; when `ENABLE_DYNAMIC_GL_MAPPING` is enabled, `concept_code` resolution is authoritative and missing/invalid mappings raise `GLMappingError`.
- User-configured expense category accounts remain explicit configured-account postings rather than hardcoded legacy postings; in dynamic mode they are validated as same-tenant, active, postable GL accounts.
- `ENABLE_DYNAMIC_GL_MAPPING` remains disabled by default. No historical transactions or journal entries were changed.

## Phase 1L - Controlled Transaction-Flow QA with Dynamic GL Mapping Enabled Temporarily

- Executed real transaction-flow QA with `ENABLE_DYNAMIC_GL_MAPPING=True` in a temporary, test-only context.
- All 9 core auto-posting flows were exercised: sale invoice, purchase invoice, customer receipt, supplier payment, sales return, inventory adjustment, cheque receive/clear, cheque issue/bounce, and expense.
- Every journal entry created during testing was verified as balanced (total_debit == total_credit), with all lines resolving through approved `concept_code` mappings.
- No line posted to a header/group account; no cross-tenant account was used; no inactive account was used.
- Test records were clearly prefixed `QA-TEST-1L` and automatically cleaned up after verification, including all associated journal entries and lines (10 entries, 24 lines deleted).
- The feature flag default in `config.py` was never modified; the flag was restored to `False` immediately after testing.
- `tools/qa/gl_transaction_flow_qa.py` was added to support future controlled transaction-flow regression testing.
- Result: Dynamic GL Mapping is safe to enable locally for broader manual testing, provided the target tenant has active `GLAccountMapping` rows for all concepts in the posting paths to be exercised.
