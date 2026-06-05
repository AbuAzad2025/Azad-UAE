"""Add MWAC, Exchange Rate, and Treasury models

Revision ID: phase3_001
Revises: phase2_001
Create Date: 2026-06-05

Adds:
- product_warehouse_costs (MWAC)
- product_cost_history (MWAC audit)
- exchange_rate_records
- cash_boxes
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'phase3_001'
down_revision = 'phase2_001'
branch_labels = None
depends_on = None


def _table_exists(name):
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def _index_exists(table, idx):
    bind = op.get_bind()
    idxs = [i['name'] for i in inspect(bind).get_indexes(table)]
    return idx in idxs


def upgrade():
    # product_warehouse_costs
    if not _table_exists('product_warehouse_costs'):
        op.create_table(
            'product_warehouse_costs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), nullable=False),
            sa.Column('average_cost', sa.Numeric(18, 6), nullable=False, server_default='0'),
            sa.Column('total_quantity', sa.Numeric(18, 3), nullable=False, server_default='0'),
            sa.Column('total_value', sa.Numeric(18, 3), nullable=False, server_default='0'),
            sa.Column('currency', sa.String(3), nullable=False, server_default='AED'),
            sa.Column('last_updated', sa.DateTime(), nullable=False),
            sa.Column('updated_by_movement_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
            sa.ForeignKeyConstraint(['updated_by_movement_id'], ['stock_movements.id']),
            sa.UniqueConstraint('tenant_id', 'product_id', 'warehouse_id', name='uq_pwc_tenant_product_warehouse'),
        )
        op.create_index('ix_product_warehouse_costs_tenant_id', 'product_warehouse_costs', ['tenant_id'], unique=False)
        op.create_index('ix_product_warehouse_costs_product_id', 'product_warehouse_costs', ['product_id'], unique=False)
        op.create_index('ix_product_warehouse_costs_warehouse_id', 'product_warehouse_costs', ['warehouse_id'], unique=False)

    # product_cost_history
    if not _table_exists('product_cost_history'):
        op.create_table(
            'product_cost_history',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), nullable=False),
            sa.Column('movement_type', sa.String(30), nullable=False),
            sa.Column('movement_id', sa.Integer(), nullable=True),
            sa.Column('reference_type', sa.String(50), nullable=True),
            sa.Column('reference_id', sa.Integer(), nullable=True),
            sa.Column('old_average_cost', sa.Numeric(18, 6), nullable=True),
            sa.Column('new_average_cost', sa.Numeric(18, 6), nullable=False),
            sa.Column('quantity_change', sa.Numeric(18, 3), nullable=False),
            sa.Column('old_total_quantity', sa.Numeric(18, 3), nullable=True),
            sa.Column('new_total_quantity', sa.Numeric(18, 3), nullable=False),
            sa.Column('old_total_value', sa.Numeric(18, 3), nullable=True),
            sa.Column('new_total_value', sa.Numeric(18, 3), nullable=False),
            sa.Column('movement_unit_cost', sa.Numeric(18, 6), nullable=True),
            sa.Column('currency', sa.String(3), nullable=False, server_default='AED'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
        )
        op.create_index('ix_product_cost_history_tenant_id', 'product_cost_history', ['tenant_id'], unique=False)
        op.create_index('ix_product_cost_history_product_id', 'product_cost_history', ['product_id'], unique=False)
        op.create_index('ix_product_cost_history_warehouse_id', 'product_cost_history', ['warehouse_id'], unique=False)
        op.create_index('ix_product_cost_history_created_at', 'product_cost_history', ['created_at'], unique=False)

    # exchange_rate_records
    if not _table_exists('exchange_rate_records'):
        op.create_table(
            'exchange_rate_records',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('from_currency', sa.String(3), nullable=False),
            sa.Column('to_currency', sa.String(3), nullable=False),
            sa.Column('rate', sa.Numeric(18, 6), nullable=False),
            sa.Column('source', sa.String(30), nullable=False, server_default='manual'),
            sa.Column('api_provider', sa.String(50), nullable=True),
            sa.Column('api_response_id', sa.String(100), nullable=True),
            sa.Column('effective_date', sa.Date(), nullable=False),
            sa.Column('locked_by_document_type', sa.String(50), nullable=True),
            sa.Column('locked_by_document_id', sa.Integer(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.UniqueConstraint('tenant_id', 'from_currency', 'to_currency', 'effective_date', name='uq_rate_tenant_pair_date'),
        )
        op.create_index('ix_exchange_rate_records_tenant_id', 'exchange_rate_records', ['tenant_id'], unique=False)
        op.create_index('ix_exchange_rate_records_from_currency', 'exchange_rate_records', ['from_currency'], unique=False)
        op.create_index('ix_exchange_rate_records_to_currency', 'exchange_rate_records', ['to_currency'], unique=False)
        op.create_index('ix_exchange_rate_records_effective_date', 'exchange_rate_records', ['effective_date'], unique=False)

    # cash_boxes
    if not _table_exists('cash_boxes'):
        op.create_table(
            'cash_boxes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('branch_id', sa.Integer(), nullable=True),
            sa.Column('code', sa.String(20), nullable=False),
            sa.Column('name_ar', sa.String(200), nullable=False),
            sa.Column('name_en', sa.String(200), nullable=True),
            sa.Column('box_type', sa.String(30), nullable=False, server_default='cash'),
            sa.Column('currency', sa.String(3), nullable=False, server_default='AED'),
            sa.Column('current_balance', sa.Numeric(18, 3), nullable=False, server_default='0'),
            sa.Column('bank_name', sa.String(200), nullable=True),
            sa.Column('account_number', sa.String(100), nullable=True),
            sa.Column('iban', sa.String(50), nullable=True),
            sa.Column('swift_code', sa.String(20), nullable=True),
            sa.Column('gateway_provider', sa.String(50), nullable=True),
            sa.Column('gateway_merchant_id', sa.String(100), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('gl_account_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
            sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
            sa.ForeignKeyConstraint(['gl_account_id'], ['gl_accounts.id']),
            sa.UniqueConstraint('tenant_id', 'code', name='uq_cash_boxes_tenant_code'),
        )
        op.create_index('ix_cash_boxes_tenant_id', 'cash_boxes', ['tenant_id'], unique=False)
        op.create_index('ix_cash_boxes_branch_id', 'cash_boxes', ['branch_id'], unique=False)
        op.create_index('ix_cash_boxes_code', 'cash_boxes', ['code'], unique=False)
        op.create_index('ix_cash_boxes_is_active', 'cash_boxes', ['is_active'], unique=False)
        op.create_index('ix_cash_boxes_gl_account_id', 'cash_boxes', ['gl_account_id'], unique=False)


def downgrade():
    if _table_exists('cash_boxes'):
        op.drop_index('ix_cash_boxes_gl_account_id', table_name='cash_boxes')
        op.drop_index('ix_cash_boxes_is_active', table_name='cash_boxes')
        op.drop_index('ix_cash_boxes_code', table_name='cash_boxes')
        op.drop_index('ix_cash_boxes_branch_id', table_name='cash_boxes')
        op.drop_index('ix_cash_boxes_tenant_id', table_name='cash_boxes')
        op.drop_table('cash_boxes')

    if _table_exists('exchange_rate_records'):
        op.drop_index('ix_exchange_rate_records_effective_date', table_name='exchange_rate_records')
        op.drop_index('ix_exchange_rate_records_to_currency', table_name='exchange_rate_records')
        op.drop_index('ix_exchange_rate_records_from_currency', table_name='exchange_rate_records')
        op.drop_index('ix_exchange_rate_records_tenant_id', table_name='exchange_rate_records')
        op.drop_table('exchange_rate_records')

    if _table_exists('product_cost_history'):
        op.drop_index('ix_product_cost_history_created_at', table_name='product_cost_history')
        op.drop_index('ix_product_cost_history_warehouse_id', table_name='product_cost_history')
        op.drop_index('ix_product_cost_history_product_id', table_name='product_cost_history')
        op.drop_index('ix_product_cost_history_tenant_id', table_name='product_cost_history')
        op.drop_table('product_cost_history')

    if _table_exists('product_warehouse_costs'):
        op.drop_index('ix_product_warehouse_costs_warehouse_id', table_name='product_warehouse_costs')
        op.drop_index('ix_product_warehouse_costs_product_id', table_name='product_warehouse_costs')
        op.drop_index('ix_product_warehouse_costs_tenant_id', table_name='product_warehouse_costs')
        op.drop_table('product_warehouse_costs')
