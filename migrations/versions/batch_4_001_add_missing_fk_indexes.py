"""add_missing_fk_indexes

Revision ID: batch_4_001
Revises: batch_3_001
Create Date: 2026-06-04 08:10:00.000000

Batch 4: Indexing & Schema Hardening
Add secondary indexes on high-traffic Foreign Key columns that were missing
database-level index support. This improves JOIN performance on financial
and operational queries without changing any data.

Indexes added:
- sales.seller_id
- purchases.user_id
- payments.user_id
- receipts.user_id
- expenses.user_id
- cheques.user_id
- stock_movements.user_id
- gl_journal_lines.cost_center_id
- product_returns.customer_id
- product_returns.processed_by
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'batch_4_001'
down_revision = 'batch_3_001'
branch_labels = None
depends_on = None


def upgrade():
    # ── Sales ────────────────────────────────────────────────
    op.create_index(op.f('ix_sales_seller_id'), 'sales', ['seller_id'], unique=False)

    # ── Purchases ────────────────────────────────────────────
    op.create_index(op.f('ix_purchases_user_id'), 'purchases', ['user_id'], unique=False)

    # ── Payments ─────────────────────────────────────────────
    op.create_index(op.f('ix_payments_user_id'), 'payments', ['user_id'], unique=False)

    # ── Receipts ───────────────────────────────────────────────
    op.create_index(op.f('ix_receipts_user_id'), 'receipts', ['user_id'], unique=False)

    # ── Expenses ─────────────────────────────────────────────
    op.create_index(op.f('ix_expenses_user_id'), 'expenses', ['user_id'], unique=False)

    # ── Cheques ──────────────────────────────────────────────
    op.create_index(op.f('ix_cheques_user_id'), 'cheques', ['user_id'], unique=False)

    # ── Stock Movements ──────────────────────────────────────
    op.create_index(op.f('ix_stock_movements_user_id'), 'stock_movements', ['user_id'], unique=False)

    # ── GL Journal Lines ─────────────────────────────────────
    op.create_index(op.f('ix_gl_journal_lines_cost_center_id'), 'gl_journal_lines', ['cost_center_id'], unique=False)

    # ── Product Returns ──────────────────────────────────────
    op.create_index(op.f('ix_product_returns_customer_id'), 'product_returns', ['customer_id'], unique=False)
    op.create_index(op.f('ix_product_returns_processed_by'), 'product_returns', ['processed_by'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_product_returns_processed_by'), table_name='product_returns')
    op.drop_index(op.f('ix_product_returns_customer_id'), table_name='product_returns')
    op.drop_index(op.f('ix_gl_journal_lines_cost_center_id'), table_name='gl_journal_lines')
    op.drop_index(op.f('ix_stock_movements_user_id'), table_name='stock_movements')
    op.drop_index(op.f('ix_cheques_user_id'), table_name='cheques')
    op.drop_index(op.f('ix_expenses_user_id'), table_name='expenses')
    op.drop_index(op.f('ix_receipts_user_id'), table_name='receipts')
    op.drop_index(op.f('ix_payments_user_id'), table_name='payments')
    op.drop_index(op.f('ix_purchases_user_id'), table_name='purchases')
    op.drop_index(op.f('ix_sales_seller_id'), table_name='sales')
