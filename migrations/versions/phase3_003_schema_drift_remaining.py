"""Schema drift remaining fixes

Revision ID: phase3_003
Revises: phase3_002
Create Date: 2026-06-05

Idempotent fixes for remaining schema/model drift.
No table drops.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'phase3_003'
down_revision = 'phase3_002'
branch_labels = None
depends_on = None


def _index_exists(table, idx):
    return idx in [i['name'] for i in inspect(op.get_bind()).get_indexes(table)]


def _constraint_exists(table, cname):
    uqs = [c['name'] for c in inspect(op.get_bind()).get_unique_constraints(table)]
    return cname in uqs


def upgrade():
    # sales
    if 'sales' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('sales', schema=None) as batch_op:
            if _index_exists('sales', 'ix_sales_tenant_sale_date'):
                batch_op.drop_index('ix_sales_tenant_sale_date')
            if _index_exists('sales', 'uq_sales_tenant_sale_number'):
                batch_op.drop_index('uq_sales_tenant_sale_number')
            if not _constraint_exists('sales', 'uq_sales_tenant_sale_number'):
                batch_op.create_unique_constraint('uq_sales_tenant_sale_number', ['tenant_id', 'sale_number'])
            if not _index_exists('sales', 'ix_sales_sale_number'):
                batch_op.create_index('ix_sales_sale_number', ['sale_number'], unique=False)

    # sale_lines
    if 'sale_lines' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('sale_lines', schema=None) as batch_op:
            if _index_exists('sale_lines', 'ix_sale_lines_product_id'):
                batch_op.drop_index('ix_sale_lines_product_id')

    # shop_customer_accounts
    if 'shop_customer_accounts' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('shop_customer_accounts', schema=None) as batch_op:
            if _index_exists('shop_customer_accounts', 'ix_shop_customer_password_reset_token'):
                batch_op.drop_index('ix_shop_customer_password_reset_token')
            if not _index_exists('shop_customer_accounts', 'ix_shop_customer_accounts_customer_id'):
                batch_op.create_index('ix_shop_customer_accounts_customer_id', ['customer_id'], unique=False)
            if not _index_exists('shop_customer_accounts', 'ix_shop_customer_accounts_password_reset_token'):
                batch_op.create_index('ix_shop_customer_accounts_password_reset_token', ['password_reset_token'], unique=False)

    # stock_movements
    if 'stock_movements' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('stock_movements', schema=None) as batch_op:
            if _index_exists('stock_movements', 'ix_stock_movements_tenant_product_created'):
                batch_op.drop_index('ix_stock_movements_tenant_product_created')
            if _index_exists('stock_movements', 'ix_stock_movements_tenant_warehouse_created'):
                batch_op.drop_index('ix_stock_movements_tenant_warehouse_created')

    # receipts
    if 'receipts' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('receipts', schema=None) as batch_op:
            if _index_exists('receipts', 'ix_receipts_receipt_number'):
                batch_op.drop_index('ix_receipts_receipt_number')
            if not _index_exists('receipts', 'ix_receipts_receipt_number'):
                batch_op.create_index('ix_receipts_receipt_number', ['receipt_number'], unique=False)
            if not _constraint_exists('receipts', 'uq_receipts_tenant_receipt_number'):
                batch_op.create_unique_constraint('uq_receipts_tenant_receipt_number', ['tenant_id', 'receipt_number'])

    # store_payment_methods
    if 'store_payment_methods' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('store_payment_methods', schema=None) as batch_op:
            if _constraint_exists('store_payment_methods', 'store_payment_methods_code_key'):
                batch_op.drop_constraint('store_payment_methods_code_key', type_='unique')

    # tenant_stores
    if 'tenant_stores' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
            if _constraint_exists('tenant_stores', 'tenant_stores_store_slug_key'):
                batch_op.drop_constraint('tenant_stores_store_slug_key', type_='unique')
            if _constraint_exists('tenant_stores', 'tenant_stores_tenant_id_key'):
                batch_op.drop_constraint('tenant_stores_tenant_id_key', type_='unique')


def downgrade():
    if 'tenant_stores' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
            if not _constraint_exists('tenant_stores', 'tenant_stores_store_slug_key'):
                batch_op.create_unique_constraint('tenant_stores_store_slug_key', ['store_slug'])
            if not _constraint_exists('tenant_stores', 'tenant_stores_tenant_id_key'):
                batch_op.create_unique_constraint('tenant_stores_tenant_id_key', ['tenant_id'])

    if 'store_payment_methods' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('store_payment_methods', schema=None) as batch_op:
            if not _constraint_exists('store_payment_methods', 'store_payment_methods_code_key'):
                batch_op.create_unique_constraint('store_payment_methods_code_key', ['code'])

    if 'receipts' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('receipts', schema=None) as batch_op:
            if _constraint_exists('receipts', 'uq_receipts_tenant_receipt_number'):
                batch_op.drop_constraint('uq_receipts_tenant_receipt_number', type_='unique')
            if _index_exists('receipts', 'ix_receipts_receipt_number'):
                batch_op.drop_index('ix_receipts_receipt_number')

    if 'stock_movements' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('stock_movements', schema=None) as batch_op:
            if not _index_exists('stock_movements', 'ix_stock_movements_tenant_product_created'):
                batch_op.create_index('ix_stock_movements_tenant_product_created', ['tenant_id', 'product_id', 'created_at'], unique=False)
            if not _index_exists('stock_movements', 'ix_stock_movements_tenant_warehouse_created'):
                batch_op.create_index('ix_stock_movements_tenant_warehouse_created', ['tenant_id', 'warehouse_id', 'created_at'], unique=False)

    if 'shop_customer_accounts' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('shop_customer_accounts', schema=None) as batch_op:
            if _index_exists('shop_customer_accounts', 'ix_shop_customer_accounts_password_reset_token'):
                batch_op.drop_index('ix_shop_customer_accounts_password_reset_token')
            if _index_exists('shop_customer_accounts', 'ix_shop_customer_accounts_customer_id'):
                batch_op.drop_index('ix_shop_customer_accounts_customer_id')
            if not _index_exists('shop_customer_accounts', 'ix_shop_customer_password_reset_token'):
                batch_op.create_index('ix_shop_customer_password_reset_token', ['password_reset_token'], unique=False)

    if 'sale_lines' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('sale_lines', schema=None) as batch_op:
            if not _index_exists('sale_lines', 'ix_sale_lines_product_id'):
                batch_op.create_index('ix_sale_lines_product_id', ['product_id'], unique=False)

    if 'sales' in inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('sales', schema=None) as batch_op:
            if _index_exists('sales', 'ix_sales_sale_number'):
                batch_op.drop_index('ix_sales_sale_number')
            if _constraint_exists('sales', 'uq_sales_tenant_sale_number'):
                batch_op.drop_constraint('uq_sales_tenant_sale_number', type_='unique')
            if not _index_exists('sales', 'uq_sales_tenant_sale_number'):
                batch_op.create_index('uq_sales_tenant_sale_number', ['tenant_id', 'sale_number'], unique=True)
