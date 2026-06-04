# Future Roadmap: Moving Weighted Average Cost (MWAC) & Ledger Reconciliation

**Status:** Planned — awaiting owner approval on DM-01 through DM-13  
**Recommended Priority:** HIGH (Phase 2)  
**Estimated Effort:** 9-10 sprints (see phased plan)  
**Accounting Standard:** Perpetual Inventory System with Moving Weighted Average Cost

---

## 1. Goal

Replace the **Last Purchase Cost** inventory valuation method with **Moving Weighted Average Cost (MWAC)** per product per warehouse, and build a **read-only Ledger-to-Stock Reconciliation** reporting engine. This aligns the system with standard ERP accounting practices (Bisan, Al-Shamel, Odoo, SAP B1, Oracle NetSuite).

**Key constraints from ERP Accounting Principles:**
- True MWAC formula — not FIFO layer consumption.
- Perpetual inventory — every movement has immediate GL impact.
- Reconciliation reports only — no auto-correction.
- Closed periods are immutable.
- All GL postings must eventually use configurable concept mappings.

---

## 2. Current Problem

### 2.1 Last Purchase Cost Drift
- `Product.cost_price` is overwritten on every purchase at a different price.
- `SaleLine.cost_price` captures a snapshot at sale time using Last Purchase Cost.
- The GL inventory account (1140) accumulates actual purchase costs.
- **Result:** `Product.current_stock * Product.cost_price` frequently diverges from the GL balance, creating "valuation jumps" and balance sheet volatility.

### 2.2 No True Weighted Average
- The current system has no running weighted average calculation.
- There is no `ProductWarehouseCost` table or equivalent.
- `StockMovement` tracks quantities but not the cost context of each movement.

### 2.3 Manual Repair Dependency
- `runtime_core/accounting_repair.py` exists solely to calculate the gap between stock value and ledger balance.
- It is reactive, not preventive. It does not stop drift; it only reports it.
- Running it in production risks unintended side effects on posted GL entries.

### 2.4 Financial Impact
- Inaccurate inventory valuation on the balance sheet.
- COGS snapshots in `SaleLine` may not reflect true weighted cost, distorting margin reports.
- Auditors cannot reconcile physical stock value to ledger without manual intervention.

---

## 3. Business Decisions Required (All Require Owner Approval)

### Decision DM-01: Costing Method
**Question:** Which inventory costing method should the system use?

| Option | Pros | Cons |
|--------|------|------|
| Last Purchase Cost (current) | Simple | Valuation jumps; no true average |
| FIFO | Precise cost matching | Complex layer tracking; not dominant in UAE |
| **Moving Weighted Average** ✅ | Smooths volatility; UAE standard; simple audit | Requires per-warehouse tracking |
| Standard Cost | Predictable budgeting | Requires variance analysis; overkill for SMB |

**Recommended:** **Moving Weighted Average Cost** — dominant in UAE ERP practice (Bisan, Al-Shamel, SAP B1).  
**Financial Impact:** Eliminates balance sheet volatility. COGS reflects blended historical cost.  
**Audit Impact:** Simpler audit trail (one running average vs. layer stacks).  
**Requires Owner Approval:** **Yes** 🔒

---

### Decision DM-02: MWAC Scope
**Question:** Should MWAC be calculated per product (tenant-wide) or per product per warehouse?

| Option | Pros | Cons |
|--------|------|------|
| Global per product | Simplest; one cost per product | Ignores warehouse-specific procurement pricing |
| **Per product per warehouse** ✅ | Accurate for multi-warehouse; transfer cost flow is natural | More complex; requires warehouse context in all cost lookups |
| Per product per branch | Aligns with branch P&L | Branch may have multiple warehouses; adds complexity |

**Recommended:** **Per product per warehouse** — UAE businesses operate multiple warehouses with independent suppliers.  
**Financial Impact:** Accurate local inventory valuation. Transparent transfer cost flow.  
**Audit Impact:** Each warehouse's inventory value is independently auditable.  
**Requires Owner Approval:** **Yes** 🔒

---

### Decision DM-03: Transfer Costing
**Question:** At what cost should inter-warehouse transfers be recorded?

| Option | Pros | Cons |
|--------|------|------|
| **Source warehouse MWAC** ✅ | Total inventory value unchanged; standard ERP behavior | Destination warehouse average may shift |
| Destination warehouse MWAC | Destination average unchanged | Creates phantom gain/loss; non-standard |
| Manual transfer price | Flexibility | Requires admin overhead per transfer |

**Recommended:** **Source warehouse's current MWAC** — standard in Odoo, SAP B1, NetSuite.  
**Financial Impact:** Total inventory value across warehouses remains constant. No phantom gains/losses.  
**Audit Impact:** Clean GL: Dr Destination Inventory / Cr Source Inventory at same amount.  
**Requires Owner Approval:** **Yes** 🔒

---

### Decision DM-04: Linked Sales Return Cost
**Question:** For sales returns linked to the original invoice, which cost should be used?

| Option | Pros | Cons |
|--------|------|------|
| **Original `SaleLine.cost_price`** ✅ | Perfect COGS reversal; preserves original period margin | Requires `sale_line_id` on return (already exists) |
| Current MWAC at return date | Simpler lookup | Distorts current-period margin; inventory value may not match original deduction |

**Recommended:** **Original `SaleLine.cost_price`** — standard audited ERP practice.  
**Financial Impact:** Perfect reversal. Inventory value increase matches original deduction.  
**Audit Impact:** Crystal-clear traceability: Sale → SaleLine.cost_price → Return → COGS reversal.  
**Requires Owner Approval:** **Yes** 🔒

---

### Decision DM-05: Unlinked Sales Return Cost
**Question:** For sales returns NOT linked to an original invoice, which cost should be used?

| Option | Pros | Cons |
|--------|------|------|
| **Current MWAC at return date** ✅ | Practical; reflects replacement value | May differ from original cost |
| Historical MWAC from reference period | More accurate | Requires lookup logic; ambiguous which period |
| Manual cost entry | Maximum flexibility | Requires training; slows workflow |

**Recommended:** **Current MWAC at return date** (with optional manual override field).  
**Financial Impact:** Acceptable variance for exceptions (unlinked returns should be rare).  
**Audit Impact:** System must record: unlinked flag, MWAC used, override reason if any.  
**Requires Owner Approval:** **Yes** 🔒

---

### Decision DM-06: Landed Cost Allocation
**Question:** How should landed costs (freight, customs, insurance) be allocated across products in a shipment?

| Option | Pros | Cons |
|--------|------|------|
| **By Value** ✅ | Most common ERP default; fair for mixed-price products | Higher-value items absorb more cost |
| By Quantity | Fair for similar products | Under-allocates to expensive items |
| By Weight | Accurate for heavy goods | Requires weight data on all products |
| By Volume | Accurate for bulky goods | Requires dimension data |
| Manual | Maximum control | Administrative overhead |

**Recommended:** **By Value** (default), with per-purchase override capability.  
**Financial Impact:** Higher-value items absorb more landed cost, reflecting higher shipping/insurance risk.  
**Audit Impact:** Allocation base and calculation must be logged per purchase line.  
**Requires Owner Approval:** **Yes** 🔒

---

### Decision DM-07: Landed Cost Treatment
**Question:** Should landed costs be capitalized into inventory or expensed immediately?

| Option | Pros | Cons |
|--------|------|------|
| **Capitalize into inventory** ✅ | Compliant with IAS 2 / UAE standards; accurate COGS | Higher inventory balance |
| Expense immediately | Lower inventory; higher current expenses | Non-compliant; distorts margins |

**Recommended:** **Capitalize into inventory** — required by IAS 2 and UAE accounting standards.  
**Financial Impact:** Inventory balance is higher. COGS reflects true acquisition cost. P&L smoothed over sale periods.  
**Audit Impact:** Capitalized costs are auditable via purchase document and inventory valuation report.  
**Requires Owner Approval:** **Yes** 🔒

---

### Decision DM-08: FX Rate Source
**Question:** Which exchange rate should be used for foreign-currency inventory purchases?

| Option | Pros | Cons |
|--------|------|------|
| **CBUAE official rate** ✅ | Authoritative; publicly verifiable; audit-friendly | May differ from bank rate by small margin |
| Bank transaction rate | Matches actual cash flow | Varies by institution; harder to verify |
| Tenant manual rate | Flexibility for forward contracts | Audit risk if not justified |

**Recommended:** **CBUAE official rate** (default), with manual override per purchase and justification note.  
**Financial Impact:** Inventory cost remains consistent. FX differences flow to P&L, not inventory.  
**Audit Impact:** CBUAE rate is verifiable by external auditors. Overrides require justification.  
**Requires Owner Approval:** **Yes** 🔒

---

### Decision DM-09: FX Difference Treatment
**Question:** Where should exchange rate differences between purchase and payment be posted?

| Option | Pros | Cons |
|--------|------|------|
| **FX Gain/Loss to P&L** ✅ | Compliant with IAS 21; inventory remains at historical cost | P&L volatility from exchange rates |
| Adjust inventory cost with FX difference | Smooths P&L | Non-compliant; restates non-monetary item |

**Recommended:** **FX Gain/Loss to P&L** — required by IAS 21. Inventory is non-monetary; fixed at historical cost.  
**Financial Impact:** Inventory cost fixed at purchase-date rate. FX volatility affects P&L only.  
**Audit Impact:** Clean separation: inventory at historical cost, FX differences in dedicated P&L account.  
**Requires Owner Approval:** **Yes** 🔒

---

## 4. Technical Approach

### 4.1 Core MWAC Formula (True Moving Average)

```python
from decimal import Decimal, ROUND_HALF_UP

def calculate_new_average_cost(
    old_quantity: Decimal,
    old_average_cost: Decimal,
    incoming_quantity: Decimal,
    incoming_unit_cost: Decimal
) -> Decimal:
    """
    True Moving Weighted Average Cost formula.
    Applied on every incoming movement (purchase, adjustment increase, transfer-in).
    """
    if old_quantity + incoming_quantity == 0:
        return Decimal('0')
    total_old_value = old_quantity * old_average_cost
    total_incoming_value = incoming_quantity * incoming_unit_cost
    new_average = (total_old_value + total_incoming_value) / (old_quantity + incoming_quantity)
    return new_average.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
```

**Important:** Outgoing movements (sales, adjustments out, transfers out) **do not change** the average cost. They only reduce quantity. The average cost is updated only on incoming movements.

### 4.2 New Model: `ProductWarehouseCost`

```python
class ProductWarehouseCost(db.Model):
    """
    Stores the current Moving Weighted Average Cost and quantity
    for a single product in a single warehouse.
    This is NOT a FIFO layer table. It stores ONE running average per scope.
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

    quantity = db.Column(db.Numeric(15, 3), default=0)
    average_cost = db.Column(db.Numeric(15, 3), default=0)
```

**Why not `ProductCostLayer`?**
- `ProductCostLayer` with `consume_layer()` logic is **FIFO**, not MWAC.
- MWAC does not consume layers. It maintains a single running average.
- Layer tables are appropriate for FIFO or specific identification, not for moving average.

### 4.3 New Model: `ProductCostHistory` (Audit Only)

```python
class ProductCostHistory(db.Model):
    """Read-only audit trail of how MWAC changed over time. NOT used for layer consumption."""
    __tablename__ = 'product_cost_history'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    movement_type = db.Column(db.String(20))
    movement_id = db.Column(db.Integer)

    quantity_before = db.Column(db.Numeric(15, 3))
    quantity_change = db.Column(db.Numeric(15, 3))
    unit_cost = db.Column(db.Numeric(15, 3))
    average_cost_before = db.Column(db.Numeric(15, 3))
    average_cost_after = db.Column(db.Numeric(15, 3))

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

### 4.4 New Service: `MWACStockService`

```python
class MWACStockService:
    """Core service for Moving Weighted Average Cost calculations."""

    @classmethod
    def get_cost(cls, tenant_id, product_id, warehouse_id):
        record = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id
        ).first()
        if record:
            return record.quantity, record.average_cost
        return Decimal('0'), Decimal('0')

    @classmethod
    def incoming_movement(cls, tenant_id, product_id, warehouse_id,
                          quantity, unit_cost, movement_type, movement_id):
        """Apply MWAC formula for an incoming movement. Updates ProductWarehouseCost and logs history."""
        record = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id
        ).first()

        old_qty = record.quantity if record else Decimal('0')
        old_avg = record.average_cost if record else Decimal('0')
        new_avg = calculate_new_average_cost(old_qty, old_avg, quantity, unit_cost)
        new_qty = old_qty + quantity

        if not record:
            record = ProductWarehouseCost(
                tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id,
                quantity=new_qty, average_cost=new_avg
            )
            db.session.add(record)
        else:
            record.quantity = new_qty
            record.average_cost = new_avg

        history = ProductCostHistory(
            tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id,
            movement_type=movement_type, movement_id=movement_id,
            quantity_before=old_qty, quantity_change=quantity, unit_cost=unit_cost,
            average_cost_before=old_avg, average_cost_after=new_avg
        )
        db.session.add(history)
        return new_qty, new_avg

    @classmethod
    def outgoing_movement(cls, tenant_id, product_id, warehouse_id,
                          quantity, movement_type, movement_id):
        """Record an outgoing movement. Does NOT change average cost. Only reduces quantity.
        Returns the MWAC at time of movement (for COGS snapshot)."""
        record = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id
        ).first()

        if not record or record.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for product {product_id} in warehouse {warehouse_id}"
            )

        old_qty = record.quantity
        old_avg = record.average_cost
        new_qty = old_qty - quantity
        record.quantity = new_qty
        # average_cost remains unchanged

        history = ProductCostHistory(
            tenant_id=tenant_id, product_id=product_id, warehouse_id=warehouse_id,
            movement_type=movement_type, movement_id=movement_id,
            quantity_before=old_qty, quantity_change=-quantity, unit_cost=old_avg,
            average_cost_before=old_avg, average_cost_after=old_avg
        )
        db.session.add(history)
        return old_avg
```

### 4.5 GL Integration with Dynamic Mapping

All GL postings must use concept-based mapping (see `FUTURE_ROADMAP_DYNAMIC_GL_MAPPING.md`):

```python
inventory_account = GLAccountMapping.get_account(tenant_id, GLConcept.INVENTORY_ASSET, branch_id)
ap_account = GLAccountMapping.get_account(tenant_id, GLConcept.AP, branch_id)
revenue_account = GLAccountMapping.get_account(tenant_id, GLConcept.SALES_REVENUE, branch_id)
cogs_account = GLAccountMapping.get_account(tenant_id, GLConcept.COGS, branch_id)
```

**During transition (before GL mapping is fully implemented):**
- Phase 1: Use hardcoded account codes as fallback with a compatibility shim.
- Phase 2: Migrate to full concept-based mapping.

### 4.6 Reconciliation Engine (Read-Only)

```python
class InventoryReconciliationService:
    @staticmethod
    def generate_report(tenant_id, warehouse_id=None, as_of_date=None):
        """
        Produces a read-only reconciliation report comparing:
        - System stock quantities (from StockMovement aggregation)
        - System inventory valuation (from ProductWarehouseCost)
        - GL inventory account balance (from GLJournalLine)
        - Period COGS (from GLJournalLine vs SaleLine snapshots)
        Returns a dataclass (not a DB write).
        """
```

**Reconciliation is reporting only.** It does not:
- Auto-post correcting journal entries.
- Auto-adjust MWAC.
- Auto-modify stock quantities.
- Override closed-period data.

### 4.7 Closed Period Protection

All posting services must enforce:

```python
def assert_period_open(tenant_id, transaction_date):
    period = GLPeriod.query.filter(
        GLPeriod.tenant_id == tenant_id,
        GLPeriod.start_date <= transaction_date,
        GLPeriod.end_date >= transaction_date
    ).first()
    if period and period.is_closed:
        raise ClosedPeriodError(
            f"Period {period.name} is closed. Create an adjustment entry in an open period."
        )
```

---

## 5. Transaction Flows (Target State)

### 5.1 Purchase Receipt
1. Calculate `incoming_unit_cost = PurchaseLine.unit_cost + allocated_landed_cost`.
2. Call `MWACStockService.incoming_movement()` to update MWAC.
3. Post GL:
   ```
   Dr Inventory Asset (at incoming_unit_cost × qty)
       Cr AP / Cash
   ```

### 5.2 Sale
1. Call `MWACStockService.outgoing_movement()` to get current MWAC (`sale_cost`).
2. Store `SaleLine.cost_price = sale_cost`.
3. Post GL:
   ```
   Dr AR / Cash (at sale total)
       Cr Sales Revenue
   Dr COGS (at sale_cost × qty)
       Cr Inventory Asset
   ```

### 5.3 Sales Return (Linked)
1. Retrieve original `SaleLine.cost_price` (`original_cost`).
2. Call `MWACStockService.incoming_movement()` with `unit_cost=original_cost`.
3. Post GL:
   ```
   Dr Sales Returns (at sale price × qty)
       Cr AR / Cash
   Dr Inventory Asset (at original_cost × qty)
       Cr COGS Reversal
   ```

### 5.4 Inter-Warehouse Transfer
1. Retrieve source warehouse MWAC (`transfer_cost`).
2. Call `MWACStockService.outgoing_movement()` at source.
3. Call `MWACStockService.incoming_movement()` at destination with `unit_cost=transfer_cost`.
4. Post GL:
   ```
   Dr Inventory Asset — Destination (at transfer_cost × qty)
       Cr Inventory Asset — Source (at transfer_cost × qty)
   ```

### 5.5 Inventory Adjustment
- **Increase:** Incoming at current MWAC. Dr Inventory Asset / Cr Inventory Adjustment Gain.
- **Decrease:** Outgoing at current MWAC. Dr Inventory Adjustment Loss / Cr Inventory Asset.

---

## 6. Migration Plan

### Phase 0: Owner Approval
- Obtain written approval on DM-01 through DM-09.
- Do not proceed to Phase 1 without approval.

### Phase 1: Create Tables
- Alembic migration: `product_warehouse_costs` and `product_cost_history`.
- Seed `ProductWarehouseCost` from existing `Product.current_stock` and `Product.cost_price`.
- All new tables are **additive**; no existing data is modified.

### Phase 2: Implement `MWACStockService`
- Build `incoming_movement()` and `outgoing_movement()`.
- Unit tests with edge cases (zero stock, rounding, negative quantity prevention).

### Phase 3: Update Purchase Posting
- On purchase confirmation: call `MWACStockService.incoming_movement()`.
- Include landed cost in `incoming_unit_cost`.

### Phase 4: Update Sale Posting
- On sale confirmation: snapshot MWAC into `SaleLine.cost_price`.
- Post COGS at snapshot cost.

### Phase 5: Update Return, Adjustment, Transfer Posting
- Linked returns: use original `SaleLine.cost_price`.
- Unlinked returns: use current MWAC with manual override.
- Transfers: at source MWAC.

### Phase 6: Build Reconciliation Reporting
- `InventoryReconciliationService.generate_report()`.
- PDF/Excel export. Dashboard in Admin UI.

### Phase 7: Deprecate `accounting_repair.py`
- Move to `tools/legacy/`.
- Replace with reconciliation report workflow.

---

## 7. Migration Risk

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Historical purchase data gaps | Medium | High | Pre-migration validation; abort if unmapped products found |
| MWAC precision drift over many transactions | Low | Medium | Use `Decimal('0.001')` consistently; unit test rounding edge cases |
| GL balance mismatch after go-live | High | High | Reconciliation report before go-live; allow manual adjustment period |
| Performance on high-volume products | Low | Medium | Index `product_warehouse_costs` on `(tenant_id, product_id, warehouse_id)` |
| User confusion about changed cost_price | Medium | Low | Update UI labels; add tooltip explaining MWAC vs Last Purchase |
| Landed cost data missing historically | High | Medium | Historical purchases default to zero landed cost; new purchases capture it |

---

## 8. Testing Plan

### 8.1 Unit Tests
- `test_mwac_single_purchase()` — one purchase, MWAC equals purchase cost.
- `test_mwac_multiple_purchases()` — two purchases at different prices, verify weighted average.
- `test_mwac_outgoing_does_not_change_average()` — sale reduces qty but average stays same.
- `test_mwac_return_linked_uses_original_cost()` — linked return uses SaleLine.cost_price.
- `test_mwac_return_unlinked_uses_current_average()` — unlinked return uses current MWAC.
- `test_mwac_transfer_cost_flow()` — transfer at source cost; destination recalculates.
- `test_mwac_zero_stock()` — all stock sold, average cost is preserved.
- `test_mwac_rounding_precision()` — verify no penny drift over 1000 transactions.

### 8.2 Integration Tests
- End-to-end: Purchase → confirm → MWAC updated → Sale → COGS posted → Return → COGS reversed.
- Landed cost: Purchase with freight → freight allocated → MWAC includes freight.
- Multi-currency: Foreign purchase → CBUAE rate → AED MWAC → FX diff to P&L.
- Closed period: Attempt to post to closed period → blocked with clear error.

### 8.3 Migration Tests
- `test_migration_seed_accuracy()` — seeded quantities match `current_stock`.
- `test_migration_abort_on_gaps()` — abort if purchase data is missing.

### 8.4 Performance Tests
- Simulate 10,000 movements on a single product.
- Target: < 50ms per movement.

---

## 9. Rollback Strategy

1. **Before migration:** Full database backup.
2. **Migration is additive** — new tables do not modify existing data.
3. **Downgrade migration:** Drops `product_warehouse_costs` and `product_cost_history`.
4. **Code rollback:** Revert `StockService` to use `Product.cost_price` directly (Last Purchase Cost). `SaleLine.cost_price` snapshots are preserved.
5. **Emergency switch:** Feature flag `ENABLE_MWAC` (default `False` during transition).

---

## 10. Recommended Priority

**HIGH (Phase 2)**

Rationale:
- Directly impacts financial statement accuracy (Balance Sheet + P&L).
- Eliminates recurring manual repair (`accounting_repair.py`).
- Required before any external audit or IPO readiness.
- Aligns with UAE ERP standards (Bisan, Al-Shamel, SAP B1).

**Dependencies:** None (can run in parallel with UI improvements).  
**Suggested Start Date:** After owner approval on DM-01 through DM-09.

---

*Roadmap document updated: June 4, 2026*  
*Aligned with ERP Accounting Principles v1.0*
