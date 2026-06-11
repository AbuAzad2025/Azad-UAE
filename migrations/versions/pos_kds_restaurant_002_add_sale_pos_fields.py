"""Add Sale.pos_session_id, Sale.order_type, Sale.table_id

Revision ID: pos_kds_restaurant_002
Revises: e074faa9530c
"""
from alembic import op
import sqlalchemy as sa


revision = 'pos_kds_restaurant_002'
down_revision = 'e074faa9530c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pos_session_id', sa.Integer(), sa.ForeignKey('pos_sessions.id'), nullable=True))
        batch_op.add_column(sa.Column('order_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('table_id', sa.Integer(), sa.ForeignKey('pos_tables.id'), nullable=True))
        batch_op.create_index('ix_sales_pos_session_id', ['pos_session_id'])
        batch_op.create_index('ix_sales_order_type', ['order_type'])
        batch_op.create_index('ix_sales_table_id', ['table_id'])


def downgrade():
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_index('ix_sales_table_id')
        batch_op.drop_index('ix_sales_order_type')
        batch_op.drop_index('ix_sales_pos_session_id')
        batch_op.drop_column('table_id')
        batch_op.drop_column('order_type')
        batch_op.drop_column('pos_session_id')
