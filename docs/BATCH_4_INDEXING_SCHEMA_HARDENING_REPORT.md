# Batch 4: Indexing & Schema Hardening Report

**Date:** June 4, 2026  
**Status:** COMPLETED  
**Author:** Cascade (AI Pair Programmer)

---

## 1. Executive Summary

Batch 4 addressed missing secondary indexes on high-traffic Foreign Key (FK) columns. PostgreSQL does **not** automatically create indexes on FK columns — they must be added manually for efficient JOINs and constraint lookups. This batch identified and fixed 10 such gaps across financial and operational tables.

**Methodology:**
1. Queried `information_schema.table_constraints` for all FK relationships.
2. Queried `pg_index` / `pg_class` for existing indexes.
3. Compared the two sets to find FK columns lacking index support.
4. Added `index=True` to model definitions and created a safe Alembic migration.

**Zero data changes.** Only index metadata was added.

---

## 2. Missing Indexes Identified

| # | Table | Column | References | Query Impact |
|---|-------|--------|------------|--------------|
| 1 | `sales` | `seller_id` | `users.id` | Sales-by-seller reports, commission calculations |
| 2 | `purchases` | `user_id` | `users.id` | Purchase audit trails, user activity logs |
| 3 | `payments` | `user_id` | `users.id` | Payment audit trails, cashier reconciliation |
| 4 | `receipts` | `user_id` | `users.id` | Receipt audit trails, cashier reconciliation |
| 5 | `expenses` | `user_id` | `users.id` | Expense approval workflows, user tracking |
| 6 | `cheques` | `user_id` | `users.id` | Cheque issuance tracking, user audit |
| 7 | `stock_movements` | `user_id` | `users.id` | Inventory movement audit, user accountability |
| 8 | `gl_journal_lines` | `cost_center_id` | `cost_centers.id` | Cost center reporting, departmental P&L |
| 9 | `product_returns` | `customer_id` | `customers.id` | Customer return history, CRM lookups |
| 10 | `product_returns` | `processed_by` | `users.id` | Return processing audit, staff performance |

---

## 3. Changes Made

### 3.1 Model Updates

Added `index=True` to the following columns:

| File | Line | Change |
|------|------|--------|
| `models/sale.py` | 21 | `seller_id = db.Column(..., index=True)` |
| `models/purchase.py` | 49 | `user_id = db.Column(..., index=True)` |
| `models/payment.py` | 65 | `user_id = db.Column(..., index=True)` (Payment) |
| `models/payment.py` | 198 | `user_id = db.Column(..., index=True)` (Receipt) |
| `models/expense.py` | 56 | `user_id = db.Column(..., index=True)` |
| `models/cheque.py` | 112 | `user_id = db.Column(..., index=True)` |
| `models/warehouse.py` | 65 | `user_id = db.Column(..., index=True)` (StockMovement) |
| `models/gl.py` | 224 | `cost_center_id = db.Column(..., index=True)` |
| `models/product_return.py` | 17 | `customer_id = db.Column(..., index=True)` |
| `models/product_return.py` | 43 | `processed_by = db.Column(..., index=True)` |

### 3.2 Database Migration

**File:** `migrations/versions/batch_4_001_add_missing_fk_indexes.py`

**Upgrade:** Creates 10 `CREATE INDEX` statements.

**Downgrade:** Drops all 10 indexes via `DROP INDEX`.

**Migration chain:**
```
batch_3_001 → batch_4_001 (head)
```

---

## 4. Verification

### 4.1 PostgreSQL Index Inspection

Query:
```sql
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname LIKE 'ix_%';
```

**Results — All 10 indexes confirmed:**

| Table | Index Name |
|-------|------------|
| `sales` | `ix_sales_seller_id` |
| `purchases` | `ix_purchases_user_id` |
| `payments` | `ix_payments_user_id` |
| `receipts` | `ix_receipts_user_id` |
| `expenses` | `ix_expenses_user_id` |
| `cheques` | `ix_cheques_user_id` |
| `stock_movements` | `ix_stock_movements_user_id` |
| `gl_journal_lines` | `ix_gl_journal_lines_cost_center_id` |
| `product_returns` | `ix_product_returns_customer_id` |
| `product_returns` | `ix_product_returns_processed_by` |

**Total confirmed:** 10 / 10 ✅

### 4.2 Application Load Test

- **Test:** `python -c "from app import create_app; app = create_app()"`
- **Result:** `OK: App loads after Batch 4 model changes`
- **Status:** PASSED

### 4.3 Migration Test

- **Test:** `flask db upgrade batch_4_001`
- **Result:** `Running upgrade batch_3_001 -> batch_4_001, add_missing_fk_indexes`
- **Status:** PASSED

---

## 5. Performance Impact

**Expected improvements:**

| Query Pattern | Before | After |
|---------------|--------|-------|
| `SELECT * FROM sales WHERE seller_id = ?` | Seq Scan | Index Scan |
| `SELECT * FROM payments WHERE user_id = ?` | Seq Scan | Index Scan |
| `SELECT * FROM gl_journal_lines WHERE cost_center_id = ?` | Seq Scan | Index Scan |
| JOIN `sales` → `users` on `seller_id` | Nested Loop + Seq Scan | Nested Loop + Index Scan |
| JOIN `payments` → `users` on `user_id` | Nested Loop + Seq Scan | Nested Loop + Index Scan |

**Note:** Exact improvement depends on table size and PostgreSQL query planner statistics. Running `ANALYZE` on affected tables after deployment is recommended.

---

## 6. Recommendations

1. **Batch 5:** Completed. Confirmed model/database nullability mismatches were fixed in `batch_5_001`.
2. **Post-Deployment:** Run `ANALYZE` on affected tables to update PostgreSQL statistics:
   ```sql
   ANALYZE sales, purchases, payments, receipts, expenses, cheques, stock_movements, gl_journal_lines, product_returns;
   ```
3. **Future Monitoring:** Use `pg_stat_user_indexes` to confirm index usage in production and identify additional missing indexes.

---

*Report generated: June 4, 2026*
