# WAC Accounting Architecture Review

**Status:** Review — awaiting owner approval on all decisions  
**Date:** June 4, 2026  
**Purpose:** Evaluate the current Azad-UAE inventory and costing architecture against standard ERP accounting principles (Bisan, Al-Shamel, Odoo, SAP B1, Oracle NetSuite). Identify gaps and define the target architecture for Moving Weighted Average Cost (MWAC) implementation.

---

## 1. Current Architecture Assessment

### 1.1 Current Costing Method: Last Purchase Cost

```
Product.cost_price = last purchase unit price
SaleLine.cost_price = snapshot at sale time
```

**How it works today:**
- When a purchase is confirmed, `PurchaseLine.unit_cost` is copied to `Product.cost_price`.
- When a sale is created, `Product.cost_price` is snapshot into `SaleLine.cost_price`.
- `Product.current_stock` is updated via `StockMovement` records.
- The GL inventory account (1140) accumulates actual purchase costs via `GLJournalEntry`.

**Why this is problematic:**
1. **Valuation Jump:** If product A was bought at 100 AED and then at 200 AED, `cost_price` instantly becomes 200. All existing stock is now valued at 200 in the product record, but the GL may still reflect the 100 purchases.
2. **COGS Distortion:** A sale made after the second purchase shows COGS at 200, even though half the stock was bought at 100.
3. **Reconciliation Gap:** `Product.current_stock × Product.cost_price` frequently does not match the GL inventory balance, requiring manual `accounting_repair.py` runs.

### 1.2 Current Data Model

**Product model:**
```python
class Product(db.Model):
    cost_price = db.Column(db.Numeric(15, 3), default=0)
    current_stock = db.Column(db.Numeric(15, 3), default=0)
    # No warehouse-specific cost or quantity
```

**SaleLine model:**
```python
class SaleLine(db.Model):
    cost_price = db.Column(db.Numeric(15, 3), default=0)  # snapshot at sale time
```

**StockMovement model:**
```python
class StockMovement(db.Model):
    product_id = db.ForeignKey('products.id', ondelete='RESTRICT')
    warehouse_id = db.ForeignKey('warehouses.id')
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    # No cost information stored
```

### 1.3 Current GL Posting

**Purchase:**
```
Dr Inventory Asset (at purchase total)
    Cr AP / Cash
```

**Sale:**
```
Dr AR / Cash (at sale total)
    Cr Sales Revenue

Dr COGS (at SaleLine.cost_price × qty)
    Cr Inventory Asset
```

**Issues with current GL posting:**
- COGS is based on Last Purchase Cost snapshot, not MWAC.
- Inventory Asset balance in GL may not match system stock valuation.
- No dedicated `Inventory Adjustment` accounts for gains/losses.

---

## 2. Target Architecture: Moving Weighted Average Cost (MWAC)

### 2.1 Core Formula

```
New Average Cost =
    (Old Quantity × Old Average Cost + Incoming Quantity × Incoming Unit Cost)
    / (Old Quantity + Incoming Quantity)
```

**At sale time:**
```
COGS = Quantity Sold × Current Average Cost (at moment of sale)
```

### 2.2 Per-Warehouse MWAC (Recommended)

If owner approves DM-02 (per-warehouse scope):

```
ProductWarehouseCost:
    product_id → products.id
    warehouse_id → warehouses.id
    quantity = current stock in this warehouse
    average_cost = current MWAC for this product in this warehouse
```

**Why per-warehouse:**
- Warehouse A buys from Supplier X at 100 AED.
- Warehouse B buys from Supplier Y at 120 AED.
- MWAC for the product is different in each warehouse.
- Transfers between warehouses create transparent cost flow.

**Why not per-branch:**
- A branch may have multiple warehouses with different procurement channels.
- Branch P&L can be derived by aggregating warehouse data.
- Per-branch costing adds unnecessary complexity.

### 2.3 Data Model Changes (Conceptual — Not Yet Implemented)

#### Option A: Extend Product model with warehouse context

```python
class ProductWarehouseCost(db.Model):
    __tablename__ = 'product_warehouse_costs'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'product_id', 'warehouse_id',
                            name='uq_product_warehouse_cost_tenant_product_warehouse'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    quantity = db.Column(db.Numeric(15, 3), default=0)         # current stock
    average_cost = db.Column(db.Numeric(15, 3), default=0)    # current MWAC

    # Indexes for fast lookup
    # db.Index('ix_product_warehouse_cost_tenant_product', 'tenant_id', 'product_id')
    # db.Index('ix_product_warehouse_cost_tenant_warehouse', 'tenant_id', 'warehouse_id')
```

**Pros:**
- Clean separation of cost data from product master.
- Easy to query "all products in warehouse X with their costs."
- Natural fit for multi-warehouse operations.

**Cons:**
- Requires join on every inventory lookup.
- Need to maintain consistency with `StockMovement` totals.

#### Option B: Keep cost in Product, add warehouse quantity table

```python
class Product(db.Model):
    # global fields remain
    global_average_cost = db.Column(db.Numeric(15, 3), default=0)  # optional aggregate

class WarehouseStock(db.Model):
    product_id = db.ForeignKey('products.id')
    warehouse_id = db.ForeignKey('warehouses.id')
    quantity = db.Column(db.Numeric(15, 3), default=0)
    average_cost = db.Column(db.Numeric(15, 3), default=0)  # MWAC per warehouse
```

**Pros:**
- `Product` model stays simpler.
- `WarehouseStock` is a natural extension of current `StockMovement` logic.

**Cons:**
- Still requires a new table.
- `Product.cost_price` becomes ambiguous (is it global or warehouse-specific?).

**Recommendation:** Option A (`ProductWarehouseCost`) is cleaner. It makes the warehouse-specific cost explicit and avoids overloading the `Product` model.

### 2.4 Cost History for Audit (Read-Only)

```python
class ProductCostHistory(db.Model):
    __tablename__ = 'product_cost_history'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    movement_type = db.Column(db.String(20))  # 'purchase', 'sale', 'return', 'adjustment', 'transfer_in', 'transfer_out'
    movement_id = db.Column(db.Integer)       # reference to source document

    quantity_before = db.Column(db.Numeric(15, 3))
    quantity_change = db.Column(db.Numeric(15, 3))
    unit_cost = db.Column(db.Numeric(15, 3))     # for incoming: the cost used; for outgoing: the MWAC at time of sale
    average_cost_before = db.Column(db.Numeric(15, 3))
    average_cost_after = db.Column(db.Numeric(15, 3))

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

**Purpose:**
- Audit trail for how MWAC changed over time.
- NOT used for layer consumption (this is not FIFO).
- Read-only after creation.
- Supports regulatory audit requirements.

---

## 3. Transaction Flows (Target State)

### 3.1 Purchase Receipt (Incoming)

**Input:** Purchase confirmed, goods received at Warehouse A.

**Process:**
1. Create `StockMovement` (type='purchase_in').
2. Calculate total incoming cost:
   ```
   incoming_unit_cost = PurchaseLine.unit_cost + allocated_landed_cost
   ```
3. Update MWAC for (product, Warehouse A):
   ```
   old_qty = ProductWarehouseCost.quantity
   old_avg = ProductWarehouseCost.average_cost
   incoming_qty = PurchaseLine.quantity

   new_avg = (old_qty × old_avg + incoming_qty × incoming_unit_cost) / (old_qty + incoming_qty)

   ProductWarehouseCost.quantity = old_qty + incoming_qty
   ProductWarehouseCost.average_cost = new_avg
   ```
4. Log `ProductCostHistory`.
5. Post GL:
   ```
   Dr Inventory Asset (at incoming_unit_cost × qty)
       Cr AP / Cash
   ```

### 3.2 Sale (Outgoing)

**Input:** Sale confirmed, goods shipped from Warehouse A.

**Process:**
1. Determine current MWAC for (product, Warehouse A) — call it `sale_cost`.
2. Create `SaleLine` with `cost_price = sale_cost`.
3. Create `StockMovement` (type='sale_out').
4. Update MWAC for (product, Warehouse A):
   ```
   ProductWarehouseCost.quantity -= SaleLine.quantity
   # average_cost remains unchanged (MWAC does not change on outgoing movements)
   ```
5. Log `ProductCostHistory`.
6. Post GL:
   ```
   Dr AR / Cash (at sale total)
       Cr Sales Revenue

   Dr COGS (at sale_cost × qty)
       Cr Inventory Asset
   ```

### 3.3 Sales Return (Linked to Original Sale)

**Input:** Customer returns goods to Warehouse A. Return is linked to `sale_id` / `sale_line_id`.

**Process:**
1. Retrieve original `SaleLine.cost_price` — call it `original_cost`.
2. Create `StockMovement` (type='return_in').
3. Update MWAC for (product, Warehouse A):
   ```
   old_qty = ProductWarehouseCost.quantity
   old_avg = ProductWarehouseCost.average_cost
   return_qty = ReturnLine.quantity

   new_avg = (old_qty × old_avg + return_qty × original_cost) / (old_qty + return_qty)

   ProductWarehouseCost.quantity = old_qty + return_qty
   ProductWarehouseCost.average_cost = new_avg
   ```
4. Log `ProductCostHistory`.
5. Post GL:
   ```
   Dr Sales Returns (at sale price × qty)
       Cr AR / Cash / Refund Payable

   Dr Inventory Asset (at original_cost × qty)
       Cr COGS Reversal
   ```

### 3.4 Inter-Warehouse Transfer

**Input:** Transfer 100 units of Product P from Warehouse A to Warehouse B.

**Process:**
1. Retrieve Warehouse A's current MWAC for Product P — call it `transfer_cost`.
2. Create `StockMovement` (type='transfer_out') for Warehouse A.
3. Create `StockMovement` (type='transfer_in') for Warehouse B.
4. Update Warehouse A:
   ```
   ProductWarehouseCost.quantity -= 100
   # average_cost unchanged
   ```
5. Update Warehouse B:
   ```
   old_qty = ProductWarehouseCost.quantity (B)
   old_avg = ProductWarehouseCost.average_cost (B)

   new_avg = (old_qty × old_avg + 100 × transfer_cost) / (old_qty + 100)

   ProductWarehouseCost.quantity = old_qty + 100
   ProductWarehouseCost.average_cost = new_avg
   ```
6. Post GL:
   ```
   Dr Inventory Asset — Warehouse B (at transfer_cost × 100)
       Cr Inventory Asset — Warehouse A (at transfer_cost × 100)
   ```
   **Note:** Total inventory value across all warehouses is unchanged.

### 3.5 Inventory Adjustment — Increase (Physical Count > System)

**Input:** Physical count shows 110 units; system shows 100 units. Variance = +10.

**Process:**
1. Retrieve current MWAC for (product, Warehouse A) — call it `adj_cost`.
2. Create `StockMovement` (type='adjustment_in', quantity=10).
3. Update MWAC:
   ```
   old_qty = ProductWarehouseCost.quantity
   old_avg = ProductWarehouseCost.average_cost

   new_avg = (old_qty × old_avg + 10 × adj_cost) / (old_qty + 10)

   ProductWarehouseCost.quantity = old_qty + 10
   ProductWarehouseCost.average_cost = new_avg
   ```
4. Post GL:
   ```
   Dr Inventory Asset (at adj_cost × 10)
       Cr Inventory Adjustment Gain
   ```

### 3.6 Inventory Adjustment — Decrease (Physical Count < System)

**Input:** Physical count shows 90 units; system shows 100 units. Variance = -10.

**Process:**
1. Retrieve current MWAC for (product, Warehouse A) — call it `adj_cost`.
2. Create `StockMovement` (type='adjustment_out', quantity=10).
3. Update MWAC:
   ```
   ProductWarehouseCost.quantity -= 10
   # average_cost unchanged
   ```
4. Post GL:
   ```
   Dr Inventory Adjustment Loss (at adj_cost × 10)
       Cr Inventory Asset
   ```

---

## 4. GL Account Mapping (Concept-Based)

All GL postings in the target architecture must use configurable concept mappings, not hardcoded account codes.

### 4.1 Required Concepts for Inventory & Costing

| Concept | Used In | Typical Account Type |
|---------|---------|---------------------|
| `INVENTORY_ASSET` | Purchases, transfers, adjustments, returns | Asset (Balance Sheet) |
| `COGS` | Sale COGS postings | Expense (P&L) |
| `COGS_REVERSAL` | Sales return COGS reversals | Contra-Expense (P&L) |
| `SALES_REVENUE` | Sales postings | Revenue (P&L) |
| `SALES_RETURNS` | Sales return revenue reversals | Contra-Revenue (P&L) |
| `AR` | Sales on credit | Asset (Balance Sheet) |
| `AP` | Purchases on credit | Liability (Balance Sheet) |
| `CASH` | Cash sales/payments | Asset (Balance Sheet) |
| `BANK` | Bank transfers | Asset (Balance Sheet) |
| `VAT_INPUT` | Purchase VAT | Asset (Balance Sheet) |
| `VAT_OUTPUT` | Sale VAT | Liability (Balance Sheet) |
| `INVENTORY_ADJUSTMENT_GAIN` | Positive adjustments | Revenue / Other Income (P&L) |
| `INVENTORY_ADJUSTMENT_LOSS` | Negative adjustments, write-offs | Expense (P&L) |
| `FREIGHT_IN` | Freight capitalized into inventory | Asset (Balance Sheet) |
| `CUSTOMS_DUTY` | Customs duties capitalized | Asset (Balance Sheet) |
| `FX_GAIN` | FX differences (favorable) | Revenue (P&L) |
| `FX_LOSS` | FX differences (unfavorable) | Expense (P&L) |

### 4.2 Dynamic Resolution Example

```python
# Instead of:
inventory_account = GLAccount.query.filter_by(code='1140').first()

# Use:
inventory_account = GLAccountMapping.get_account(
    tenant_id=tenant_id,
    concept_code=GLConcept.INVENTORY_ASSET,
    branch_id=branch_id  # optional override
)
```

---

## 5. Reconciliation Architecture

### 5.1 Reconciliation as Reporting Only

The reconciliation engine is **read-only**. It produces reports, not journal entries.

### 5.2 Reconciliation Dimensions

| Dimension | Source | Compared Against |
|-----------|--------|------------------|
| Quantity | `StockMovement` aggregated qty per product/warehouse | Physical count (entered via adjustment) |
| Valuation | `ProductWarehouseCost.quantity × average_cost` | GL inventory account balance |
| COGS | Sum of `GLJournalLine` on COGS account for period | Sum of `SaleLine.cost_price × quantity` for period |
| Movements | `StockMovement` audit trail | `GLJournalEntry` reference linkage |

### 5.3 Reconciliation Report Output

```python
class InventoryReconciliationReport:
    tenant_id: int
    warehouse_id: int | None  # None = all warehouses
    as_of_date: date

    products: List[ReconciliationLine]

class ReconciliationLine:
    product_id: int
    product_name: str
    system_quantity: Decimal
    physical_quantity: Decimal | None
    quantity_variance: Decimal | None
    system_value: Decimal      # qty × MWAC
    gl_balance: Decimal        # from GL account
    value_variance: Decimal
    period_cogs_from_gl: Decimal
    period_cogs_from_sales: Decimal
    cogs_variance: Decimal
    status: 'ok' | 'quantity_mismatch' | 'value_mismatch' | 'cogs_mismatch'
    recommended_action: str    # e.g., "Create adjustment entry for qty variance of -5"
```

### 5.4 No Auto-Correction

- The report is exported as PDF or Excel.
- The accountant reviews variances.
- If approved, the accountant creates a manual `InventoryAdjustment` with linked `GLJournalEntry`.
- The system logs who approved the adjustment and when.

---

## 6. Gap Analysis: Current vs. Target

| Area | Current State | Target State | Gap |
|------|---------------|--------------|-----|
| Costing method | Last Purchase Cost | Moving Weighted Average | Full redesign of cost calculation |
| Cost scope | Global per product | Per product per warehouse | New `ProductWarehouseCost` table needed |
| SaleLine.cost_price | Snapshot of Last Purchase Cost | Snapshot of MWAC at sale time | Same field, different source |
| StockMovement | Tracks qty only | Tracks qty + references cost | Add `reference_cost` for audit |
| Landed costs | Not supported | Capitalized into MWAC | New `PurchaseLine.allocated_landed_cost` field |
| Multi-currency | Partial (amount_aed exists) | Formal FX rate + source tracking | Add `exchange_rate_source` to Purchase |
| GL posting | Hardcoded account codes | Concept-based dynamic mapping | New `GLAccountMapping` system |
| Reconciliation | Manual `accounting_repair.py` | Automated report generation | New `InventoryReconciliationService` |
| Returns | Current MWAC or manual | Original cost (linked), current MWAC (unlinked) | Update return posting logic |
| Closed periods | Partial (GLPeriod exists) | Enforced on all inventory posting | Add `assert_period_open()` to all services |

---

## 7. Implementation Phasing (Recommended)

| Phase | Deliverable | Dependencies | Est. Effort |
|-------|-------------|--------------|-------------|
| 0 | Owner approval on all 13 DM decisions | This document | 1-2 days |
| 1 | `ProductWarehouseCost` model + MWAC service | Phase 0 | 1 sprint |
| 2 | Update purchase/sale/return/transfer posting to use MWAC | Phase 1 | 2 sprints |
| 3 | Landed cost support | Phase 2 | 1 sprint |
| 4 | Multi-currency FX formalization | Phase 2 | 1 sprint |
| 5 | `GLAccountMapping` system + concept registry | Phase 0-2 | 2 sprints |
| 6 | Inventory reconciliation reporting | Phase 1-5 | 1 sprint |
| 7 | Migration: seed `ProductWarehouseCost` from historical data | Phase 1-6 | 1 sprint |
| 8 | UAT + go-live | Phase 7 | 1 sprint |

**Total estimated effort:** 9-10 sprints (~4-5 months with 1 developer)

---

## 8. Risk Summary

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Historical data gaps (missing purchases for existing stock) | Medium | High | Pre-migration validation script; abort if unmapped products found |
| MWAC precision drift over many transactions | Low | Medium | Use `Decimal('0.001')` consistently; unit test rounding edge cases |
| User confusion about changed cost_price behavior | Medium | Low | Update UI labels; add tooltip explaining MWAC vs Last Purchase Cost |
| GL balance mismatch after migration | High | High | Reconciliation report before go-live; allow manual adjustment period |
| Performance on high-volume products | Low | Medium | Index `product_warehouse_costs` on `(tenant_id, product_id, warehouse_id)` |
| Feature flag complexity during transition | Medium | Low | Single `ENABLE_MWAC` flag; no dual-path logic in posting services |

---

*Architecture review created: June 4, 2026*
*Status: Awaiting owner approval on DM-01 through DM-13*
