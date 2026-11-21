"""Close the tenant-isolation gap on the money/identity child tables.

Only ``gl_journal_lines`` currently carries composite tenant FKs (see
``h2i3j4k5l6m10``). Roughly 530 other tenant-scoped child tables rely on the
ORM's ``tenant_query()`` guard alone; a raw SQL write or a restored backup can
point a child at another tenant's parent and the single-column FK happily
accepts it because the id exists — in another tenant.

This migration adds composite ``(tenant_id, parent_id) -> parent(tenant_id, id)``
FKs to the child tables where a wrong-tenant parent corrupts *money* or
*statutory evidence*, and adds the ``UNIQUE (tenant_id, id)`` anchors those FKs
need on the parent tables (none of the parents below had one).

Selection criteria — kept deliberately to 15 constraints, not all ~530:
  1. Statutory tax evidence: ``e_invoices`` -> sales / maintenance_invoices.
     A wrong-tenant link attaches one tenant's UBL/QR artifact to another's
     document.
  2. Counterparty money (AR/AP): ``payments``, ``receipts`` and ``cheques``
     -> customers / suppliers. These drive the customer and supplier balances,
     so a cross-tenant parent silently moves money between ledgers.
  3. Bank money: ``bank_reconciliations.bank_account_id`` -> gl_accounts and
     ``bank_reconciliation_items.reconciliation_id`` -> bank_reconciliations.
  4. Workshop money: ``maintenance_invoices`` / ``maintenance_receipts``
     -> maintenance_orders.
  5. Drawer money: ``pos_shifts`` / ``pos_carts`` / ``pos_cash_movements``
     -> pos_sessions (and cash movements -> pos_shifts).
  6. Monetary lines / vault: ``sale_lines`` -> sales and
     ``payment_transactions`` -> payment_vault.

Deliberately out of scope: configuration, catalogues, telemetry, and the
user/branch FKs — lower blast radius, and they can be added by a later
migration using the same helpers.

NOT VALID, idempotent and PostgreSQL-only, matching ``h2i3j4k5l6m10``:
historical drift never blocks a deploy, every subsequent write is checked,
constraints are guarded by ``pg_constraint`` so re-runs are no-ops, and SQLite
degrades safely (a fresh SQLite DB gets such guarantees from model metadata,
not from an in-place ALTER). ``ON DELETE NO ACTION`` is intentional: these
composite FKs include the NOT NULL ``tenant_id`` column, so ``SET NULL`` is
impossible, and unlike ``RESTRICT`` the ``NO ACTION`` check is deferred to the
end of the statement — letting the pre-existing single-column ``SET NULL`` /
``CASCADE`` actions (e-invoice links, POS carts, maintenance cascade) run first
without changing deletion semantics.

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-11-21 01:00:00.000000

"""

from alembic import op

revision = "q5r6s7t8u9v0"
down_revision = "p4q5r6s7t8u9"
branch_labels = None
depends_on = None

# (parent_table, anchor_constraint_name). The gl_accounts anchor already
# exists (created by h2i3j4k5l6m10) and is intentionally not listed here.
_UNIQUE_ANCHORS = (
    ("sales", "uq_sales_tenant_id"),
    ("maintenance_invoices", "uq_maintenance_invoices_tenant_id"),
    ("bank_reconciliations", "uq_bank_reconciliations_tenant_id"),
    ("customers", "uq_customers_tenant_id"),
    ("suppliers", "uq_suppliers_tenant_id"),
    ("maintenance_orders", "uq_maintenance_orders_tenant_id"),
    ("pos_sessions", "uq_pos_sessions_tenant_id"),
    ("pos_shifts", "uq_pos_shifts_tenant_id"),
    ("payment_vault", "uq_payment_vault_tenant_id"),
)

# (child_table, child_column, parent_table, constraint_name)
_COMPOSITE_FKS = (
    ("e_invoices", "sale_id", "sales", "fk_e_invoices_tenant_sale_composite"),
    (
        "e_invoices",
        "maintenance_invoice_id",
        "maintenance_invoices",
        "fk_e_invoices_tenant_maintenance_invoice_composite",
    ),
    (
        "bank_reconciliations",
        "bank_account_id",
        "gl_accounts",
        "fk_bank_reconciliations_tenant_account_composite",
    ),
    (
        "bank_reconciliation_items",
        "reconciliation_id",
        "bank_reconciliations",
        "fk_bank_reconciliation_items_tenant_reconciliation_composite",
    ),
    ("cheques", "customer_id", "customers", "fk_cheques_tenant_customer_composite"),
    ("cheques", "supplier_id", "suppliers", "fk_cheques_tenant_supplier_composite"),
    ("payments", "customer_id", "customers", "fk_payments_tenant_customer_composite"),
    ("receipts", "customer_id", "customers", "fk_receipts_tenant_customer_composite"),
    (
        "maintenance_invoices",
        "order_id",
        "maintenance_orders",
        "fk_maintenance_invoices_tenant_order_composite",
    ),
    (
        "maintenance_receipts",
        "order_id",
        "maintenance_orders",
        "fk_maintenance_receipts_tenant_order_composite",
    ),
    ("pos_shifts", "session_id", "pos_sessions", "fk_pos_shifts_tenant_session_composite"),
    ("pos_carts", "session_id", "pos_sessions", "fk_pos_carts_tenant_session_composite"),
    (
        "pos_cash_movements",
        "shift_id",
        "pos_shifts",
        "fk_pos_cash_movements_tenant_shift_composite",
    ),
    ("sale_lines", "sale_id", "sales", "fk_sale_lines_tenant_sale_composite"),
    (
        "payment_transactions",
        "vault_id",
        "payment_vault",
        "fk_payment_transactions_tenant_vault_composite",
    ),
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

    # The gl_accounts anchor belongs to h2i3j4k5l6m10 and is never dropped here.
    for table, name in reversed(_UNIQUE_ANCHORS):
        op.execute(_drop_guard(table, name))
