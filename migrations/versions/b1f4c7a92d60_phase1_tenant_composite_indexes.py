"""Phase 1: composite (tenant_id, <filter>) indexes on hot transactional tables.

A tenant-leading index already existed on all 146 tenant-scoped tables, so this
revision deliberately does not re-create that. It adds the *second* column that the
query layer actually filters on, derived from the real call sites instead of
guessed:

* ``status`` is filtered in 64 places, and the core money/document tables had no
  (tenant_id, status) index, so a status filter degraded into a tenant-wide scan.
* newest-first listing per tenant (created_at) is the default read pattern for
  receipts, payments, POS sessions, GL entries and stock movements.
* reference/code/SKU lookups drive three-way match, warehouse, GL account and
  currency resolution.

Every statement is idempotent: an index is created only when its name is absent
from ``pg_indexes``, so re-running the revision is a no-op. The downgrade drops
exactly the names this revision creates and nothing else.

The indexes are built with CREATE INDEX CONCURRENTLY inside an autocommit block,
because concurrent index builds cannot run inside a transaction and a plain
CREATE INDEX would take a write lock on live tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1f4c7a92d60"
down_revision = "e2f7a5b3c9d4"
branch_labels = None
depends_on = None

# (table, column) pairs owned by this revision.
INDEXES: tuple[tuple[str, str], ...] = (
    # (tenant_id, status)
    ("azad_platform_fees", "status"),
    ("budgets", "status"),
    ("card_payments", "status"),
    ("cheques", "status"),
    ("crm_leads", "status"),
    ("donations", "status"),
    ("expenses", "status"),
    ("fixed_assets", "status"),
    ("gl_journal_entries", "status"),
    ("goods_receipts", "status"),
    ("overtime_entries", "status"),
    ("partner_profit_distributions", "status"),
    ("pos_sessions", "status"),
    ("pos_shifts", "status"),
    ("product_returns", "status"),
    ("purchase_orders", "status"),
    ("purchases", "status"),
    ("quotations", "status"),
    ("tickets", "status"),
    ("warranty_claims", "status"),
    # (tenant_id, created_at)
    ("customers", "created_at"),
    ("employees", "created_at"),
    ("error_audit_logs", "created_at"),
    ("leave_requests", "created_at"),
    ("package_purchases", "created_at"),
    ("partner_commission_entries", "created_at"),
    ("payment_transactions", "created_at"),
    ("payment_vault", "created_at"),
    ("payments", "created_at"),
    ("pos_carts", "created_at"),
    ("products", "created_at"),
    ("receipts", "created_at"),
    ("sales", "created_at"),
    ("stock_movements", "created_at"),
    ("suppliers", "created_at"),
    ("warehouses", "created_at"),
    # (tenant_id, <code>)
    ("currencies", "code"),
    ("gl_accounts", "code"),
    ("store_payment_methods", "code"),
    ("tickets", "number"),
    ("warehouses", "code"),
)


def _index_name(table: str, column: str) -> str:
    return f"ix_{table}_tenant_{column}"


def _existing() -> set[str]:
    rows = op.get_bind().execute(sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"))
    return {row[0] for row in rows}


def _resolvable() -> set[tuple[str, str]]:
    """Pairs whose table actually exists in this schema and carries both columns.

    A migration must not assume the final shape of a table: earlier revisions in
    this chain add, rename and drop columns (for example the package_purchases
    tenant_id rework), so a hard-coded CREATE INDEX would abort the whole upgrade
    on a table that is not shaped the way the models describe it today. Anything
    that cannot be verified is skipped instead of failing the deployment.
    """
    rows = op.get_bind().execute(
        sa.text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
            """
        )
    )
    columns: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        columns.setdefault(table_name, set()).add(column_name)
    return {(table, column) for table, column in INDEXES if {"tenant_id", column} <= columns.get(table, set())}


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY is not allowed inside a transaction
    with op.get_context().autocommit_block():
        existing = _existing()
        for table, column in _resolvable():
            name = _index_name(table, column)
            if name in existing:
                continue
            op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" ON "{table}" (tenant_id, "{column}")')


def downgrade() -> None:
    with op.get_context().autocommit_block():
        existing = _existing()
        for table, column in INDEXES:
            name = _index_name(table, column)
            if name in existing:
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
