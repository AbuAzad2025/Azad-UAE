"""Add allow_negative_inventory to warehouses

Revision ID: negative_inventory_001
Revises: dynamic_currency_001
Create Date: 2026-06-21

Adds the allow_negative_inventory flag to the warehouses table so that
negative inventory can be selectively enabled per warehouse.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'negative_inventory_001'
down_revision = 'dynamic_currency_001'
branch_labels = None
depends_on = None


def _column_exists(table, col):
    bind = op.get_bind()
    return col in [c['name'] for c in inspect(bind).get_columns(table)]


def upgrade():
    if not _column_exists('warehouses', 'allow_negative_inventory'):
        with op.batch_alter_table('warehouses', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('allow_negative_inventory', sa.Boolean(), nullable=True, server_default=sa.false())
            )
            batch_op.create_index(
                'ix_warehouses_allow_negative_inventory',
                ['allow_negative_inventory'],
                unique=False
            )

    # Backfill existing warehouses: default to False (safe default)
    op.execute("UPDATE warehouses SET allow_negative_inventory = FALSE WHERE allow_negative_inventory IS NULL")

    # Make NOT NULL after backfill
    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.alter_column('allow_negative_inventory', nullable=False, server_default=sa.false())


def downgrade():
    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.drop_index('ix_warehouses_allow_negative_inventory')
        batch_op.drop_column('allow_negative_inventory')
