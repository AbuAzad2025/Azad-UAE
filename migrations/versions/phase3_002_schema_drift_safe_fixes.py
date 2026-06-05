"""Schema drift safe fixes (indexes, constraints, nullable alignments)

Revision ID: phase3_002
Revises: phase3_001
Create Date: 2026-06-05

Idempotent alignment of existing schema to model definitions.
No table drops. Only adds missing constraints/indexes and
adjusts nullable where safe.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = 'phase3_002'
down_revision = 'phase3_001'
branch_labels = None
depends_on = None


def _table_exists(name):
    return name in inspect(op.get_bind()).get_table_names()


def _index_exists(table, idx):
    return idx in [i['name'] for i in inspect(op.get_bind()).get_indexes(table)]


def _constraint_exists(table, cname):
    # Check both unique constraints and foreign keys by name
    insp = inspect(op.get_bind())
    uqs = [c['name'] for c in insp.get_unique_constraints(table)]
    fks = [c['name'] for c in insp.get_foreign_keys(table)]
    return cname in uqs or cname in fks


def _column_exists(table, col):
    return col in [c['name'] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade():
    # branches
    if _table_exists('branches'):
        with op.batch_alter_table('branches', schema=None) as batch_op:
            if _index_exists('branches', 'uq_branches_tenant_code'):
                batch_op.drop_index('uq_branches_tenant_code')
            if not _constraint_exists('branches', 'uq_branches_tenant_code'):
                batch_op.create_unique_constraint('uq_branches_tenant_code', ['tenant_id', 'code'])
            if _index_exists('branches', 'uq_branches_tenant_name'):
                batch_op.drop_index('uq_branches_tenant_name')
            if not _constraint_exists('branches', 'uq_branches_tenant_name'):
                batch_op.create_unique_constraint('uq_branches_tenant_name', ['tenant_id', 'name'])

    # cheques
    if _table_exists('cheques'):
        with op.batch_alter_table('cheques', schema=None) as batch_op:
            if _index_exists('cheques', 'uq_cheques_tenant_cheque_number'):
                batch_op.drop_index('uq_cheques_tenant_cheque_number')
            if not _constraint_exists('cheques', 'uq_cheques_tenant_cheque_number'):
                batch_op.create_unique_constraint('uq_cheques_tenant_cheque_number', ['tenant_id', 'cheque_number'])
            if not _index_exists('cheques', 'ix_cheques_cheque_number'):
                batch_op.create_index('ix_cheques_cheque_number', ['cheque_number'], unique=False)

    # cost_centers
    if _table_exists('cost_centers'):
        with op.batch_alter_table('cost_centers', schema=None) as batch_op:
            if not _index_exists('cost_centers', 'ix_cost_centers_code'):
                batch_op.create_index('ix_cost_centers_code', ['code'], unique=False)

    # error_audit_logs
    if _table_exists('error_audit_logs'):
        with op.batch_alter_table('error_audit_logs', schema=None) as batch_op:
            for idx in ['ix_error_audit_logs_fingerprint', 'ix_error_audit_logs_first_seen_at',
                        'ix_error_audit_logs_last_seen_at', 'ix_error_audit_logs_request_id']:
                if not _index_exists('error_audit_logs', idx):
                    col = idx.replace('ix_error_audit_logs_', '')
                    batch_op.create_index(idx, [col], unique=False)

    # expense_categories
    if _table_exists('expense_categories'):
        with op.batch_alter_table('expense_categories', schema=None) as batch_op:
            if not _index_exists('expense_categories', 'ix_expense_categories_name'):
                batch_op.create_index('ix_expense_categories_name', ['name'], unique=False)
            if not _constraint_exists('expense_categories', 'uq_expense_categories_tenant_name'):
                batch_op.create_unique_constraint('uq_expense_categories_tenant_name', ['tenant_id', 'name'])

    # expenses
    if _table_exists('expenses'):
        with op.batch_alter_table('expenses', schema=None) as batch_op:
            if _index_exists('expenses', 'ix_expenses_expense_number'):
                batch_op.drop_index('ix_expenses_expense_number')
            if not _index_exists('expenses', 'ix_expenses_expense_number'):
                batch_op.create_index('ix_expenses_expense_number', ['expense_number'], unique=False)
            if not _constraint_exists('expenses', 'uq_expenses_tenant_expense_number'):
                batch_op.create_unique_constraint('uq_expenses_tenant_expense_number', ['tenant_id', 'expense_number'])

    # gl_journal_entries
    if _table_exists('gl_journal_entries'):
        with op.batch_alter_table('gl_journal_entries', schema=None) as batch_op:
            if _index_exists('gl_journal_entries', 'ix_gl_journal_entries_tenant_entry_date'):
                batch_op.drop_index('ix_gl_journal_entries_tenant_entry_date')

    # gl_journal_lines
    if _table_exists('gl_journal_lines'):
        with op.batch_alter_table('gl_journal_lines', schema=None) as batch_op:
            if _index_exists('gl_journal_lines', 'ix_gl_journal_lines_tenant_account'):
                batch_op.drop_index('ix_gl_journal_lines_tenant_account')

    # partner_commission_entries
    if _table_exists('partner_commission_entries'):
        with op.batch_alter_table('partner_commission_entries', schema=None) as batch_op:
            if _index_exists('partner_commission_entries', 'ix_partner_commission_entries_tenant_product'):
                batch_op.drop_index('ix_partner_commission_entries_tenant_product')

    # partners
    if _table_exists('partners'):
        with op.batch_alter_table('partners', schema=None) as batch_op:
            if not _constraint_exists('partners', 'uq_partners_tenant_code'):
                batch_op.create_unique_constraint('uq_partners_tenant_code', ['tenant_id', 'code'])

    # payments
    if _table_exists('payments'):
        with op.batch_alter_table('payments', schema=None) as batch_op:
            if _index_exists('payments', 'uq_payments_tenant_payment_number'):
                batch_op.drop_index('uq_payments_tenant_payment_number')
            if not _constraint_exists('payments', 'uq_payments_tenant_payment_number'):
                batch_op.create_unique_constraint('uq_payments_tenant_payment_number', ['tenant_id', 'payment_number'])
            if not _index_exists('payments', 'ix_payments_payment_number'):
                batch_op.create_index('ix_payments_payment_number', ['payment_number'], unique=False)

    # product_categories
    if _table_exists('product_categories'):
        with op.batch_alter_table('product_categories', schema=None) as batch_op:
            if _index_exists('product_categories', 'uq_product_categories_tenant_name'):
                batch_op.drop_index('uq_product_categories_tenant_name')
            if not _constraint_exists('product_categories', 'uq_product_categories_tenant_name'):
                batch_op.create_unique_constraint('uq_product_categories_tenant_name', ['tenant_id', 'name'])
            if not _index_exists('product_categories', 'ix_product_categories_name'):
                batch_op.create_index('ix_product_categories_name', ['name'], unique=False)

    # product_return_lines
    if _table_exists('product_return_lines'):
        with op.batch_alter_table('product_return_lines', schema=None) as batch_op:
            pass  # tenant_id nullable fix skipped for safety (may have null rows)

    # product_returns
    if _table_exists('product_returns'):
        with op.batch_alter_table('product_returns', schema=None) as batch_op:
            if _index_exists('product_returns', 'ix_product_returns_return_number'):
                batch_op.drop_index('ix_product_returns_return_number')
            if not _index_exists('product_returns', 'ix_product_returns_return_number'):
                batch_op.create_index('ix_product_returns_return_number', ['return_number'], unique=False)
            if not _constraint_exists('product_returns', 'uq_product_returns_tenant_return_number'):
                batch_op.create_unique_constraint('uq_product_returns_tenant_return_number', ['tenant_id', 'return_number'])

    # products
    if _table_exists('products'):
        with op.batch_alter_table('products', schema=None) as batch_op:
            if not _index_exists('products', 'ix_products_barcode'):
                batch_op.create_index('ix_products_barcode', ['barcode'], unique=False)
            if not _index_exists('products', 'ix_products_sku'):
                batch_op.create_index('ix_products_sku', ['sku'], unique=False)

    # purchase_lines
    if _table_exists('purchase_lines'):
        with op.batch_alter_table('purchase_lines', schema=None) as batch_op:
            if _index_exists('purchase_lines', 'ix_purchase_lines_product_id'):
                batch_op.drop_index('ix_purchase_lines_product_id')

    # purchases
    if _table_exists('purchases'):
        with op.batch_alter_table('purchases', schema=None) as batch_op:
            if _index_exists('purchases', 'uq_purchases_tenant_purchase_number'):
                batch_op.drop_index('uq_purchases_tenant_purchase_number')
            if not _constraint_exists('purchases', 'uq_purchases_tenant_purchase_number'):
                batch_op.create_unique_constraint('uq_purchases_tenant_purchase_number', ['tenant_id', 'purchase_number'])
            if not _index_exists('purchases', 'ix_purchases_purchase_number'):
                batch_op.create_index('ix_purchases_purchase_number', ['purchase_number'], unique=False)

    # warehouses
    if _table_exists('warehouses'):
        with op.batch_alter_table('warehouses', schema=None) as batch_op:
            if _index_exists('warehouses', 'uq_warehouses_tenant_code'):
                batch_op.drop_index('uq_warehouses_tenant_code')
            if not _constraint_exists('warehouses', 'uq_warehouses_tenant_code'):
                batch_op.create_unique_constraint('uq_warehouses_tenant_code', ['tenant_id', 'code'])
            if _index_exists('warehouses', 'uq_warehouses_tenant_name'):
                batch_op.drop_index('uq_warehouses_tenant_name')
            if not _constraint_exists('warehouses', 'uq_warehouses_tenant_name'):
                batch_op.create_unique_constraint('uq_warehouses_tenant_name', ['tenant_id', 'name'])


def downgrade():
    # Reverse operations (idempotent where possible)
    if _table_exists('warehouses'):
        with op.batch_alter_table('warehouses', schema=None) as batch_op:
            if _constraint_exists('warehouses', 'uq_warehouses_tenant_name'):
                batch_op.drop_constraint('uq_warehouses_tenant_name', type_='unique')
            if _constraint_exists('warehouses', 'uq_warehouses_tenant_code'):
                batch_op.drop_constraint('uq_warehouses_tenant_code', type_='unique')

    if _table_exists('purchases'):
        with op.batch_alter_table('purchases', schema=None) as batch_op:
            if _index_exists('purchases', 'ix_purchases_purchase_number'):
                batch_op.drop_index('ix_purchases_purchase_number')
            if _constraint_exists('purchases', 'uq_purchases_tenant_purchase_number'):
                batch_op.drop_constraint('uq_purchases_tenant_purchase_number', type_='unique')

    if _table_exists('purchase_lines'):
        with op.batch_alter_table('purchase_lines', schema=None) as batch_op:
            if not _index_exists('purchase_lines', 'ix_purchase_lines_product_id'):
                batch_op.create_index('ix_purchase_lines_product_id', ['product_id'], unique=False)

    if _table_exists('products'):
        with op.batch_alter_table('products', schema=None) as batch_op:
            if _index_exists('products', 'ix_products_sku'):
                batch_op.drop_index('ix_products_sku')
            if _index_exists('products', 'ix_products_barcode'):
                batch_op.drop_index('ix_products_barcode')

    if _table_exists('product_returns'):
        with op.batch_alter_table('product_returns', schema=None) as batch_op:
            if _constraint_exists('product_returns', 'uq_product_returns_tenant_return_number'):
                batch_op.drop_constraint('uq_product_returns_tenant_return_number', type_='unique')
            if not _index_exists('product_returns', 'ix_product_returns_return_number'):
                batch_op.create_index('ix_product_returns_return_number', ['return_number'], unique=False)

    if _table_exists('product_categories'):
        with op.batch_alter_table('product_categories', schema=None) as batch_op:
            if _index_exists('product_categories', 'ix_product_categories_name'):
                batch_op.drop_index('ix_product_categories_name')
            if _constraint_exists('product_categories', 'uq_product_categories_tenant_name'):
                batch_op.drop_constraint('uq_product_categories_tenant_name', type_='unique')

    if _table_exists('payments'):
        with op.batch_alter_table('payments', schema=None) as batch_op:
            if _index_exists('payments', 'ix_payments_payment_number'):
                batch_op.drop_index('ix_payments_payment_number')
            if _constraint_exists('payments', 'uq_payments_tenant_payment_number'):
                batch_op.drop_constraint('uq_payments_tenant_payment_number', type_='unique')

    if _table_exists('partners'):
        with op.batch_alter_table('partners', schema=None) as batch_op:
            if _constraint_exists('partners', 'uq_partners_tenant_code'):
                batch_op.drop_constraint('uq_partners_tenant_code', type_='unique')

    if _table_exists('partner_commission_entries'):
        with op.batch_alter_table('partner_commission_entries', schema=None) as batch_op:
            if not _index_exists('partner_commission_entries', 'ix_partner_commission_entries_tenant_product'):
                batch_op.create_index('ix_partner_commission_entries_tenant_product', ['tenant_id', 'product_id'], unique=False)

    if _table_exists('gl_journal_lines'):
        with op.batch_alter_table('gl_journal_lines', schema=None) as batch_op:
            if not _index_exists('gl_journal_lines', 'ix_gl_journal_lines_tenant_account'):
                batch_op.create_index('ix_gl_journal_lines_tenant_account', ['tenant_id', 'account_id'], unique=False)

    if _table_exists('gl_journal_entries'):
        with op.batch_alter_table('gl_journal_entries', schema=None) as batch_op:
            if not _index_exists('gl_journal_entries', 'ix_gl_journal_entries_tenant_entry_date'):
                batch_op.create_index('ix_gl_journal_entries_tenant_entry_date', ['tenant_id', 'entry_date'], unique=False)

    if _table_exists('expenses'):
        with op.batch_alter_table('expenses', schema=None) as batch_op:
            if _constraint_exists('expenses', 'uq_expenses_tenant_expense_number'):
                batch_op.drop_constraint('uq_expenses_tenant_expense_number', type_='unique')
            if _index_exists('expenses', 'ix_expenses_expense_number'):
                batch_op.drop_index('ix_expenses_expense_number')

    if _table_exists('expense_categories'):
        with op.batch_alter_table('expense_categories', schema=None) as batch_op:
            if _constraint_exists('expense_categories', 'uq_expense_categories_tenant_name'):
                batch_op.drop_constraint('uq_expense_categories_tenant_name', type_='unique')
            if _index_exists('expense_categories', 'ix_expense_categories_name'):
                batch_op.drop_index('ix_expense_categories_name')

    if _table_exists('error_audit_logs'):
        with op.batch_alter_table('error_audit_logs', schema=None) as batch_op:
            for idx in ['ix_error_audit_logs_request_id', 'ix_error_audit_logs_last_seen_at',
                        'ix_error_audit_logs_first_seen_at', 'ix_error_audit_logs_fingerprint']:
                if _index_exists('error_audit_logs', idx):
                    batch_op.drop_index(idx)

    if _table_exists('cost_centers'):
        with op.batch_alter_table('cost_centers', schema=None) as batch_op:
            if _index_exists('cost_centers', 'ix_cost_centers_code'):
                batch_op.drop_index('ix_cost_centers_code')

    if _table_exists('cheques'):
        with op.batch_alter_table('cheques', schema=None) as batch_op:
            if _index_exists('cheques', 'ix_cheques_cheque_number'):
                batch_op.drop_index('ix_cheques_cheque_number')
            if _constraint_exists('cheques', 'uq_cheques_tenant_cheque_number'):
                batch_op.drop_constraint('uq_cheques_tenant_cheque_number', type_='unique')

    if _table_exists('branches'):
        with op.batch_alter_table('branches', schema=None) as batch_op:
            if _constraint_exists('branches', 'uq_branches_tenant_name'):
                batch_op.drop_constraint('uq_branches_tenant_name', type_='unique')
            if _constraint_exists('branches', 'uq_branches_tenant_code'):
                batch_op.drop_constraint('uq_branches_tenant_code', type_='unique')
