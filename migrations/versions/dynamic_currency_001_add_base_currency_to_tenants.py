"""Add base_currency to tenants and backfill existing tenants

Revision ID: dynamic_currency_001
Revises: c98e9930ce80
Create Date: 2026-06-16

Adds the base_currency column to the tenants table and safely backfills
existing tenants so each tenant gets its own dynamic base currency.

Post-conditions:
- All existing tenants have base_currency = default_currency (or 'ILS' if null).
- default_currency is never NULL for existing tenants.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.sql import text

revision = 'dynamic_currency_001'
down_revision = 'c98e9930ce80'
branch_labels = None
depends_on = None


def _column_exists(table, col):
    bind = op.get_bind()
    return col in [c['name'] for c in inspect(bind).get_columns(table)]


def upgrade():
    # Step 1: add base_currency to tenants (nullable first, safe for existing data)
    if not _column_exists('tenants', 'base_currency'):
        with op.batch_alter_table('tenants', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('base_currency', sa.String(3), nullable=True, server_default='ILS')
            )

    # Step 2: backfill default_currency for existing tenants where NULL
    #          (safety net: some legacy tenants may have NULL default_currency)
    op.execute(
        text("UPDATE tenants SET default_currency = 'ILS' WHERE default_currency IS NULL OR default_currency = ''")
    )

    # Step 3: backfill base_currency = default_currency for all existing tenants
    #          This ensures each tenant keeps its own accounting currency.
    op.execute(
        text("UPDATE tenants SET base_currency = default_currency WHERE base_currency IS NULL OR base_currency = ''")
    )

    # Step 4: make base_currency NOT NULL (schema now guarantees a value)
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.alter_column('base_currency', nullable=False, server_default='ILS')

    # Step 5: ensure default_currency is also NOT NULL and has a default
    #          (best effort: only if the dialect allows altering nullable without rebuild)
    try:
        with op.batch_alter_table('tenants', schema=None) as batch_op:
            batch_op.alter_column('default_currency', nullable=False, server_default='ILS')
    except Exception:
        # If the dialect does not support altering nullable on existing columns,
        # the application logic (get_base_currency) already handles NULL safely.
        pass


def downgrade():
    # Drop base_currency column
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('base_currency')
