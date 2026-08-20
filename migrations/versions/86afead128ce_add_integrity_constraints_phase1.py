"""add_integrity_constraints_phase1

Revision ID: 86afead128ce
Revises: e1f2a3b4c5d6
Create Date: 2026-08-21 01:05:22.001375

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '86afead128ce'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


# Tables where is_active is commonly nullable and should be NOT NULL.
# Backfill NULL -> true, then enforce NOT NULL.
_IS_ACTIVE_TABLES = [
    "products",
    "customers",
    "suppliers",
    "warehouses",
    "branches",
    "cheques",
    "expenses",
    "pos_sessions",
    "pos_shifts",
    "crm_leads",
    "helpdesk_tickets",
    "fixed_assets",
    "expense_categories",
    "campaigns",
    "cost_centers",
    "fiscal_positions",
    "gl_accounts",
]


def _table_exists(name: str) -> bool:
    """Return True if the named table exists in the current database."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    """Return True if the column exists on the table."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def _set_not_null(table: str, column: str, default):
    """Backfill NULL values then set the column NOT NULL, SQLite-safe."""
    if not _table_exists(table) or not _column_exists(table, column):
        return
    op.execute(sa.text(f"UPDATE {table} SET {column} = :default WHERE {column} IS NULL").bindparams(default=default))
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.alter_column(column, existing_nullable=True, nullable=False)


def upgrade():
    # ── 1. CHECK constraints for status/type enums ──────────────────────────
    enum_checks = [
        ("sales", "ck_sales_status", "status", "('draft','confirmed','cancelled','returned')"),
        ("sales", "ck_sales_payment_status", "payment_status", "('unpaid','partial','paid','pending_cheque')"),
        ("purchases", "ck_purchases_status", "status", "('draft','confirmed','cancelled')"),
        ("gl_accounts", "ck_gl_accounts_type", "type", "('asset','liability','equity','revenue','expense')"),
        ("gl_journal_entries", "ck_gl_entries_status", "status", "('draft','validated','posted','reversed','cancelled','error')"),
        ("stock_movements", "ck_stock_movement_type", "movement_type", "('purchase','sale','adjustment','return','damage','transfer')"),
    ]
    for table, name, column, predicate in enum_checks:
        if _table_exists(table) and _column_exists(table, column):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.create_check_constraint(name, sa.text(f"{column} IN {predicate}"))

    # ── 2. Numeric range CHECK constraints ──────────────────────────────────
    numeric_checks = [
        ("sale_lines", "ck_sale_lines_discount_percent", "discount_percent BETWEEN 0 AND 100"),
        ("product_warehouse_stock", "ck_pws_quantity", "quantity >= 0"),
        ("products", "ck_products_regular_price", "regular_price >= 0"),
    ]
    for table, name, predicate in numeric_checks:
        if _table_exists(table):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.create_check_constraint(name, sa.text(predicate))

    # ── 3. Backfill then NOT NULL on core financial columns ─────────────────
    financial_defaults = [
        ("sales", "subtotal", 0),
        ("sales", "discount_amount", 0),
        ("sales", "tax_amount", 0),
        ("sales", "paid_amount", 0),
        ("sales", "balance_due", 0),
        ("purchases", "subtotal", 0),
        ("purchases", "discount_amount", 0),
        ("purchases", "tax_amount", 0),
    ]
    for table, column, default in financial_defaults:
        _set_not_null(table, column, default)

    # Ensure is_active is NOT NULL on key tables (backfill NULL -> true)
    for table in _IS_ACTIVE_TABLES:
        _set_not_null(table, "is_active", True)


def downgrade():
    # Drop is_active NOT NULL (SQLite-safe via batch_alter_table)
    for table in _IS_ACTIVE_TABLES:
        if _table_exists(table) and _column_exists(table, "is_active"):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.alter_column("is_active", existing_nullable=False, nullable=True)

    # Drop financial NOT NULL
    financial_cols = [
        ("sales", "subtotal"),
        ("sales", "discount_amount"),
        ("sales", "tax_amount"),
        ("sales", "paid_amount"),
        ("sales", "balance_due"),
        ("purchases", "subtotal"),
        ("purchases", "discount_amount"),
        ("purchases", "tax_amount"),
    ]
    for table, column in financial_cols:
        if _table_exists(table) and _column_exists(table, column):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.alter_column(column, existing_nullable=False, nullable=True)

    # Drop CHECK constraints
    checks = [
        ("sales", "ck_sales_status"),
        ("sales", "ck_sales_payment_status"),
        ("purchases", "ck_purchases_status"),
        ("gl_accounts", "ck_gl_accounts_type"),
        ("gl_journal_entries", "ck_gl_entries_status"),
        ("stock_movements", "ck_stock_movement_type"),
        ("sale_lines", "ck_sale_lines_discount_percent"),
        ("product_warehouse_stock", "ck_pws_quantity"),
        ("products", "ck_products_regular_price"),
    ]
    for table, name in checks:
        if _table_exists(table):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_constraint(name, type_="check")
