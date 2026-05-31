"""store_init_002 — storefront fields

Revision ID: store_init_002
Revises: store_init_001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'store_init_002'
down_revision = 'store_init_001'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c.get('name') for c in insp.get_columns('tenant_stores')}
    with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
        if 'min_order_amount' not in cols:
            batch_op.add_column(sa.Column('min_order_amount', sa.Numeric(15, 3), nullable=True))
        if 'delivery_note' not in cols:
            batch_op.add_column(sa.Column('delivery_note', sa.String(500), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c.get('name') for c in insp.get_columns('tenant_stores')}
    with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
        if 'delivery_note' in cols:
            batch_op.drop_column('delivery_note')
        if 'min_order_amount' in cols:
            batch_op.drop_column('min_order_amount')
