"""Add landed cost fields to Purchase and PurchaseLine

Revision ID: phase5_001
Revises: phase3_006
Create Date: 2026-06-05

Adds:
- freight, insurance, customs_duty, other_landed_cost to purchases
- landed_cost to purchase_lines
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'phase5_001'
down_revision = 'phase3_006'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    bind = op.get_bind()
    cols = [c['name'] for c in inspect(bind).get_columns(table)]
    return column in cols


def upgrade():
    # Add landed cost fields to purchases
    if not _column_exists('purchases', 'freight'):
        op.add_column('purchases', sa.Column('freight', sa.Numeric(15, 3), nullable=False, server_default='0'))
    if not _column_exists('purchases', 'insurance'):
        op.add_column('purchases', sa.Column('insurance', sa.Numeric(15, 3), nullable=False, server_default='0'))
    if not _column_exists('purchases', 'customs_duty'):
        op.add_column('purchases', sa.Column('customs_duty', sa.Numeric(15, 3), nullable=False, server_default='0'))
    if not _column_exists('purchases', 'other_landed_cost'):
        op.add_column('purchases', sa.Column('other_landed_cost', sa.Numeric(15, 3), nullable=False, server_default='0'))

    # Add landed_cost to purchase_lines
    if not _column_exists('purchase_lines', 'landed_cost'):
        op.add_column('purchase_lines', sa.Column('landed_cost', sa.Numeric(15, 3), nullable=False, server_default='0'))


def downgrade():
    if _column_exists('purchase_lines', 'landed_cost'):
        op.drop_column('purchase_lines', 'landed_cost')
    for col in ('other_landed_cost', 'customs_duty', 'insurance', 'freight'):
        if _column_exists('purchases', col):
            op.drop_column('purchases', col)
