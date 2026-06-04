# ERP Accounting Decision Matrix

**Status:** Approved & Finalized (Incorporates Owner Approvals & Regional ERP Alignment)  
**Date:** June 4, 2026  
**Purpose:** Consolidated decision matrix for all accounting policy choices required for Moving Weighted Average Cost (MWAC), ledger reconciliation, multi-currency, and localized country frameworks.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| APPROVED | Decision finalized and approved by business owner |
| PENDING | Awaiting final review (requires comparative evaluation) |
| ✅ | Recommended option |
| 🔒 | Owner approval mandatory |

---

## DM-01: Inventory Costing Method

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Inventory Costing Method |
| **Status** | **APPROVED** |
| **Approved Choice** | **Moving Weighted Average Cost (MWAC)** |
| **Prohibited Methods** | Last Purchase Cost, FIFO as primary valuation method, hybrid valuation models |
| **Rationale** | Alignment with Bisan, Al-Shamel, SAP B1, Odoo, NetSuite. Smoothes price volatility and prevents artificial margins. |
| **Financial Impact** | Eliminates valuation jumps on the Balance Sheet. COGS reflects true blended acquisition costs on the P&L. |
| **Audit Impact** | Transparent running average per item. Approved by regional (Palestine/GCC) and international auditors. |
| **Technical Impact** | Uses single unit cost updated programmatically on receipt. No FIFO layers or stack queues are created. |

---

## DM-02: MWAC Scope

| Attribute | Value |
|-----------|-------|
| **Decision Area** | MWAC Calculation Scope |
| **Status** | **APPROVED** |
| **Approved Choice** | **Per Product, Per Warehouse** |
| **Alternatives Evaluated** | Global per product (tenant-wide), Per product per branch |
| **Rationale** | Accurate cost tracking across multiple physical storage hubs with varying supplier logistics. |
| **Financial Impact** | Accurate localized asset valuation. Reflects regional procurement differences. |
| **Technical Impact** | Recalculation logic is scoped to `(product_id, warehouse_id)`. Inter-warehouse transfers are treated as cost-generating receipt events. |

---

## DM-03: Warehouse Transfer Cost

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Valuation of stock during inter-warehouse transfers |
| **Status** | **APPROVED** |
| **Approved Choice** | **Use the source warehouse MWAC at the exact transfer time** |
| **Rationale** | Prevents artificial cost adjustments during movements.Recipients value the inventory at its actual leaving cost, then recalculate destination MWAC upon receipt. |
| **Financial Impact** | Absolute balance sheet neutrality. Consolidated inventory asset value remains unchanged. |
| **Technical Impact** | The transfer document records `source_mwac`. Recalculation triggers at the destination warehouse using `source_mwac` as the incoming unit cost. |

---

## DM-04: Linked Sales Return Cost

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Valuation of returned inventory linked to a original invoice |
| **Status** | **APPROVED** |
| **Approved Choice** | **Use original `SaleLine.cost_price`** |
| **Rationale** | Perfectly reverses the original COGS transaction, restoring the exact historical asset value. |
| **Financial Impact** | Zero margin distortion. Reinstates inventory at its original cost, preventing margin drift in the return period. |
| **Audit Impact** | Matches original deduction exactly. High audit trail compliance. |

---

## DM-05: Unlinked Sales Return Cost

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Valuation of returned inventory NOT linked to an invoice |
| **Status** | **APPROVED** |
| **Approved Choice** | **Use current MWAC of the receiving warehouse, with optional manual override and audit trail** |
| **Rationale** | Simplest baseline for unlinked exceptions. Override allows capturing depreciated or damaged returns. |
| **Financial Impact** | Standardizes incoming value to current replacement cost. Manual overrides allow valuation write-down at source. |
| **Audit Impact** | Audit logs capture the user ID, return reason, and any manual override value for compliance checking. |

---

## DM-06: Landed Cost Allocation

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Allocation basis of freight, customs, and clearance costs across purchase items |
| **Status** | **APPROVED** |
| **Approved Choice** | **Default: Allocate By Value (Proportional to line item amount)** |
| **Future Extensions** | Future system updates may support allocation by Quantity, Weight, Volume, or Manual override |
| **Rationale** | Matches default behavior of SAP Business One and NetSuite. Most logical allocation for mixed shipments. |
| **Technical Impact** | Sum of landed costs is divided proportionally using line item price weights. Adds `allocated_landed_cost` to purchase lines. |

---

## DM-07: Landed Cost Treatment

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Capitalization vs Expensing of acquisition costs |
| **Status** | **APPROVED** |
| **Approved Choice** | **Capitalize landed costs into inventory valuation** |
| **Included Costs** | Freight, Customs, Insurance, Clearance, Handling Charges |
| **Rationale** | Mandated by IAS 2 and local regulatory tax authorities. Under-allocating increases period volatility. |
| **Financial Impact** | Increases stock asset value on the Balance Sheet; defers cost impact to P&L until item is sold (via COGS). |

---

## DM-08: Exchange Rate Strategy

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Foreign currency document conversion and historical locking |
| **Status** | **APPROVED (REVISED)** |
| **Primary Source** | **Manual exchange rate entered by an authorized manager** takes precedence. |
| **Fallback Rule** | If no approved manual rate exists, retrieve the online rate from a configured source (e.g. Central Bank APIs) at document creation time. |
| **Accounting Rule** | Once a document is posted, its exchange rate becomes part of the permanent, immutable accounting record. The rate used by a posted transaction must never be recalculated automatically. |
| **Audit Rule** | The retrieved/fallback rate must be stored permanently on the document schema. |
| **Historical Rule** | Future exchange rate updates or rate adjustments must never alter historical transactions. |
| **Future Requirement** | Support multiple rate providers and country-specific sources (e.g., PMA for Palestine, SAMA for Saudi Arabia, CBUAE for UAE). |
| **Rationale** | Standard practice for international multi-currency systems. Protects accounting ledger from rate adjustments. |

---

## DM-09: Foreign Exchange Differences

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Accounting treatment of rate fluctuations between invoice and payment |
| **Status** | **APPROVED** |
| **Approved Choice** | **Post differences to FX Gain / FX Loss accounts through standard P&L** |
| **Prohibited Action** | Retroactive adjustments to inventory assets or original purchase costs are strictly banned. |
| **Rationale** | Standard double-entry compliance (IAS 21). Inventory is non-monetary and remains valued at historical conversion cost. |

---

## DM-10: Closed Period Protection

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Modification of records in closed fiscal periods |
| **Status** | **APPROVED** |
| **Approved Choice** | **Block all modifications (No historical recalculation, no silent corrections, no rewriting posted accounting history)** |
| **Correction Rules** | All corrections must utilize: Reversal Entries (Credit/Debit Notes), Adjustment Entries in open periods, and a full Audit Trail. |
| **Rationale** | Standard financial integrity safeguard across enterprise-level platforms (NetSuite, SAP, Bisan). |

---

## DM-11: Reconciliation Behavior

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Scope and capability of the stock-to-ledger reconciliation system |
| **Status** | **APPROVED** |
| **Approved Choice** | **Reconciliation is limited to: Reporting, Monitoring, and Validation** |
| **Prohibited Action** | The reconciliation engine must **NOT auto-post corrections** or **auto-change accounting records**. |
| **Rationale** | Maintains the division of control. Accountants analyze variances and manually post adjustment entries. |

---

## DM-12: Dynamic GL Mapping

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Custom charts of accounts mappings |
| **Status** | **APPROVED** |
| **Approved Choice** | **Phase 1: Per Tenant. Future: Optional Branch Override.** |
| **Core Mandate** | **Remove all dependencies on hardcoded account codes** (e.g. `'1130'`, `'1140'`) in business logic. Resolve posting lines dynamically via GL Concepts. |
| **Rationale** | Allows tenants in Palestine (Bisan/Al-Shamel standard charts) and GCC to map transactions to their own localized ledger codes. |

---

## DM-13: Precision Rules

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Decimal precision and rounding parameters across operational and financial modules |
| **Status** | **APPROVED** |
| **1. Recommended Internal Precision** | **6 Decimals** (`Decimal('0.000001')`). All mathematical processes, intermediate calculations, landed cost splits, and average updates are processed at 6-decimal precision to prevent penny drift. |
| **2. Quantity Precision** | **3 Decimals** (`Decimal('0.001')`). Standard for weights, dimensions, and fractional items (e.g., `10.500` kg or `1.000` unit). |
| **3. Unit Cost Precision** | **4 Decimals** (`Decimal('0.0001')`) for purchase and sale document unit costs. |
| **4. Exchange Rate Precision** | **6 Decimals** (`Decimal('0.000001')`) for currency exchange rate definitions. |
| **5. Inventory Valuation Precision** | **MWAC stored precision = 6 decimals**, **Inventory valuation calculations = 6 decimals internally**, and **Final journal amounts = currency-specific decimals** |
| **6. Journal Entry Precision** | **Base Currency Decimals** (Typically 2 decimals for AED, SAR; 3 decimals for JOD, KWD) utilizing banker's rounding (`ROUND_HALF_EVEN`) to guarantee ledger balance integrity (debits = credits). |
| **7. Currency-Specific Display Precision** | **Localized Decimal Formats** (e.g., 2 decimals for AED/SAR/ILS/USD/EUR; 3 decimals for JOD/KWD/BHD/OMR). |
| **Evaluated Options** | - **A. 3 Decimals everywhere:** Standardizes database fields but creates severe rounding drift in high-volume inventory cost updates and landed cost divisions.  <br>- **B. 4 Decimals everywhere:** Standard ERP pricing default, but inadequate for foreign exchange rates where minor variations cause large ledger differences.  <br>- **C. 6 Decimals everywhere:** Eliminates drift but floods ledger reports, invoices, tax calculations, and cash books with non-payable fractional decimals. |
| **Comparative Analysis & Rationale** | - **MWAC Drift Prevention:** Calculating averages at 6 decimals prevents the loss of fractional currency over continuous sales and receipts.  <br>- **Exchange Rate Conversions:** 6 decimals is the global banking standard. Under-scaling rates causes heavy P&L adjustments.  <br>- **Human Readability:** Keeping display decimals aligned to local currency norms (e.g., 2 or 3 decimals) maintains customer trust and standard invoicing. |

### DM-13 Practical Examples

#### 1. MWAC Calculation Example
* **Initial State:** 1,000 units on hand at an average cost of JOD `1.450375` (Total Value = JOD `1,450.375000`).
* **Incoming Receipt:** 15 units at JOD `1.485200` per unit (Receipt Value = JOD `22.278000`).
* **Formula Execution (6 Decimals Internal):**
  ```
  New MWAC = (1,450.375000 + 22.278000) / (1,000 + 15)
           = 1,472.653000 / 1,015
           = 1.450889655...
  ```
* **Resolved Database Average Cost:** JOD `1.450890` (Rounded to 6 decimals).
* **Comparison with Low-Precision Methods:**
  * *If rounded to 3 decimals (JOD 1.451):* Stock Value = JOD `1,472.765` (Creates an artificial valuation gain of JOD `0.112`).
  * *If rounded to 4 decimals (JOD 1.4509):* Stock Value = JOD `1,472.664` (Creates a gain of JOD `0.011`).
  * *At 6 decimals (JOD 1.450890):* Stock Value = JOD `1,472.653` (Zero rounding drift).

#### 2. FX Conversion Example
* **Transaction Amount:** USD `100,000.00`
* **Exchange Rate (USD to AED):** CBUAE Rate = `3.672520` (6 decimals).
* **Formula Execution:**
  ```
  AED Amount = 100,000.00 * 3.672520 = 367,252.00 AED
  ```
* **Rounding Comparison:**
  * *If rounded to 3 decimals (3.673):* Amount = `367,300.00` AED (Differs by **+48.00 AED**).
  * *If rounded to 4 decimals (3.6725):* Amount = `367,250.00` AED (Differs by **-2.00 AED**).
  * *At 6 decimals (3.672520):* Amount = `367,252.00` AED (Perfect conversion match).

#### 3. Inventory Valuation Aggregate
* **Scenario:** A product in Warehouse A has a quantity of `10,000` units with a MWAC of `1.125642` AED.
* **Valuation Calculation:**
  ```
  Asset Value = 10,000 * 1.125642 = 11,256.42 AED
  ```
* **Rounding Comparison:**
  * *Using 3-decimal cost (1.126):* Asset Value = `11,260.00` AED (Valuation drift = **+3.58 AED**).
  * *Using 4-decimal cost (1.1256):* Asset Value = `11,256.00` AED (Valuation drift = **-0.42 AED**).
  * *Using 6-decimal cost (1.125642):* Asset Value = `11,256.42` AED (Perfect match to GL balance).

---

## DM-14: Multi-Country Localization Strategy

| Attribute | Value |
|-----------|-------|
| **Decision Area** | Software architecture for multi-region tax and compliance |
| **Status** | **APPROVED** |
| **Evaluated Options** | - **A. UAE-centric architecture:** Restricts systems to AED base currency and 5% VAT.  
| | - **B. GCC-centric architecture:** Scales VAT dynamically (5%-15%) and supports SAR/AED/QAR but misses Palestine rules.  
| | - **C. Arabic multi-country architecture:** Supports regional Arab world but lacks structural flexibility for global operations.  
| | - **D. Global Localization Framework** ✅ (Recommended). |
| **Rationale** | Bisan/Al-Shamel standard markets (Palestine) use 16% VAT and multi-currency ledgers (ILS, JOD, USD). GCC markets use single currency with 5-15% VAT. Option D abstracts localization into hot-swappable plugins. |
| **Financial Impact** | Supports localized tax returns (VAT filings per country regulations) and multi-currency reporting. |
| **Technical Impact** | Creates localization layers for: Currencies, Tax calculation engines, Bank/Government interfaces (e.g. WPS, e-invoicing). |

---

## Summary of Decisions

| ID | Decision | Recommendation / Status | Impact |
|----|----------|-------------------------|--------|
| **DM-01** | Costing Method | MWAC (No FIFO/Last Purchase fallback) | **APPROVED** |
| **DM-02** | MWAC Scope | Per Product, Per Warehouse | **APPROVED** |
| **DM-03** | Transfer Cost | Source warehouse MWAC at transfer | **APPROVED** |
| **DM-04** | Linked Return | Original SaleLine cost_price | **APPROVED** |
| **DM-05** | Unlinked Return | Current MWAC with manual override | **APPROVED** |
| **DM-06** | Landed Cost Alloc | Default: Allocate By Value | **APPROVED** |
| **DM-07** | Landed Cost Treat | Capitalize into inventory valuation | **APPROVED** |
| **DM-08** | Exchange Rate | Manager manual rate / Fallback online rate, locked on posting | **APPROVED** |
| **DM-09** | FX Differences | Post to standard P&L (FX Gain/Loss) | **APPROVED** |
| **DM-10** | Closed Periods | Block all edits, use adjustment entries | **APPROVED** |
| **DM-11** | Reconciliation | Read-only report, no auto-corrections | **APPROVED** |
| **DM-12** | Dynamic GL Mapping | Resolution via GL Concepts (Tenant-level) | **APPROVED** |
| **DM-13** | Precision Rules | Intermediates: 6 decimals; display: currency decimals | **APPROVED** |
| **DM-14** | Localization | Global Localization Framework (Option D) | **APPROVED** |
