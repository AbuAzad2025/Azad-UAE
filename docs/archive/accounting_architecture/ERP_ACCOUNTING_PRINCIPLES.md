# ERP Accounting Principles: Azad ERP

**Status:** Approved & Finalized (Incorporating Owner Feedback & Target ERP Architecture)  
**Date:** June 4, 2026  
**Purpose:** Define the mandatory accounting framework, principles, and strategic localization roadmap for Azad ERP as it expands from a UAE-focused system to Palestine, GCC countries, Arabic markets, and future international expansion.

---

## Strategic Vision & ERP Reference Framework
Azad ERP is designed as a multi-tenant, multi-country enterprise resource planning platform. Its accounting and financial architecture is modeled after the discipline, auditability, and financial correctness of leading international and regional ERP platforms, including:
- **Regional Standard Bearers:** Bisan, Al-Shamel (widely used in Palestine and Levant markets).
- **Global Mid-Market & Enterprise ERPs:** SAP Business One, Oracle NetSuite, Odoo, Microsoft Dynamics.
- **Modern Cloud Accounting Platforms:** Xero.

The goal is to adopt proven, standard accounting principles and modern, dimensions-based ERP architecture, completely eliminating custom/ad-hoc accounting methodologies and hardcoded account codes.

---

## Principle 1: Perpetual Inventory System
The system operates on a **Perpetual (Continuous) Inventory System**.
Every confirmed transaction that affects inventory quantity or value must simultaneously:
1. Update the physical stock record (quantity on hand).
2. Post the correct double-entry journal entry to the General Ledger.
3. Update the inventory valuation (Moving Weighted Average Cost).

There is no periodic physical-count adjustment that replaces the system balance. Physical counts are used only to generate variance reports and adjustment entries.

---

## Principle 2: Moving Weighted Average Cost (MWAC) — Not FIFO
### 2.1 The Authoritative Costing Method
The sole inventory costing method is **Moving Weighted Average Cost (MWAC)**.
- **NO FIFO valuation** is used as a primary or fallback valuation method.
- **NO hidden FIFO consumption logic** is permitted in the valuation engine.
- **NO FIFO layer accounting** or queue-based layer matching is performed.
- **Cost History is Audit-Only:** The system may log cost history records (timestamp, quantity before/after, unit cost, new average) for tracing and audit purposes. These are read-only logs and are NEVER used to consume or calculate inventory values.

### 2.2 Formula
On every incoming movement (purchase, positive adjustment, transfer-in):
```
New Average Cost = (Old Quantity × Old Average Cost + Incoming Quantity × Incoming Unit Cost) / (Old Quantity + Incoming Quantity)
```
At sale time (COGS calculation):
```
COGS = Quantity Sold × Current Moving Average Cost (at the exact moment of sale)
```

---

## Principle 3: Warehouse-Level Costing
### 3.1 Scope of MWAC
MWAC is calculated **Per Product, Per Warehouse** (Approved Decision DM-02).
- Inventory costs are tracked independently for each warehouse to reflect localized procurement pricing and landed cost variances.
- Global product cost averages are derived only for reporting purposes and are not used in posting logic.

### 3.2 Inter-Warehouse Transfer Costing (Approved Decision DM-03)
Transfers between warehouses must use the **source warehouse's MWAC at the exact transfer time**.
```
Transfer Out (Source Warehouse):
    Dr Inventory Asset — Destination Warehouse
    Cr Inventory Asset — Source Warehouse
    (Valued at Source Warehouse MWAC)
```
The destination warehouse's average cost is recalculated upon receipt using the standard MWAC formula. Recalculation is triggered at the receipt confirmation timestamp.

---

## Principle 4: Returns Valuation Rules
### 4.1 Linked Sales Return Cost (Approved Decision DM-04)
When a sales return is linked to the original sale invoice:
- The returned goods are reinstated in the warehouse inventory.
- The inventory valuation increase and COGS reversal must use the **original `SaleLine.cost_price`** to preserve historical margin integrity and avoid phantom variance.

### 4.2 Unlinked Sales Return Cost (Approved Decision DM-05)
When a return is unlinked (standalone return):
- The system defaults to the **current MWAC of the product in the receiving warehouse at the return date**.
- An optional manual override is permitted for authorized managers (e.g., in case of damaged goods returned at scrap value).
- All unlinked returns must write a permanent audit trail entry detailing the user, reason, and any cost override.

---

## Principle 5: Landed Cost Capitalization & Allocation
### 5.1 Capitalization Requirement (Approved Decision DM-07)
All landed costs incurred to bring inventory to its usable location and condition must be **capitalized directly into the inventory valuation (asset value)**, rather than expensed as period costs. This includes:
- Freight & Shipping Charges
- Customs Duties & Clearance Fees (non-recoverable taxes)
- Transit Insurance
- Handling Charges
- Clearance & Handling Fees

### 5.2 Allocation Method (Approved Decision DM-06)
- **Default Method:** Allocate **By Value** (proportional to line item amount).
- **Future Extension:** The allocation engine must support future expansion to allocate by Quantity, Weight, Volume, or Manual Percentage overrides.

---

## Principle 6: Multi-Currency & Exchange Rate Strategy
All accounting and costing records are permanently recorded in the tenant's **Base Currency** (e.g., AED in the UAE, JOD/ILS in Palestine, SAR in Saudi Arabia).

### 6.1 Exchange Rate Rules (Approved Decision DM-08 & DM-09)
1. **Primary Rate Source:** The manual exchange rate entered by an authorized manager on the document takes precedence.
2. **Permanent Historical Record:** Once a transaction is posted, its exchange rate becomes part of the permanent accounting record. The rate used by a posted transaction must never be recalculated or altered automatically.
3. **Fallback Rate Source:** If no manual rate is provided at document creation, the system retrieves an online rate from an approved provider (e.g., Central Bank APIs or commercial rate feeds) at the moment of document creation. This rate is stored permanently on the document.
4. **Historical Immutability:** Future exchange rate updates or rate adjustments must never alter historical transactions.
5. **Multi-Provider Support:** The core multi-currency module must support multiple exchange rate providers and country-specific sources (e.g., PMA for Palestine, CBUAE for UAE, SAMA for Saudi Arabia).
6. **FX Differences Treatment:** All differences arising between the invoice rate and the payment rate are recognized immediately as **FX Gain** or **FX Loss** through standard P&L accounts (not capitalized into inventory).

---

## Principle 7: Closed Period Protection (Approved Decision DM-10)
To enforce strict audit compliance and prevent retroactive financial manipulation:
- **Block All Modifications:** All postings, corrections, deletion attempts, or cost recalculations in a closed period are strictly blocked.
- **No Historical Recalculation:** The system will never silently recalculate past averages or rewrite posted GL entries.
- **Correction Workflow:** All corrections must be posted in an open period using:
  1. Reversal Entries (credit notes / debit notes).
  2. Adjustment Entries.
  3. All entries maintain a full audit trail linking back to the original document.

---

## Principle 8: Reconciliation Behavior (Approved Decision DM-11)
Reconciliation is strictly a **Reporting, Monitoring, and Validation control tool**.
- The reconciliation engine compares physical stock quantities, MWAC system valuations, and GL Inventory Account balances.
- **No Auto-Posting / Auto-Correction:** Under no circumstances should the reconciliation process auto-post correcting entries or auto-change accounting records. It is a read-only reporting tool for review by the authorized accountant, who must manually post adjustments.

---

## Principle 9: Dynamic GL Account Mapping (Approved Decision DM-12)
All posting logic is decoupled from hardcoded account codes.
- **Phase 1 (Per Tenant):** Mappings are configured globally per tenant.
- **Future Phase:** Mappings can be overridden at the Branch level.
- Posting logic references **GL Concepts** rather than account code strings.

---

## Principle 10: Precision Rules (DM-13 Analysis & Recommendation)
To ensure compliance with mature ERP practices, the precision architecture is defined via a **hybrid precision framework**:

### 10.1 Recommended Precision Parameters
1. **Internal Precision:** **6 Decimals** (`Decimal('0.000001')`). All mathematical processes, intermediate calculations, landed cost splits, and average updates are processed at 6-decimal precision to prevent penny drift.
2. **Quantity Precision:** **3 Decimals** (`Decimal('0.001')`). Standard for weights, dimensions, and fractional items (e.g., `10.500` kg or `1.000` unit).
3. **Unit Cost Precision:** **4 Decimals** (`Decimal('0.0001')`) for purchase and sale document unit costs.
4. **Exchange Rate Precision:** **6 Decimals** (`Decimal('0.000001')`) for currency exchange rate definitions.
5. **Inventory Valuation Precision:** **MWAC stored precision = 6 decimals**, **Inventory valuation calculations = 6 decimals internally**, and **Final journal amounts = currency-specific decimals**
6. **Journal Entry Precision:** **Base Currency Decimals** (Typically 2 decimals for AED, SAR; 3 decimals for JOD, KWD) utilizing banker's rounding (`ROUND_HALF_EVEN`) to guarantee ledger balance integrity (debits = credits).
7. **Currency-Specific Display Precision:** **Localized Decimal Formats** (e.g., 2 decimals for AED/SAR/ILS/USD/EUR; 3 decimals for JOD/KWD/BHD/OMR).

### 10.2 Comparative Rationale & Evaluation
- **Why preferred over 3 decimals everywhere:** Standardizing database fields to 3 decimals creates severe rounding drift in high-volume inventory cost updates and landed cost divisions.
- **Why preferred over 4 decimals everywhere:** 4 decimals is a standard ERP pricing default, but inadequate for foreign exchange rates where minor rate differences on multi-million dollar invoices result in massive ledger differences.
- **Why preferred over 6 decimals everywhere:** Eliminates drift but floods ledger reports, invoices, tax calculations, and cash books with non-payable fractional decimals, harming readability.

### 10.3 Precision Rule Practical Examples

#### A. MWAC Calculation Example
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

#### B. FX Conversion Example
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

#### C. Inventory Valuation Aggregate
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

## Principle 11: Multi-Country Localization Strategy (DM-14 Analysis & Recommendation)
To support international expansion, four localization approaches were evaluated:
- **A. UAE-centric architecture:** Highly restrictive, binds tax to 5% VAT and currency to AED.
- **B. GCC-centric architecture:** Accommodates KSA, UAE, Qatar (5%-15% VAT, similar currencies), but lacks flexibility for Palestine/Levant.
- **C. Arabic multi-country architecture:** Supports regional variations but struggles with future European or global expansion.
- **D. Global Localization Framework (Recommended):** Extensible core that abstracts tax engines, currency regulations, and localization layers.

### 11.1 Localization Recommendation
The system will implement a **Global Localization Framework** structured to support:
1. **Multiple Currencies:** Native support for local currency and transaction currency with daily exchange rate feeds per country.
2. **Multiple Tax Systems:** Abstract tax calculations (e.g., UAE VAT at 5%, Palestine VAT at 16%, KSA VAT at 15%) into a country-specific tax rules engine.
3. **Country-Specific Compliance:** Support WPS (Wage Protection System) in UAE/GCC, e-invoicing compliance (ZATCA in Saudi Arabia), and local regulatory reporting (Palestine Ministry of Finance audits).

---

## Principle 12: Target ERP Accounting Architecture
To support mature financial controls, the following principles are mandatory:

### 12.1 Account Structure Principle: Accounts vs. Dimensions
- **Accounts** represent the financial nature of a transaction (e.g., *What type of money is this?*).
- **Dimensions** represent the business context (e.g., *Where, why, and for whom did it happen?*).
- **Tree Explosion Prevention:** We must NOT duplicate accounts for operational divisions. 
  - *Incorrect:* Account codes for `Sales_Ramallah`, `Sales_Nablus`, `Inventory_Hebron`.
  - *Correct:* A single account `SALES_REVENUE` with a `branch_id` dimension (e.g., `branch_id = Ramallah`).

### 12.2 Financial Dimensions Registry
The system must support the following dimensions across all transactions:
- `tenant_id`: Strict isolation.
- `branch_id`: Branch-level identity and reporting.
- `warehouse_id`: Operational storage location.
- `cost_center_id`: Expense tracking (e.g., Department, Project).
- `profit_center_id`: Revenue and margin tracking (e.g., Product Line, Branch).
- `partner_id`: Customer or vendor association.
- `currency`: Transaction currency.
- `payment_channel`: Cash box, bank account, payment gateway.

### 12.3 Tenant Isolation
Each tenant has a completely isolated database schema or row-level logical separation. Under no circumstances can a tenant view, access, or modify another tenant's charts of accounts, mappings, ledger balances, or transactions. Platform settings remain strictly separated from tenant accounting structures.

### 12.4 Branch Model
A branch is an operational dimension, not a separate chart of accounts. A branch is defined by:
- Branch Identity and permissions.
- Specific Cash Locations and assigned Bank Accounts.
- Linked Warehouses.
- Cost/Profit attribution.
All branch transactions flow to the central chart of accounts but are tagged with the `branch_id` dimension.

### 12.5 Warehouse Model
A warehouse is primarily an operational stock-tracking dimension.
- By default, warehouses do not require independent inventory accounts.
- **Enterprise Override Capability:** To support advanced enterprises, the system must allow a warehouse-specific inventory account override in the dynamic GL mapping registry (e.g., mapping `INVENTORY_ASSET` to a specific GL account for Warehouse A).

### 12.6 Cost Centers & Profit Centers
- **Cost Centers:** Used to capture costs for specific internal departments, projects, or fleets (e.g., `cost_center_id = HR_Department`).
- **Profit Centers:** Used to measure performance and profitability of business units (e.g., `profit_center_id = Ramallah_Retail_Store`).
Ledger entries must support posting lines with both `cost_center_id` and `profit_center_id` to generate departmental P&Ls and project budgets.

### 12.7 Treasury & Cash Management
The roadmap must support:
- **Multiple Cash Boxes:** Tracked per branch with cashiers as sub-dimensions.
- **Multiple Bank Accounts:** Configured per tenant, assigned to branches.
- **Employee Advances:** Tracked as temporary receivables under employee sub-ledgers.
- **Internal Transfers:** Structured double-entry controls for cash-to-bank and cash-box-to-cash-box transfers.
- **Treasury Controls & Cash Positioning:** Real-time cash positioning reports showing cash-in-transit, cheques under collection, and bank balances.

---

## Principle 13: Core GL Concept Mapping Registry
Tenants map their charts of accounts to standard GL Concepts:
1. `AR`: Accounts Receivable
2. `AP`: Accounts Payable
3. `CASH`: Cash On Hand
4. `BANK`: Cash in Bank
5. `INVENTORY_ASSET`: Inventory asset valuation
6. `SALES_REVENUE`: Revenue from sales
7. `SALES_DISCOUNT`: Customer discount expenses
8. `PURCHASE_DISCOUNT`: Vendor discounts earned
9. `COGS`: Cost of goods sold
10. `VAT_INPUT`: Paid VAT on purchases
11. `VAT_OUTPUT`: Collected VAT on sales
12. `FX_GAIN`: Foreign exchange gains
13. `FX_LOSS`: Foreign exchange losses
14. `CHEQUES_UNDER_COLLECTION`: Received post-dated cheques
15. `INVENTORY_ADJUSTMENT_GAIN`: Value increase from count discrepancies
16. `INVENTORY_ADJUSTMENT_LOSS`: Value write-offs from count discrepancies
17. `FREIGHT_IN`: Capitalized shipping costs
18. `CUSTOMS_DUTY`: Capitalized customs fees

---

## Principle 14: Posting Rules Engine
Business logic will delegate journal entry creation to a Posting Rules Engine. The engine executes templates based on transaction types:

### 14.1 Cash Sale
- **Debit:** `CASH` (at full sale amount + VAT)
- **Credit:** `SALES_REVENUE` (at sale amount net of VAT)
- **Credit:** `VAT_OUTPUT` (at VAT amount)
- **Debit:** `COGS` (at MWAC value)
- **Credit:** `INVENTORY_ASSET` (at MWAC value)

### 14.2 Credit Sale
- **Debit:** `AR` (at invoice total)
- **Credit:** `SALES_REVENUE` (at invoice net)
- **Credit:** `VAT_OUTPUT` (at VAT amount)
- **Debit:** `COGS` (at MWAC value)
- **Credit:** `INVENTORY_ASSET` (at MWAC value)

### 14.3 Inventory Purchase (Credit)
- **Debit:** `INVENTORY_ASSET` (at purchase net cost + capitalized landed cost)
- **Debit:** `VAT_INPUT` (at recoverable VAT amount)
- **Credit:** `AP` (at invoice total)

### 14.4 Incoming Cheque
- **Debit:** `CHEQUES_UNDER_COLLECTION` (at cheque face value)
- **Credit:** `AR` (at customer balance reduction)
