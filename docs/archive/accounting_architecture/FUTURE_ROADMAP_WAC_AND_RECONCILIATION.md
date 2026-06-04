# Future Roadmap: Moving Weighted Average Cost (MWAC) & Ledger Reconciliation

**Status:** Approved & Scheduled (Aligned with Regional and International ERP Guidelines)  
**Date:** June 4, 2026  
**Recommended Priority:** CRITICAL (Phase 2)  
**Estimated Effort:** 8-9 Sprints  

---

## 1. Vision & Strategy
The goal of this roadmap is to establish a robust, compliant, and auditable inventory valuation and ledger reconciliation engine for Azad ERP. 
- **Strategic Target Markets:** Expanding from the UAE to Palestine, GCC countries (KSA, Qatar, Oman, Bahrain, Kuwait), Arabic markets, and future international expansion.
- **Reference Architectures:** Modeling system controls after the financial correctness and structural discipline of Bisan, Al-Shamel, SAP Business One, Oracle NetSuite, Odoo, Microsoft Dynamics, and Xero.
- **Core Standard:** True Moving Weighted Average Cost (MWAC) perpetual inventory system. Custom/ad-hoc valuation models and legacy repair scripts are phased out.

---

## 2. Core Principles & Validation

### 2.1 WAC Validation & Immutability
This roadmap implements a **TRUE Moving Weighted Average Cost** valuation framework:
- **No FIFO Valuation:** Under no circumstances will FIFO be utilized as a primary or fallback valuation method.
- **No FIFO Layer Logic:** The system will not track, consume, or expire inventory cost layers (First-In, First-Out queue logic).
- **Cost History is Audit-Only:** All cost tracking tables are strictly for audit-trail logging and reporting. They are never read by the transaction posting engine to consume cost layers.
- **Authoritative MWAC:** The per-warehouse `average_cost` column in `ProductWarehouseCost` is the sole, authoritative source of truth for inventory asset valuation and COGS calculations.

### 2.2 Ledger Reconciliation Mandate
- **Read-Only Reporting:** Reconciliation is strictly a validation and reporting control tool.
- **No Auto-Posting / Auto-Correction:** The reconciliation engine must **NOT** automatically write correcting journals, adjust stock quantities, or alter average costs in the database.
- **Closed Period Lock:** The system blocks all postings, changes, and cost recalculations in closed periods. Corrections are posted in open periods using standard adjustment and reversal workflows.

---

## 3. Approved Decisions Matrix (DM-01 to DM-14)

### Costing & Scope
- **DM-01 (Costing Method):** APPROVED. Moving Weighted Average Cost (MWAC) only.
- **DM-02 (MWAC Scope):** APPROVED. Recalculated independent per product, per warehouse.
- **DM-03 (Transfer Costing):** APPROVED. Stock leaves the source warehouse at its current MWAC. Recalculation is triggered at the destination warehouse upon receipt.

### Sales & Landed Costs
- **DM-04 (Linked Return Cost):** APPROVED. Use the original invoice's `SaleLine.cost_price` to reverse COGS.
- **DM-05 (Unlinked Return Cost):** APPROVED. Use current MWAC of the receiving warehouse, with optional manual override and audit trail.
- **DM-06 (Landed Cost Allocation):** APPROVED. Default allocation: Allocate By Value. Future support: Quantity, Weight, Volume, Manual allocation.
- **DM-07 (Landed Cost Treatment):** APPROVED. Landed costs (Freight, Customs, Insurance, Clearance, Handling) are capitalized into inventory value.

### Multi-Currency & Treasury
- **DM-08 (Exchange Rate Strategy):** APPROVED. Primary source is manual exchange rate entered by authorized manager. Fallback: online rate retrieved at creation time. Once posted, rates are permanent and never recalculated.
- **DM-09 (FX Differences):** APPROVED. Recognized immediately in standard P&L FX Gain/Loss accounts.
- **DM-10 (Closed Periods):** APPROVED. Block all edits; use reversal/adjustment entries.
- **DM-11 (Reconciliation):** APPROVED. Reporting and monitoring only; no auto-posting.
- **DM-12 (GL Mapping):** APPROVED. Concept-based resolution (Phase 1: Tenant-level; Future: Branch override). Remove hardcoded accounts.

### Precision & Localization
- **DM-13 (Precision Rules):** APPROVED. Intermediate calculations and exchange rates calculated at 6 decimals; unit costs at 4 decimals; quantities at 3 decimals; display and ledger balances at localized currency decimals.
- **DM-14 (Localization Strategy):** APPROVED. Implement a Global Localization Framework (Option D) to support multi-currency, multi-tax, and regional compliance (ZATCA, WPS, PMA audits).

---

## 4. Target ERP Accounting Architecture
To support enterprise-grade operations, the system integrates the following dimensions-driven model:

### 4.1 Account Structure Principle: Accounts vs. Dimensions
- **Accounts** represent the financial category (e.g. `SALES_REVENUE`, `INVENTORY_ASSET`).
- **Dimensions** represent the operational context (e.g. branch, warehouse, cost center, project).
- **Chart of Accounts Bloat Prevention:** The system prohibits creating separate accounts for separate branches/warehouses (e.g. no `Sales_Ramallah`). A single central account is used, and lines are tagged with dimensions.

### 4.2 Financial Dimensions Registry
Every journal line must support and validate the following dimensions:
- `tenant_id`: Mandatory tenant-isolation key.
- `branch_id`: Attribution to specific branch entities.
- `warehouse_id`: Operational warehouse location.
- `cost_center_id`: Internally-scoped expense centers (e.g. departments, fleets).
- `profit_center_id`: Revenue-generating divisions.
- `partner_id`: Customer/supplier accounts.
- `currency`: Base and transaction currency.
- `payment_channel`: Cash register cashier or bank account.

### 4.3 Tenant Isolation
Each tenant operates in complete database isolation. Under no circumstances can a tenant view, edit, or join another tenant's ledger accounts, journal entries, balances, cash box setups, or mappings. Platform admin settings remain strictly decoupled.

### 4.4 Branch & Warehouse Models
- **Branch Model:** Includes branch identity, user permissions, assigned bank accounts, cash registers, warehouses, and cost/profit attribution dimensions.
- **Warehouse Model:** Operational dimension. Mappings support future enterprise overrides to route specific warehouse inventory to customized asset accounts.

### 4.5 Treasury & Cash Management
- **Multiple Cash Boxes:** Cash registers tracked independently per branch.
- **Multiple Bank Accounts:** Configured per tenant and assigned to branches.
- **Employee Advances:** Tracked as employee receivables, cleared against payroll.
- **Internal Transfers:** Dual-control workflows for cash-to-bank and cash-box transfers.
- **Cash Position Reporting:** Aggregated cash positioning reports showing cash-in-transit, bank balances, and cheques under collection.

---

## 5. Technical Approach & Data Model

### 5.1 Data Model: `ProductWarehouseCost` & `ProductCostHistory`
```python
class ProductWarehouseCost(db.Model):
    __tablename__ = 'product_warehouse_costs'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    quantity = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    average_cost = db.Column(db.Numeric(15, 6), default=0, nullable=False) # stored at 6 decimals

class ProductCostHistory(db.Model):
    __tablename__ = 'product_cost_history'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    movement_type = db.Column(db.String(20), nullable=False) # purchase, sale, transfer_in, return, etc.
    movement_id = db.Column(db.Integer, nullable=False)
    quantity_before = db.Column(db.Numeric(15, 3), nullable=False)
    quantity_change = db.Column(db.Numeric(15, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(15, 6), nullable=False)
    average_cost_before = db.Column(db.Numeric(15, 6), nullable=False)
    average_cost_after = db.Column(db.Numeric(15, 6), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
```

---

## 6. Implementation Sprints & Phase Roadmap

### Sprint 1: Database Migration & Schema Setup
- Create `product_warehouse_costs` and `product_cost_history` tables.
- Seed data from existing `Product.current_stock` and `Product.cost_price`.
- Remove legacy client-side cascades on `StockMovement` models.

### Sprint 2: Core Costing Engine (`MWACStockService`)
- Implement `incoming_movement()` and `outgoing_movement()` logic.
- Add validations (negative stock checks, division-by-zero checks, period open checks).
- Run exhaustive unit tests on rounding precision.

### Sprint 3: Purchase & Landed Cost Integration
- Modify purchase confirmation hooks to call `incoming_movement()`.
- Incorporate allocated landed costs (freight, customs, insurance, clearance, handling) into `incoming_unit_cost`.
- Update GL posting logic to debit `INVENTORY_ASSET` with capitalized cost.

### Sprint 4: Sale & Return Posting Updates
- Hook sale confirmation to snapshot MWAC into `SaleLine.cost_price` and write `outgoing_movement()`.
- Hook returns: Linked returns use original `SaleLine.cost_price`; unlinked returns use current MWAC with manual override audits.
- Post COGS reversals to ledger.

### Sprint 5: Inter-Warehouse Transfers & Adjustments
- Write double-entry transfer logic (out at source MWAC, recalculate average cost at destination upon receipt).
- Update positive and negative stock adjustments.
- Implement closed period verification checking `GLPeriod.is_closed` prior to posting.

### Sprint 6: Configurable GL Concept Mapping
- Set up `GLAccountMapping` registry per tenant.
- Replace hardcoded account codes in services with dynamic lookups (`INVENTORY_ASSET`, `COGS`, `AR`, `AP`, `CASH`, `BANK`, etc.).

### Sprint 7: Ledger-to-Stock Reconciliation Report
- Develop `InventoryReconciliationService` to compare physical counts, MWAC stock values, and GL account balances.
- Generate read-only reports (PDF and Excel formats).
- Deprecate `accounting_repair.py`.

### Sprint 8: User Acceptance Testing (UAT) & Localization Compliance
- Run dual-posting tests to verify zero currency rounding drift on foreign purchases.
- Verify Palestinian (ILS/JOD) and GCC tax reporting structures.
- Launch the production transition.

---

## 7. Migration Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Missing historical pricing data for initial MWAC | High | High | Seed initial `average_cost` from `Product.cost_price`. Validate stock values prior to migration. |
| Rounding precision drift | Low | Medium | Calculate and persist MWAC intermediates at 6 decimals. Run daily validation scripts. |
| Ledger mismatch after go-live | High | High | Require a baseline reconciliation report and manual adjustment entry at go-live. |
| User confusion regarding changing costs | Medium | Low | Update UI tooltips to display MWAC vs Last Purchase Cost. |
