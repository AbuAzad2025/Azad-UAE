Subject: Inventory, Products & Warehouses — Critical Design Flaws Found

Dr. AI,

I have completed a deep manual audit of the Azad ERP inventory, product, warehouse, and branch management system. The full technical report is in:

  docs/inventory-audit-report.md

I found 9 critical issues including a fundamental design contradiction that makes per-warehouse stock tracking unreliable.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — Fix Architecture (Highest Priority)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A1  CREATE ProductWarehouseStock model
    New table: product_warehouse_stock
    Columns: id, tenant_id, product_id, warehouse_id, quantity, updated_at
    Unique: (tenant_id, product_id, warehouse_id)
    Replace ALL reads of Product.current_stock with a query to this table.

A2  REPLACE Product.current_stock with computed property
    In models/product.py:
      - Keep column for migration compatibility but mark deprecated
      - Add @property current_stock that sums ProductWarehouseStock.quantity
      - Remove setters stock_quantity and quantity_in_stock
    Update ALL callers to use StockService.get_product_stock().

A3  REWRITE StockService.create_movement
    Current: product.current_stock += quantity (global flat field)
    Target:
      - Update ProductWarehouseStock for the specific warehouse
      - If warehouse_id is None: use default warehouse for tenant
      - Auto-create default warehouse WITH tenant_id (not after)
    File: services/stock_service.py

A4  ADD stock reconciliation command
    New: flask reconcile-stock
    Compares ProductWarehouseStock.quantity with sum(StockMovement) per warehouse
    Reports mismatches. Can auto-fix with --commit.
    File: cli_commands.py or scripts/reconcile_stock.py

A5  FIX default warehouse creation (tenant leak)
    Current in stock_service.py:114:
      warehouse = Warehouse(name='Main Warehouse', ...)
      # tenant_id assigned AFTER flush
    Fix:
      warehouse = Warehouse(name='Main Warehouse', tenant_id=tenant_id, ...)
      tenant_id MUST be known before creation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 — Fix Business Logic
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

B1  RENAME price columns to reflect actual behavior
    Current: merchant_price, partner_price (treated as percentage discounts)
    Target: merchant_discount_pct, partner_discount_pct
    Or: Fix the logic to treat them as absolute prices (breaking change).
    Decision needed from user.

B2  ADD partner percentage sum validation
    In routes/products.py _parse_product_partners:
      if total > 100:
          return None, 'Total partner share cannot exceed 100%'

B3  MAKE GL accounts dynamic
    In services/stock_service.py _post_adjustment_gl:
      Replace hardcoded '5150' and '1140' with:
        GLService.resolve_account_by_concept('INVENTORY_ADJUSTMENT_LOSS')
        GLService.resolve_account_by_concept('INVENTORY_ASSET')

B4  ENFORCE branch scope on product edit
    In routes/products.py:
      _ensure_product_scope should check if user is branch-scoped
      and if the product is linked to their branch via warehouse.
    Or: Add branch_id to Product (if business requires branch-specific products).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 3 — UI & Reporting
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

C1  UPDATE warehouse/index.html
    Show per-warehouse stock from ProductWarehouseStock instead of visible_stock hack.

C2  UPDATE products/index.html
    Show warehouse-wise stock breakdown (expandable row).

C3  UPDATE POS product search
    Filter products by stock availability in the user's assigned warehouse.

C4  ADD stock alert system
    New model: stock_alerts (product_id, warehouse_id, alert_type, threshold, notified_at)
    Alerts: low_stock, out_of_stock, negative_stock

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILES TO MODIFY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Models:
  models/warehouse.py              — add ProductWarehouseStock
  models/product.py              — current_stock as computed property

Services:
  services/stock_service.py      — rewrite create_movement, add reconciliation
  services/gl_service.py         — add resolve_account_by_concept

Routes:
  routes/products.py             — partner validation, branch scope
  routes/warehouse.py            — use ProductWarehouseStock

Templates:
  templates/warehouse/index.html  — per-warehouse stock display
  templates/products/index.html   — warehouse stock breakdown

Scripts:
  scripts/reconcile_stock.py     — NEW
  cli_commands.py                — add reconcile-stock command

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DELIVERABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. All code changes with tests (unit + integration)
2. Migration script for ProductWarehouseStock population
3. Reconciliation report before/after
4. No inline CSS/JS in any touched template
5. Updated docs/inventory-audit-report.md with completion status
6. Report any NEW issues discovered during implementation

Execute Phase A first. Do not start Phase B until Phase A tests pass.
Report completion status per phase.

Proceed.
