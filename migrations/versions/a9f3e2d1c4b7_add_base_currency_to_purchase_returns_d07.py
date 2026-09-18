"""add base_currency to purchase_returns D07

Revision ID: a9f3e2d1c4b7
Revises: k8e4g03c6f59
Create Date: 2026-09-18

D07: purchase_returns missing base_currency tenant-aware column.
Adds base_currency with tenant backfill; handles both PostgreSQL and SQLite
via batch_alter_table. Backfills from tenants.base_currency / default_currency
falling back to ILS (regional fallback) to avoid AED drift.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "a9f3e2d1c4b7"
down_revision = "k8e4g03c6f59"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False


def upgrade():
    # 1. Add column if missing — nullable + server_default ILS so existing rows pass
    if not _column_exists("purchase_returns", "base_currency"):
        with op.batch_alter_table("purchase_returns", schema=None) as batch_op:
            batch_op.add_column(sa.Column("base_currency", sa.String(length=3), nullable=True, server_default="ILS"))

    # 2. Backfill from tenant (base_currency > default_currency > ILS)
    conn = op.get_bind()

    # Normalize empty strings to NULL for coalescing; SQLite lacks FROM UPDATE syntax
    # so use correlated subqueries which work on both dialects.
    # First, fill NULL/empty rows
    conn.execute(
        text(
            """
            UPDATE purchase_returns
            SET base_currency = COALESCE(
                NULLIF((SELECT t.base_currency FROM tenants t WHERE t.id = purchase_returns.tenant_id), ''),
                NULLIF((SELECT t.default_currency FROM tenants t WHERE t.id = purchase_returns.tenant_id), ''),
                'ILS'
            )
            WHERE base_currency IS NULL OR base_currency = ''
            """
        )
    )

    # Second, fix AED drift where tenant's real base is not AED (D09-style backfill)
    conn.execute(
        text(
            """
            UPDATE purchase_returns
            SET base_currency = (
                SELECT COALESCE(NULLIF(t.base_currency, ''), NULLIF(t.default_currency, ''), 'ILS')
                FROM tenants t WHERE t.id = purchase_returns.tenant_id
            )
            WHERE base_currency = 'AED'
              AND EXISTS (
                SELECT 1 FROM tenants t2
                WHERE t2.id = purchase_returns.tenant_id
                  AND COALESCE(NULLIF(t2.base_currency, ''), NULLIF(t2.default_currency, ''), 'ILS') != 'AED'
              )
            """
        )
    )

    # 3. Enforce NOT NULL and drop server_default (drift guard — Python default is tenant-aware)
    # Use batch_alter_table for SQLite + PostgreSQL portability.
    with op.batch_alter_table("purchase_returns", schema=None) as batch_op:
        batch_op.alter_column(
            "base_currency",
            existing_type=sa.String(length=3),
            nullable=False,
            server_default=None,
            existing_nullable=True,
            existing_server_default="ILS",
        )


def downgrade():
    if _column_exists("purchase_returns", "base_currency"):
        with op.batch_alter_table("purchase_returns", schema=None) as batch_op:
            batch_op.drop_column("base_currency")
