"""add_performance_indexes_round1

Revision ID: perf_idx_round1_001
Revises: store_init_005
Create Date: 2026-06-01 12:00:00.000000

For large production databases, consider creating equivalent indexes
concurrently in a maintenance window (CREATE INDEX CONCURRENTLY outside
a transactional Alembic upgrade).
"""
from alembic import op
import sqlalchemy as sa


revision = "perf_idx_round1_001"
down_revision = "store_init_005"
branch_labels = None
depends_on = None


# (index_name, table_name, columns, postgresql_ops for DESC)
PERFORMANCE_INDEXES = [
    (
        "ix_stock_movements_tenant_product_created",
        "stock_movements",
        ["tenant_id", "product_id", "created_at"],
        {"created_at": "DESC"},
    ),
    (
        "ix_stock_movements_tenant_warehouse_created",
        "stock_movements",
        ["tenant_id", "warehouse_id", "created_at"],
        {"created_at": "DESC"},
    ),
    (
        "ix_sales_tenant_sale_date",
        "sales",
        ["tenant_id", "sale_date"],
        {"sale_date": "DESC"},
    ),
    ("ix_sale_lines_product_id", "sale_lines", ["product_id"], None),
    ("ix_purchase_lines_product_id", "purchase_lines", ["product_id"], None),
    (
        "ix_gl_journal_entries_tenant_entry_date",
        "gl_journal_entries",
        ["tenant_id", "entry_date"],
        {"entry_date": "DESC"},
    ),
    (
        "ix_gl_journal_lines_tenant_account",
        "gl_journal_lines",
        ["tenant_id", "account_id"],
        None,
    ),
    (
        "ix_partner_commission_entries_tenant_product",
        "partner_commission_entries",
        ["tenant_id", "product_id"],
        None,
    ),
]


def _existing_public_indexes(connection):
    rows = connection.execute(
        sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    ).fetchall()
    return {r[0] for r in rows}


def upgrade():
    bind = op.get_bind()
    existing = _existing_public_indexes(bind)
    for name, table, columns, pg_ops in PERFORMANCE_INDEXES:
        if name in existing:
            continue
        kwargs = {}
        if pg_ops:
            kwargs["postgresql_ops"] = pg_ops
        op.create_index(name, table, columns, unique=False, **kwargs)


def downgrade():
    for name, _table, _columns, _pg_ops in reversed(PERFORMANCE_INDEXES):
        op.drop_index(name, table_name=_table)
