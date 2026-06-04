# ERP SYSTEM REVERSE ENGINEERING MASTER REPORT

## 1. Executive Summary
The **Azad-UAE ERP** is a sophisticated multi-tenant system designed for the UAE market, featuring robust modules for Sales, Inventory, and General Ledger (GL) management. While the system demonstrates a high degree of functional maturity, a comprehensive reverse engineering audit has identified critical structural and financial integrity risks. These risks primarily stem from inconsistent multi-tenant scoping in specialized modules, unsafe data deletion policies that threaten financial auditability, and a volatile inventory costing model. This report synthesizes four phases of analysis and provides a definitive strategic roadmap for system hardening and accuracy improvement.

---

## 2. System Architecture
### 2.1 Core Infrastructure
- **Framework:** Flask (Python) with a service-oriented business logic layer.
- **Database:** PostgreSQL with SQLAlchemy ORM.
- **Multitenancy:** Shared-database, row-level isolation via `tenant_id`.
- **Localization:** Full support for Arabic (AR) and English (EN) interfaces and data.

### 2.2 Functional Module Map
- **Sales:** Manages the full lifecycle from creation and fulfillment to payment and cancellation.
- **Inventory:** Centralized stock management with warehouse and branch-level scoping.
- **Accounting (GL):** A double-entry core with automated posting hooks for all major business events.
- **Purchases:** Supplier procurement integrated with stock receiving and cost management.
- **AI Integration:** Predictive analytics for sales and margin optimization.

---

## 3. Database Architecture
### 3.1 Primary Entities
- **Tenants:** `tenants` table (ID, name, slug, settings).
- **Accounting:** `gl_accounts`, `gl_journal_entries`, `gl_journal_lines`.
- **Operations:** `sales`, `sale_lines`, `purchases`, `purchase_lines`, `payments`, `receipts`.
- **Inventory:** `products`, `warehouses`, `stock_movements`.

### 3.2 Integrity Observations
- **Foreign Keys:** Extensively used but inconsistent in `ondelete` behavior.
- **Audit Trails:** Captured via `created_at`, `updated_at`, and `created_by` fields across most tables.
- **Scoping:** Tenant and branch scoping are prevalent but missing in advanced accounting modules (specifically `CustomsTax`, `AdvancedExpense`).

---

## 4. Accounting Analysis
### 4.1 GL Posting Logic
- Centralized via `GLService` and `gl_posting.py`.
- Enforces balanced entries (`debit == credit`) and closed-period protection (`gl_helpers.assert_period_open`).
- Links journal entries to source documents via `reference_type` and `reference_id`.

### 4.2 Financial Integrity Risks
- **Hardcoded Accounts:** Several services hardcode GL codes (e.g., '1130' for AR, '2110' for AP), which may conflict with custom tenant charts.
- **Balance Accumulators:** Customer/Supplier balances are maintained as total columns in models, risking "drift" from the ledger if transactions fail partially or are reversed manually.
- **Cancellation Safety:** Robust reversal logic (`GLService.reverse_entry`) ensures audit trails are preserved by creating reversing entries rather than deleting history.

---

## 5. Inventory and Costing Analysis
### 5.1 Stock Management
- **Negative Stock:** Strictly prevented via service-level checks in `StockService.create_movement`.
- **Accumulators:** `Product.current_stock` is updated immediately on movement. Warehouse-level availability is calculated dynamically.

### 5.2 Costing & Valuation
- **Costing Method:** **Last Purchase Cost**. Every purchase overwrites the global `Product.cost_price`.
- **COGS Logic:** Captured as a "snapshot" in `SaleLine.cost_price` at the time of sale creation.
- **Valuation Vulnerability:** Using Last Purchase Cost for valuation (`Quantity * Latest Cost`) causes massive Balance Sheet volatility and necessitates the use of "repair" scripts like `accounting_repair.py`.

---

## 6. Multi-Tenant Analysis
- **Status:** Isolation is well-implemented in core modules but fails in `models/advanced_accounting.py`.
- **Risk:** Data leakage between tenants in tax and specialized expense modules.
- **Constraint:** Current circular dependency between `Tenant` and `User` models complicates initial system bootstrapping.

---

## 7. Risks and Findings Summary
| Risk Level | Area | Finding |
| :--- | :--- | :--- |
| **CRITICAL** | Audit Trail | `ON DELETE CASCADE` on `StockMovement` wipes audit history if a product is deleted. |
| **HIGH** | Security | Missing `tenant_id` in advanced accounting models leads to cross-tenant data visibility. |
| **HIGH** | Accuracy | Last Purchase Cost method causes "valuation jumps" and Ledger-Stock drift. |
| **MEDIUM** | Integrity | Manual balance accumulators for Customers/Suppliers are prone to sync issues. |
| **MEDIUM** | Hardcoding | Hardcoded GL account codes in services bypasses tenant customization. |

---

## 8. Strategic Roadmap
### Phase 1: Hardening (Immediate)
1. **Security:** Add `tenant_id` to all `advanced_accounting` models with safe backfill.
2. **Auditability:** Change `CASCADE` to `RESTRICT` for `StockMovement.product_id` and `Payment.sale_id`.
3. **UI Workflow:** Replace "Delete" with "Cancel/Void" in financial interfaces.

### Phase 2: Accuracy (Short-Term)
1. **Costing:** Migrate `StockService` to **Weighted Average Cost (WAC)** to stabilize valuation.
2. **Reconciliation:** Automate ledger-to-stock reconciliation and phase out `accounting_repair.py`.

### Phase 3: Scaling (Mid-Term)
1. **Performance:** Apply secondary indexing round (`perf_idx_round2`) on high-traffic join columns.
2. **Dynamic GL:** Replace hardcoded account codes with a configurable "Account Mapping" system per tenant.

---

## 9. Open Questions
- **Payment Vault:** The level of PCI-DSS compliance for the encrypted card data in `card_vault.py`.
- **AI Influence:** Does the AI pricing recommendation have the authority to bypass the `StockService` negative stock prevention?
- **Payroll Reconciliation:** How are manual GL payroll adjustments reconciled with the `PayrollTransaction` history?

---

## 10. References to Source Files
- **Models:** `models/gl.py`, `models/sale.py`, `models/product.py`, `models/warehouse.py`, `models/advanced_accounting.py`.
- **Services:** `services/gl_service.py`, `services/sale_service.py`, `services/stock_service.py`, `services/payment_service.py`.
- **Integrity Utils:** `utils/gl_helpers.py`, `utils/tenanting.py`, `runtime_core/accounting_repair.py`.

---
*End of Master Report - Generated June 2026*
