# ERP Accounting Principles: Azad-UAE

**Status:** Draft — awaiting owner approval on all decisions  
**Date:** June 4, 2026  
**Purpose:** Define the mandatory accounting framework that all future cost, inventory, GL, and reconciliation designs must follow.

---

## Principle 1: Perpetual Inventory System

The system operates on a **Perpetual (Continuous) Inventory System**.

Every confirmed transaction that affects inventory quantity or value must simultaneously:
1. Update the physical stock record (quantity on hand).
2. Post the correct double-entry journal entry to the General Ledger.
3. Update the inventory valuation (Moving Weighted Average Cost).

There is no periodic physical-count adjustment that replaces the system balance. Physical counts are used only to generate variance reports and adjustment entries.

**Supported by:** Bisan, Al-Shamel, Odoo, SAP B1, NetSuite.

---

## Principle 2: Moving Weighted Average Cost (MWAC) — Not FIFO

### 2.1 Accepted Method
The sole inventory costing method is **Moving Weighted Average Cost**.

This is the dominant costing method in UAE accounting practice, GCC ERP implementations (Bisan, Al-Shamel), and is natively supported by SAP Business One and Oracle NetSuite.

### 2.2 Formula

**On every incoming movement (purchase, adjustment increase, transfer-in):**

```
New Average Cost =
    (Old Quantity × Old Average Cost + Incoming Quantity × Incoming Unit Cost)
    / (Old Quantity + Incoming Quantity)
```

**At sale time (COGS):**

```
COGS = Quantity Sold × Current Moving Average Cost (at moment of sale)
```

### 2.3 What MWAC Is NOT

MWAC is **not** a layer consumption system. The system maintains **one average cost per product** (or per product+warehouse), not a stack of purchase layers.

| Behavior | FIFO Layer System | Moving Weighted Average |
|----------|-------------------|------------------------|
| Cost tracked as | Stack of layers | Single running average |
| Sale consumes | Oldest layer | Current average |
| Complexity | High (layer tracking) | Low (single value update) |
| UAE ERP standard | Rare | Dominant |

### 2.4 Cost History for Audit

If regulatory audit or internal control requires a traceable history of how the average cost changed, the system may log **cost history records** (timestamp, quantity before, quantity added, unit cost, new average). These are **read-only audit records**, not layers used for consumption.

---

## Principle 3: Warehouse-Level Costing Decision

### 3.1 The Decision

Before implementing MWAC, the owner must approve one of the following:

| Option | Scope | Pros | Cons |
|--------|-------|------|------|
| A | **Global per product (tenant-wide)** | Simplest; one cost per product | Cannot reflect different procurement prices in different warehouses |
| B | **Per product per warehouse** | Accurate for multi-warehouse businesses; reflects local procurement | Transfers between warehouses create cost variance that must be absorbed or tracked |
| C | **Per product per branch** | Aligns with branch P&L reporting | More complex; branch may have multiple warehouses |

### 3.2 Recommended: Option B (Per Product Per Warehouse)

Rationale:
- UAE businesses frequently operate multiple warehouses with independent suppliers and procurement channels.
- Transfers between warehouses are business reality; Option B handles them naturally (transfer out at source cost, transfer in at destination cost).
- Branch-level costing (Option C) can be derived by aggregating warehouse costs if needed.

**Requires owner approval:** Yes.

### 3.3 Inter-Warehouse Transfer Costing

If Option B is approved, the transfer posting must be:

```
Transfer Out (Source Warehouse):
    Dr Inventory Asset — Destination Warehouse
    Cr Inventory Asset — Source Warehouse
    (at source warehouse's current average cost)
```

The destination warehouse's average cost is recalculated upon receipt using the MWAC formula with the transferred quantity and cost.

---

## Principle 4: GL Integration — Double-Entry for Every Movement

### 4.1 Purchase (Goods Receipt)

```
Dr Inventory Asset            (at unit cost × qty)
    Cr Accounts Payable / Cash

Dr VAT Input (if applicable)
    Cr AP / Cash

Dr Freight-In / Customs / Landed Costs (if applicable and capitalized)
    Cr AP / Cash / Accrued Expenses
```

The inventory asset debit uses the **purchase unit cost including landed costs** that are capitalized into inventory.

### 4.2 Sale

```
Dr Accounts Receivable / Cash    (sale total)
    Cr Sales Revenue

Dr VAT Output (if applicable)
    Cr AR / Cash

Dr Cost of Goods Sold
    Cr Inventory Asset           (at MWAC × qty sold)
```

### 4.3 Sales Return (linked to original sale)

```
Dr Sales Revenue Reversal / Sales Returns
    Cr Accounts Receivable / Cash

Dr Inventory Asset              (at original SaleLine.cost_price)
    Cr Cost of Goods Sold Reversal
```

**Important:** If the original `SaleLine.cost_price` is available (linked return), use it. If not linked, a policy decision is required (see Principle 6).

### 4.4 Purchase Return (linked to original purchase)

```
Dr Accounts Payable / Cash      (at original purchase unit cost × qty)
    Cr Inventory Asset

Dr Inventory Asset Variance (if return cost differs from current MWAC)
    Cr Inventory Adjustment Loss
```

### 4.5 Inventory Adjustment — Increase

```
Dr Inventory Asset              (at current MWAC × qty)
    Cr Inventory Adjustment Gain Account
```

### 4.6 Inventory Adjustment — Decrease

```
Dr Inventory Adjustment Loss Account
    Cr Inventory Asset          (at current MWAC × qty)
```

### 4.7 Damaged / Obsolete Write-Off

```
Dr Inventory Write-Off / Loss Account
    Cr Inventory Asset          (at current MWAC × qty)
```

---

## Principle 5: Returns — Use Original Cost When Linked

### 5.1 Sales Returns

When a sales return is **linked to the original sale invoice** (via `sale_id` or `sale_line_id`):

- The returned goods are added back to inventory.
- The inventory value increase should use the **original `SaleLine.cost_price`**.
- The COGS reversal should match the original COGS amount.

**Why:** This preserves the accuracy of the original period's margin and avoids inflating current inventory value with today's (possibly different) average cost.

If the return is **not linked** to an original sale (standalone/manual return), a policy decision is required:

| Option | Method | Impact |
|--------|--------|--------|
| A | Use current MWAC at return date | Simple; may create valuation variance |
| B | Use historical average cost from a reference period | More accurate; requires lookup logic |
| C | Manual cost entry per return | Most flexible; requires user training |

**Recommended:** Option A for unlinked returns (use current MWAC), with a manual override field.

**Requires owner approval:** Yes.

### 5.2 Purchase Returns

When a purchase return is **linked to the original purchase**:

- Deduct from inventory at the **original purchase unit cost**.
- Reverse AP at the same amount.

If the original purchase cost differs from the current MWAC, the difference flows to an **Inventory Cost Variance** account:

```
If original cost > current MWAC:
    Dr Inventory Cost Variance (Loss)
If original cost < current MWAC:
    Cr Inventory Cost Variance (Gain)
```

---

## Principle 6: Landed Costs

### 6.1 Definition

Landed costs are costs incurred to bring inventory to its usable condition and location. They must be **capitalized into inventory value** when applicable under UAE accounting standards.

Examples:
- Freight / shipping
- Customs duties and taxes (non-recoverable)
- Insurance in transit
- Clearance and handling fees
- Inspection and quality control costs
- Other acquisition costs directly attributable

### 6.2 What Is NOT Landed Cost

The following are **period expenses**, not inventory costs:
- Recoverable VAT (separate asset)
- Sales commissions
- Marketing costs
- Administrative overheads
- Post-receipt storage (unless required for production)

### 6.3 Allocation Methods

When a single landed cost invoice covers multiple products, it must be allocated:

| Method | Use When | Example |
|--------|----------|---------|
| By Quantity | Products are similar in nature | 100 chairs + 50 tables; freight allocated by unit count |
| By Value | Products differ significantly in price | $10k electronics + $1k accessories |
| By Weight | Heavy goods, freight by weight | Steel + aluminum shipment |
| By Volume | Bulky goods, freight by CBM | Furniture + cushions |
| Manual | Complex mixed shipments | Owner assigns percentages |

**Recommended:** Default to "By Value" (most common in ERP systems); allow override per purchase.

**Requires owner approval:** Yes.

### 6.4 Landed Cost GL Posting

When landed costs are capitalized:

```
Dr Inventory Asset              (allocated to each product line)
    Cr Freight-In Payable / Cash / AP
```

The allocated amount increases the product's MWAC calculation.

If landed costs are expensed (not capitalized — rare, requires policy approval):

```
Dr Freight Expense
    Cr AP / Cash
```

---

## Principle 7: Multi-Currency

### 7.1 Inventory Costing Base Currency

All inventory costing and GL inventory postings are recorded in the **tenant's base currency (AED)**.

For foreign-currency purchases:
1. Record the original currency amount on the purchase document.
2. Convert to AED using the **approved exchange rate on the transaction date**.
3. Use the AED amount for MWAC calculation and GL posting.

### 7.2 Exchange Rate Source

| Source | Pros | Cons |
|--------|------|------|
| Central Bank of UAE (CBUAE) official rate | Authoritative; audit-friendly | Fixed daily; may not match bank rate |
| Bank transaction rate | Matches actual cash flow | Varies by bank; requires per-transaction entry |
| Tenant-defined rate | Flexibility | Requires manual maintenance; audit risk |

**Recommended:** Use CBUAE official rate as default; allow manual override per transaction with justification note.

**Requires owner approval:** Yes.

### 7.3 FX Differences

If payment is made at a different rate from the purchase-date rate:

```
At purchase:
    Dr Inventory Asset (at purchase-date rate)
        Cr AP (at purchase-date rate)

At payment (if rate changed):
    Dr AP (original AED amount)
    Dr/Cr FX Gain/Loss (difference)
        Cr Bank (at payment-date rate)
```

FX gains/losses are **not** part of inventory cost. They are period P&L items.

---

## Principle 8: Closed Periods

### 8.1 Immutable Historical Data

Once an accounting period is closed (month/quarter/year):
- **No recalculation** of historical MWAC.
- **No restatement** of historical journal entries.
- **No deletion** of posted transactions in closed periods.
- **No modification** of `SaleLine.cost_price` for closed-period sales.

### 8.2 Correction Entries

Any error discovered in a closed period must be corrected via an **adjustment entry in an open period**:

```
Dr/Cr Correcting Account
    Cr/Dr Adjustment Account
```

With a clear reference to the original period and document.

### 8.3 Period Lock Implementation

- `GLPeriod` model already exists (`gl_periods` table with `is_closed` flag).
- All inventory-posting services must check `assert_period_open()` before posting.
- The MWAC calculation should also be blocked from retroactive changes to closed periods.

---

## Principle 9: Reconciliation as Reporting, Not Auto-Correction

### 9.1 Purpose

Reconciliation compares:
1. Physical stock quantities (from stock movements or cycle counts).
2. System inventory valuation (`current_stock × MWAC`).
3. GL inventory account balance (from `GLJournalLine` on inventory asset account).
4. COGS postings for the period.
5. Stock movement audit trail.

### 9.2 What Reconciliation Must NOT Do

- Auto-post correcting journal entries.
- Auto-adjust MWAC.
- Auto-modify stock quantities.
- Override closed-period data.

### 9.3 Reconciliation Report Output

The reconciliation engine produces a **read-only report** with:
- Product-by-product quantity variance (physical vs system).
- Product-by-product value variance (system valuation vs GL balance).
- Period COGS summary.
- Unexplained movement flags.
- Recommended action (manual adjustment entry).

The **accountant** decides whether to create an adjustment.

---

## Principle 10: Dynamic GL Account Mapping

### 10.1 No Hardcoded Account Codes

All GL account references in posting logic must use a **configurable concept mapping**, not hardcoded 4-digit strings.

**Forbidden:**
```python
GLAccount.query.filter_by(code='1130').first()  # AR
GLAccount.query.filter_by(code='1140').first()  # Inventory
GLAccount.query.filter_by(code='5100').first()  # Revenue
```

**Required:**
```python
GLAccountMapping.get_account(tenant_id, GLConcept.AR)
GLAccountMapping.get_account(tenant_id, GLConcept.INVENTORY_ASSET)
GLAccountMapping.get_account(tenant_id, GLConcept.SALES_REVENUE)
```

### 10.2 Concept Registry

Standard concepts the system must support:

| Concept | Typical Account Type | Used In |
|---------|---------------------|---------|
| `AR` | Asset | Sales postings |
| `AP` | Liability | Purchase postings |
| `CASH` | Asset | Cash sales/payments |
| `BANK` | Asset | Bank transfers, deposits |
| `INVENTORY_ASSET` | Asset | Purchases, adjustments, transfers |
| `SALES_REVENUE` | Revenue | Sales postings |
| `COGS` | Expense | Sale COGS postings |
| `VAT_INPUT` | Asset | Purchase VAT |
| `VAT_OUTPUT` | Liability | Sale VAT |
| `INVENTORY_ADJUSTMENT_GAIN` | Revenue | Positive adjustments |
| `INVENTORY_ADJUSTMENT_LOSS` | Expense | Negative adjustments, write-offs |
| `FREIGHT_IN` | Asset (capitalized) / Expense | Landed costs |
| `CUSTOMS_DUTY` | Asset (capitalized) | Landed costs |
| `PURCHASE_DISCOUNT` | Contra-expense | Early payment discounts |
| `SALES_DISCOUNT` | Contra-revenue | Customer discounts |
| `FX_GAIN` | Revenue | Currency gains |
| `FX_LOSS` | Expense | Currency losses |

---

## Principle 11: Rounding Rules

All monetary calculations must use consistent rounding to prevent penny drift:

| Context | Precision | Rule |
|---------|-----------|------|
| Unit prices | 3 decimals | `Decimal('0.001')`, ROUND_HALF_UP |
| Line totals | 3 decimals | `Decimal('0.001')`, ROUND_HALF_UP |
| Tax amounts | 2 decimals | `Decimal('0.01')`, ROUND_HALF_UP |
| Journal entry totals | 3 decimals | `Decimal('0.001')`, ROUND_HALF_UP |
| COGS per unit | 3 decimals | `Decimal('0.001')`, ROUND_HALF_UP |
| Inventory valuation | 3 decimals | `Decimal('0.001')`, ROUND_HALF_UP |

MWAC calculation must be performed with full `Decimal` precision; rounding should only occur at display or reporting boundaries.

---

## Principle 12: Approval Workflow for All Decisions

For every accounting rule, formula, journal entry pattern, valuation method, rounding rule, return rule, landed cost allocation rule, FX rule, and closed-period behavior:

1. **Explain the options** clearly.
2. **Recommend one** option with justification.
3. **Explain the financial impact** (P&L, Balance Sheet, tax, audit).
4. **Explain the audit impact** (traceability, compliance, evidence).
5. **Mark as "Requires owner approval: Yes"** if the decision affects financial statements.
6. **Wait for explicit written approval** before implementation.

---

*Document created: June 4, 2026*
*Status: Awaiting owner approval on all marked decisions*
