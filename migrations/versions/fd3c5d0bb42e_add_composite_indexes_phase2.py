"""add_composite_indexes_phase2

Revision ID: fd3c5d0bb42e
Revises: f0d6a3c015ab
Create Date: 2026-08-21 01:08:49.600231

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'fd3c5d0bb42e'
down_revision = 'f0d6a3c015ab'
branch_labels = None
depends_on = None


# Composite indexes to add. Tuple: (table, index_name, columns, unique)
NEW_INDEXES = [
    ("payments", "idx_payments_tenant_sale_date", ["tenant_id", "sale_id", "payment_date"], False),
    ("payments", "idx_payments_tenant_purchase_date", ["tenant_id", "purchase_id", "payment_date"], False),
    ("payments", "idx_payments_tenant_customer_date", ["tenant_id", "customer_id", "payment_date", "payment_confirmed"], False),
    ("payments", "idx_payments_tenant_supplier_date", ["tenant_id", "supplier_id", "payment_date", "payment_confirmed"], False),
    ("purchases", "idx_purchases_tenant_supplier_date", ["tenant_id", "supplier_id", "purchase_date"], False),
    ("purchases", "idx_purchases_tenant_status_date", ["tenant_id", "status", "purchase_date"], False),
    ("stock_movements", "idx_stock_movements_tenant_product_warehouse_date", ["tenant_id", "product_id", "warehouse_id", "created_at"], False),
    ("gl_journal_entries", "idx_gl_entries_tenant_date_status", ["tenant_id", "entry_date", "status"], False),
    ("gl_journal_lines", "idx_gl_lines_tenant_account_entry", ["tenant_id", "account_id", "entry_id"], False),
    ("audit_logs", "idx_audit_logs_tenant_table_created", ["tenant_id", "table_name", "created_at"], False),
    ("audit_logs", "idx_audit_logs_tenant_action_created", ["tenant_id", "action", "created_at"], False),
    ("sales", "idx_sales_tenant_pos_session", ["tenant_id", "pos_session_id"], False),
    ("pos_cash_movements", "idx_pos_cash_movements_tenant_shift_session", ["tenant_id", "shift_id", "session_id"], False),
    ("cheques", "idx_cheques_tenant_status_due_date", ["tenant_id", "status", "due_date"], False),
]


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return index_name in [idx["name"] for idx in insp.get_indexes(table)]


def upgrade():
    for table, index_name, columns, unique in NEW_INDEXES:
        if not _table_exists(table):
            continue
        if not all(_column_exists(table, c) for c in columns):
            continue
        if _index_exists(table, index_name):
            continue
        op.create_index(index_name, table, columns, unique=unique)


def downgrade():
    for table, index_name, _, _ in NEW_INDEXES:
        if not _table_exists(table):
            continue
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)
