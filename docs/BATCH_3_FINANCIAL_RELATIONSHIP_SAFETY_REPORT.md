# Batch 3: Financial Relationship Safety Report

**Date:** June 4, 2026  
**Status:** COMPLETED  
**Author:** Cascade (AI Pair Programmer)

---

## 1. Executive Summary

Batch 3 focused on protecting financial audit history by removing unsafe ORM-level `cascade='all, delete-orphan'` relationships and enforcing `ON DELETE RESTRICT` at the PostgreSQL database level for three critical parent->child financial relationships:

| Parent | Child | Risk |
|--------|-------|------|
| `Sale` | `SaleLine` | Deleting a sale would silently wipe all line items, breaking revenue traceability |
| `Purchase` | `PurchaseLine` | Deleting a purchase would silently wipe all line items, breaking cost traceability |
| `GLJournalEntry` | `GLJournalLine` | Deleting a journal entry would erase the entire double-entry record, breaking GAAP compliance |

**Rules applied:**
1. No financial records are deleted.
2. No cascade delete is added.
3. `ON DELETE RESTRICT` is preferred.
4. Only confirmed unsafe relationships are fixed.
5. Safe Alembic migration with full rollback support.

---

## 2. Changes Made

### 2.1 Model Changes

#### `models/sale.py`
- **ORM:** Removed `cascade='all, delete-orphan'` from `Sale.lines` relationship
- **DB:** Changed `sale_id` ForeignKey to `db.ForeignKey('sales.id', ondelete='RESTRICT')`

```python
# Before
lines = db.relationship('SaleLine', back_populates='sale', lazy='joined', cascade='all, delete-orphan')
sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)

# After
lines = db.relationship('SaleLine', back_populates='sale', lazy='joined')
sale_id = db.Column(db.Integer, db.ForeignKey('sales.id', ondelete='RESTRICT'), nullable=False, index=True)
```

#### `models/purchase.py`
- **ORM:** Removed `cascade='all, delete-orphan'` from `Purchase.lines` relationship
- **DB:** Changed `purchase_id` ForeignKey to `db.ForeignKey('purchases.id', ondelete='RESTRICT')`

```python
# Before
lines = db.relationship('PurchaseLine', back_populates='purchase', lazy='joined', cascade='all, delete-orphan')
purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=False, index=True)

# After
lines = db.relationship('PurchaseLine', back_populates='purchase', lazy='joined')
purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id', ondelete='RESTRICT'), nullable=False, index=True)
```

#### `models/gl.py`
- **ORM:** Removed `cascade='all, delete-orphan'` from `GLJournalEntry.lines` relationship
- **DB:** Changed `entry_id` ForeignKey to `db.ForeignKey('gl_journal_entries.id', ondelete='RESTRICT')`

```python
# Before
lines = db.relationship('GLJournalLine', back_populates='entry', lazy='dynamic', cascade='all, delete-orphan')
entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), nullable=False, index=True)

# After
lines = db.relationship('GLJournalLine', back_populates='entry', lazy='dynamic')
entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id', ondelete='RESTRICT'), nullable=False, index=True)
```

### 2.2 Database Migration

**File:** `migrations/versions/batch_3_001_financial_relationship_safety.py`

**Upgrade path:**
1. Drop existing FK `fk_sale_lines_sale_id_sales` → recreate with `ON DELETE RESTRICT`
2. Drop existing FK `fk_purchase_lines_purchase_id_purchases` → recreate with `ON DELETE RESTRICT`
3. Drop existing FK `fk_gl_journal_lines_entry_id_gl_journal_entries` → recreate with `ON DELETE RESTRICT`

**Downgrade path:**
1. Drop RESTRICT FKs → recreate with default `NO ACTION`

**Migration chain:**
```
partner_system_001 → batch_3_001 (head)
```

---

## 3. Verification

### 3.1 PostgreSQL Constraint Inspection

Query:
```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname IN (
    'fk_sale_lines_sale_id_sales',
    'fk_purchase_lines_purchase_id_purchases',
    'fk_gl_journal_lines_entry_id_gl_journal_entries'
);
```

**Results:**

| Constraint Name | Definition |
|-----------------|------------|
| `fk_sale_lines_sale_id_sales` | `FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE RESTRICT` |
| `fk_purchase_lines_purchase_id_purchases` | `FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE RESTRICT` |
| `fk_gl_journal_lines_entry_id_gl_journal_entries` | `FOREIGN KEY (entry_id) REFERENCES gl_journal_entries(id) ON DELETE RESTRICT` |

### 3.2 Application Load Test

- **Test:** `python -c "from app import create_app; app = create_app()"`
- **Result:** `OK: App loads after Batch 3 changes`
- **Status:** PASSED

### 3.3 Behavioral Impact

| Operation | Before (Unsafe) | After (Safe) |
|-----------|-------------------|--------------|
| `db.session.delete(sale)` with lines | Silently deletes all SaleLines | Raises `IntegrityError` (RESTRICT) |
| `db.session.delete(purchase)` with lines | Silently deletes all PurchaseLines | Raises `IntegrityError` (RESTRICT) |
| `db.session.delete(entry)` with lines | Silently deletes all GLJournalLines | Raises `IntegrityError` (RESTRICT) |

**Note:** The application routes (`sales.py`, `purchases.py`) already handle deletion via explicit line deletion (`SaleLine.query.filter_by(sale_id=...).delete()`) followed by parent deletion, OR archiving when financial links exist. The RESTRICT constraint acts as a **safety net** for any direct `db.session.delete()` calls in code, tests, or scripts.

---

## 4. Remaining ORM Cascades (Intentionally Preserved)

The following `cascade='all, delete-orphan'` relationships were **intentionally NOT changed** in Batch 3 because they are non-financial or auxiliary:

| Parent | Child | Reason for Preservation |
|--------|-------|--------------------------|
| `Product` | `ProductPartner` | Product-level partner share config; not financial history |
| `Partner` | `PartnerProfitDistribution` | Partner lifecycle-owned distributions |
| `Partner` | `PartnerTransaction` | Partner lifecycle-owned transactions |
| `FixedAsset` | `DepreciationSchedule` | Asset lifecycle schedules |
| `Budget` | `BudgetLine` | Budget planning lines (not posted transactions) |
| `BankReconciliation` | `BankReconciliationItem` | Reconciliation worksheet items |
| `ProductReturn` | `ProductReturnLine` | Return document lines (handled via voiding workflow) |

These may be addressed in future batches if they are confirmed to hold financial audit value.

---

## 5. Recommendations

1. **Batch 4:** Completed. Missing secondary indexes on high-traffic FK join columns were added in `batch_4_001`.
2. **Batch 5:** Completed. Confirmed model/database nullability mismatches were fixed in `batch_5_001`.
3. **Future Hardening:** Consider applying `ON DELETE RESTRICT` to `Payment.sale_id` and `Receipt.customer_id` if the business logic requires preventing deletion of paid sales or customers with receipts.

---

*Report generated: June 4, 2026*
