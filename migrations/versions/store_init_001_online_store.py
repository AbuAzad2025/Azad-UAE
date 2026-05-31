"""store_init_001 — online warehouse type, tenant_stores, sale.source

Revision ID: store_init_001
Revises: accounting_scope_001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = 'store_init_001'
down_revision = 'accounting_scope_001'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    wh_cols = {c.get('name') for c in insp.get_columns('warehouses')}
    if 'warehouse_type' not in wh_cols:
        with op.batch_alter_table('warehouses', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('warehouse_type', sa.String(length=20), nullable=True, server_default='physical')
            )
    op.execute(text("UPDATE warehouses SET warehouse_type = 'physical' WHERE warehouse_type IS NULL OR warehouse_type = ''"))
    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.alter_column('warehouse_type', nullable=False, server_default='physical')

    wh_indexes = {idx.get('name') for idx in insp.get_indexes('warehouses')}
    if 'ix_warehouses_warehouse_type' not in wh_indexes:
        op.create_index('ix_warehouses_warehouse_type', 'warehouses', ['warehouse_type'], unique=False)

    if 'tenant_stores' not in insp.get_table_names():
        op.create_table(
            'tenant_stores',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), nullable=False),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('store_slug', sa.String(length=100), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=True),
            sa.Column('tagline', sa.String(length=255), nullable=True),
            sa.Column('phone', sa.String(length=50), nullable=True),
            sa.Column('whatsapp', sa.String(length=50), nullable=True),
            sa.Column('email', sa.String(length=120), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('tenant_id'),
            sa.UniqueConstraint('store_slug'),
        )
        op.create_index('ix_tenant_stores_tenant_id', 'tenant_stores', ['tenant_id'], unique=True)
        op.create_index('ix_tenant_stores_warehouse_id', 'tenant_stores', ['warehouse_id'], unique=False)
        op.create_index('ix_tenant_stores_store_slug', 'tenant_stores', ['store_slug'], unique=True)

    sale_cols = {c.get('name') for c in insp.get_columns('sales')}
    if 'source' not in sale_cols:
        with op.batch_alter_table('sales', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('source', sa.String(length=30), nullable=True, server_default='internal')
            )
    op.execute(text("UPDATE sales SET source = 'internal' WHERE source IS NULL OR source = ''"))
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.alter_column('source', nullable=False, server_default='internal')

    sale_indexes = {idx.get('name') for idx in insp.get_indexes('sales')}
    if 'ix_sales_source' not in sale_indexes:
        op.create_index('ix_sales_source', 'sales', ['source'], unique=False)


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    sale_indexes = {idx.get('name') for idx in insp.get_indexes('sales')}
    if 'ix_sales_source' in sale_indexes:
        op.drop_index('ix_sales_source', table_name='sales')
    sale_cols = {c.get('name') for c in insp.get_columns('sales')}
    if 'source' in sale_cols:
        with op.batch_alter_table('sales', schema=None) as batch_op:
            batch_op.drop_column('source')

    if 'tenant_stores' in insp.get_table_names():
        op.drop_table('tenant_stores')

    wh_indexes = {idx.get('name') for idx in insp.get_indexes('warehouses')}
    if 'ix_warehouses_warehouse_type' in wh_indexes:
        op.drop_index('ix_warehouses_warehouse_type', table_name='warehouses')
    wh_cols = {c.get('name') for c in insp.get_columns('warehouses')}
    if 'warehouse_type' in wh_cols:
        with op.batch_alter_table('warehouses', schema=None) as batch_op:
            batch_op.drop_column('warehouse_type')
