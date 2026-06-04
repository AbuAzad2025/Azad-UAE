# ERP Accounting Decision Matrix

**Status:** Draft — awaiting owner approval on all "Yes" items  
**Date:** June 4, 2026  
**Purpose:** Consolidated decision matrix for all accounting policy choices required before any WAC, reconciliation, GL mapping, or financial redesign implementation.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Recommended option |
| 🔒 | Owner approval mandatory before implementation |

---

## DM-01: Inventory Costing Method

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Inventory Costing Method |
| **Options** | A. Last Purchase Cost (current)  
| | B. FIFO (First-In-First-Out)  
| | C. **Moving Weighted Average Cost (MWAC)** ✅  
| | D. Standard Cost |
| **Recommended** | **C. Moving Weighted Average Cost** |
| **Rationale** | Dominant method in UAE ERP practice (Bisan, Al-Shamel, SAP B1). Smoothes price volatility. Easier reconciliation with GL. Does not require layer tracking complexity. |
| **Financial Impact** | Eliminates "valuation jumps" on the balance sheet. COGS reflects blended historical cost, improving margin accuracy. |
| **Audit Impact** | Simpler audit trail (one running average per product/warehouse). UAE auditors are familiar with MWAC. |
| **Technical Impact** | Low complexity: single `cost_price` field per scope, updated via formula on every receipt. No layer tables needed. |
| **Risk** | Low. MWAC is a mature, well-understood method. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-02: MWAC Scope (Global vs. Per-Warehouse)

| Attribute | Value |
|-----------|-------|
| **Decision Area** | MWAC Calculation Scope |
| **Options** | A. One MWAC per product (tenant-wide)  
| | B. **One MWAC per product per warehouse** ✅  
| | C. One MWAC per product per branch |
| **Recommended** | **B. Per product per warehouse** |
| **Rationale** | UAE businesses frequently operate multiple warehouses with independent suppliers and pricing. Transfers between warehouses are natural cost events that Option B handles correctly. Branch-level P&L can be derived by aggregating warehouse data. |
| **Financial Impact** | Accurate local inventory valuation. Transfer variances are transparently absorbed at destination warehouse. |
| **Audit Impact** | Each warehouse's inventory value is independently auditable. |
| **Technical Impact** | Requires `warehouse_id` in MWAC calculation context. Transfer logic must update source and destination averages. Moderate complexity. |
| **Risk** | Medium. Inter-warehouse transfers must be handled carefully to prevent cost leakage or double-counting. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-03: Inter-Warehouse Transfer Costing

| Attribute | Value |
|-----------|-------|
| **Decision Area** | How transfer cost flows between warehouses |
| **Options** | A. **Transfer at source warehouse's current MWAC** ✅  
| | B. Transfer at destination warehouse's current MWAC  
| | C. Transfer at manual/admin-defined transfer price  
| | D. Transfer at zero cost (not recommended) |
| **Recommended** | **A. Source warehouse's current MWAC** |
| **Rationale** | The goods left the source warehouse at its known average cost. The destination warehouse receives them and recalculates its own MWAC using the received quantity and cost. This is the standard ERP behavior (Odoo, SAP B1, NetSuite). |
| **Financial Impact** | Total inventory value across all warehouses remains constant during transfer. No phantom gains/losses. |
| **Audit Impact** | Transfer GL entry is clean: Dr Destination Inventory / Cr Source Inventory at same amount. |
| **Technical Impact** | Single GL entry per transfer. MWAC recalculation at destination only. |
| **Risk** | Low. Standard behavior in all major ERPs. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-04: Sales Return — Linked Returns Cost Basis

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Which cost to use for sales returns linked to original invoice |
| **Options** | A. **Use original `SaleLine.cost_price`** ✅  
| | B. Use current MWAC at return date |
| **Recommended** | **A. Original `SaleLine.cost_price`** |
| **Rationale** | The original COGS was posted at this cost. Reversing it at the same amount preserves period accuracy and creates a clean audit trail. This is standard practice in all audited ERPs. |
| **Financial Impact** | Perfect reversal of original COGS. Inventory value increase matches what was originally deducted. No artificial variance. |
| **Audit Impact** | Crystal-clear traceability: Sale → SaleLine.cost_price → Return → COGS reversal. Auditor can verify exact match. |
| **Technical Impact** | Requires `sale_line_id` or `sale_id` on `ProductReturn`. System already has this relationship. |
| **Risk** | Very low. Standard practice. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-05: Sales Return — Unlinked Returns Cost Basis

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Which cost to use for sales returns NOT linked to original invoice |
| **Options** | A. **Use current MWAC at return date** ✅  
| | B. Use historical MWAC from a reference period  
| | C. Manual cost entry per return |
| **Recommended** | **A. Use current MWAC at return date** (with manual override field) |
| **Rationale** | Most practical for operational workflow. Current MWAC reflects the current replacement value of inventory. Manual override accommodates special cases (damaged goods, price agreements). |
| **Financial Impact** | Current-period margin may be slightly affected if MWAC has changed significantly since original sale. This is acceptable for unlinked returns (which are typically exceptions). |
| **Audit Impact** | Audit trail must record: (1) that the return was unlinked, (2) the MWAC used, (3) any manual override reason. |
| **Technical Impact** | Simple lookup of current MWAC. Add optional `override_cost_price` field to `ProductReturnLine`. |
| **Risk** | Low. Unlinked returns should be rare if the system properly links returns to original sales. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-06: Landed Cost Allocation Method

| Attribute | Value |
|-----------|-------|
| **Decision Area** | How to allocate landed costs across products in a single shipment |
| **Options** | A. **By Value** (proportional to line total) ✅  
| | B. By Quantity (proportional to unit count)  
| | C. By Weight  
| | D. By Volume (CBM)  
| | E. Manual allocation |
| **Recommended** | **A. By Value** (default), with per-purchase override capability |
| **Rationale** | By Value is the most common default in ERP systems (Odoo, SAP). It is fair when products vary significantly in price. Override allows flexibility for weight-based freight or bulky items. |
| **Financial Impact** | Higher-value items absorb more landed cost, reflecting their typically higher shipping/insurance risk. |
| **Audit Impact** | Allocation must be logged per purchase line: landed cost amount, allocation base (value/qty/weight/volume), and calculation formula. |
| **Technical Impact** | Requires `landed_cost_allocation_method` on `Purchase` model. Calculation service applies method and stores per-line `allocated_landed_cost`. |
| **Risk** | Low. By Value is widely accepted. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-07: Landed Cost Capitalization vs. Expense

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Are landed costs capitalized into inventory or expensed immediately? |
| **Options** | A. **Capitalize into inventory** (standard under UAE accounting) ✅  
| | B. Expense immediately (non-standard; requires justification) |
| **Recommended** | **A. Capitalize into inventory** |
| **Rationale** | IAS 2 / UAE accounting standards require all costs necessary to bring inventory to its present location and condition to be included in inventory cost. Expensing them immediately understates inventory and overstates current-period expenses. |
| **Financial Impact** | Inventory balance is higher. COGS reflects true acquisition cost. P&L is smoothed over sale periods rather than front-loaded. |
| **Audit Impact** | Capitalized costs are auditable via the purchase document and the inventory valuation report. |
| **Technical Impact** | `PurchaseLine` must support `allocated_landed_cost`. MWAC formula must include landed cost in `Incoming Unit Cost`. |
| **Risk** | Very low. This is the only compliant option under IAS 2. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-08: Multi-Currency Exchange Rate Source

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Which exchange rate to use for foreign-currency inventory purchases |
| **Options** | A. **Central Bank of UAE (CBUAE) official rate** ✅  
| | B. Bank transaction rate (per payment)  
| | C. Tenant-defined manual rate |
| **Recommended** | **A. CBUAE official rate** (default), with manual override per purchase |
| **Rationale** | CBUAE rate is authoritative, publicly available, and audit-friendly. Bank rate is more accurate for cash flow but varies by institution. Manual override handles exceptional cases (forward contracts, agreed rates). |
| **Financial Impact** | Official rate may differ from bank rate by a small margin. FX differences are posted to FX Gain/Loss, not inventory, so inventory valuation remains consistent. |
| **Audit Impact** | CBUAE rate is verifiable by external auditors. Manual overrides must include a justification note. |
| **Technical Impact** | Integrate CBUAE API or daily rate table. Store `exchange_rate` and `exchange_rate_source` on `Purchase`. |
| **Risk** | Low. Standard practice in UAE accounting. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-09: FX Difference Treatment

| Attribute | Value |
|-----------|-------|
| **Decision Area** | How to handle exchange rate differences between purchase date and payment date |
| **Options** | A. **Post FX Gain/Loss to P&L** (standard accounting) ✅  
| | B. Adjust inventory cost with FX difference (non-standard) |
| **Recommended** | **A. Post FX Gain/Loss to P&L** |
| **Rationale** | IAS 21 and UAE standards require FX differences on monetary items (AP) to be recognized in P&L. Inventory is a non-monetary item recorded at historical cost; it is not revalued for FX changes. |
| **Financial Impact** | Inventory cost remains fixed at purchase-date rate. FX volatility affects P&L, not balance sheet inventory. |
| **Audit Impact** | Clean separation: inventory at historical cost, FX differences in a dedicated P&L account. |
| **Technical Impact** | Standard GL posting. No inventory model changes needed. |
| **Risk** | Very low. This is the only compliant option. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-10: Closed Period Protection

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Behavior when a user attempts to modify data in a closed accounting period |
| **Options** | A. **Block all changes with clear error message** ✅  
| | B. Allow changes with elevated permission + audit log  
| | C. Silently redirect to adjustment entry workflow |
| **Recommended** | **A. Block all changes; direct user to create an adjustment entry in an open period** |
| **Rationale** | Prevents accidental restatement of closed periods. Adjustment entries in open periods preserve the original period's integrity. This is the standard in all audited ERPs (SAP, Oracle, NetSuite). |
| **Financial Impact** | Historical periods remain immutable. Any correction is visible as a separate adjustment with full traceability. |
| **Audit Impact** | Auditor can trust that closed-period data has not been altered after the fact. |
| **Technical Impact** | All posting services call `assert_period_open()` before any DB write. `GLPeriod` model already supports this. |
| **Risk** | Very low. Standard control. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-11: Reconciliation Behavior

| Attribute | Value |
|-----------|-------|
| **Decision Area** | What should the reconciliation engine do when it finds a variance |
| **Options** | A. **Report only; no auto-correction** ✅  
| | B. Auto-generate a suggested adjustment entry for manual approval  
| | C. Auto-post correction entry (not recommended) |
| **Recommended** | **A. Report only** |
| **Rationale** | Reconciliation is a control mechanism, not an accounting action. Auto-correction bypasses human judgment and creates audit risk. The report should clearly state the variance and recommend a manual adjustment. |
| **Financial Impact** | None (reporting only). Accountant decides whether and how to adjust. |
| **Audit Impact** | Reconciliation report becomes an audit document. Variance + resolution are both traceable. |
| **Technical Impact** | Read-only service. Generates PDF/Excel report. No DB writes during reconciliation. |
| **Risk** | Very low. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-12: GL Mapping Granularity

| Attribute | Value |
|-----------|-------|
| **Decision Area** | At what level should GL account mappings be defined |
| **Options** | A. **Per tenant** (single mapping per tenant) ✅  
| | B. Per branch (branch overrides tenant mapping)  
| | C. Per warehouse |
| **Recommended** | **A. Per tenant** (Phase 1), with optional branch override (Phase 2) |
| **Rationale** | Most tenants use unified books. Branch override is an advanced feature for holding companies or franchises. Starting with tenant-level keeps Phase 1 simple and deliverable. |
| **Financial Impact** | Unified books simplify consolidation. Branch override adds flexibility later. |
| **Audit Impact** | Mapping changes are auditable per tenant. Branch overrides are auditable per branch. |
| **Technical Impact** | Tenant-level: simple `tenant_id` + `concept_code` unique constraint. Branch override: add nullable `branch_id` with fallback logic. |
| **Risk** | Low for Phase 1. Medium for Phase 2 if branch override logic is not well-tested. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## DM-13: Rounding Rules for MWAC

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Decimal precision and rounding rules for MWAC and COGS |
| **Options** | A. **3 decimals for unit costs, 2 for currency display** ✅  
| | B. 2 decimals throughout  
| | C. System-defined per tenant |
| **Recommended** | **A. 3 decimals for unit costs and line totals; 2 decimals for tax and display** |
| **Rationale** | 3-decimal precision prevents rounding drift in MWAC calculations over many transactions. Display rounding to 2 decimals is standard for invoices and reports. This matches Bisan and Al-Shamel behavior. |
| **Financial Impact** | Prevents penny drift in COGS over time. Display remains user-friendly. |
| **Audit Impact** | Internal precision is auditable. Display rounding is cosmetic only. |
| **Technical Impact** | `Decimal('0.001')` for MWAC, `Decimal('0.01')` for tax. Already partially implemented. |
| **Risk** | Very low. |
| **Requires Owner Approval** | **Yes** 🔒 |

---

## Summary: Decisions Requiring Approval

| ID | Decision | Recommended | Impact | Status |
|----|----------|-------------|--------|--------|
| DM-01 | Costing Method | MWAC | Financial + Audit | ⏳ Pending |
| DM-02 | MWAC Scope | Per product per warehouse | Financial + Technical | ⏳ Pending |
| DM-03 | Transfer Costing | Source MWAC | Financial + Audit | ⏳ Pending |
| DM-04 | Linked Return Cost | Original SaleLine cost_price | Financial + Audit | ⏳ Pending |
| DM-05 | Unlinked Return Cost | Current MWAC | Financial + Audit | ⏳ Pending |
| DM-06 | Landed Cost Allocation | By Value (default) | Financial + Audit | ⏳ Pending |
| DM-07 | Landed Cost Treatment | Capitalize into inventory | Financial + Compliance | ⏳ Pending |
| DM-08 | FX Rate Source | CBUAE official | Financial + Audit | ⏳ Pending |
| DM-09 | FX Difference | P&L Gain/Loss | Financial + Compliance | ⏳ Pending |
| DM-10 | Closed Period | Block all changes | Compliance + Audit | ⏳ Pending |
| DM-11 | Reconciliation | Report only | Audit + Control | ⏳ Pending |
| DM-12 | GL Mapping | Tenant-level (Phase 1) | Technical + Audit | ⏳ Pending |
| DM-13 | Rounding | 3-decimal internal, 2-decimal display | Financial + Technical | ⏳ Pending |

**Total pending approvals: 13**

---

*Decision Matrix created: June 4, 2026*
*Status: Awaiting owner approval on all 13 decisions*
