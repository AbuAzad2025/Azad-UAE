"""Second focused batch of composite tenant FKs on money/identity tables.

The first batch (``q5r6s7t8u9v0``) covered the highest-value money tables:
statutory e-invoice links, AR/AP counterparties, bank reconciliation, workshop
money, drawer money and the sale/vault monetary lines. Roughly 500 other
tenant-scoped child tables still rely on the ORM's ``tenant_query()`` guard
alone; a raw SQL write or a restored backup can point a child at another
tenant's parent and the single-column FK happily accepts it because the id
exists — in another tenant.

This revision covers the next-highest-value tables, where a wrong-tenant
parent corrupts money or statutory evidence:

Selection criteria — kept to 16 FKs + 8 anchors (24 constraints), not all 500:
  1. Procurement money: ``purchase_lines`` -> purchases,
     ``purchase_order_lines`` -> purchase_orders and
     ``purchases.supplier_id`` -> suppliers (AP) — a wrong-tenant purchase
     line attaches cost and landed cost to another tenant's invoice.
  2. Sales-side reversals: ``product_returns`` -> sales/customers (AR) and
     ``product_return_lines`` -> product_returns — a cross-tenant return
     credits the wrong receivable and reverses the wrong COGS.
  3. Expense money: ``expenses.category_id`` -> expense_categories — the
     category owns the GL posting concept, so a wrong-tenant category posts
     the expense to another tenant's chart.
  4. Partner money: ``partner_transactions`` / ``partner_profit_distributions``
     -> partners and ``partner_commission_entries`` -> sales — these drive the
     partner running balance and the commission payable.
  5. Campaign money: ``sale_campaigns`` -> campaigns/sales — discount amounts
     must belong to the same tenant as their campaign and invoice.
  6. Stock valuation: ``product_warehouse_costs`` (the MWAC ledger) and
     ``stock_movements`` -> products/warehouses — a wrong-tenant valuation row
     corrupts every part issued at that warehouse's moving average.

Before adding a composite ``(tenant_id, parent_id) -> parent(tenant_id, id)``
FK, the parent must have a ``UNIQUE (tenant_id, id)`` anchor. The parents
already anchored by ``h2i3j4k5l6m10`` (gl_accounts, gl_journal_entries) and
``q5r6s7t8u9v0`` (sales, customers, suppliers, maintenance orders/invoices,
bank reconciliations, POS sessions/shifts, payment_vault) are reused as-is.
Every other parent below has no such anchor in the chain, so this migration
adds one — verified against the live model metadata by
``tests/unit/models/test_schema_parity_migrations.py``.

Deliberately out of scope: configuration, catalogues, telemetry, and the
user/branch FKs — lower blast radius, and they can be added by a later
migration using the same helpers.

NOT VALID, idempotent and PostgreSQL-only, matching the two earlier batches:
historical drift never blocks a deploy, every subsequent write is checked,
constraints are guarded by ``pg_constraint`` so re-runs are no-ops, and SQLite
degrades safely (a fresh SQLite DB gets such guarantees from model metadata,
not from an in-place ALTER). ``ON DELETE NO ACTION`` is intentional: these
composite FKs include the NOT NULL ``tenant_id`` column, so ``SET NULL`` is
impossible, and unlike ``RESTRICT`` the ``NO ACTION`` check is deferred to the
end of the statement — letting the pre-existing single-column ``CASCADE`` /
``SET NULL`` actions run first without changing deletion semantics.

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-11-21 02:00:00.000000

"""

from alembic import op

revision = "r6s7t8u9v0w1"
down_revision = "q5r6s7t8u9v0"
branch_labels = None
depends_on = None

# (parent_table, anchor_constraint_name). Parents already anchored by
# h2i3j4k5l6m10 or q5r6s7t8u9v0 are intentionally not listed here.
_UNIQUE_ANCHORS = (
    ("purchases", "uq_purchases_tenant_id"),
    ("purchase_orders", "uq_purchase_orders_tenant_id"),
    ("product_returns", "uq_product_returns_tenant_id"),
    ("expense_categories", "uq_expense_categories_tenant_id"),
    ("partners", "uq_partners_tenant_id"),
    ("campaigns", "uq_campaigns_tenant_id"),
    ("products", "uq_products_tenant_id"),
    ("warehouses", "uq_warehouses_tenant_id"),
)

# (child_table, child_column, parent_table, constraint_name)
_COMPOSITE_FKS = (
    ("purchase_lines", "purchase_id", "purchases", "fk_purchase_lines_tenant_purchase_composite"),
    ("purchase_order_lines", "po_id", "purchase_orders", "fk_purchase_order_lines_tenant_po_composite"),
    ("purchases", "supplier_id", "suppliers", "fk_purchases_tenant_supplier_composite"),
    ("product_returns", "sale_id", "sales", "fk_product_returns_tenant_sale_composite"),
    ("product_returns", "customer_id", "customers", "fk_product_returns_tenant_customer_composite"),
    ("product_return_lines", "return_id", "product_returns", "fk_product_return_lines_tenant_return_composite"),
    ("expenses", "category_id", "expense_categories", "fk_expenses_tenant_category_composite"),
    ("partner_transactions", "partner_id", "partners", "fk_partner_transactions_tenant_partner_composite"),
    (
        "partner_profit_distributions",
        "partner_id",
        "partners",
        "fk_partner_distributions_tenant_partner_composite",
    ),
    ("partner_commission_entries", "sale_id", "sales", "fk_partner_commissions_tenant_sale_composite"),
    ("sale_campaigns", "campaign_id", "campaigns", "fk_sale_campaigns_tenant_campaign_composite"),
    ("sale_campaigns", "sale_id", "sales", "fk_sale_campaigns_tenant_sale_composite"),
    ("product_warehouse_costs", "product_id", "products", "fk_pwc_tenant_product_composite"),
    ("product_warehouse_costs", "warehouse_id", "warehouses", "fk_pwc_tenant_warehouse_composite"),
    ("stock_movements", "product_id", "products", "fk_stock_movements_tenant_product_composite"),
    ("stock_movements", "warehouse_id", "warehouses", "fk_stock_movements_tenant_warehouse_composite"),
)


def _add_guard(name: str, ddl: str) -> str:
    return (
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN {ddl}; END IF; END $$;"
    )


def _drop_guard(table: str, name: str) -> str:
    return (
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') "
        f"THEN ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}; END IF; END $$;"
    )


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite cannot add constraints to an existing table; a fresh SQLite
        # database receives them from db.metadata instead.
        return

    # Anchors first: a composite FK needs UNIQUE (tenant_id, id) on the parent.
    for table, name in _UNIQUE_ANCHORS:
        op.execute(
            _add_guard(
                name,
                f"ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE (tenant_id, id)",
            )
        )

    for table, column, parent, name in _COMPOSITE_FKS:
        op.execute(
            _add_guard(
                name,
                f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                f"FOREIGN KEY (tenant_id, {column}) REFERENCES {parent} (tenant_id, id) "
                "ON DELETE NO ACTION NOT VALID",
            )
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, _column, _parent, name in reversed(_COMPOSITE_FKS):
        op.execute(_drop_guard(table, name))

    # Anchors from h2i3j4k5l6m10 and q5r6s7t8u9v0 belong to those revisions
    # and are never dropped here; only the ones declared above are ours.
    for table, name in reversed(_UNIQUE_ANCHORS):
        op.execute(_drop_guard(table, name))
