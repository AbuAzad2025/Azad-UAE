"""Fix remaining indexes and constraints

Revision ID: phase3_005
Revises: phase3_004
Create Date: 2026-06-05

Idempotent fixes for:
- Missing indexes on expenses, product_returns, receipts
- Orphaned unique constraint on expense_categories.name
"""
from alembic import op
from sqlalchemy import inspect

revision = 'phase3_005'
down_revision = 'phase3_004'
branch_labels = None
depends_on = None


def _index_exists(table, idx):
    return idx in [i['name'] for i in inspect(op.get_bind()).get_indexes(table)]


def _constraint_exists(table, cname):
    uqs = [c['name'] for c in inspect(op.get_bind()).get_unique_constraints(table)]
    return cname in uqs


def upgrade():
    # Add missing indexes
    if not _index_exists('expenses', 'ix_expenses_expense_number'):
        op.create_index('ix_expenses_expense_number', 'expenses', ['expense_number'], unique=False)

    if not _index_exists('product_returns', 'ix_product_returns_return_number'):
        op.create_index('ix_product_returns_return_number', 'product_returns', ['return_number'], unique=False)

    if not _index_exists('receipts', 'ix_receipts_receipt_number'):
        op.create_index('ix_receipts_receipt_number', 'receipts', ['receipt_number'], unique=False)

    # Drop orphaned unique constraint (replaced by uq_expense_categories_tenant_name)
    if _constraint_exists('expense_categories', 'expense_categories_name_key'):
        op.drop_constraint('expense_categories_name_key', 'expense_categories', type_='unique')


def downgrade():
    if not _constraint_exists('expense_categories', 'expense_categories_name_key'):
        op.create_unique_constraint('expense_categories_name_key', 'expense_categories', ['name'])

    if _index_exists('receipts', 'ix_receipts_receipt_number'):
        op.drop_index('ix_receipts_receipt_number', table_name='receipts')

    if _index_exists('product_returns', 'ix_product_returns_return_number'):
        op.drop_index('ix_product_returns_return_number', table_name='product_returns')

    if _index_exists('expenses', 'ix_expenses_expense_number'):
        op.drop_index('ix_expenses_expense_number', table_name='expenses')
