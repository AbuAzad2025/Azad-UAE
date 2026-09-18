"""fix base_currency AED drift D09

Revision ID: b8c4d2e1a5f6
Revises: a9f3e2d1c4b7
Create Date: 2026-09-18

D09: migrations set server_default="AED" for base_currency, drifting from the
deployment fallback (ILS / regional_defaults.FALLBACK_CURRENCY). This migration:
  1) backfills rows where base_currency='AED' but the owning tenant's real
     base_currency is not AED,
  2) drops the DB server_default (or sets it to ILS) on every table that
     carries base_currency.

Tables covered: expenses, payments, product_returns, purchases, receipts,
sales, quotations, purchase_returns (added by D07). Handles both PostgreSQL
and SQLite via batch_alter_table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "b8c4d2e1a5f6"
down_revision = "a9f3e2d1c4b7"
branch_labels = None
depends_on = None

# Tables that historically received server_default="AED" for base_currency
BASE_CURRENCY_TABLES = [
    "expenses",
    "payments",
    "product_returns",
    "purchases",
    "receipts",
    "sales",
    "quotations",
    "purchase_returns",
]


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False


def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        return insp.has_table(table)
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()

    # 1. Backfill AED -> tenant's real base_currency where drift exists.
    # Use correlated subquery for SQLite/Postgres portablity.
    for table in BASE_CURRENCY_TABLES:
        if not _table_exists(table):
            continue
        if not _column_exists(table, "base_currency"):
            continue
        conn.execute(
            text(
                f"""
                UPDATE {table}
                SET base_currency = (
                    SELECT COALESCE(NULLIF(t.base_currency, ''), NULLIF(t.default_currency, ''), 'ILS')
                    FROM tenants t WHERE t.id = {table}.tenant_id
                )
                WHERE {table}.base_currency = 'AED'
                  AND EXISTS (
                    SELECT 1 FROM tenants t2
                    WHERE t2.id = {table}.tenant_id
                      AND COALESCE(NULLIF(t2.base_currency, ''), NULLIF(t2.default_currency, ''), 'ILS') != 'AED'
                  )
                """
            )
        )

    # 2. Drop server_default AED (or set to ILS) — keep Python tenant-aware default.
    # Batch mode is required for SQLite (recreates table) and safe for Postgres.
    for table in BASE_CURRENCY_TABLES:
        if not _table_exists(table):
            continue
        if not _column_exists(table, "base_currency"):
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                "base_currency",
                existing_type=sa.String(length=3),
                nullable=False,
                server_default=None,
                # existing_* hints help batch mode recreate correctly
            )

    # Also fix any stray currency columns that still default to AED at DB level
    # (legacy procurement tables). These are transaction currencies, not base,
    # but AED default is misleading — drop it so Python default (tenant-aware) wins.
    for table, col in [("purchase_orders", "currency"), ("quotations", "currency")]:
        if _table_exists(table) and _column_exists(table, col):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.alter_column(
                    col,
                    existing_type=sa.String(length=3),
                    nullable=False,
                    server_default=None,
                )


def downgrade():
    # Downgrade is a no-op for the backfill (data already corrected) but
    # restores server_default='AED' for schema-roundtrip fidelity if needed.
    for table in BASE_CURRENCY_TABLES:
        if not _table_exists(table):
            continue
        if not _column_exists(table, "base_currency"):
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                "base_currency",
                existing_type=sa.String(length=3),
                nullable=False,
                server_default=sa.DefaultClause(sa.text("'AED'")),
            )
    for table, col in [("purchase_orders", "currency"), ("quotations", "currency")]:
        if _table_exists(table) and _column_exists(table, col):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.alter_column(
                    col,
                    existing_type=sa.String(length=3),
                    nullable=False,
                    server_default=sa.DefaultClause(sa.text("'AED'")),
                )
