# WAC Accounting Architecture Review

**Status:** Approved & Aligned (Incorporating Business Feedback & Target ERP Architecture)  
**Date:** June 4, 2026  
**Purpose:** Evaluate the Azad ERP inventory, costing, and general ledger architecture against mature, audited regional and global ERP standard principles (Bisan, Al-Shamel, SAP Business One, NetSuite, Odoo). Define the specifications for Moving Weighted Average Cost (MWAC) implementation and ledger integration.

---

## 1. Executive Summary & Reference Standards
Azad ERP is transitioning from a UAE-only product to a comprehensive multi-tenant financial system supporting:
- **Target Markets:** Palestine, Jordan, GCC countries (KSA, UAE, Qatar), and future international expansion.
- **Reference Architectures:** Bisan, Al-Shamel (for Palestine tax and currency localization compliance), SAP Business One, NetSuite, Odoo (for global standard ledger, dimensions, and posting rules engines).
- **Core Costing Rule:** **Moving Weighted Average Cost (MWAC)** calculated *per product, per warehouse*. Any use of Last Purchase Cost or FIFO layer consumption is deprecated.

---

## 2. Assessment of Current Legacy Costing Model

### 2.1 Legacy Costing Method: Last Purchase Cost (Overwritten)
In the legacy implementation:
- `Product.cost_price` is directly overwritten with the latest `PurchaseLine.unit_cost` on every purchase receipt.
- `SaleLine.cost_price` takes a point-in-time snapshot of the global `Product.cost_price`.
- Stock quantities are updated via `StockMovement`.
- The ledger (Inventory Account `1140`) records historical costs.

### 2.2 Critical Vulnerabilities of Legacy Costing
1. **Valuation Jumps:** Buying a product at 100 AED, and subsequently at 150 AED, immediately recalculates the value of all remaining on-hand stock to 150 AED. This creates artificial Balance Sheet volatility.
2. **COGS Distortion:** Sales made after a price increase reflect a higher COGS than was actually paid for the inventory sold, skewing gross margin reports.
3. **Drift and Repair Scripts:** The difference between `Stock * Latest Cost` and the actual General Ledger balance drifts continually, requiring reactive correction scripts (`accounting_repair.py`) that violate auditing standards by injecting correcting journals directly.

---

## 3. Target Costing Architecture: True MWAC Valuation

### 3.1 The MWAC Principle
The costing engine tracks **one running average cost per product, per warehouse**.
- **No FIFO valuation:** No queue layer processing or consumption.
- **Audit-Only History:** Cost history is logged for historical audit trails, never for calculation flow.
- **Recalculation Scope:** Recalculations are isolated to incoming movements (purchases, positive adjustments, incoming warehouse transfers). Outgoing movements (sales, write-offs, outbound transfers) consume inventory at the current MWAC and do not alter the unit average cost.

### 3.2 Conceptual Data Model: `ProductWarehouseCost`
To enable per-product, per-warehouse costing, the costing data is decoupled from the `Product` master table:

```python
class ProductWarehouseCost(db.Model):
    """
    Tracks the active Moving Weighted Average Cost and current stock
    for a product within a specific warehouse.
    """
    __tablename__ = 'product_warehouse_costs'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'product_id', 'warehouse_id',
                            name='uq_product_warehouse_cost_tenant_product_warehouse'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    quantity = db.Column(db.Numeric(15, 3), default=0, nullable=False)        # Physical stock on hand in this warehouse
    average_cost = db.Column(db.Numeric(15, 6), default=0, nullable=False)    # Running MWAC (stored at 6 decimals)
```

---

## 4. Operational Posting & Recalculation Flows

### 4.1 Purchase Receipt (Incoming)
1. **Landed Costs Allocation:** The system calculates the incoming cost by adding allocated freight, customs, clearance, and handling costs directly to the unit purchase price:
   ```
   incoming_unit_cost = unit_purchase_price + allocated_landed_cost
   ```
2. **Formula Execution:**
   ```
   new_average_cost = (old_quantity × old_average_cost + incoming_quantity × incoming_unit_cost) / (old_quantity + incoming_quantity)
   ```
3. **Ledger Posting:**
   - **Debit:** `INVENTORY_ASSET` (amount = `incoming_unit_cost * incoming_quantity`)
   - **Credit:** `AP` / `CASH`

### 4.2 Sale (Outgoing)
1. **Cost Snapshot:** Retrieve the current `average_cost` from `ProductWarehouseCost`.
2. **Document Record:** Store this value as `SaleLine.cost_price`.
3. **Quantity Reduction:** Deduct the sold quantity from `ProductWarehouseCost.quantity` (the average cost remains unchanged).
4. **Ledger Posting:**
   - **Debit:** `AR` / `CASH` (at sales price)
   - **Credit:** `SALES_REVENUE`
   - **Debit:** `COGS` (at snapshot cost)
   - **Credit:** `INVENTORY_ASSET` (at snapshot cost)

### 4.3 Sales Returns (Customer Returns)
- **Linked Return:** The system retrieves the original `SaleLine.cost_price` and uses it as the incoming unit cost in the MWAC formula, reversing the COGS entry exactly.
- **Unlinked Return:** The system uses the warehouse's current MWAC as the incoming unit cost, allowing authorized managers to manually override the value (recorded with a justification and audit log).

### 4.4 Inter-Warehouse Transfers
1. **Outflow (Source Warehouse):** Deduct quantity from the source warehouse. The movement is valued at the source warehouse's current MWAC.
2. **Inflow (Destination Warehouse):** Recalculate the destination warehouse's MWAC using the source MWAC as the incoming unit cost.
3. **Ledger Posting:**
   - **Debit:** `INVENTORY_ASSET` — Destination Warehouse (at source MWAC value)
   - **Credit:** `INVENTORY_ASSET` — Source Warehouse (at source MWAC value)
   - *Result:* Neutral consolidated value change. Zero phantom profit or loss.

---

## 5. Account Structure: Accounts vs. Dimensions
To prevent chart of accounts bloat (tree explosion) and mirror SAP B1 / NetSuite best practices, the system separates **what** the transaction is from **where/why** it happened.

### 5.1 The Dimension Principle
- **Accounts** answer: *"What type of transaction is this?"* (e.g. `SALES_REVENUE`, `INVENTORY_ASSET`).
- **Dimensions** answer: *"Where, why, and for whom did it happen?"* (e.g. branch, warehouse, cost center).
- **Tree Explosion Violation:** Mappings must NOT define accounts per branch or location.
  - *Incorrect Account Tree:* `1141-Ramallah-Inventory`, `1142-Nablus-Inventory`, `4111-Ramallah-Sales`.
  - *Correct Dimensions Approach:* A single `INVENTORY_ASSET` (Code `1140`) account and a single `SALES_REVENUE` (Code `5100`) account, with lines tagged with `branch_id = Ramallah` or `branch_id = Nablus`.

### 5.2 Mandatory Financial Dimensions
The system enforces validation of the following dimensions on all postings:
- `tenant_id`: Mandatory row-level isolation key.
- `branch_id`: Represents profit attribution and operational branch identity.
- `warehouse_id`: Identifies the stock tracking dimension.
- `cost_center_id`: Identifies departmental cost attribution.
- `profit_center_id`: Identifies revenue-producing divisions.
- `partner_id`: Links entries to specific customer or vendor sub-ledgers.
- `currency`: Identifies transaction currency.
- `payment_channel`: Identifies cash box, bank account, or gateway.

---

## 6. Ledger Posting Rules Engine & Dynamic Mapping

### 6.1 Concept-Based GL Resolution
Business logic never references hardcoded account numbers. It interacts with standard **GL Concepts** which each tenant maps to their own Chart of Accounts (COA):

```
+--------------------+       +----------------------+       +-----------------------+
|  Business Logic    |       |  Dynamic Mapping     |       |   Tenant Chart        |
|  (e.g., Post Sale) |  ==>  |  (GLAccountMapping)  |  ==>  |   (e.g., Code '1205') |
|  Request: "CASH"   |       |  Tenant: 1, PMA COA  |       |   Name: Ramallah cash |
+--------------------+       +----------------------+       +-----------------------+
```

### 6.2 Target Posting Rules
The system translates operational events to balanced journal lines:
1. **Cash Sale:**
   - Debit: `CASH` (Full invoice total)
   - Credit: `SALES_REVENUE` (Net of tax)
   - Credit: `VAT_OUTPUT` (Tax amount)
   - Debit: `COGS` (MWAC amount)
   - Credit: `INVENTORY_ASSET` (MWAC amount)
2. **Credit Purchase:**
   - Debit: `INVENTORY_ASSET` (Cost + Capitalized Landed Cost)
   - Debit: `VAT_INPUT` (Recoverable VAT)
   - Credit: `AP` (Total vendor payable)
3. **Incoming Cheque:**
   - Debit: `CHEQUES_UNDER_COLLECTION`
   - Credit: `AR`

---

## 7. Operational Management Features

### 7.1 Tenant Isolation & Data Security
Each tenant is completely isolated. No user from Tenant A can view, modify, or join data with Tenant B's ledger, journals, mappings, or dimensions. Platform admin configurations are logically split from the tenant-specific sub-ledgers.

### 7.2 Branch & Warehouse Models
- **Branch:** Holds its own branch identity, users, permissions, cash boxes, bank accounts, and cost/profit center attributes.
- **Warehouse:** Operational dimension. If required, the system allows **enterprise override mappings** to post specific warehouse assets to independent GL accounts, while default setups share the standard `INVENTORY_ASSET` account.

### 7.3 Cost Centers & Profit Centers
- **Branch = Profit Center:** Revenue and COGS are grouped by `branch_id` to evaluate regional performance.
- **Project/Fleet = Cost Center:** Overhead and operating expenses are tagged with `cost_center_id` to trace project expenditure against budget limits.

### 7.4 Treasury and Cash Management
- **Multiple Cash Boxes:** Cash registers tracked independently per branch.
- **Multiple Bank Accounts:** Assigned to branches but managed centrally.
- **Employee Advances:** Tracked in dedicated employee sub-ledger accounts, cleared upon payroll run.
- **Cash Positioning:** Real-time cash positioning reports aggregate cash box balances, bank accounts, and cheques under collection.

---

## 8. Financial Precision and Localizations

### 8.1 Precision Analysis (DM-13)
To align with regional standard practices (Bisan/Al-Shamel) and prevent currency conversion anomalies:
- **1. Recommended Internal Precision:** **6 Decimals** (`Decimal('0.000001')`). All intermediate average calculations, landed cost splits, and average updates are processed at 6-decimal precision.
- **2. Quantity Precision:** **3 Decimals** (`Decimal('0.001')`). Standard for weights and fractional items.
- **3. Unit Cost Precision:** **4 Decimals** (`Decimal('0.0001')`) for purchase and sale document unit costs.
- **4. Exchange Rate Precision:** **6 Decimals** (`Decimal('0.000001')`) for currency exchange rate definitions.
- **5. Inventory Valuation Precision:** **MWAC stored precision = 6 decimals**, **Inventory valuation calculations = 6 decimals internally**, and **Final journal amounts = currency-specific decimals**
- **6. Journal Entry Precision:** **Base Currency Decimals** (Typically 2 decimals for AED, SAR; 3 decimals for JOD, KWD) utilizing banker's rounding (`ROUND_HALF_EVEN`) to guarantee ledger balance integrity.
- **7. Currency-Specific Display Precision:** **Localized Decimal Formats** (e.g., 2 decimals for AED/SAR/ILS/USD/EUR; 3 decimals for JOD/KWD/BHD/OMR).

#### A. MWAC Calculation Example
* **Initial State:** 1,000 units on hand at an average cost of JOD `1.450375` (Total Value = JOD `1,450.375000`).
* **Incoming Receipt:** 15 units at JOD `1.485200` per unit (Receipt Value = JOD `22.278000`).
* **Formula Execution (6 Decimals Internal):**
  ```
  New MWAC = (1,450.375000 + 22.278000) / (1,000 + 15) = 1,472.653000 / 1,015 = 1.450889655...
  ```
* **Resolved Database Average Cost:** JOD `1.450890` (Rounded to 6 decimals).
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
  * *If rounded to 3 decimals (3.673):* Amount = `367,300.00` AED (Differs by **+48.00 AED**).
  * *If rounded to 4 decimals (3.6725):* Amount = `367,250.00` AED (Differs by **-2.00 AED**).
  * *At 6 decimals (3.672520):* Amount = `367,252.00` AED (Perfect conversion match).

#### C. Inventory Valuation Aggregate
* **Scenario:** A product in Warehouse A has a quantity of `10,000` units with a MWAC of `1.125642` AED.
* **Valuation Calculation:**
  ```
  Asset Value = 10,000 * 1.125642 = 11,256.42 AED
  ```
  * *Using 3-decimal cost (1.126):* Asset Value = `11,260.00` AED (Valuation drift = **+3.58 AED**).
  * *Using 4-decimal cost (1.1256):* Asset Value = `11,256.00` AED (Valuation drift = **-0.42 AED**).
  * *Using 6-decimal cost (1.125642):* Asset Value = `11,256.42` AED (Perfect match to GL balance).

#### D. Comparative Evaluation
- **Why preferred over 3 decimals everywhere:** Standardizing database fields to 3 decimals creates severe rounding drift in high-volume inventory cost updates and landed cost divisions.
- **Why preferred over 4 decimals everywhere:** 4 decimals is a standard ERP pricing default, but inadequate for foreign exchange rates where minor rate differences on multi-million dollar invoices result in massive ledger differences.
- **Why preferred over 6 decimals everywhere:** Eliminates drift but floods ledger reports, invoices, tax calculations, and cash books with non-payable fractional decimals, harming readability.

### 8.2 Localization Architecture (DM-14)
The system adopts a **Global Localization Framework**:
- Swappable country plugins calculate tax (UAE 5%, Palestine 16%, KSA 15% ZATCA).
- Support for WPS (Wage Protection System) formatting in GCC countries.
- Custom e-invoicing export files compliant with country-specific tax authorities.
