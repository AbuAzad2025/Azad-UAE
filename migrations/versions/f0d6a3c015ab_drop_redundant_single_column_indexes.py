"""drop_redundant_single_column_indexes

Revision ID: f0d6a3c015ab
Revises: 15b4a5a98444
Create Date: 2026-08-21 01:08:08.288176

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f0d6a3c015ab"
down_revision = "15b4a5a98444"
branch_labels = None
depends_on = None


# Indexes to drop where a composite already covers the leading/access path.
# Document-number single indexes are intentionally omitted to avoid breaking
# any non-tenant-scoped lookups.
INDEXES_TO_DROP = [
    ("customers", "ix_customers_name"),
    ("gl_accounts", "ix_gl_accounts_code"),
    ("product_warehouse_costs", "ix_product_warehouse_costs_tenant_id"),
    ("product_warehouse_costs", "ix_product_warehouse_costs_product_id"),
    ("product_warehouse_costs", "ix_product_warehouse_costs_warehouse_id"),
    ("product_warehouse_stock", "ix_product_warehouse_stock_tenant_id"),
    ("product_warehouse_stock", "ix_product_warehouse_stock_product_id"),
    ("product_warehouse_stock", "ix_product_warehouse_stock_warehouse_id"),
]


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return index_name in [idx["name"] for idx in insp.get_indexes(table)]


def upgrade():
    for table, index_name in INDEXES_TO_DROP:
        if not _table_exists(table):
            continue
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)


def downgrade():
    # Re-create the dropped single-column indexes.
    # Note: product_warehouse_* composite unique constraints still exist; these
    # single-column indexes are additional, not conflicting.
    recreate = [
        ("customers", "ix_customers_name", ["name"], False),
        ("gl_accounts", "ix_gl_accounts_code", ["code"], False),
        ("product_warehouse_costs", "ix_product_warehouse_costs_tenant_id", ["tenant_id"], False),
        ("product_warehouse_costs", "ix_product_warehouse_costs_product_id", ["product_id"], False),
        ("product_warehouse_costs", "ix_product_warehouse_costs_warehouse_id", ["warehouse_id"], False),
        ("product_warehouse_stock", "ix_product_warehouse_stock_tenant_id", ["tenant_id"], False),
        ("product_warehouse_stock", "ix_product_warehouse_stock_product_id", ["product_id"], False),
        ("product_warehouse_stock", "ix_product_warehouse_stock_warehouse_id", ["warehouse_id"], False),
    ]
    for table, index_name, columns, unique in recreate:
        if not _table_exists(table):
            continue
        if not _index_exists(table, index_name):
            op.create_index(index_name, table, columns, unique=unique)
