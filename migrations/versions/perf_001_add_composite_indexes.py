"""Add composite indexes for multi-tenant performance
Revision ID: perf_001
Revises: cbcda1ac36c4
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'perf_001'
down_revision = 'cbcda1ac36c4'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("SET statement_timeout = '120s'")

    op.create_index('ix_sales_tenant_status_date', 'sales', ['tenant_id', 'status', 'sale_date'])
    op.create_index('ix_sales_tenant_customer', 'sales', ['tenant_id', 'customer_id'])
    op.create_index('ix_sale_lines_sale_product', 'sale_lines', ['sale_id', 'product_id'])
    op.create_index('ix_purchases_tenant_status_date', 'purchases', ['tenant_id', 'status', 'purchase_date'])
    op.create_index('ix_purchases_tenant_supplier', 'purchases', ['tenant_id', 'supplier_id'])
    op.create_index('ix_purchase_lines_purchase_product', 'purchase_lines', ['purchase_id', 'product_id'])
    op.create_index('ix_payments_tenant_date_direction', 'payments', ['tenant_id', 'payment_date', 'direction'])
    op.create_index('ix_payments_tenant_customer', 'payments', ['tenant_id', 'customer_id'])
    op.create_index('ix_payments_tenant_supplier', 'payments', ['tenant_id', 'supplier_id'])
    op.create_index('ix_receipts_tenant_date', 'receipts', ['tenant_id', 'receipt_date'])
    op.create_index('ix_receipts_tenant_customer', 'receipts', ['tenant_id', 'customer_id'])
    op.create_index('ix_products_tenant_active', 'products', ['tenant_id', 'is_active'])
    op.create_index('ix_customers_tenant_active', 'customers', ['tenant_id', 'is_active'])
    op.create_index('ix_suppliers_tenant_active', 'suppliers', ['tenant_id', 'is_active'])
    op.create_index('ix_users_tenant_active', 'users', ['tenant_id', 'is_active'])
    op.create_index('ix_stock_movements_tenant_product_warehouse', 'stock_movements', ['tenant_id', 'product_id', 'warehouse_id'])
    op.create_index('ix_gl_accounts_tenant_code', 'gl_accounts', ['tenant_id', 'account_code'])
    op.create_index('ix_partner_tx_tenant_partner_date', 'partner_transactions', ['tenant_id', 'partner_id', 'transaction_date'])

def downgrade():
    for idx in [
        'ix_sales_tenant_status_date',
        'ix_sales_tenant_customer',
        'ix_sale_lines_sale_product',
        'ix_purchases_tenant_status_date',
        'ix_purchases_tenant_supplier',
        'ix_purchase_lines_purchase_product',
        'ix_payments_tenant_date_direction',
        'ix_payments_tenant_customer',
        'ix_payments_tenant_supplier',
        'ix_receipts_tenant_date',
        'ix_receipts_tenant_customer',
        'ix_products_tenant_active',
        'ix_customers_tenant_active',
        'ix_suppliers_tenant_active',
        'ix_users_tenant_active',
        'ix_stock_movements_tenant_product_warehouse',
        'ix_gl_accounts_tenant_code',
        'ix_partner_tx_tenant_partner_date',
    ]:
        op.drop_index(idx)
