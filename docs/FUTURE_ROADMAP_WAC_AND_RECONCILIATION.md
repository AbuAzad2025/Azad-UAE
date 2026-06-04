# Future Roadmap: Weighted Average Cost (WAC) & Ledger Reconciliation

**Status:** Planned — awaiting business approval  
**Recommended Priority:** HIGH (Phase 2)  
**Estimated Effort:** 3-4 sprints

---

## 1. Goal

Replace the **Last Purchase Cost** inventory valuation method with **Weighted Average Cost (WAC)** per product per warehouse, and build an automated **Ledger-to-Stock Reconciliation** engine that eliminates the need for manual `accounting_repair.py` scripts.

---

## 2. Current Problem

### 2.1 Last Purchase Cost Drift
- `Product.cost_price` is overwritten on every purchase at a different price.
- `SaleLine.cost_price` captures a snapshot at sale time.
- The GL inventory account (1140) accumulates actual purchase costs.
- **Result:** `Product.current_stock * Product.cost_price` frequently diverges from the GL balance, creating "valuation jumps" and balance sheet volatility.

### 2.2 Manual Repair Dependency
- `runtime_core/accounting_repair.py` exists solely to calculate the gap between stock value and ledger balance.
- It is reactive, not preventive. It does not stop drift; it only reports it.
- Running it in production risks unintended side effects on posted GL entries.

### 2.3 Financial Impact
- Inaccurate inventory valuation on the balance sheet.
- COGS snapshots in `SaleLine` may not reflect true weighted cost, distorting margin reports.
- Auditors cannot reconcile physical stock value to ledger without manual intervention.

---

## 3. Business Decision Required

### Decision 1: WAC Scope
**Question:** Should WAC be calculated **globally per product** or **per warehouse per product**?

| Option | Pros | Cons |
|--------|------|------|
| Global WAC | Simpler; one cost per product | Ignores warehouse-specific procurement pricing |
| Per-warehouse WAC | Accurate for multi-warehouse operations | More complex; requires `warehouse_id` on every cost layer |

**Recommended:** Per-warehouse WAC — the system already supports multi-warehouse operations and the `warehouse_id` scoping is mature.

### Decision 2: Retroactive Application
**Question:** Should existing historical sales and inventory be retroactively restated to WAC?

| Option | Pros | Cons |
|--------|------|------|
| Prospective only (from cutover date) | Simple migration; no historical restatement | Historical margin reports remain based on Last Purchase Cost |
| Full retroactive restatement | Complete accuracy across all periods | Massive migration complexity; may restate closed periods |

**Recommended:** Prospective only. Add a `costing_method` column to `products` and phase in WAC for new purchases. Preserve `SaleLine.cost_price` as-is for historical records.

### Decision 3: GL Inventory Account Strategy
**Question:** Should the system maintain separate GL accounts for inventory at cost vs. WAC adjustment?

**Recommended:** No. Post purchases directly to the standard inventory account (1140) at actual cost. WAC is a valuation methodology, not a separate balance. The reconciliation engine should verify that `Sum(WAC layers) == GL balance`, not create adjustment entries.

---

## 4. Technical Approach

### 4.1 New Model: `ProductCostLayer`

```python
class ProductCostLayer(db.Model):
    """FIFO-like layer tracking for WAC calculation."""
    __tablename__ = 'product_cost_layers'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    quantity = db.Column(db.Numeric(15, 3), nullable=False)      # remaining qty in layer
    unit_cost = db.Column(db.Numeric(15, 3), nullable=False)      # cost for this layer
    total_cost = db.Column(db.Numeric(15, 3), nullable=False)    # quantity * unit_cost

    source_type = db.Column(db.String(20))  # 'purchase', 'opening_balance', 'adjustment'
    source_id = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
```

### 4.2 New Service: `WACStockService`

- `create_layer(purchase_line)` — insert a new cost layer on every confirmed purchase.
- `consume_layer(product_id, warehouse_id, quantity)` — deduct from oldest layer(s) on sale/adjustment.
- `get_wac(product_id, warehouse_id)` — calculate `Sum(total_cost) / Sum(quantity)` across active layers.
- `reconcile_with_gl(product_id, warehouse_id)` — compare `Sum(quantity * unit_cost)` to GL account 1140 balance.

### 4.3 Changes to `StockService`

- On `create_movement` with `movement_type='purchase'`: call `WACStockService.create_layer()`.
- On `create_movement` with `movement_type='sale'` or `'return'`: call `WACStockService.consume_layer()`.
- `Product.cost_price` becomes a **read-only computed property** reflecting current WAC (for backward compatibility).
- `SaleLine.cost_price` remains a snapshot but is populated from WAC at sale time.

### 4.4 Reconciliation Engine

```python
class StockReconciliationService:
    @staticmethod
    def reconcile(tenant_id, warehouse_id=None, as_of_date=None):
        """
        Returns a report of:
        - Physical stock value (from cost layers)
        - GL inventory balance (from journal lines on account 1140)
        - Variance and variance %
        - List of products with non-zero variance
        """
```

- Runs automatically on month-end close (triggered by GL period closure).
- Generates a reconciliation report accessible to accountants.
- **Does not auto-correct.** Only reports. Corrections are manual journal entries.

### 4.5 Migration Plan

1. **Create `product_cost_layers` table** with migration.
2. **Seed layers** from existing purchases (one layer per `PurchaseLine` with full quantity).
3. **Back-calculate consumption** from `SaleLine` quantities to reduce layer quantities.
4. **Verify** that `Sum(quantity)` across layers == `Product.current_stock` per warehouse.
5. **Add `costing_method` enum** to `products` (`last_purchase`, `wac`). Default to `wac` for new products.
6. **Soft-deprecate** `accounting_repair.py` (move to `tools/legacy/`).

---

## 5. Migration Risk

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Historical purchase data has gaps (missing `PurchaseLine`) | Medium | High | Pre-migration validation script; abort if unmapped products found |
| WAC calculation precision issues (Decimal rounding) | Medium | Medium | Use `Decimal('0.001')` consistently; unit tests for rounding edge cases |
| GL balance does not match seeded layers | High | High | Reconciliation report flags variances before go-live; allow manual adjustment period |
| Performance degradation on high-volume products | Low | Medium | Index `product_cost_layers` on `(tenant_id, product_id, warehouse_id)`; consider materialized WAC cache |
| User confusion about changed cost_price behavior | Medium | Low | Update UI labels; add tooltip explaining WAC vs Last Purchase |

---

## 6. Testing Plan

### 6.1 Unit Tests
- `test_wac_single_purchase()` — one purchase, verify WAC equals purchase cost.
- `test_wac_multiple_purchases()` — two purchases at different prices, verify weighted average.
- `test_wac_consumption_fifo()` — sale consumes oldest layer first.
- `test_wac_zero_stock()` — all layers consumed, WAC returns 0.

### 6.2 Integration Tests
- End-to-end: Create purchase → confirm → check layer → create sale → check layer reduced → verify `SaleLine.cost_price == WAC`.
- GL reconciliation: Run `StockReconciliationService.reconcile()` and assert variance == 0 for a controlled dataset.

### 6.3 Migration Tests
- `test_migration_seed_accuracy()` — after seeding, layer quantities match `current_stock`.
- `test_migration_abort_on_gaps()` — if purchase data is missing, migration should abort safely.

### 6.4 Performance Tests
- Simulate 10,000 movements on a single product. Measure `consume_layer()` query time.
- Target: < 100ms per movement.

---

## 7. Rollback Strategy

1. **Before migration:** Full database backup.
2. **Migration is additive** — new `product_cost_layers` table does not modify existing data.
3. **Downgrade migration:** Drops `product_cost_layers` table and removes `costing_method` column.
4. **Code rollback:** Revert `StockService` to use `Product.cost_price` directly (Last Purchase Cost). `SaleLine.cost_price` snapshots are preserved and still valid.
5. **Emergency switch:** Add a feature flag `ENABLE_WAC` (default `False` during transition). Set to `True` only after validation.

---

## 8. Recommended Priority

**HIGH (Phase 2)**

Rationale:
- Directly impacts financial statement accuracy (Balance Sheet + P&L).
- Eliminates a recurring manual repair process (`accounting_repair.py`).
- Required before any external audit or IPO readiness assessment.
- Lower risk than Batch 1-5 because it is a **methodology change**, not a schema constraint change.

**Dependencies:** None (can run in parallel with UI improvements).
**Suggested Start Date:** After Batch 1-5 stabilization (1-2 weeks post-hardening).

---

*Roadmap document created: June 4, 2026*
