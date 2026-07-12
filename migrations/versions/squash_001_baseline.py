"""Squashed explicit platform baseline.

Revision ID: squash_001
Revises:
Create Date: 2026-07-12

This is a fully-squashed baseline. The schema is compiled explicitly with
op.create_table() (NO db.create_all() / NO live-model dependency). It creates
the full platform schema (tables, indexes, foreign keys) and provides an
explicit downgrade. NO tenant data is seeded here -- tenants (e.g. demo) are
provisioned by the dedicated seed commands at runtime.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = 'squash_001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('branches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=50), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('is_main', sa.Boolean(), nullable=True),
    sa.Column('prices_include_vat', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_branches_tenant_code'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_branches_tenant_name')
    )
    op.create_table('cheques',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('cheque_number', sa.String(length=50), nullable=False),
    sa.Column('cheque_bank_number', sa.String(length=50), nullable=False),
    sa.Column('cheque_type', sa.String(length=20), nullable=False),
    sa.Column('bank_name', sa.String(length=200), nullable=False),
    sa.Column('bank_branch', sa.String(length=200), nullable=True),
    sa.Column('account_number', sa.String(length=100), nullable=True),
    sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=True),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('clearance_exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('actual_amount_aed', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('currency_gain_loss', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('issue_date', sa.Date(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('deposit_date', sa.Date(), nullable=True),
    sa.Column('clearance_date', sa.Date(), nullable=True),
    sa.Column('cleared_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('drawer_name', sa.String(length=200), nullable=True),
    sa.Column('drawer_id_number', sa.String(length=50), nullable=True),
    sa.Column('payee_name', sa.String(length=200), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('supplier_id', sa.Integer(), nullable=True),
    sa.Column('sale_id', sa.Integer(), nullable=True),
    sa.Column('purchase_id', sa.Integer(), nullable=True),
    sa.Column('payment_id', sa.Integer(), nullable=True),
    sa.Column('receipt_id', sa.Integer(), nullable=True),
    sa.Column('expense_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('bounce_reason', sa.String(length=500), nullable=True),
    sa.Column('days_until_due', sa.Integer(), nullable=True),
    sa.Column('is_overdue', sa.Boolean(), nullable=True),
    sa.Column('alert_sent', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('archive_reason', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'cheque_number', name='uq_cheques_tenant_cheque_number')
    )
    op.create_table('currencies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=3), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('symbol', sa.String(length=10), nullable=True),
    sa.Column('is_base', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('industry_field_definitions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('industry_code', sa.String(length=50), nullable=False),
    sa.Column('field_code', sa.String(length=50), nullable=False),
    sa.Column('field_name_ar', sa.String(length=100), nullable=False),
    sa.Column('field_name_en', sa.String(length=100), nullable=False),
    sa.Column('field_type', sa.String(length=20), nullable=True),
    sa.Column('field_options', sa.JSON(), nullable=True),
    sa.Column('applies_to', sa.String(length=20), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('is_required', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('industry_code', 'field_code', name='uq_industry_field_code')
    )
    op.create_table('packages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=False),
    sa.Column('name_en', sa.String(length=100), nullable=False),
    sa.Column('slug', sa.String(length=50), nullable=False),
    sa.Column('icon', sa.String(length=50), nullable=True),
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=True),
    sa.Column('description_ar', sa.Text(), nullable=True),
    sa.Column('description_en', sa.Text(), nullable=True),
    sa.Column('features', sa.JSON(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('is_featured', sa.Boolean(), nullable=True),
    sa.Column('badge_text', sa.String(length=50), nullable=True),
    sa.Column('badge_color', sa.String(length=20), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('support_duration_months', sa.Integer(), nullable=True),
    sa.Column('max_users', sa.Integer(), nullable=True),
    sa.Column('max_branches', sa.Integer(), nullable=True),
    sa.Column('has_ai', sa.Boolean(), nullable=True),
    sa.Column('has_whatsapp', sa.Boolean(), nullable=True),
    sa.Column('has_pos', sa.Boolean(), nullable=True),
    sa.Column('has_advanced_reports', sa.Boolean(), nullable=True),
    sa.Column('has_customization', sa.Boolean(), nullable=True),
    sa.Column('has_training', sa.Boolean(), nullable=True),
    sa.Column('has_priority_support', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('payment_number', sa.String(length=50), nullable=False),
    sa.Column('payment_type', sa.String(length=20), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=True),
    sa.Column('sale_id', sa.Integer(), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('supplier_id', sa.Integer(), nullable=True),
    sa.Column('supplier_name', sa.String(length=200), nullable=True),
    sa.Column('purchase_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('payment_method', sa.String(length=20), nullable=False),
    sa.Column('reference_number', sa.String(length=100), nullable=True),
    sa.Column('cheque_number', sa.String(length=50), nullable=True),
    sa.Column('cheque_date', sa.Date(), nullable=True),
    sa.Column('bank_name', sa.String(length=100), nullable=True),
    sa.Column('cheque_id', sa.Integer(), nullable=True),
    sa.Column('payment_confirmed', sa.Boolean(), nullable=True),
    sa.Column('confirmation_date', sa.DateTime(), nullable=True),
    sa.Column('rejection_reason', sa.String(length=500), nullable=True),
    sa.Column('payment_date', sa.DateTime(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'payment_number', name='uq_payments_tenant_payment_number')
    )
    op.create_table('permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('category', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('receipts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('receipt_number', sa.String(length=50), nullable=False),
    sa.Column('source_type', sa.String(length=20), nullable=True),
    sa.Column('source_id', sa.Integer(), nullable=True),
    sa.Column('direction', sa.String(length=10), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('payment_method', sa.String(length=20), nullable=False),
    sa.Column('reference_number', sa.String(length=100), nullable=True),
    sa.Column('cheque_number', sa.String(length=50), nullable=True),
    sa.Column('cheque_date', sa.Date(), nullable=True),
    sa.Column('bank_name', sa.String(length=100), nullable=True),
    sa.Column('cheque_id', sa.Integer(), nullable=True),
    sa.Column('payment_confirmed', sa.Boolean(), nullable=True),
    sa.Column('confirmation_date', sa.DateTime(), nullable=True),
    sa.Column('rejection_reason', sa.String(length=500), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('receipt_date', sa.DateTime(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'receipt_number', name='uq_receipts_tenant_receipt_number')
    )
    op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('name_ar', sa.String(length=50), nullable=True),
    sa.Column('slug', sa.String(length=50), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('store_payment_methods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name_ar', sa.String(length=120), nullable=False),
    sa.Column('name_en', sa.String(length=120), nullable=False),
    sa.Column('description_ar', sa.Text(), nullable=True),
    sa.Column('description_en', sa.Text(), nullable=True),
    sa.Column('icon', sa.String(length=80), nullable=True),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('is_builtin', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('config_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tenants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('business_type', sa.String(length=50), nullable=True),
    sa.Column('industry', sa.String(length=100), nullable=True),
    sa.Column('address_ar', sa.Text(), nullable=True),
    sa.Column('address_en', sa.Text(), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('country', sa.String(length=100), nullable=True),
    sa.Column('phone_1', sa.String(length=50), nullable=True),
    sa.Column('phone_2', sa.String(length=50), nullable=True),
    sa.Column('mobile', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('website', sa.String(length=200), nullable=True),
    sa.Column('tax_number', sa.String(length=100), nullable=True),
    sa.Column('commercial_register', sa.String(length=100), nullable=True),
    sa.Column('license_number', sa.String(length=100), nullable=True),
    sa.Column('license_expiry', sa.Date(), nullable=True),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.Column('logo_dark_url', sa.String(length=500), nullable=True),
    sa.Column('favicon_url', sa.String(length=500), nullable=True),
    sa.Column('brand_color_primary', sa.String(length=20), nullable=True),
    sa.Column('brand_color_secondary', sa.String(length=20), nullable=True),
    sa.Column('subscription_plan', sa.String(length=50), nullable=True),
    sa.Column('subscription_start', sa.DateTime(), nullable=True),
    sa.Column('subscription_end', sa.DateTime(), nullable=True),
    sa.Column('is_trial', sa.Boolean(), nullable=True),
    sa.Column('trial_days_remaining', sa.Integer(), nullable=True),
    sa.Column('max_users', sa.Integer(), nullable=True),
    sa.Column('max_products', sa.Integer(), nullable=True),
    sa.Column('max_customers', sa.Integer(), nullable=True),
    sa.Column('max_suppliers', sa.Integer(), nullable=True),
    sa.Column('max_branches', sa.Integer(), nullable=True),
    sa.Column('max_warehouses', sa.Integer(), nullable=True),
    sa.Column('max_storage_mb', sa.Integer(), nullable=True),
    sa.Column('max_invoices_per_month', sa.Integer(), nullable=True),
    sa.Column('max_sales_per_month', sa.Integer(), nullable=True),
    sa.Column('data_retention_days', sa.Integer(), nullable=True),
    sa.Column('enable_multi_warehouse', sa.Boolean(), nullable=True),
    sa.Column('enable_multi_currency', sa.Boolean(), nullable=True),
    sa.Column('enable_gl', sa.Boolean(), nullable=True),
    sa.Column('enable_ai', sa.Boolean(), nullable=True),
    sa.Column('enable_reports', sa.Boolean(), nullable=True),
    sa.Column('enable_api', sa.Boolean(), nullable=True),
    sa.Column('enable_pos', sa.Boolean(), nullable=True),
    sa.Column('enable_payroll', sa.Boolean(), nullable=True),
    sa.Column('enable_cheques', sa.Boolean(), nullable=True),
    sa.Column('enable_expenses', sa.Boolean(), nullable=True),
    sa.Column('enable_store', sa.Boolean(), nullable=True),
    sa.Column('allow_data_export', sa.Boolean(), nullable=True),
    sa.Column('allow_custom_integrations', sa.Boolean(), nullable=True),
    sa.Column('default_currency', sa.String(length=3), nullable=True),
    sa.Column('default_language', sa.String(length=10), nullable=True),
    sa.Column('timezone', sa.String(length=50), nullable=True),
    sa.Column('date_format', sa.String(length=20), nullable=True),
    sa.Column('time_format', sa.String(length=20), nullable=True),
    sa.Column('fiscal_year_start', sa.Integer(), nullable=True),
    sa.Column('enable_tax', sa.Boolean(), nullable=True),
    sa.Column('default_tax_rate', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('vat_country', sa.String(length=2), nullable=True),
    sa.Column('base_currency', sa.String(length=3), nullable=True),
    sa.Column('prices_include_vat', sa.Boolean(), nullable=False),
    sa.Column('vat_number', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_suspended', sa.Boolean(), nullable=True),
    sa.Column('suspension_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=100), nullable=True),
    sa.Column('full_name_ar', sa.String(length=100), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('is_owner', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('email_verified', sa.Boolean(), nullable=True),
    sa.Column('last_login', sa.DateTime(), nullable=True),
    sa.Column('last_seen', sa.DateTime(), nullable=True),
    sa.Column('login_attempts', sa.Integer(), nullable=True),
    sa.Column('locked_until', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ai_expertise',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('domain', sa.String(length=100), nullable=False),
    sa.Column('topic', sa.String(length=200), nullable=False),
    sa.Column('knowledge', sa.Text(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('usage_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ai_interactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('session_id', sa.String(length=100), nullable=True),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('response', sa.Text(), nullable=True),
    sa.Column('intent', sa.String(length=100), nullable=True),
    sa.Column('was_successful', sa.Boolean(), nullable=True),
    sa.Column('response_time_ms', sa.Integer(), nullable=True),
    sa.Column('is_training_sample', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ai_memories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=True),
    sa.Column('access_count', sa.Integer(), nullable=False),
    sa.Column('last_accessed', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('api_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('secret', sa.String(length=128), nullable=True),
    sa.Column('service', sa.String(length=50), nullable=False),
    sa.Column('scope', sa.String(length=20), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('last_used', sa.DateTime(), nullable=True),
    sa.Column('usage_count', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('archived_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('table_name', sa.String(length=50), nullable=False),
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('archived_at', sa.DateTime(), nullable=False),
    sa.Column('archived_by', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('can_restore', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('attendances',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('check_in', sa.DateTime(), nullable=False),
    sa.Column('check_out', sa.DateTime(), nullable=True),
    sa.Column('work_hours', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('state', sa.String(length=20), nullable=True),
    sa.Column('notes', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('table_name', sa.String(length=50), nullable=True),
    sa.Column('record_id', sa.Integer(), nullable=True),
    sa.Column('changes', sa.JSON(), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('azad_subscription_fees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('fee_type', sa.String(length=20), nullable=False),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('billing_period_start', sa.Date(), nullable=True),
    sa.Column('billing_period_end', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('gl_posted', sa.Boolean(), nullable=False),
    sa.Column('gl_posted_at', sa.DateTime(), nullable=True),
    sa.Column('paid_at', sa.DateTime(), nullable=True),
    sa.Column('paid_amount_aed', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('payment_method', sa.String(length=50), nullable=True),
    sa.Column('payment_reference', sa.String(length=120), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('budgets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('budget_number', sa.String(length=50), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('fiscal_year', sa.Integer(), nullable=False),
    sa.Column('period_type', sa.String(length=20), nullable=True),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('total_budgeted', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('total_actual', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('total_variance', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('variance_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('approved_by', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'budget_number', name='uq_budgets_tenant_budget_number')
    )
    op.create_table('campaigns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=True),
    sa.Column('campaign_type', sa.String(length=30), nullable=False),
    sa.Column('discount_value', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('max_discount_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('start_date', sa.DateTime(), nullable=False),
    sa.Column('end_date', sa.DateTime(), nullable=False),
    sa.Column('min_order_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('min_quantity', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('applicable_products', sa.JSON(), nullable=True),
    sa.Column('applicable_categories', sa.JSON(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('usage_limit', sa.Integer(), nullable=True),
    sa.Column('usage_count', sa.Integer(), nullable=True),
    sa.Column('coupon_code', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('card_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('customer_name', sa.String(length=200), nullable=False),
    sa.Column('customer_email', sa.String(length=200), nullable=True),
    sa.Column('customer_phone', sa.String(length=50), nullable=True),
    sa.Column('transaction_type', sa.String(length=20), nullable=False),
    sa.Column('package', sa.String(length=50), nullable=True),
    sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
    sa.Column('card_last_4', sa.String(length=4), nullable=True),
    sa.Column('card_type', sa.String(length=20), nullable=True),
    sa.Column('card_bin', sa.String(length=6), nullable=True),
    sa.Column('encrypted_data', sa.LargeBinary(), nullable=True),
    sa.Column('transaction_id', sa.String(length=200), nullable=True),
    sa.Column('payment_gateway', sa.String(length=50), nullable=True),
    sa.Column('gateway_response', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('country_code', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('admin_notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('cost_centers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('level', sa.Integer(), nullable=True),
    sa.Column('center_type', sa.String(length=30), nullable=True),
    sa.Column('manager_id', sa.Integer(), nullable=True),
    sa.Column('budget_amount', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_cost_centers_tenant_code')
    )
    op.create_table('crm_stages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('sequence', sa.Integer(), nullable=True),
    sa.Column('probability', sa.Integer(), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('is_won', sa.Boolean(), nullable=True),
    sa.Column('is_lost', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('crm_teams',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('leader_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('departments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('manager_id', sa.Integer(), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('document_sequences',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('pattern', sa.String(length=200), nullable=False),
    sa.Column('prefix', sa.String(length=20), nullable=False),
    sa.Column('counter', sa.Integer(), nullable=False),
    sa.Column('counter_reset', sa.String(length=20), nullable=False),
    sa.Column('branch_scoped', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_doc_seq_tenant_code')
    )
    op.create_table('document_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('document_type', sa.String(length=50), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('snapshot_data', sa.JSON(), nullable=False),
    sa.Column('branding_snapshot', sa.JSON(), nullable=True),
    sa.Column('snapshot_reason', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('document_verifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('document_type', sa.String(length=50), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('document_hash', sa.String(length=64), nullable=False),
    sa.Column('public_token', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('donations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('amount_usd', sa.Numeric(precision=15, scale=2), nullable=False),
    sa.Column('amount_crypto', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('payment_method', sa.String(length=50), nullable=False),
    sa.Column('crypto_type', sa.String(length=20), nullable=True),
    sa.Column('wallet_address', sa.String(length=200), nullable=True),
    sa.Column('transaction_hash', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('donor_name', sa.String(length=200), nullable=True),
    sa.Column('donor_email', sa.String(length=200), nullable=True),
    sa.Column('donor_message', sa.Text(), nullable=True),
    sa.Column('transaction_type', sa.String(length=20), nullable=True),
    sa.Column('package', sa.String(length=50), nullable=True),
    sa.Column('customer_name', sa.String(length=200), nullable=True),
    sa.Column('customer_email', sa.String(length=200), nullable=True),
    sa.Column('customer_phone', sa.String(length=50), nullable=True),
    sa.Column('converted_to_crypto', sa.Boolean(), nullable=True),
    sa.Column('conversion_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('final_wallet_address', sa.String(length=200), nullable=True),
    sa.Column('gateway_name', sa.String(length=50), nullable=True),
    sa.Column('gateway_transaction_id', sa.String(length=200), nullable=True),
    sa.Column('gateway_status', sa.String(length=50), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('country_code', sa.String(length=10), nullable=True),
    sa.Column('thank_you_sent', sa.Boolean(), nullable=True),
    sa.Column('notification_sent', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('admin_notes', sa.Text(), nullable=True),
    sa.Column('gl_posted', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('email_lists',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('email_templates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('body_html', sa.Text(), nullable=False),
    sa.Column('from_email', sa.String(length=200), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('employees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=100), nullable=True),
    sa.Column('employment_type', sa.String(length=20), nullable=True),
    sa.Column('contract_type', sa.String(length=20), nullable=True),
    sa.Column('basic_salary', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('allowances', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('joined_date', sa.Date(), nullable=True),
    sa.Column('termination_date', sa.Date(), nullable=True),
    sa.Column('termination_reason', sa.String(length=255), nullable=True),
    sa.Column('annual_leave_days', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('error_audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('occurrence_count', sa.Integer(), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.Column('level', sa.String(length=20), nullable=False),
    sa.Column('category', sa.String(length=30), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('exception_type', sa.String(length=200), nullable=True),
    sa.Column('stack_trace', sa.Text(), nullable=True),
    sa.Column('request_id', sa.String(length=36), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('method', sa.String(length=10), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('environment', sa.String(length=20), nullable=True),
    sa.Column('app_version', sa.String(length=30), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('request_data', sa.JSON(), nullable=True),
    sa.Column('is_resolved', sa.Boolean(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('resolved_by', sa.Integer(), nullable=True),
    sa.Column('resolution_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('exchange_rate_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('from_currency', sa.String(length=3), nullable=False),
    sa.Column('to_currency', sa.String(length=3), nullable=False),
    sa.Column('rate', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('source', sa.String(length=30), nullable=True),
    sa.Column('api_provider', sa.String(length=50), nullable=True),
    sa.Column('api_response_id', sa.String(length=100), nullable=True),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('locked_by_document_type', sa.String(length=50), nullable=True),
    sa.Column('locked_by_document_id', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'from_currency', 'to_currency', 'effective_date', name='uq_rate_tenant_pair_date')
    )
    op.create_table('exchange_rates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('from_currency', sa.String(length=3), nullable=False),
    sa.Column('to_currency', sa.String(length=3), nullable=False),
    sa.Column('currency_id', sa.Integer(), nullable=True),
    sa.Column('rate', sa.Numeric(precision=15, scale=6), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=True),
    sa.Column('is_manual', sa.Boolean(), nullable=True),
    sa.Column('valid_from', sa.DateTime(), nullable=False),
    sa.Column('valid_until', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('expense_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('gl_account_code', sa.String(length=20), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_expense_categories_tenant_name')
    )
    op.create_table('fiscal_positions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('vat_required', sa.Boolean(), nullable=True),
    sa.Column('auto_apply', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_fiscal_pos_tenant_code')
    )
    op.create_table('gl_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('sub_type', sa.String(length=50), nullable=True),
    sa.Column('is_reconcile', sa.Boolean(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_header', sa.Boolean(), nullable=True),
    sa.Column('level', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('industry_code', sa.String(length=50), nullable=True),
    sa.Column('module_code', sa.String(length=50), nullable=True),
    sa.Column('liquidity_kind', sa.String(length=20), nullable=True),
    sa.Column('is_default_liquidity', sa.Boolean(), nullable=False),
    sa.Column('bank_name', sa.String(length=200), nullable=True),
    sa.Column('bank_account_number', sa.String(length=100), nullable=True),
    sa.Column('bank_iban', sa.String(length=50), nullable=True),
    sa.Column('bank_swift_code', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_gl_accounts_tenant_code')
    )
    op.create_table('gl_journal_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('entry_number', sa.String(length=50), nullable=False),
    sa.Column('entry_date', sa.DateTime(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('reference_type', sa.String(length=50), nullable=True),
    sa.Column('reference_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('entry_type', sa.String(length=30), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('total_debit', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('total_credit', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('is_posted', sa.Boolean(), nullable=True),
    sa.Column('is_reversed', sa.Boolean(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('validation_errors', sa.Text(), nullable=True),
    sa.Column('validated_at', sa.DateTime(), nullable=True),
    sa.Column('validated_by', sa.Integer(), nullable=True),
    sa.Column('reversed_entry_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'entry_number', name='uq_gl_journal_entries_tenant_number')
    )
    op.create_table('gl_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=False),
    sa.Column('is_closed', sa.Boolean(), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('closed_by', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'year', 'month', name='uq_gl_periods_tenant_ym')
    )
    op.create_table('integration_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('service_name', sa.String(length=50), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('config_data', sa.Text(), nullable=True),
    sa.Column('last_tested_at', sa.DateTime(), nullable=True),
    sa.Column('last_test_status', sa.String(length=20), nullable=True),
    sa.Column('last_test_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'service_name', name='uq_integration_settings_tenant_service')
    )
    op.create_table('invoice_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('company_name_ar', sa.String(length=200), nullable=False),
    sa.Column('company_name_en', sa.String(length=200), nullable=False),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.Column('logo_path', sa.String(length=500), nullable=True),
    sa.Column('stamp_url', sa.String(length=500), nullable=True),
    sa.Column('signature_url', sa.String(length=500), nullable=True),
    sa.Column('address_ar', sa.Text(), nullable=True),
    sa.Column('address_en', sa.Text(), nullable=True),
    sa.Column('phone_1', sa.String(length=50), nullable=True),
    sa.Column('phone_2', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=100), nullable=True),
    sa.Column('website', sa.String(length=200), nullable=True),
    sa.Column('tax_number', sa.String(length=100), nullable=True),
    sa.Column('commercial_register', sa.String(length=100), nullable=True),
    sa.Column('license_number', sa.String(length=100), nullable=True),
    sa.Column('bank_name', sa.String(length=200), nullable=True),
    sa.Column('bank_account_number', sa.String(length=100), nullable=True),
    sa.Column('iban', sa.String(length=100), nullable=True),
    sa.Column('swift_code', sa.String(length=50), nullable=True),
    sa.Column('header_color', sa.String(length=20), nullable=True),
    sa.Column('accent_color', sa.String(length=20), nullable=True),
    sa.Column('text_color', sa.String(length=20), nullable=True),
    sa.Column('show_logo', sa.Boolean(), nullable=True),
    sa.Column('logo_position', sa.String(length=20), nullable=True),
    sa.Column('logo_size', sa.String(length=20), nullable=True),
    sa.Column('footer_text_ar', sa.Text(), nullable=True),
    sa.Column('footer_text_en', sa.Text(), nullable=True),
    sa.Column('show_terms', sa.Boolean(), nullable=True),
    sa.Column('terms_conditions_ar', sa.Text(), nullable=True),
    sa.Column('terms_conditions_en', sa.Text(), nullable=True),
    sa.Column('payment_terms_ar', sa.Text(), nullable=True),
    sa.Column('payment_terms_en', sa.Text(), nullable=True),
    sa.Column('default_invoice_note_ar', sa.Text(), nullable=True),
    sa.Column('default_invoice_note_en', sa.Text(), nullable=True),
    sa.Column('default_receipt_note_ar', sa.Text(), nullable=True),
    sa.Column('default_receipt_note_en', sa.Text(), nullable=True),
    sa.Column('enable_qr_code', sa.Boolean(), nullable=True),
    sa.Column('qr_position', sa.String(length=20), nullable=True),
    sa.Column('enable_watermark', sa.Boolean(), nullable=True),
    sa.Column('watermark_text', sa.String(length=200), nullable=True),
    sa.Column('watermark_image_path', sa.String(length=500), nullable=True),
    sa.Column('watermark_opacity', sa.Numeric(precision=3, scale=2), nullable=True),
    sa.Column('paper_size', sa.String(length=20), nullable=True),
    sa.Column('orientation', sa.String(length=20), nullable=True),
    sa.Column('default_language', sa.String(length=10), nullable=True),
    sa.Column('show_barcode', sa.Boolean(), nullable=True),
    sa.Column('show_page_numbers', sa.Boolean(), nullable=True),
    sa.Column('show_due_date', sa.Boolean(), nullable=True),
    sa.Column('facebook_url', sa.String(length=200), nullable=True),
    sa.Column('instagram_url', sa.String(length=200), nullable=True),
    sa.Column('whatsapp_number', sa.String(length=50), nullable=True),
    sa.Column('active_template', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('leave_types',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('allocation_type', sa.String(length=20), nullable=True),
    sa.Column('days_per_year', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('login_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('login_time', sa.DateTime(), nullable=True),
    sa.Column('logout_time', sa.DateTime(), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=True),
    sa.Column('failure_reason', sa.String(length=200), nullable=True),
    sa.Column('device_type', sa.String(length=50), nullable=True),
    sa.Column('browser', sa.String(length=100), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('package_purchases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=False),
    sa.Column('customer_name', sa.String(length=200), nullable=False),
    sa.Column('customer_email', sa.String(length=200), nullable=False),
    sa.Column('customer_phone', sa.String(length=50), nullable=True),
    sa.Column('company_name', sa.String(length=200), nullable=True),
    sa.Column('payment_method', sa.String(length=50), nullable=False),
    sa.Column('payment_status', sa.String(length=50), nullable=True),
    sa.Column('amount_paid', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=True),
    sa.Column('transaction_id', sa.String(length=200), nullable=True),
    sa.Column('payment_details', sa.JSON(), nullable=True),
    sa.Column('activation_status', sa.String(length=50), nullable=True),
    sa.Column('activation_date', sa.DateTime(), nullable=True),
    sa.Column('expiry_date', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('partners',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=True),
    sa.Column('scope_type', sa.String(length=20), nullable=False),
    sa.Column('scope_id', sa.Integer(), nullable=True),
    sa.Column('partner_type', sa.String(length=30), nullable=False),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('id_number', sa.String(length=100), nullable=True),
    sa.Column('investment_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('share_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('fixed_monthly_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('expense_share_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('loss_share_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('min_profit_threshold', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('current_balance', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_profit_received', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_loss_borne', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_withdrawals', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_additional_investment', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_partners_tenant_code')
    )
    op.create_table('payment_vault',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('vault_password_hash', sa.String(length=255), nullable=False),
    sa.Column('vault_name', sa.String(length=100), nullable=True),
    sa.Column('is_locked', sa.Boolean(), nullable=True),
    sa.Column('last_access', sa.DateTime(), nullable=True),
    sa.Column('nowpayments_api_key', sa.String(length=255), nullable=True),
    sa.Column('nowpayments_ipn_secret', sa.String(length=255), nullable=True),
    sa.Column('bitcoin_address', sa.String(length=255), nullable=True),
    sa.Column('ethereum_address', sa.String(length=255), nullable=True),
    sa.Column('usdt_address', sa.String(length=255), nullable=True),
    sa.Column('paypal_client_id', sa.String(length=255), nullable=True),
    sa.Column('paypal_client_secret', sa.String(length=255), nullable=True),
    sa.Column('paypal_business_email', sa.String(length=200), nullable=True),
    sa.Column('paypal_mode', sa.String(length=20), nullable=True),
    sa.Column('bank_name', sa.String(length=200), nullable=True),
    sa.Column('bank_account_name', sa.String(length=200), nullable=True),
    sa.Column('bank_account_number', sa.String(length=100), nullable=True),
    sa.Column('bank_iban', sa.String(length=50), nullable=True),
    sa.Column('bank_swift_code', sa.String(length=20), nullable=True),
    sa.Column('bank_branch', sa.String(length=200), nullable=True),
    sa.Column('bank_country', sa.String(length=100), nullable=True),
    sa.Column('bank_currency', sa.String(length=10), nullable=True),
    sa.Column('stripe_publishable_key', sa.String(length=255), nullable=True),
    sa.Column('stripe_secret_key', sa.String(length=255), nullable=True),
    sa.Column('stripe_webhook_secret', sa.String(length=255), nullable=True),
    sa.Column('mollie_api_key', sa.String(length=255), nullable=True),
    sa.Column('square_access_token', sa.String(length=255), nullable=True),
    sa.Column('razorpay_key_id', sa.String(length=255), nullable=True),
    sa.Column('razorpay_key_secret', sa.String(length=255), nullable=True),
    sa.Column('min_donation_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('max_donation_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('daily_limit', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('donations_enabled', sa.Boolean(), nullable=True),
    sa.Column('donation_page_enabled', sa.Boolean(), nullable=True),
    sa.Column('donation_title_ar', sa.String(length=200), nullable=True),
    sa.Column('donation_title_en', sa.String(length=200), nullable=True),
    sa.Column('donation_intro_ar', sa.Text(), nullable=True),
    sa.Column('donation_intro_en', sa.Text(), nullable=True),
    sa.Column('donation_debit_account', sa.String(length=20), nullable=True),
    sa.Column('donation_credit_account', sa.String(length=20), nullable=True),
    sa.Column('require_2fa', sa.Boolean(), nullable=True),
    sa.Column('auto_lock_minutes', sa.Integer(), nullable=True),
    sa.Column('max_failed_attempts', sa.Integer(), nullable=True),
    sa.Column('failed_attempts', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('payroll_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('payroll_jurisdiction', sa.String(length=50), nullable=True),
    sa.Column('country_code', sa.String(length=3), nullable=True),
    sa.Column('annual_leave_days', sa.Integer(), nullable=True),
    sa.Column('eos_calculation_method', sa.String(length=50), nullable=True),
    sa.Column('rounding_policy', sa.String(length=20), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pos_floors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pos_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('session_number', sa.String(length=50), nullable=False),
    sa.Column('opened_at', sa.DateTime(), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('opening_balance_cash', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('closing_balance_cash', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('expected_balance', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('difference', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_sales', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_cash_sales', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_card_sales', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'session_number', name='uq_pos_sessions_tenant_session_number')
    )
    op.create_table('print_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('document_type', sa.String(length=50), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('metadata_json', sa.Text(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_product_categories_tenant_name')
    )
    op.create_table('profit_centers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('level', sa.Integer(), nullable=True),
    sa.Column('manager_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_profit_centers_tenant_code')
    )
    op.create_table('role_permissions',
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )
    op.create_table('security_alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('alert_type', sa.String(length=50), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('username', sa.String(length=50), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('method', sa.String(length=10), nullable=True),
    sa.Column('status_code', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('is_resolved', sa.Boolean(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('resolved_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shipments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('source_type', sa.String(length=20), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('carrier_name', sa.String(length=100), nullable=True),
    sa.Column('tracking_number', sa.String(length=100), nullable=True),
    sa.Column('tracking_url', sa.String(length=500), nullable=True),
    sa.Column('shipping_cost', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('customs_duty', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('insurance', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('estimated_delivery', sa.DateTime(), nullable=True),
    sa.Column('actual_delivery', sa.DateTime(), nullable=True),
    sa.Column('recipient_name', sa.String(length=200), nullable=True),
    sa.Column('recipient_phone', sa.String(length=50), nullable=True),
    sa.Column('recipient_address', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shop_newsletters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'email', name='uq_newsletter_tenant_email')
    )
    op.create_table('store_coupons',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('discount_percent', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('discount_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('min_order_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('max_uses', sa.Integer(), nullable=True),
    sa.Column('used_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('valid_from', sa.DateTime(), nullable=True),
    sa.Column('valid_until', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_store_coupon_tenant_code')
    )
    op.create_table('suppliers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=True),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('company_name', sa.String(length=200), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('phone2', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('website', sa.String(length=200), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('country', sa.String(length=100), nullable=True),
    sa.Column('tax_number', sa.String(length=50), nullable=True),
    sa.Column('commercial_registration', sa.String(length=50), nullable=True),
    sa.Column('supplier_type', sa.String(length=50), nullable=True),
    sa.Column('rating', sa.Integer(), nullable=True),
    sa.Column('credit_limit', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('payment_terms_days', sa.Integer(), nullable=True),
    sa.Column('preferred_currency', sa.String(length=3), nullable=True),
    sa.Column('total_purchases_aed', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_paid_aed', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('last_purchase_date', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('tags', sa.String(length=500), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_verified', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('system_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('system_name', sa.String(length=200), nullable=True),
    sa.Column('system_version', sa.String(length=20), nullable=True),
    sa.Column('system_mode', sa.String(length=20), nullable=True),
    sa.Column('theme', sa.String(length=50), nullable=True),
    sa.Column('primary_color', sa.String(length=20), nullable=True),
    sa.Column('secondary_color', sa.String(length=20), nullable=True),
    sa.Column('sidebar_color', sa.String(length=20), nullable=True),
    sa.Column('navbar_color', sa.String(length=20), nullable=True),
    sa.Column('sidebar_position', sa.String(length=20), nullable=True),
    sa.Column('layout_style', sa.String(length=20), nullable=True),
    sa.Column('enable_dark_mode', sa.Boolean(), nullable=True),
    sa.Column('default_dark_mode', sa.Boolean(), nullable=True),
    sa.Column('default_language', sa.String(length=10), nullable=True),
    sa.Column('available_languages', sa.Text(), nullable=True),
    sa.Column('rtl_enabled', sa.Boolean(), nullable=True),
    sa.Column('timezone', sa.String(length=50), nullable=True),
    sa.Column('date_format', sa.String(length=30), nullable=True),
    sa.Column('time_format', sa.String(length=30), nullable=True),
    sa.Column('datetime_format', sa.String(length=50), nullable=True),
    sa.Column('default_currency', sa.String(length=3), nullable=True),
    sa.Column('currency_symbol', sa.String(length=10), nullable=True),
    sa.Column('currency_position', sa.String(length=10), nullable=True),
    sa.Column('decimal_places', sa.Integer(), nullable=True),
    sa.Column('enable_tax', sa.Boolean(), nullable=True),
    sa.Column('tax_name_ar', sa.String(length=100), nullable=True),
    sa.Column('tax_name_en', sa.String(length=100), nullable=True),
    sa.Column('default_tax_rate', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('tax_number_required', sa.Boolean(), nullable=True),
    sa.Column('enable_sales', sa.Boolean(), nullable=True),
    sa.Column('enable_purchases', sa.Boolean(), nullable=True),
    sa.Column('enable_inventory', sa.Boolean(), nullable=True),
    sa.Column('enable_customers', sa.Boolean(), nullable=True),
    sa.Column('enable_suppliers', sa.Boolean(), nullable=True),
    sa.Column('enable_expenses', sa.Boolean(), nullable=True),
    sa.Column('enable_gl', sa.Boolean(), nullable=True),
    sa.Column('enable_reports', sa.Boolean(), nullable=True),
    sa.Column('enable_ai_assistant', sa.Boolean(), nullable=True),
    sa.Column('enable_pos', sa.Boolean(), nullable=True),
    sa.Column('enable_ecommerce', sa.Boolean(), nullable=True),
    sa.Column('enable_barcode_scanner', sa.Boolean(), nullable=True),
    sa.Column('enable_multi_warehouse', sa.Boolean(), nullable=True),
    sa.Column('enable_multi_currency', sa.Boolean(), nullable=True),
    sa.Column('enable_discounts', sa.Boolean(), nullable=True),
    sa.Column('enable_returns', sa.Boolean(), nullable=True),
    sa.Column('enable_batches', sa.Boolean(), nullable=True),
    sa.Column('enable_serials', sa.Boolean(), nullable=True),
    sa.Column('session_timeout', sa.Integer(), nullable=True),
    sa.Column('password_min_length', sa.Integer(), nullable=True),
    sa.Column('password_require_uppercase', sa.Boolean(), nullable=True),
    sa.Column('password_require_numbers', sa.Boolean(), nullable=True),
    sa.Column('password_require_special', sa.Boolean(), nullable=True),
    sa.Column('max_login_attempts', sa.Integer(), nullable=True),
    sa.Column('lockout_duration', sa.Integer(), nullable=True),
    sa.Column('enable_email_notifications', sa.Boolean(), nullable=True),
    sa.Column('enable_sms_notifications', sa.Boolean(), nullable=True),
    sa.Column('enable_push_notifications', sa.Boolean(), nullable=True),
    sa.Column('low_stock_notification', sa.Boolean(), nullable=True),
    sa.Column('items_per_page', sa.Integer(), nullable=True),
    sa.Column('enable_caching', sa.Boolean(), nullable=True),
    sa.Column('cache_ttl', sa.Integer(), nullable=True),
    sa.Column('enable_compression', sa.Boolean(), nullable=True),
    sa.Column('auto_backup_enabled', sa.Boolean(), nullable=True),
    sa.Column('backup_frequency', sa.String(length=20), nullable=True),
    sa.Column('backup_retention_days', sa.Integer(), nullable=True),
    sa.Column('enable_api', sa.Boolean(), nullable=True),
    sa.Column('api_rate_limit', sa.Integer(), nullable=True),
    sa.Column('custom_settings', sa.Text(), nullable=True),
    sa.Column('smtp_server', sa.String(length=200), nullable=True),
    sa.Column('smtp_port', sa.Integer(), nullable=True),
    sa.Column('smtp_username', sa.String(length=200), nullable=True),
    sa.Column('smtp_password', sa.String(length=200), nullable=True),
    sa.Column('smtp_use_tls', sa.Boolean(), nullable=True),
    sa.Column('email_from', sa.String(length=200), nullable=True),
    sa.Column('sms_provider', sa.String(length=50), nullable=True),
    sa.Column('sms_api_key', sa.String(length=200), nullable=True),
    sa.Column('sms_sender_name', sa.String(length=50), nullable=True),
    sa.Column('sms_enabled', sa.Boolean(), nullable=True),
    sa.Column('whatsapp_api_url', sa.String(length=500), nullable=True),
    sa.Column('whatsapp_api_key', sa.String(length=200), nullable=True),
    sa.Column('whatsapp_phone_number', sa.String(length=20), nullable=True),
    sa.Column('whatsapp_enabled', sa.Boolean(), nullable=True),
    sa.Column('notification_templates', sa.Text(), nullable=True),
    sa.Column('vat_enabled', sa.Boolean(), nullable=True),
    sa.Column('vat_number', sa.String(length=50), nullable=True),
    sa.Column('tax_id_number', sa.String(length=50), nullable=True),
    sa.Column('azad_platform_fee_rate', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('subscription_monthly_fee_aed', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('subscription_yearly_fee_aed', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('subscription_perpetual_fee_aed', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('auto_update_rates', sa.Boolean(), nullable=True),
    sa.Column('owner_whitelist_ips', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ticket_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('auto_assign_user_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ticket_priorities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('name_ar', sa.String(length=50), nullable=True),
    sa.Column('sequence', sa.Integer(), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('sla_hours', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('warehouses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=True),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.Column('warehouse_type', sa.String(length=20), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('manager_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('is_main', sa.Boolean(), nullable=True),
    sa.Column('allow_negative_inventory', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('extra_fields', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_warehouses_tenant_code'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_warehouses_tenant_name')
    )
    op.create_table('advanced_expenses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('expense_number', sa.String(length=50), nullable=False),
    sa.Column('expense_date', sa.Date(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('description_ar', sa.String(length=255), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('taxable_amount', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('tax_amount', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('tax_rate', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('tax_exempt', sa.Boolean(), nullable=True),
    sa.Column('customs_amount', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('customs_rate', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('customs_exempt', sa.Boolean(), nullable=True),
    sa.Column('payment_method', sa.String(length=50), nullable=True),
    sa.Column('payment_status', sa.String(length=50), nullable=True),
    sa.Column('paid_amount', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('requires_approval', sa.Boolean(), nullable=True),
    sa.Column('approval_status', sa.String(length=50), nullable=True),
    sa.Column('approved_by', sa.Integer(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('approval_notes', sa.Text(), nullable=True),
    sa.Column('attachment_count', sa.Integer(), nullable=True),
    sa.Column('has_receipt', sa.Boolean(), nullable=True),
    sa.Column('receipt_number', sa.String(length=100), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('gl_journal_entry_id', sa.Integer(), nullable=True),
    sa.Column('is_reversed', sa.Boolean(), nullable=True),
    sa.Column('reversed_at', sa.DateTime(), nullable=True),
    sa.Column('reversed_by', sa.Integer(), nullable=True),
    sa.Column('reversal_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'expense_number', name='uq_advanced_expenses_tenant_number')
    )
    op.create_table('bank_reconciliations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('reconciliation_number', sa.String(length=50), nullable=False),
    sa.Column('bank_account_id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('opening_balance_per_books', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('closing_balance_per_books', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('closing_balance_per_bank', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('outstanding_deposits', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('outstanding_withdrawals', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('bank_charges', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('bank_interest', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('errors_in_books', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('errors_in_bank', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('is_balanced', sa.Boolean(), nullable=True),
    sa.Column('difference', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('approved_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'reconciliation_number', name='uq_bank_reconciliations_tenant_number')
    )
    op.create_table('budget_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('budget_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('budgeted_amount', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('actual_amount', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('variance', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('variance_percentage', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('cash_boxes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('box_type', sa.String(length=30), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('current_balance', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('bank_name', sa.String(length=200), nullable=True),
    sa.Column('account_number', sa.String(length=100), nullable=True),
    sa.Column('iban', sa.String(length=50), nullable=True),
    sa.Column('swift_code', sa.String(length=20), nullable=True),
    sa.Column('gateway_provider', sa.String(length=50), nullable=True),
    sa.Column('gateway_merchant_id', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('gl_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_cash_boxes_tenant_code')
    )
    op.create_table('crm_team_members',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('team_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'team_id', 'user_id', name='uq_crm_team_member_tenant')
    )
    op.create_table('customers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=True),
    sa.Column('customer_type', sa.String(length=20), nullable=False),
    sa.Column('customer_classification', sa.String(length=20), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('tax_number', sa.String(length=50), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('fiscal_position_id', sa.Integer(), nullable=True),
    sa.Column('preferred_currency', sa.String(length=3), nullable=True),
    sa.Column('credit_limit', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_purchases', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('balance', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('customs_taxes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=False),
    sa.Column('tax_type', sa.String(length=50), nullable=False),
    sa.Column('rate', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('is_percentage', sa.Boolean(), nullable=True),
    sa.Column('fixed_amount', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('gl_account_id', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('email_campaigns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('list_id', sa.Integer(), nullable=True),
    sa.Column('template_id', sa.Integer(), nullable=True),
    sa.Column('scheduled_date', sa.DateTime(), nullable=True),
    sa.Column('sent_date', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('sent_count', sa.Integer(), nullable=True),
    sa.Column('open_count', sa.Integer(), nullable=True),
    sa.Column('click_count', sa.Integer(), nullable=True),
    sa.Column('bounce_count', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('employee_leaves',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('leave_type', sa.String(length=20), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('days_taken', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('expenses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('expense_number', sa.String(length=50), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('description_ar', sa.String(length=255), nullable=True),
    sa.Column('amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('expense_date', sa.DateTime(), nullable=False),
    sa.Column('payment_method', sa.String(length=20), nullable=False),
    sa.Column('reference_number', sa.String(length=100), nullable=True),
    sa.Column('cheque_number', sa.String(length=50), nullable=True),
    sa.Column('cheque_date', sa.Date(), nullable=True),
    sa.Column('bank_name', sa.String(length=100), nullable=True),
    sa.Column('supplier_name', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('is_reversed', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'expense_number', name='uq_expenses_tenant_expense_number')
    )
    op.create_table('fixed_assets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('asset_number', sa.String(length=50), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=50), nullable=True),
    sa.Column('asset_account_id', sa.Integer(), nullable=False),
    sa.Column('depreciation_account_id', sa.Integer(), nullable=True),
    sa.Column('expense_account_id', sa.Integer(), nullable=True),
    sa.Column('purchase_date', sa.Date(), nullable=False),
    sa.Column('purchase_price', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('salvage_value', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('depreciation_method', sa.String(length=30), nullable=True),
    sa.Column('useful_life_years', sa.Integer(), nullable=False),
    sa.Column('useful_life_months', sa.Integer(), nullable=True),
    sa.Column('accumulated_depreciation', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('book_value', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('last_depreciation_date', sa.Date(), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('cost_center_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('disposal_date', sa.Date(), nullable=True),
    sa.Column('disposal_price', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('disposal_gain_loss', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'asset_number', name='uq_fixed_assets_tenant_asset_number')
    )
    op.create_table('gl_account_mappings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('concept_code', sa.String(length=50), nullable=False),
    sa.Column('gl_account_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("concept_code IN ('AR', 'AP', 'CASH', 'BANK', 'INVENTORY_ASSET', 'COGS', 'COGS_REVERSAL', 'SALES_REVENUE', 'SALES_RETURNS', 'SALES_DISCOUNT', 'VAT_INPUT', 'VAT_OUTPUT', 'FX_GAIN', 'FX_LOSS', 'CHEQUES_UNDER_COLLECTION', 'INVENTORY_ADJUSTMENT_GAIN', 'INVENTORY_ADJUSTMENT_LOSS', 'FREIGHT_IN', 'CUSTOMS_DUTY', 'DEFERRED_CHEQUES_PAYABLE', 'PARTNER_CURRENT_ACCOUNT', 'MERCHANT_CURRENT_ACCOUNT', 'SHIPPING_REVENUE', 'MISC_EXPENSE', 'COMMISSION_EXPENSE', 'EMPLOYEE_ADVANCES', 'PAYROLL_EXPENSE', 'PAYROLL_PAYABLE', 'BANK_FEES', 'BANK_INTEREST_INCOME', 'DONATION_REVENUE', 'FIXED_ASSET_ASSET', 'DEPRECIATION_EXPENSE', 'ACCUMULATED_DEPRECIATION', 'FIXED_ASSET_GAIN', 'FIXED_ASSET_LOSS', 'SHOP_SALES_REVENUE', 'COUPON_EXPENSE', 'LOYALTY_LIABILITY', 'SHIPPING_COST_EXPENSE', 'CAMPAIGN_DISCOUNT_EXPENSE', 'WARRANTY_CLAIM_EXPENSE', 'PURCHASE_RETURNS', 'SALES_COMMISSION', 'TIER_DISCOUNT', 'CARD_PROCESSING_FEES', 'PURCHASES', 'LANDED_COST', 'FOOD_SALES_REVENUE', 'BEVERAGE_SALES_REVENUE', 'POS_CASH_DIFFERENCE', 'AZAD_PLATFORM_PAYABLE', 'AZAD_PLATFORM_FEE_ACCRUED', 'AZAD_PLATFORM_FEE_PAID', 'AZAD_SUBSCRIPTION_EXPENSE', 'AZAD_SUBSCRIPTION_REVENUE', 'OPENING_BALANCE_EQUITY', 'ACCOUNTS_PAYABLE', 'END_OF_SERVICE_PROVISION', 'END_OF_SERVICE_LIABILITY', 'LEAVE_ACCRUAL_LIABILITY', 'SUSPENSE')", name='ck_gl_account_mappings_concept_code'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('gl_journal_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('entry_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('debit', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('credit', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('warehouse_id', sa.Integer(), nullable=True),
    sa.Column('cost_center_id', sa.Integer(), nullable=True),
    sa.Column('profit_center_id', sa.Integer(), nullable=True),
    sa.Column('partner_id', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('job_positions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('department_id', sa.Integer(), nullable=True),
    sa.Column('no_of_employees', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('journal_entry_audits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('journal_entry_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('old_values', sa.Text(), nullable=True),
    sa.Column('new_values', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('performed_by', sa.Integer(), nullable=False),
    sa.Column('performed_at', sa.DateTime(), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('leave_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('leave_type_id', sa.Integer(), nullable=True),
    sa.Column('date_from', sa.Date(), nullable=False),
    sa.Column('date_to', sa.Date(), nullable=False),
    sa.Column('duration', sa.Numeric(precision=5, scale=1), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('state', sa.String(length=20), nullable=True),
    sa.Column('manager_id', sa.Integer(), nullable=True),
    sa.Column('rejected_reason', sa.String(length=500), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('partner_profit_distributions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('partner_id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('scope_type', sa.String(length=20), nullable=True),
    sa.Column('scope_id', sa.Integer(), nullable=True),
    sa.Column('total_revenue', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_cogs', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_expenses', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('net_profit', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('share_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('share_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('expense_share_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('expense_share_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('loss_share_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('loss_share_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('fixed_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('net_due', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('approved_by', sa.Integer(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('payment_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('level', sa.String(length=20), nullable=True),
    sa.Column('transaction_id', sa.String(length=100), nullable=True),
    sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('vault_id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('payment_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('transaction_id', sa.String(length=100), nullable=False),
    sa.Column('amount_usd', sa.Numeric(precision=15, scale=2), nullable=False),
    sa.Column('amount_crypto', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('crypto_currency', sa.String(length=10), nullable=False),
    sa.Column('payment_address', sa.String(length=255), nullable=True),
    sa.Column('payment_status', sa.String(length=20), nullable=True),
    sa.Column('payment_method', sa.String(length=50), nullable=True),
    sa.Column('customer_email', sa.String(length=255), nullable=True),
    sa.Column('customer_name', sa.String(length=255), nullable=True),
    sa.Column('customer_phone', sa.String(length=50), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('is_verified', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('vault_id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('transaction_id')
    )
    op.create_table('payroll_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=True),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('basic_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('days_worked', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('allowances', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('deductions', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('advances_deducted', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('net_salary', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('gl_entry_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'employee_id', 'month', 'year', name='uq_payroll_tenant_employee_period')
    )
    op.create_table('pos_tables',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('floor_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=20), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=True),
    sa.Column('pos_x', sa.Integer(), nullable=True),
    sa.Column('pos_y', sa.Integer(), nullable=True),
    sa.Column('shape', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('purchases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('purchase_number', sa.String(length=50), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=True),
    sa.Column('warehouse_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('supplier_name', sa.String(length=200), nullable=False),
    sa.Column('supplier_phone', sa.String(length=20), nullable=True),
    sa.Column('supplier_email', sa.String(length=120), nullable=True),
    sa.Column('purchase_date', sa.DateTime(), nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('discount_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('tax_rate', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('tax_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('taxable_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('prices_include_vat', sa.Boolean(), nullable=False),
    sa.Column('freight', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('insurance', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('customs_duty', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('other_landed_cost', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'purchase_number', name='uq_purchases_tenant_purchase_number')
    )
    op.create_table('salary_advances',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('deducted_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('remaining_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('date', sa.Date(), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('is_deducted', sa.Boolean(), nullable=True),
    sa.Column('fully_deducted_at', sa.DateTime(), nullable=True),
    sa.Column('gl_entry_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tenant_stores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('platform_disabled', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('store_slug', sa.String(length=100), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('tagline', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('whatsapp', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('min_order_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('delivery_note', sa.String(length=500), nullable=True),
    sa.Column('logo_path', sa.String(length=255), nullable=True),
    sa.Column('meta_title', sa.String(length=200), nullable=True),
    sa.Column('meta_description', sa.String(length=500), nullable=True),
    sa.Column('meta_keywords', sa.String(length=500), nullable=True),
    sa.Column('meta_title_en', sa.String(length=200), nullable=True),
    sa.Column('meta_description_en', sa.String(length=500), nullable=True),
    sa.Column('return_policy_ar', sa.Text(), nullable=True),
    sa.Column('return_policy_en', sa.Text(), nullable=True),
    sa.Column('low_stock_threshold', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('notify_whatsapp_on_order', sa.Boolean(), nullable=False),
    sa.Column('notify_email_on_order', sa.Boolean(), nullable=False),
    sa.Column('subdomain', sa.String(length=100), nullable=True),
    sa.Column('custom_domain', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_reconciliation_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('reconciliation_id', sa.Integer(), nullable=False),
    sa.Column('item_type', sa.String(length=30), nullable=False),
    sa.Column('transaction_date', sa.Date(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('journal_entry_id', sa.Integer(), nullable=True),
    sa.Column('cheque_id', sa.Integer(), nullable=True),
    sa.Column('is_cleared', sa.Boolean(), nullable=True),
    sa.Column('cleared_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('card_vault',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('card_hash', sa.String(length=64), nullable=False),
    sa.Column('card_number_encrypted', sa.LargeBinary(), nullable=False),
    sa.Column('cardholder_name_encrypted', sa.LargeBinary(), nullable=False),
    sa.Column('expiry_month_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('expiry_year_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('cvv_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('card_type', sa.String(length=20), nullable=True),
    sa.Column('last_four', sa.String(length=4), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('usage_count', sa.Integer(), nullable=True),
    sa.Column('last_used', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('crm_leads',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('company', sa.String(length=200), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('stage_id', sa.Integer(), nullable=True),
    sa.Column('team_id', sa.Integer(), nullable=True),
    sa.Column('assigned_user_id', sa.Integer(), nullable=True),
    sa.Column('expected_revenue', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('priority', sa.String(length=20), nullable=True),
    sa.Column('source', sa.String(length=50), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('depreciation_schedules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('period_date', sa.Date(), nullable=False),
    sa.Column('depreciation_amount', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('accumulated_depreciation', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('book_value', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('journal_entry_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('email_subscribers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('list_id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('unsubscribed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('list_id', 'email', name='uq_email_subscriber')
    )
    op.create_table('hr_contracts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('department_id', sa.Integer(), nullable=True),
    sa.Column('job_id', sa.Integer(), nullable=True),
    sa.Column('date_start', sa.Date(), nullable=False),
    sa.Column('date_end', sa.Date(), nullable=True),
    sa.Column('wage', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('state', sa.String(length=20), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('partner_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('partner_id', sa.Integer(), nullable=False),
    sa.Column('distribution_id', sa.Integer(), nullable=True),
    sa.Column('transaction_type', sa.String(length=30), nullable=False),
    sa.Column('amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_base', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('balance_after', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('reference_number', sa.String(length=100), nullable=True),
    sa.Column('reference_type', sa.String(length=30), nullable=True),
    sa.Column('reference_id', sa.Integer(), nullable=True),
    sa.Column('transaction_date', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('products',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=True),
    sa.Column('commercial_name', sa.String(length=200), nullable=True),
    sa.Column('sku', sa.String(length=50), nullable=True),
    sa.Column('part_number', sa.String(length=100), nullable=True),
    sa.Column('barcode', sa.String(length=100), nullable=True),
    sa.Column('country_of_origin', sa.String(length=100), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('merchant_customer_id', sa.Integer(), nullable=True),
    sa.Column('cost_price', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('regular_price', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('merchant_price', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('merchant_share', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('partner_price', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('current_stock', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('min_stock_alert', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('has_serial_number', sa.Boolean(), nullable=False),
    sa.Column('warranty_days', sa.Integer(), nullable=True),
    sa.Column('unit', sa.String(length=20), nullable=True),
    sa.Column('location', sa.String(length=50), nullable=True),
    sa.Column('warranty_period', sa.Integer(), nullable=True),
    sa.Column('warranty_unit', sa.String(length=20), nullable=True),
    sa.Column('is_returnable', sa.Boolean(), nullable=True),
    sa.Column('return_period_days', sa.Integer(), nullable=True),
    sa.Column('image_url', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('industry', sa.String(length=50), nullable=True),
    sa.Column('extra_fields', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('date_start', sa.DateTime(), nullable=True),
    sa.Column('date_end', sa.DateTime(), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('purchase_returns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('return_number', sa.String(length=50), nullable=False),
    sa.Column('purchase_id', sa.Integer(), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('return_date', sa.DateTime(), nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('processed_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'return_number', name='uq_purchase_returns_tenant_return_number')
    )
    op.create_table('sales',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('sale_number', sa.String(length=50), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('seller_id', sa.Integer(), nullable=False),
    sa.Column('sales_rep_id', sa.Integer(), nullable=True),
    sa.Column('warehouse_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('sale_date', sa.DateTime(), nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('discount_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('shipping_cost', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('tax_rate', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('tax_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('taxable_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('total_amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('paid_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('balance_due', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('paid_amount_aed', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('prices_include_vat', sa.Boolean(), nullable=False),
    sa.Column('payment_status', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('checkout_payment_method', sa.String(length=50), nullable=True),
    sa.Column('checkout_gateway_ref', sa.String(length=120), nullable=True),
    sa.Column('coupon_code', sa.String(length=50), nullable=True),
    sa.Column('pos_session_id', sa.Integer(), nullable=True),
    sa.Column('order_type', sa.String(length=20), nullable=True),
    sa.Column('table_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'sale_number', name='uq_sales_tenant_sale_number')
    )
    op.create_table('shop_customer_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=30), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.Column('password_reset_token', sa.String(length=128), nullable=True),
    sa.Column('password_reset_expires_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'email', name='uq_shop_customer_tenant_email')
    )
    op.create_table('tax_calculation_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_ar', sa.String(length=200), nullable=False),
    sa.Column('rule_type', sa.String(length=50), nullable=False),
    sa.Column('condition_field', sa.String(length=100), nullable=True),
    sa.Column('condition_operator', sa.String(length=20), nullable=True),
    sa.Column('condition_value', sa.String(length=255), nullable=True),
    sa.Column('tax_id', sa.Integer(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tickets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('number', sa.String(length=20), nullable=True),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('priority_id', sa.Integer(), nullable=True),
    sa.Column('assigned_user_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=True),
    sa.Column('sla_deadline', sa.DateTime(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('azad_platform_fees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=180), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=True),
    sa.Column('vault_id', sa.Integer(), nullable=True),
    sa.Column('rate_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('base_amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('fee_amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('transaction_scope', sa.String(length=30), nullable=False),
    sa.Column('payment_channel', sa.String(length=50), nullable=False),
    sa.Column('gateway_name', sa.String(length=50), nullable=True),
    sa.Column('gateway_reference', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('gl_posted', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key', name='uq_azad_platform_fees_idempotency_key')
    )
    op.create_table('bank_statement_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('bank_account_id', sa.Integer(), nullable=False),
    sa.Column('statement_date', sa.Date(), nullable=False),
    sa.Column('source_filename', sa.String(length=255), nullable=True),
    sa.Column('imported_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('transaction_date', sa.Date(), nullable=False),
    sa.Column('reference', sa.String(length=120), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('matched_at', sa.DateTime(), nullable=True),
    sa.Column('matched_by', sa.Integer(), nullable=True),
    sa.Column('match_type', sa.String(length=30), nullable=True),
    sa.Column('matched_journal_entry_id', sa.Integer(), nullable=True),
    sa.Column('matched_cheque_id', sa.Integer(), nullable=True),
    sa.Column('reconciliation_item_id', sa.Integer(), nullable=True),
    sa.Column('raw_data', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('campaign_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('campaign_id', sa.Integer(), nullable=False),
    sa.Column('subscriber_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=True),
    sa.Column('clicked_at', sa.DateTime(), nullable=True),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('crm_activities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('lead_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('activity_type', sa.String(length=30), nullable=False),
    sa.Column('summary', sa.String(length=500), nullable=True),
    sa.Column('date_deadline', sa.DateTime(), nullable=True),
    sa.Column('done_date', sa.DateTime(), nullable=True),
    sa.Column('is_done', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('fiscal_position_tax_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('fiscal_position_id', sa.Integer(), nullable=False),
    sa.Column('source_tax_id', sa.Integer(), nullable=True),
    sa.Column('source_account_id', sa.Integer(), nullable=True),
    sa.Column('destination_tax_id', sa.Integer(), nullable=True),
    sa.Column('destination_account_id', sa.Integer(), nullable=True),
    sa.Column('rule_type', sa.String(length=20), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pos_kds_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('order_number', sa.String(length=50), nullable=False),
    sa.Column('items_json', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pos_table_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('table_id', sa.Integer(), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('guest_count', sa.Integer(), nullable=True),
    sa.Column('is_split', sa.Boolean(), nullable=True),
    sa.Column('split_group', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_cost_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=False),
    sa.Column('movement_type', sa.String(length=30), nullable=False),
    sa.Column('movement_id', sa.Integer(), nullable=True),
    sa.Column('reference_type', sa.String(length=50), nullable=True),
    sa.Column('reference_id', sa.Integer(), nullable=True),
    sa.Column('old_average_cost', sa.Numeric(precision=18, scale=6), nullable=True),
    sa.Column('new_average_cost', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('quantity_change', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('old_total_quantity', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('new_total_quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('old_total_value', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('new_total_value', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('movement_unit_cost', sa.Numeric(precision=18, scale=6), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_images',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('image_url', sa.String(length=500), nullable=False),
    sa.Column('image_type', sa.String(length=20), nullable=True),
    sa.Column('caption_ar', sa.String(length=200), nullable=True),
    sa.Column('caption_en', sa.String(length=200), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_partners',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('partner_customer_id', sa.Integer(), nullable=False),
    sa.Column('percentage', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product_id', 'partner_customer_id', name='uq_product_partner')
    )
    op.create_table('product_price_tiers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('tier_code', sa.String(length=30), nullable=False),
    sa.Column('min_quantity', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('price', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'product_id', 'tier_code', name='uq_product_price_tier')
    )
    op.create_table('product_returns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('return_number', sa.String(length=50), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('reverses_invoice_id', sa.Integer(), nullable=True),
    sa.Column('return_date', sa.DateTime(), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('refund_amount', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True),
    sa.Column('amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('return_reason', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('processed_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'return_number', name='uq_product_returns_tenant_return_number')
    )
    op.create_table('product_warehouse_stock',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('warehouse_barcode', sa.String(length=100), nullable=True),
    sa.Column('warehouse_description_ar', sa.Text(), nullable=True),
    sa.Column('warehouse_description_en', sa.Text(), nullable=True),
    sa.Column('warehouse_country_of_origin', sa.String(length=100), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'product_id', 'warehouse_id', name='uq_product_warehouse_stock')
    )
    op.create_table('project_members',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=30), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'user_id', name='uq_project_member')
    )
    op.create_table('purchase_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('purchase_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('discount_percent', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('line_total', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('landed_cost', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sale_campaigns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('campaign_id', sa.Integer(), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('discount_amount', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sale_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('discount_percent', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('line_total', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('cost_price', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('warranty_start_date', sa.DateTime(), nullable=True),
    sa.Column('warranty_end_date', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shop_abandoned_carts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=True),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('cart_data', sa.Text(), nullable=True),
    sa.Column('reminder_sent_at', sa.DateTime(), nullable=True),
    sa.Column('reminder_count', sa.Integer(), nullable=False),
    sa.Column('recovered', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shop_loyalty',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('points_earned', sa.Integer(), nullable=False),
    sa.Column('points_redeemed', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shop_loyalty_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=True),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shop_product_variants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('sku', sa.String(length=100), nullable=True),
    sa.Column('price_adjustment', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('stock_quantity', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shop_reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=True),
    sa.Column('customer_name', sa.String(length=100), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('is_approved', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shop_saved_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('method_code', sa.String(length=50), nullable=False),
    sa.Column('label', sa.String(length=100), nullable=True),
    sa.Column('details', sa.Text(), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shop_stock_alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('is_notified', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email', 'product_id', name='uq_stock_alert_email_product')
    )
    op.create_table('shop_wishlist',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'product_id', name='uq_wishlist_account_product')
    )
    op.create_table('stock_movements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=False),
    sa.Column('movement_type', sa.String(length=20), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('reference_type', sa.String(length=50), nullable=True),
    sa.Column('reference_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('task_stages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('name_ar', sa.String(length=100), nullable=True),
    sa.Column('sequence', sa.Integer(), nullable=True),
    sa.Column('is_closed', sa.Boolean(), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ticket_comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('is_internal', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('partner_commission_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('warehouse_id', sa.Integer(), nullable=True),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('sale_line_id', sa.Integer(), nullable=True),
    sa.Column('partner_customer_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('percentage', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('base_currency', sa.String(length=3), nullable=True),
    sa.Column('cost_basis', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('profit_margin', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('base_amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('commission_amount_aed', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_return_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('return_id', sa.Integer(), nullable=False),
    sa.Column('sale_line_id', sa.Integer(), nullable=True),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('line_total', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('condition', sa.String(length=50), nullable=True),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_serials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=True),
    sa.Column('serial_number', sa.String(length=100), nullable=False),
    sa.Column('imei1', sa.String(length=15), nullable=True),
    sa.Column('imei2', sa.String(length=15), nullable=True),
    sa.Column('model_number', sa.String(length=50), nullable=True),
    sa.Column('iccid', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('purchase_line_id', sa.Integer(), nullable=True),
    sa.Column('sale_line_id', sa.Integer(), nullable=True),
    sa.Column('warranty_start_date', sa.DateTime(), nullable=True),
    sa.Column('warranty_end_date', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'serial_number', name='uq_serial_tenant_serial')
    )
    op.create_table('product_warehouse_costs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('warehouse_id', sa.Integer(), nullable=False),
    sa.Column('average_cost', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('total_quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('total_value', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('last_updated', sa.DateTime(), nullable=False),
    sa.Column('updated_by_movement_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'product_id', 'warehouse_id', name='uq_pwc_tenant_product_warehouse')
    )
    op.create_table('purchase_return_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('return_id', sa.Integer(), nullable=False),
    sa.Column('purchase_line_id', sa.Integer(), nullable=True),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('line_total', sa.Numeric(precision=15, scale=3), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('stage_id', sa.Integer(), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('assigned_user_id', sa.Integer(), nullable=True),
    sa.Column('priority', sa.String(length=20), nullable=True),
    sa.Column('date_deadline', sa.DateTime(), nullable=True),
    sa.Column('planned_hours', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('effective_hours', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('warranty_claims',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('sale_id', sa.Integer(), nullable=False),
    sa.Column('sale_line_id', sa.Integer(), nullable=True),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('claim_date', sa.DateTime(), nullable=True),
    sa.Column('claim_type', sa.String(length=20), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('resolution_notes', sa.Text(), nullable=True),
    sa.Column('cost_to_company', sa.Numeric(precision=15, scale=3), nullable=True),
    sa.Column('warranty_start_date', sa.DateTime(), nullable=True),
    sa.Column('warranty_end_date', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('timesheets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('hours', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    with op.batch_alter_table('branches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_branches_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_branches_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_branches_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('cheques', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cheques_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_cheque_number'), ['cheque_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_cheque_type'), ['cheque_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_due_date'), ['due_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_expense_id'), ['expense_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_is_overdue'), ['is_overdue'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_payment_id'), ['payment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_purchase_id'), ['purchase_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_receipt_id'), ['receipt_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_supplier_id'), ['supplier_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cheques_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('currencies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_currencies_code'), ['code'], unique=True)
        batch_op.create_index(batch_op.f('ix_currencies_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_currencies_is_active'), ['is_active'], unique=False)

    with op.batch_alter_table('industry_field_definitions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_industry_field_definitions_industry_code'), ['industry_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_industry_field_definitions_is_active'), ['is_active'], unique=False)

    with op.batch_alter_table('packages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_packages_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_packages_is_active'), ['is_active'], unique=False)

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payments_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_cheque_id'), ['cheque_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_direction'), ['direction'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_payment_confirmed'), ['payment_confirmed'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_payment_date'), ['payment_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_payment_number'), ['payment_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_payment_type'), ['payment_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_purchase_id'), ['purchase_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_supplier_id'), ['supplier_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('permissions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_permissions_code'), ['code'], unique=True)
        batch_op.create_index(batch_op.f('ix_permissions_created_at'), ['created_at'], unique=False)

    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_receipts_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_cheque_id'), ['cheque_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_direction'), ['direction'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_payment_confirmed'), ['payment_confirmed'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_receipt_date'), ['receipt_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_receipt_number'), ['receipt_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_source_id'), ['source_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_source_type'), ['source_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_receipts_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_roles_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_roles_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_roles_slug'), ['slug'], unique=True)

    with op.batch_alter_table('store_payment_methods', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_store_payment_methods_code'), ['code'], unique=True)
        batch_op.create_index(batch_op.f('ix_store_payment_methods_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_store_payment_methods_is_enabled'), ['is_enabled'], unique=False)

    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tenants_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tenants_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_tenants_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_tenants_is_suspended'), ['is_suspended'], unique=False)
        batch_op.create_index(batch_op.f('ix_tenants_slug'), ['slug'], unique=True)
        batch_op.create_index(batch_op.f('ix_tenants_tax_number'), ['tax_number'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_is_owner'), ['is_owner'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_role_id'), ['role_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    with op.batch_alter_table('ai_expertise', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_expertise_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_expertise_domain'), ['domain'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_expertise_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_expertise_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('ai_interactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_interactions_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_interactions_is_training_sample'), ['is_training_sample'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_interactions_session_id'), ['session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_interactions_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_interactions_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('ai_memories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_memories_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_memories_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_memories_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_memories_key'), ['key'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_memories_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_keys_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_keys_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_keys_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_keys_scope'), ['scope'], unique=False)

    with op.batch_alter_table('archived_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_archived_records_archived_at'), ['archived_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_archived_records_archived_by'), ['archived_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_archived_records_table_name'), ['table_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_archived_records_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_archived_records_tenant_table', ['tenant_id', 'table_name'], unique=False)

    with op.batch_alter_table('attendances', schema=None) as batch_op:
        batch_op.create_index('ix_attendance_user_date', ['user_id', 'check_in'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendances_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendances_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendances_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendances_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_logs_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_table_name'), ['table_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('azad_subscription_fees', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_azad_subscription_fees_created_at'), ['created_at'], unique=False)
        batch_op.create_index('ix_azad_subscription_fees_period', ['billing_period_start', 'billing_period_end'], unique=False)
        batch_op.create_index(batch_op.f('ix_azad_subscription_fees_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_azad_subscription_fees_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_azad_subscription_fees_tenant_status', ['tenant_id', 'status'], unique=False)

    with op.batch_alter_table('budgets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_budgets_approved_by'), ['approved_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_budgets_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_budgets_budget_number'), ['budget_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_budgets_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_budgets_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_budgets_fiscal_year'), ['fiscal_year'], unique=False)
        batch_op.create_index(batch_op.f('ix_budgets_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_budgets_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_campaigns_coupon_code'), ['coupon_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_campaigns_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_campaigns_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_campaigns_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('card_payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_card_payments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_card_payments_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_card_payments_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_card_payments_transaction_id'), ['transaction_id'], unique=True)

    with op.batch_alter_table('cost_centers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cost_centers_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_cost_centers_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_cost_centers_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_cost_centers_manager_id'), ['manager_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cost_centers_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cost_centers_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('crm_stages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crm_stages_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_stages_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_stages_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('crm_teams', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crm_teams_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_teams_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_teams_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_departments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_departments_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_departments_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('document_sequences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_document_sequences_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_sequences_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('document_snapshots', schema=None) as batch_op:
        batch_op.create_index('ix_doc_snapshots_tenant_doc_type', ['tenant_id', 'document_type', 'document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_snapshots_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_snapshots_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_snapshots_document_type'), ['document_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_snapshots_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('document_verifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_document_verifications_document_hash'), ['document_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_document_verifications_public_token'), ['public_token'], unique=True)
        batch_op.create_index('ix_docver_tenant_doc', ['tenant_id', 'document_type', 'document_id'], unique=True)

    with op.batch_alter_table('donations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_donations_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_donations_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_donations_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('email_lists', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_lists_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_lists_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_lists_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('email_templates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_templates_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_templates_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_templates_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_employees_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_employees_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_employees_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_employees_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('error_audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_error_audit_logs_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_fingerprint'), ['fingerprint'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_first_seen_at'), ['first_seen_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_is_resolved'), ['is_resolved'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_last_seen_at'), ['last_seen_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_level'), ['level'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_request_id'), ['request_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_resolved_by'), ['resolved_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_error_audit_logs_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('exchange_rate_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_exchange_rate_records_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rate_records_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rate_records_effective_date'), ['effective_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rate_records_from_currency'), ['from_currency'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rate_records_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rate_records_to_currency'), ['to_currency'], unique=False)

    with op.batch_alter_table('exchange_rates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_exchange_rates_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rates_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rates_currency_id'), ['currency_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rates_from_currency'), ['from_currency'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rates_to_currency'), ['to_currency'], unique=False)
        batch_op.create_index(batch_op.f('ix_exchange_rates_valid_from'), ['valid_from'], unique=False)

    with op.batch_alter_table('expense_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_expense_categories_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_categories_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_categories_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_categories_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('fiscal_positions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fiscal_positions_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('gl_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gl_accounts_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_industry_code'), ['industry_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_liquidity_kind'), ['liquidity_kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_module_code'), ['module_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_sub_type'), ['sub_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_accounts_type'), ['type'], unique=False)

    with op.batch_alter_table('gl_journal_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_entry_date'), ['entry_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_entry_number'), ['entry_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_reversed_entry_id'), ['reversed_entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_entries_validated_by'), ['validated_by'], unique=False)

    with op.batch_alter_table('gl_periods', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gl_periods_closed_by'), ['closed_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_periods_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_periods_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('integration_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_integration_settings_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_settings_service_name'), ['service_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_settings_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_settings_updated_by'), ['updated_by'], unique=False)

    with op.batch_alter_table('invoice_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invoice_settings_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_invoice_settings_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_invoice_settings_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_invoice_settings_updated_by'), ['updated_by'], unique=False)

    with op.batch_alter_table('leave_types', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_leave_types_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_leave_types_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_leave_types_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('login_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_history_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('package_purchases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_package_purchases_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_package_purchases_package_id'), ['package_id'], unique=False)

    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_partners_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_partners_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_partners_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_partners_scope_id'), ['scope_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partners_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('payment_vault', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payment_vault_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_vault_tenant_id'), ['tenant_id'], unique=True)

    with op.batch_alter_table('payroll_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payroll_settings_tenant_id'), ['tenant_id'], unique=True)

    with op.batch_alter_table('pos_floors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pos_floors_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('pos_sessions', schema=None) as batch_op:
        batch_op.create_index('idx_pos_session_branch_status', ['branch_id', 'status'], unique=False)
        batch_op.create_index('idx_pos_session_user_status', ['user_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_sessions_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_sessions_session_number'), ['session_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_sessions_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_sessions_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_sessions_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('print_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_print_history_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_print_history_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_print_history_document_type'), ['document_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_print_history_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_print_history_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('product_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_categories_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_categories_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_categories_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_categories_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_categories_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('profit_centers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profit_centers_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_profit_centers_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_profit_centers_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_profit_centers_manager_id'), ['manager_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_profit_centers_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_profit_centers_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('security_alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_security_alerts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_alerts_resolved_by'), ['resolved_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_alerts_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('shipments', schema=None) as batch_op:
        batch_op.create_index('ix_shipment_source', ['source_type', 'source_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shipments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shipments_source_id'), ['source_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shipments_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_shipments_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_newsletters', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_newsletters_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_newsletters_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_newsletters_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('store_coupons', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_store_coupons_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_store_coupons_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_store_coupons_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_store_coupons_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_suppliers_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_suppliers_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_suppliers_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_suppliers_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_suppliers_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('system_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_settings_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_settings_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_settings_updated_by'), ['updated_by'], unique=False)

    with op.batch_alter_table('ticket_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ticket_categories_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ticket_categories_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_ticket_categories_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('ticket_priorities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ticket_priorities_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ticket_priorities_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_ticket_priorities_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_warehouses_allow_negative_inventory'), ['allow_negative_inventory'], unique=False)
        batch_op.create_index(batch_op.f('ix_warehouses_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_warehouses_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_warehouses_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_warehouses_manager_id'), ['manager_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_warehouses_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_warehouses_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_warehouses_warehouse_type'), ['warehouse_type'], unique=False)

    with op.batch_alter_table('advanced_expenses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_advanced_expenses_approved_by'), ['approved_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_category_id'), ['category_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_expense_date'), ['expense_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_expense_number'), ['expense_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_gl_journal_entry_id'), ['gl_journal_entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_reversed_by'), ['reversed_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_supplier_id'), ['supplier_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_advanced_expenses_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('bank_reconciliations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bank_reconciliations_approved_by'), ['approved_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliations_bank_account_id'), ['bank_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliations_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliations_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliations_period_end'), ['period_end'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliations_reconciliation_number'), ['reconciliation_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliations_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliations_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('budget_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_budget_lines_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_budget_lines_budget_id'), ['budget_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_budget_lines_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('cash_boxes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cash_boxes_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cash_boxes_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_cash_boxes_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_cash_boxes_gl_account_id'), ['gl_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cash_boxes_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_cash_boxes_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('crm_team_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crm_team_members_team_id'), ['team_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_team_members_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_team_members_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.create_index('idx_customer_active_type', ['is_active', 'customer_type'], unique=False)
        batch_op.create_index('idx_customer_balance', ['balance'], unique=False)
        batch_op.create_index(batch_op.f('ix_customers_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_customers_customer_classification'), ['customer_classification'], unique=False)
        batch_op.create_index(batch_op.f('ix_customers_customer_type'), ['customer_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_customers_fiscal_position_id'), ['fiscal_position_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_customers_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_customers_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_customers_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('customs_taxes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_customs_taxes_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_customs_taxes_gl_account_id'), ['gl_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_customs_taxes_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_customs_taxes_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('email_campaigns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_campaigns_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_campaigns_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_campaigns_list_id'), ['list_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_campaigns_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_campaigns_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('employee_leaves', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_employee_leaves_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_employee_leaves_employee_id'), ['employee_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_employee_leaves_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_employee_leaves_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_expenses_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_category_id'), ['category_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_expense_date'), ['expense_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_expense_number'), ['expense_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_is_reversed'), ['is_reversed'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_expenses_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('fixed_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fixed_assets_asset_account_id'), ['asset_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_asset_number'), ['asset_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_cost_center_id'), ['cost_center_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_depreciation_account_id'), ['depreciation_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_expense_account_id'), ['expense_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_purchase_date'), ['purchase_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_fixed_assets_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('gl_account_mappings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gl_account_mappings_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_account_mappings_concept_code'), ['concept_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_account_mappings_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_account_mappings_gl_account_id'), ['gl_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_account_mappings_is_active'), ['is_active'], unique=False)
        batch_op.create_index('ix_gl_account_mappings_tenant_concept_active', ['tenant_id', 'concept_code', 'is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_account_mappings_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('uq_gl_account_mappings_tenant_concept_branch', ['tenant_id', 'concept_code', 'branch_id'], unique=True, postgresql_where=sa.text('branch_id IS NOT NULL'), sqlite_where=sa.text('branch_id IS NOT NULL'))
        batch_op.create_index('uq_gl_account_mappings_tenant_concept_default', ['tenant_id', 'concept_code'], unique=True, postgresql_where=sa.text('branch_id IS NULL'), sqlite_where=sa.text('branch_id IS NULL'))

    with op.batch_alter_table('gl_journal_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gl_journal_lines_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_lines_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_lines_cost_center_id'), ['cost_center_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_lines_entry_id'), ['entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_lines_partner_id'), ['partner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_lines_profit_center_id'), ['profit_center_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_lines_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gl_journal_lines_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('job_positions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_job_positions_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_job_positions_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_job_positions_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('journal_entry_audits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_journal_entry_audits_journal_entry_id'), ['journal_entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_journal_entry_audits_performed_by'), ['performed_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_journal_entry_audits_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('leave_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_leave_requests_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_leave_requests_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_leave_requests_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_leave_requests_state'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('ix_leave_requests_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_leave_requests_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('partner_profit_distributions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_partner_profit_distributions_approved_by'), ['approved_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_profit_distributions_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_profit_distributions_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_profit_distributions_partner_id'), ['partner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_profit_distributions_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_profit_distributions_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('payment_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payment_logs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_logs_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_logs_vault_id'), ['vault_id'], unique=False)

    with op.batch_alter_table('payment_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payment_transactions_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_transactions_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_transactions_vault_id'), ['vault_id'], unique=False)

    with op.batch_alter_table('payroll_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payroll_transactions_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payroll_transactions_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_payroll_transactions_employee_id'), ['employee_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payroll_transactions_gl_entry_id'), ['gl_entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payroll_transactions_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_payroll_transactions_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('pos_tables', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pos_tables_floor_id'), ['floor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_tables_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_tables_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('purchases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchases_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_purchase_date'), ['purchase_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_purchase_number'), ['purchase_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_supplier_id'), ['supplier_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('salary_advances', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_salary_advances_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_salary_advances_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_salary_advances_employee_id'), ['employee_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_salary_advances_gl_entry_id'), ['gl_entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_salary_advances_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_salary_advances_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tenant_stores_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tenant_stores_custom_domain'), ['custom_domain'], unique=True)
        batch_op.create_index(batch_op.f('ix_tenant_stores_store_slug'), ['store_slug'], unique=True)
        batch_op.create_index(batch_op.f('ix_tenant_stores_subdomain'), ['subdomain'], unique=True)
        batch_op.create_index(batch_op.f('ix_tenant_stores_tenant_id'), ['tenant_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_tenant_stores_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('bank_reconciliation_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bank_reconciliation_items_cheque_id'), ['cheque_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliation_items_journal_entry_id'), ['journal_entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliation_items_reconciliation_id'), ['reconciliation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_reconciliation_items_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('card_vault', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_card_vault_card_hash'), ['card_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_card_vault_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_card_vault_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_card_vault_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_card_vault_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_card_vault_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('crm_leads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crm_leads_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_leads_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_leads_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_leads_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_leads_stage_id'), ['stage_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_leads_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('depreciation_schedules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_depreciation_schedules_asset_id'), ['asset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_depreciation_schedules_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_depreciation_schedules_journal_entry_id'), ['journal_entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_depreciation_schedules_period_date'), ['period_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_depreciation_schedules_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('email_subscribers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_subscribers_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_subscribers_list_id'), ['list_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_subscribers_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_subscribers_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('hr_contracts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_hr_contracts_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_hr_contracts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_hr_contracts_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_hr_contracts_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_hr_contracts_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('partner_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_partner_transactions_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_transactions_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_transactions_distribution_id'), ['distribution_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_transactions_partner_id'), ['partner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_transactions_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.create_index('idx_product_active_stock', ['is_active', 'current_stock'], unique=False)
        batch_op.create_index('idx_product_category_active', ['category_id', 'is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_barcode'), ['barcode'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_category_id'), ['category_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_merchant_customer_id'), ['merchant_customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_part_number'), ['part_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_sku'), ['sku'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('uq_products_tenant_barcode', ['tenant_id', 'barcode'], unique=True, postgresql_where=sa.text("(barcode IS NOT NULL) AND (TRIM(barcode::text) <> '')"))
        batch_op.create_index('uq_products_tenant_sku', ['tenant_id', 'sku'], unique=True, postgresql_where=sa.text("(sku IS NOT NULL) AND (TRIM(sku::text) <> '')"))

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_projects_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_projects_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_projects_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_projects_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_projects_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('purchase_returns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchase_returns_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_returns_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_returns_processed_by'), ['processed_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_returns_purchase_id'), ['purchase_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_returns_return_date'), ['return_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_returns_return_number'), ['return_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_returns_supplier_id'), ['supplier_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_returns_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_returns_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.create_index('idx_sale_customer_date', ['customer_id', 'sale_date'], unique=False)
        batch_op.create_index('idx_sale_payment_status', ['payment_status', 'customer_id'], unique=False)
        batch_op.create_index('idx_sale_status_date', ['status', 'sale_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_checkout_payment_method'), ['checkout_payment_method'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_order_type'), ['order_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_payment_status'), ['payment_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_pos_session_id'), ['pos_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_sale_date'), ['sale_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_sale_number'), ['sale_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_sales_rep_id'), ['sales_rep_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_seller_id'), ['seller_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_table_id'), ['table_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('shop_customer_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_customer_accounts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_customer_accounts_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_customer_accounts_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_customer_accounts_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_customer_accounts_password_reset_token'), ['password_reset_token'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_customer_accounts_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('tax_calculation_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tax_calculation_rules_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tax_calculation_rules_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_tax_calculation_rules_tax_id'), ['tax_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tax_calculation_rules_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tickets_assigned_user_id'), ['assigned_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_number'), ['number'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('azad_platform_fees', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_azad_platform_fees_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_azad_platform_fees_payment_id'), ['payment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_azad_platform_fees_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_azad_platform_fees_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_azad_platform_fees_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_azad_platform_fees_tenant_sale', ['tenant_id', 'sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_azad_platform_fees_vault_id'), ['vault_id'], unique=False)

    with op.batch_alter_table('bank_statement_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_bank_account_id'), ['bank_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_matched_by'), ['matched_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_matched_cheque_id'), ['matched_cheque_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_matched_journal_entry_id'), ['matched_journal_entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_reconciliation_item_id'), ['reconciliation_item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_reference'), ['reference'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_statement_date'), ['statement_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_statement_lines_transaction_date'), ['transaction_date'], unique=False)

    with op.batch_alter_table('campaign_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_campaign_logs_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_campaign_logs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_campaign_logs_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('crm_activities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crm_activities_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_activities_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crm_activities_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('fiscal_position_tax_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fiscal_position_tax_rules_fiscal_position_id'), ['fiscal_position_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_fiscal_position_tax_rules_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('pos_kds_orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pos_kds_orders_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_kds_orders_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_kds_orders_session_id'), ['session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_kds_orders_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_kds_orders_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('pos_table_orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pos_table_orders_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_table_orders_table_id'), ['table_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pos_table_orders_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('product_cost_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_cost_history_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_cost_history_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_cost_history_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_cost_history_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('product_images', schema=None) as batch_op:
        batch_op.create_index('ix_product_image_type_order', ['product_id', 'image_type', 'sort_order'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_images_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_images_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_images_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_images_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('product_partners', schema=None) as batch_op:
        batch_op.create_index('idx_product_partner_partner', ['partner_customer_id'], unique=False)
        batch_op.create_index('idx_product_partner_product', ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_partners_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_partners_partner_customer_id'), ['partner_customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_partners_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_partners_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('product_price_tiers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_price_tiers_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_price_tiers_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_price_tiers_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_price_tiers_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_price_tiers_tier_code'), ['tier_code'], unique=False)

    with op.batch_alter_table('product_returns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_returns_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_processed_by'), ['processed_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_return_date'), ['return_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_return_number'), ['return_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_reverses_invoice_id'), ['reverses_invoice_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_returns_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('product_warehouse_stock', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_warehouse_stock_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_warehouse_stock_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_warehouse_stock_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('project_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_project_members_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_project_members_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_project_members_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('purchase_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchase_lines_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_lines_purchase_id'), ['purchase_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_lines_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('sale_campaigns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sale_campaigns_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sale_campaigns_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_sale_campaigns_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sale_campaigns_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('sale_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sale_lines_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sale_lines_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sale_lines_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_abandoned_carts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_abandoned_carts_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_abandoned_carts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_abandoned_carts_recovered'), ['recovered'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_abandoned_carts_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_loyalty', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_loyalty_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_loyalty_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_loyalty_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_loyalty_transactions_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_loyalty_transactions_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_loyalty_transactions_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_loyalty_transactions_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_product_variants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_product_variants_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_product_variants_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_product_variants_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_product_variants_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_reviews', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_reviews_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_reviews_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_reviews_is_approved'), ['is_approved'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_reviews_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_reviews_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_saved_payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_saved_payments_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_saved_payments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_saved_payments_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_stock_alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_stock_alerts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_stock_alerts_is_notified'), ['is_notified'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_stock_alerts_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_stock_alerts_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('shop_wishlist', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_wishlist_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_wishlist_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_wishlist_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_wishlist_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('stock_movements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_stock_movements_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_movements_movement_type'), ['movement_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_movements_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_movements_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_movements_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_movements_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('task_stages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_stages_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_stages_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('ticket_comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ticket_comments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ticket_comments_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ticket_comments_ticket_id'), ['ticket_id'], unique=False)

    with op.batch_alter_table('partner_commission_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_partner_commission_entries_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_commission_entries_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_commission_entries_partner_customer_id'), ['partner_customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_commission_entries_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_commission_entries_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_commission_entries_sale_line_id'), ['sale_line_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_commission_entries_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_partner_commission_entries_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('product_return_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_return_lines_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_return_lines_return_id'), ['return_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_return_lines_sale_line_id'), ['sale_line_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_return_lines_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('product_serials', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_serials_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_imei1'), ['imei1'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_imei2'), ['imei2'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_purchase_line_id'), ['purchase_line_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_sale_line_id'), ['sale_line_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_serial_number'), ['serial_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_serials_warehouse_id'), ['warehouse_id'], unique=False)
        batch_op.create_index('ix_serial_tenant_imei1', ['tenant_id', 'imei1'], unique=False, sqlite_where=sa.text("imei1 IS NOT NULL AND imei1 != ''"), postgresql_where=sa.text("imei1 IS NOT NULL AND imei1 != ''"))
        batch_op.create_index('ix_serial_tenant_imei2', ['tenant_id', 'imei2'], unique=False, sqlite_where=sa.text("imei2 IS NOT NULL AND imei2 != ''"), postgresql_where=sa.text("imei2 IS NOT NULL AND imei2 != ''"))

    with op.batch_alter_table('product_warehouse_costs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_warehouse_costs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_warehouse_costs_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_warehouse_costs_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_warehouse_costs_updated_by_movement_id'), ['updated_by_movement_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_warehouse_costs_warehouse_id'), ['warehouse_id'], unique=False)

    with op.batch_alter_table('purchase_return_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchase_return_lines_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_return_lines_purchase_line_id'), ['purchase_line_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_return_lines_return_id'), ['return_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_return_lines_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tasks_assigned_user_id'), ['assigned_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_stage_id'), ['stage_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('warranty_claims', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_warranty_claims_claim_date'), ['claim_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_warranty_claims_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_warranty_claims_sale_id'), ['sale_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_warranty_claims_sale_line_id'), ['sale_line_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_warranty_claims_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_warranty_claims_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('timesheets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_timesheets_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_timesheets_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_timesheets_date'), ['date'], unique=False)
        batch_op.create_index(batch_op.f('ix_timesheets_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_timesheets_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_timesheets_user_id'), ['user_id'], unique=False)


    with op.batch_alter_table('branches'):
        op.create_foreign_key('fk_branches_tenant_id', 'branches', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_branch_id', 'cheques', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_customer_id', 'cheques', 'customers', ['customer_id'], ['id'])
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_expense_id', 'cheques', 'expenses', ['expense_id'], ['id'])
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_payment_id', 'cheques', 'payments', ['payment_id'], ['id'])
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_purchase_id', 'cheques', 'purchases', ['purchase_id'], ['id'])
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_receipt_id', 'cheques', 'receipts', ['receipt_id'], ['id'])
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_sale_id', 'cheques', 'sales', ['sale_id'], ['id'])
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_supplier_id', 'cheques', 'suppliers', ['supplier_id'], ['id'])
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_tenant_id', 'cheques', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('cheques'):
        op.create_foreign_key('fk_cheques_user_id', 'cheques', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('payments'):
        op.create_foreign_key('fk_payments_branch_id', 'payments', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('payments'):
        op.create_foreign_key('fk_payments_cheque_id', 'payments', 'cheques', ['cheque_id'], ['id'])
    with op.batch_alter_table('payments'):
        op.create_foreign_key('fk_payments_customer_id', 'payments', 'customers', ['customer_id'], ['id'])
    with op.batch_alter_table('payments'):
        op.create_foreign_key('fk_payments_purchase_id', 'payments', 'purchases', ['purchase_id'], ['id'])
    with op.batch_alter_table('payments'):
        op.create_foreign_key('fk_payments_sale_id', 'payments', 'sales', ['sale_id'], ['id'])
    with op.batch_alter_table('payments'):
        op.create_foreign_key('fk_payments_supplier_id', 'payments', 'suppliers', ['supplier_id'], ['id'])
    with op.batch_alter_table('payments'):
        op.create_foreign_key('fk_payments_tenant_id', 'payments', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('payments'):
        op.create_foreign_key('fk_payments_user_id', 'payments', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('receipts'):
        op.create_foreign_key('fk_receipts_branch_id', 'receipts', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('receipts'):
        op.create_foreign_key('fk_receipts_cheque_id', 'receipts', 'cheques', ['cheque_id'], ['id'])
    with op.batch_alter_table('receipts'):
        op.create_foreign_key('fk_receipts_customer_id', 'receipts', 'customers', ['customer_id'], ['id'])
    with op.batch_alter_table('receipts'):
        op.create_foreign_key('fk_receipts_tenant_id', 'receipts', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('receipts'):
        op.create_foreign_key('fk_receipts_user_id', 'receipts', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('tenants'):
        op.create_foreign_key('fk_tenants_created_by', 'tenants', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('users'):
        op.create_foreign_key('fk_users_branch_id', 'users', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('users'):
        op.create_foreign_key('fk_users_role_id', 'users', 'roles', ['role_id'], ['id'])
    with op.batch_alter_table('users'):
        op.create_foreign_key('fk_users_tenant_id', 'users', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('ai_expertise'):
        op.create_foreign_key('fk_ai_expertise_tenant_id', 'ai_expertise', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('ai_interactions'):
        op.create_foreign_key('fk_ai_interactions_tenant_id', 'ai_interactions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('ai_interactions'):
        op.create_foreign_key('fk_ai_interactions_user_id', 'ai_interactions', 'users', ['user_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('ai_memories'):
        op.create_foreign_key('fk_ai_memories_tenant_id', 'ai_memories', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('api_keys'):
        op.create_foreign_key('fk_api_keys_created_by', 'api_keys', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('archived_records'):
        op.create_foreign_key('fk_archived_records_archived_by', 'archived_records', 'users', ['archived_by'], ['id'])
    with op.batch_alter_table('archived_records'):
        op.create_foreign_key('fk_archived_records_tenant_id', 'archived_records', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('attendances'):
        op.create_foreign_key('fk_attendances_branch_id', 'attendances', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('attendances'):
        op.create_foreign_key('fk_attendances_tenant_id', 'attendances', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('attendances'):
        op.create_foreign_key('fk_attendances_user_id', 'attendances', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('audit_logs'):
        op.create_foreign_key('fk_audit_logs_tenant_id', 'audit_logs', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('audit_logs'):
        op.create_foreign_key('fk_audit_logs_user_id', 'audit_logs', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('azad_subscription_fees'):
        op.create_foreign_key('fk_azad_subscription_fees_tenant_id', 'azad_subscription_fees', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('budgets'):
        op.create_foreign_key('fk_budgets_approved_by', 'budgets', 'users', ['approved_by'], ['id'])
    with op.batch_alter_table('budgets'):
        op.create_foreign_key('fk_budgets_branch_id', 'budgets', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('budgets'):
        op.create_foreign_key('fk_budgets_created_by', 'budgets', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('budgets'):
        op.create_foreign_key('fk_budgets_tenant_id', 'budgets', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('campaigns'):
        op.create_foreign_key('fk_campaigns_tenant_id', 'campaigns', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('card_payments'):
        op.create_foreign_key('fk_card_payments_tenant_id', 'card_payments', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('cost_centers'):
        op.create_foreign_key('fk_cost_centers_manager_id', 'cost_centers', 'users', ['manager_id'], ['id'])
    with op.batch_alter_table('cost_centers'):
        op.create_foreign_key('fk_cost_centers_parent_id', 'cost_centers', 'cost_centers', ['parent_id'], ['id'])
    with op.batch_alter_table('cost_centers'):
        op.create_foreign_key('fk_cost_centers_tenant_id', 'cost_centers', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_stages'):
        op.create_foreign_key('fk_crm_stages_tenant_id', 'crm_stages', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_teams'):
        op.create_foreign_key('fk_crm_teams_leader_id', 'crm_teams', 'users', ['leader_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('crm_teams'):
        op.create_foreign_key('fk_crm_teams_tenant_id', 'crm_teams', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('departments'):
        op.create_foreign_key('fk_departments_manager_id', 'departments', 'users', ['manager_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('departments'):
        op.create_foreign_key('fk_departments_parent_id', 'departments', 'departments', ['parent_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('departments'):
        op.create_foreign_key('fk_departments_tenant_id', 'departments', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('document_sequences'):
        op.create_foreign_key('fk_document_sequences_tenant_id', 'document_sequences', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('document_snapshots'):
        op.create_foreign_key('fk_document_snapshots_created_by', 'document_snapshots', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('document_snapshots'):
        op.create_foreign_key('fk_document_snapshots_tenant_id', 'document_snapshots', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('document_verifications'):
        op.create_foreign_key('fk_document_verifications_created_by', 'document_verifications', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('document_verifications'):
        op.create_foreign_key('fk_document_verifications_tenant_id', 'document_verifications', 'tenants', ['tenant_id'], ['id'])
    with op.batch_alter_table('donations'):
        op.create_foreign_key('fk_donations_tenant_id', 'donations', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('email_lists'):
        op.create_foreign_key('fk_email_lists_tenant_id', 'email_lists', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('email_templates'):
        op.create_foreign_key('fk_email_templates_tenant_id', 'email_templates', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('employees'):
        op.create_foreign_key('fk_employees_branch_id', 'employees', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('employees'):
        op.create_foreign_key('fk_employees_tenant_id', 'employees', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('error_audit_logs'):
        op.create_foreign_key('fk_error_audit_logs_resolved_by', 'error_audit_logs', 'users', ['resolved_by'], ['id'])
    with op.batch_alter_table('error_audit_logs'):
        op.create_foreign_key('fk_error_audit_logs_tenant_id', 'error_audit_logs', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('error_audit_logs'):
        op.create_foreign_key('fk_error_audit_logs_user_id', 'error_audit_logs', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('exchange_rate_records'):
        op.create_foreign_key('fk_exchange_rate_records_created_by', 'exchange_rate_records', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('exchange_rate_records'):
        op.create_foreign_key('fk_exchange_rate_records_tenant_id', 'exchange_rate_records', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('exchange_rates'):
        op.create_foreign_key('fk_exchange_rates_created_by', 'exchange_rates', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('exchange_rates'):
        op.create_foreign_key('fk_exchange_rates_currency_id', 'exchange_rates', 'currencies', ['currency_id'], ['id'])
    with op.batch_alter_table('expense_categories'):
        op.create_foreign_key('fk_expense_categories_tenant_id', 'expense_categories', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('fiscal_positions'):
        op.create_foreign_key('fk_fiscal_positions_tenant_id', 'fiscal_positions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('gl_accounts'):
        op.create_foreign_key('fk_gl_accounts_branch_id', 'gl_accounts', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('gl_accounts'):
        op.create_foreign_key('fk_gl_accounts_parent_id', 'gl_accounts', 'gl_accounts', ['parent_id'], ['id'])
    with op.batch_alter_table('gl_accounts'):
        op.create_foreign_key('fk_gl_accounts_tenant_id', 'gl_accounts', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('gl_journal_entries'):
        op.create_foreign_key('fk_gl_journal_entries_branch_id', 'gl_journal_entries', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('gl_journal_entries'):
        op.create_foreign_key('fk_gl_journal_entries_created_by', 'gl_journal_entries', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('gl_journal_entries'):
        op.create_foreign_key('fk_gl_journal_entries_reversed_entry_id', 'gl_journal_entries', 'gl_journal_entries', ['reversed_entry_id'], ['id'])
    with op.batch_alter_table('gl_journal_entries'):
        op.create_foreign_key('fk_gl_journal_entries_tenant_id', 'gl_journal_entries', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('gl_journal_entries'):
        op.create_foreign_key('fk_gl_journal_entries_validated_by', 'gl_journal_entries', 'users', ['validated_by'], ['id'])
    with op.batch_alter_table('gl_periods'):
        op.create_foreign_key('fk_gl_periods_closed_by', 'gl_periods', 'users', ['closed_by'], ['id'])
    with op.batch_alter_table('gl_periods'):
        op.create_foreign_key('fk_gl_periods_tenant_id', 'gl_periods', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('integration_settings'):
        op.create_foreign_key('fk_integration_settings_tenant_id', 'integration_settings', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('integration_settings'):
        op.create_foreign_key('fk_integration_settings_updated_by', 'integration_settings', 'users', ['updated_by'], ['id'])
    with op.batch_alter_table('invoice_settings'):
        op.create_foreign_key('fk_invoice_settings_tenant_id', 'invoice_settings', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('invoice_settings'):
        op.create_foreign_key('fk_invoice_settings_updated_by', 'invoice_settings', 'users', ['updated_by'], ['id'])
    with op.batch_alter_table('leave_types'):
        op.create_foreign_key('fk_leave_types_tenant_id', 'leave_types', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('login_history'):
        op.create_foreign_key('fk_login_history_user_id', 'login_history', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('package_purchases'):
        op.create_foreign_key('fk_package_purchases_package_id', 'package_purchases', 'packages', ['package_id'], ['id'])
    with op.batch_alter_table('partners'):
        op.create_foreign_key('fk_partners_tenant_id', 'partners', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('payment_vault'):
        op.create_foreign_key('fk_payment_vault_tenant_id', 'payment_vault', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('payroll_settings'):
        op.create_foreign_key('fk_payroll_settings_tenant_id', 'payroll_settings', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('pos_floors'):
        op.create_foreign_key('fk_pos_floors_tenant_id', 'pos_floors', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('pos_sessions'):
        op.create_foreign_key('fk_pos_sessions_branch_id', 'pos_sessions', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('pos_sessions'):
        op.create_foreign_key('fk_pos_sessions_tenant_id', 'pos_sessions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('pos_sessions'):
        op.create_foreign_key('fk_pos_sessions_user_id', 'pos_sessions', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('print_history'):
        op.create_foreign_key('fk_print_history_tenant_id', 'print_history', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('print_history'):
        op.create_foreign_key('fk_print_history_user_id', 'print_history', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('product_categories'):
        op.create_foreign_key('fk_product_categories_parent_id', 'product_categories', 'product_categories', ['parent_id'], ['id'])
    with op.batch_alter_table('product_categories'):
        op.create_foreign_key('fk_product_categories_tenant_id', 'product_categories', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('profit_centers'):
        op.create_foreign_key('fk_profit_centers_manager_id', 'profit_centers', 'users', ['manager_id'], ['id'])
    with op.batch_alter_table('profit_centers'):
        op.create_foreign_key('fk_profit_centers_parent_id', 'profit_centers', 'profit_centers', ['parent_id'], ['id'])
    with op.batch_alter_table('profit_centers'):
        op.create_foreign_key('fk_profit_centers_tenant_id', 'profit_centers', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('role_permissions'):
        op.create_foreign_key('fk_role_permissions_permission_id', 'role_permissions', 'permissions', ['permission_id'], ['id'])
    with op.batch_alter_table('role_permissions'):
        op.create_foreign_key('fk_role_permissions_role_id', 'role_permissions', 'roles', ['role_id'], ['id'])
    with op.batch_alter_table('security_alerts'):
        op.create_foreign_key('fk_security_alerts_resolved_by', 'security_alerts', 'users', ['resolved_by'], ['id'])
    with op.batch_alter_table('security_alerts'):
        op.create_foreign_key('fk_security_alerts_user_id', 'security_alerts', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('shipments'):
        op.create_foreign_key('fk_shipments_tenant_id', 'shipments', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_newsletters'):
        op.create_foreign_key('fk_shop_newsletters_tenant_id', 'shop_newsletters', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('store_coupons'):
        op.create_foreign_key('fk_store_coupons_tenant_id', 'store_coupons', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('suppliers'):
        op.create_foreign_key('fk_suppliers_created_by', 'suppliers', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('suppliers'):
        op.create_foreign_key('fk_suppliers_tenant_id', 'suppliers', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('system_settings'):
        op.create_foreign_key('fk_system_settings_updated_by', 'system_settings', 'users', ['updated_by'], ['id'])
    with op.batch_alter_table('ticket_categories'):
        op.create_foreign_key('fk_ticket_categories_auto_assign_user_id', 'ticket_categories', 'users', ['auto_assign_user_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('ticket_categories'):
        op.create_foreign_key('fk_ticket_categories_tenant_id', 'ticket_categories', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('ticket_priorities'):
        op.create_foreign_key('fk_ticket_priorities_tenant_id', 'ticket_priorities', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('warehouses'):
        op.create_foreign_key('fk_warehouses_branch_id', 'warehouses', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('warehouses'):
        op.create_foreign_key('fk_warehouses_manager_id', 'warehouses', 'users', ['manager_id'], ['id'])
    with op.batch_alter_table('warehouses'):
        op.create_foreign_key('fk_warehouses_parent_id', 'warehouses', 'warehouses', ['parent_id'], ['id'])
    with op.batch_alter_table('warehouses'):
        op.create_foreign_key('fk_warehouses_tenant_id', 'warehouses', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('advanced_expenses'):
        op.create_foreign_key('fk_advanced_expenses_approved_by', 'advanced_expenses', 'users', ['approved_by'], ['id'])
    with op.batch_alter_table('advanced_expenses'):
        op.create_foreign_key('fk_advanced_expenses_branch_id', 'advanced_expenses', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('advanced_expenses'):
        op.create_foreign_key('fk_advanced_expenses_category_id', 'advanced_expenses', 'expense_categories', ['category_id'], ['id'])
    with op.batch_alter_table('advanced_expenses'):
        op.create_foreign_key('fk_advanced_expenses_created_by', 'advanced_expenses', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('advanced_expenses'):
        op.create_foreign_key('fk_advanced_expenses_gl_journal_entry_id', 'advanced_expenses', 'gl_journal_entries', ['gl_journal_entry_id'], ['id'])
    with op.batch_alter_table('advanced_expenses'):
        op.create_foreign_key('fk_advanced_expenses_reversed_by', 'advanced_expenses', 'users', ['reversed_by'], ['id'])
    with op.batch_alter_table('advanced_expenses'):
        op.create_foreign_key('fk_advanced_expenses_supplier_id', 'advanced_expenses', 'suppliers', ['supplier_id'], ['id'])
    with op.batch_alter_table('advanced_expenses'):
        op.create_foreign_key('fk_advanced_expenses_tenant_id', 'advanced_expenses', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('bank_reconciliations'):
        op.create_foreign_key('fk_bank_reconciliations_approved_by', 'bank_reconciliations', 'users', ['approved_by'], ['id'])
    with op.batch_alter_table('bank_reconciliations'):
        op.create_foreign_key('fk_bank_reconciliations_bank_account_id', 'bank_reconciliations', 'gl_accounts', ['bank_account_id'], ['id'])
    with op.batch_alter_table('bank_reconciliations'):
        op.create_foreign_key('fk_bank_reconciliations_created_by', 'bank_reconciliations', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('bank_reconciliations'):
        op.create_foreign_key('fk_bank_reconciliations_tenant_id', 'bank_reconciliations', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('budget_lines'):
        op.create_foreign_key('fk_budget_lines_account_id', 'budget_lines', 'gl_accounts', ['account_id'], ['id'])
    with op.batch_alter_table('budget_lines'):
        op.create_foreign_key('fk_budget_lines_budget_id', 'budget_lines', 'budgets', ['budget_id'], ['id'])
    with op.batch_alter_table('budget_lines'):
        op.create_foreign_key('fk_budget_lines_tenant_id', 'budget_lines', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('cash_boxes'):
        op.create_foreign_key('fk_cash_boxes_branch_id', 'cash_boxes', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('cash_boxes'):
        op.create_foreign_key('fk_cash_boxes_gl_account_id', 'cash_boxes', 'gl_accounts', ['gl_account_id'], ['id'])
    with op.batch_alter_table('cash_boxes'):
        op.create_foreign_key('fk_cash_boxes_tenant_id', 'cash_boxes', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_team_members'):
        op.create_foreign_key('fk_crm_team_members_team_id', 'crm_team_members', 'crm_teams', ['team_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_team_members'):
        op.create_foreign_key('fk_crm_team_members_tenant_id', 'crm_team_members', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_team_members'):
        op.create_foreign_key('fk_crm_team_members_user_id', 'crm_team_members', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('customers'):
        op.create_foreign_key('fk_customers_fiscal_position_id', 'customers', 'fiscal_positions', ['fiscal_position_id'], ['id'])
    with op.batch_alter_table('customers'):
        op.create_foreign_key('fk_customers_tenant_id', 'customers', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('customs_taxes'):
        op.create_foreign_key('fk_customs_taxes_gl_account_id', 'customs_taxes', 'gl_accounts', ['gl_account_id'], ['id'])
    with op.batch_alter_table('customs_taxes'):
        op.create_foreign_key('fk_customs_taxes_tenant_id', 'customs_taxes', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('email_campaigns'):
        op.create_foreign_key('fk_email_campaigns_list_id', 'email_campaigns', 'email_lists', ['list_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('email_campaigns'):
        op.create_foreign_key('fk_email_campaigns_template_id', 'email_campaigns', 'email_templates', ['template_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('email_campaigns'):
        op.create_foreign_key('fk_email_campaigns_tenant_id', 'email_campaigns', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('employee_leaves'):
        op.create_foreign_key('fk_employee_leaves_employee_id', 'employee_leaves', 'employees', ['employee_id'], ['id'])
    with op.batch_alter_table('employee_leaves'):
        op.create_foreign_key('fk_employee_leaves_tenant_id', 'employee_leaves', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('expenses'):
        op.create_foreign_key('fk_expenses_branch_id', 'expenses', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('expenses'):
        op.create_foreign_key('fk_expenses_category_id', 'expenses', 'expense_categories', ['category_id'], ['id'])
    with op.batch_alter_table('expenses'):
        op.create_foreign_key('fk_expenses_tenant_id', 'expenses', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('expenses'):
        op.create_foreign_key('fk_expenses_user_id', 'expenses', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('fixed_assets'):
        op.create_foreign_key('fk_fixed_assets_asset_account_id', 'fixed_assets', 'gl_accounts', ['asset_account_id'], ['id'])
    with op.batch_alter_table('fixed_assets'):
        op.create_foreign_key('fk_fixed_assets_branch_id', 'fixed_assets', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('fixed_assets'):
        op.create_foreign_key('fk_fixed_assets_cost_center_id', 'fixed_assets', 'cost_centers', ['cost_center_id'], ['id'])
    with op.batch_alter_table('fixed_assets'):
        op.create_foreign_key('fk_fixed_assets_created_by', 'fixed_assets', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('fixed_assets'):
        op.create_foreign_key('fk_fixed_assets_depreciation_account_id', 'fixed_assets', 'gl_accounts', ['depreciation_account_id'], ['id'])
    with op.batch_alter_table('fixed_assets'):
        op.create_foreign_key('fk_fixed_assets_expense_account_id', 'fixed_assets', 'gl_accounts', ['expense_account_id'], ['id'])
    with op.batch_alter_table('fixed_assets'):
        op.create_foreign_key('fk_fixed_assets_tenant_id', 'fixed_assets', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('gl_account_mappings'):
        op.create_foreign_key('fk_gl_account_mappings_branch_id', 'gl_account_mappings', 'branches', ['branch_id'], ['id'], ondelete='RESTRICT')
    with op.batch_alter_table('gl_account_mappings'):
        op.create_foreign_key('fk_gl_account_mappings_gl_account_id', 'gl_account_mappings', 'gl_accounts', ['gl_account_id'], ['id'], ondelete='RESTRICT')
    with op.batch_alter_table('gl_account_mappings'):
        op.create_foreign_key('fk_gl_account_mappings_tenant_id', 'gl_account_mappings', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('gl_journal_lines'):
        op.create_foreign_key('fk_gl_journal_lines_account_id', 'gl_journal_lines', 'gl_accounts', ['account_id'], ['id'])
    with op.batch_alter_table('gl_journal_lines'):
        op.create_foreign_key('fk_gl_journal_lines_branch_id', 'gl_journal_lines', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('gl_journal_lines'):
        op.create_foreign_key('fk_gl_journal_lines_cost_center_id', 'gl_journal_lines', 'cost_centers', ['cost_center_id'], ['id'])
    with op.batch_alter_table('gl_journal_lines'):
        op.create_foreign_key('fk_gl_journal_lines_entry_id', 'gl_journal_lines', 'gl_journal_entries', ['entry_id'], ['id'], ondelete='RESTRICT')
    with op.batch_alter_table('gl_journal_lines'):
        op.create_foreign_key('fk_gl_journal_lines_partner_id', 'gl_journal_lines', 'partners', ['partner_id'], ['id'])
    with op.batch_alter_table('gl_journal_lines'):
        op.create_foreign_key('fk_gl_journal_lines_profit_center_id', 'gl_journal_lines', 'profit_centers', ['profit_center_id'], ['id'])
    with op.batch_alter_table('gl_journal_lines'):
        op.create_foreign_key('fk_gl_journal_lines_tenant_id', 'gl_journal_lines', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('gl_journal_lines'):
        op.create_foreign_key('fk_gl_journal_lines_warehouse_id', 'gl_journal_lines', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('job_positions'):
        op.create_foreign_key('fk_job_positions_department_id', 'job_positions', 'departments', ['department_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('job_positions'):
        op.create_foreign_key('fk_job_positions_tenant_id', 'job_positions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('journal_entry_audits'):
        op.create_foreign_key('fk_journal_entry_audits_journal_entry_id', 'journal_entry_audits', 'gl_journal_entries', ['journal_entry_id'], ['id'])
    with op.batch_alter_table('journal_entry_audits'):
        op.create_foreign_key('fk_journal_entry_audits_performed_by', 'journal_entry_audits', 'users', ['performed_by'], ['id'])
    with op.batch_alter_table('journal_entry_audits'):
        op.create_foreign_key('fk_journal_entry_audits_tenant_id', 'journal_entry_audits', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('leave_requests'):
        op.create_foreign_key('fk_leave_requests_branch_id', 'leave_requests', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('leave_requests'):
        op.create_foreign_key('fk_leave_requests_leave_type_id', 'leave_requests', 'leave_types', ['leave_type_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('leave_requests'):
        op.create_foreign_key('fk_leave_requests_manager_id', 'leave_requests', 'users', ['manager_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('leave_requests'):
        op.create_foreign_key('fk_leave_requests_tenant_id', 'leave_requests', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('leave_requests'):
        op.create_foreign_key('fk_leave_requests_user_id', 'leave_requests', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('partner_profit_distributions'):
        op.create_foreign_key('fk_partner_profit_distributions_approved_by', 'partner_profit_distributions', 'users', ['approved_by'], ['id'])
    with op.batch_alter_table('partner_profit_distributions'):
        op.create_foreign_key('fk_partner_profit_distributions_created_by', 'partner_profit_distributions', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('partner_profit_distributions'):
        op.create_foreign_key('fk_partner_profit_distributions_partner_id', 'partner_profit_distributions', 'partners', ['partner_id'], ['id'])
    with op.batch_alter_table('partner_profit_distributions'):
        op.create_foreign_key('fk_partner_profit_distributions_tenant_id', 'partner_profit_distributions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('payment_logs'):
        op.create_foreign_key('fk_payment_logs_tenant_id', 'payment_logs', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('payment_logs'):
        op.create_foreign_key('fk_payment_logs_vault_id', 'payment_logs', 'payment_vault', ['vault_id'], ['id'])
    with op.batch_alter_table('payment_transactions'):
        op.create_foreign_key('fk_payment_transactions_tenant_id', 'payment_transactions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('payment_transactions'):
        op.create_foreign_key('fk_payment_transactions_vault_id', 'payment_transactions', 'payment_vault', ['vault_id'], ['id'])
    with op.batch_alter_table('payroll_transactions'):
        op.create_foreign_key('fk_payroll_transactions_branch_id', 'payroll_transactions', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('payroll_transactions'):
        op.create_foreign_key('fk_payroll_transactions_created_by', 'payroll_transactions', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('payroll_transactions'):
        op.create_foreign_key('fk_payroll_transactions_employee_id', 'payroll_transactions', 'employees', ['employee_id'], ['id'])
    with op.batch_alter_table('payroll_transactions'):
        op.create_foreign_key('fk_payroll_transactions_gl_entry_id', 'payroll_transactions', 'gl_journal_entries', ['gl_entry_id'], ['id'])
    with op.batch_alter_table('payroll_transactions'):
        op.create_foreign_key('fk_payroll_transactions_tenant_id', 'payroll_transactions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('pos_tables'):
        op.create_foreign_key('fk_pos_tables_floor_id', 'pos_tables', 'pos_floors', ['floor_id'], ['id'])
    with op.batch_alter_table('pos_tables'):
        op.create_foreign_key('fk_pos_tables_tenant_id', 'pos_tables', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('purchases'):
        op.create_foreign_key('fk_purchases_branch_id', 'purchases', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('purchases'):
        op.create_foreign_key('fk_purchases_supplier_id', 'purchases', 'suppliers', ['supplier_id'], ['id'])
    with op.batch_alter_table('purchases'):
        op.create_foreign_key('fk_purchases_tenant_id', 'purchases', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('purchases'):
        op.create_foreign_key('fk_purchases_user_id', 'purchases', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('purchases'):
        op.create_foreign_key('fk_purchases_warehouse_id', 'purchases', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('salary_advances'):
        op.create_foreign_key('fk_salary_advances_created_by', 'salary_advances', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('salary_advances'):
        op.create_foreign_key('fk_salary_advances_employee_id', 'salary_advances', 'employees', ['employee_id'], ['id'])
    with op.batch_alter_table('salary_advances'):
        op.create_foreign_key('fk_salary_advances_gl_entry_id', 'salary_advances', 'gl_journal_entries', ['gl_entry_id'], ['id'])
    with op.batch_alter_table('salary_advances'):
        op.create_foreign_key('fk_salary_advances_tenant_id', 'salary_advances', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('tenant_stores'):
        op.create_foreign_key('fk_tenant_stores_tenant_id', 'tenant_stores', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('tenant_stores'):
        op.create_foreign_key('fk_tenant_stores_warehouse_id', 'tenant_stores', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('bank_reconciliation_items'):
        op.create_foreign_key('fk_bank_reconciliation_items_cheque_id', 'bank_reconciliation_items', 'cheques', ['cheque_id'], ['id'])
    with op.batch_alter_table('bank_reconciliation_items'):
        op.create_foreign_key('fk_bank_reconciliation_items_journal_entry_id', 'bank_reconciliation_items', 'gl_journal_entries', ['journal_entry_id'], ['id'])
    with op.batch_alter_table('bank_reconciliation_items'):
        op.create_foreign_key('fk_bank_reconciliation_items_reconciliation_id', 'bank_reconciliation_items', 'bank_reconciliations', ['reconciliation_id'], ['id'])
    with op.batch_alter_table('bank_reconciliation_items'):
        op.create_foreign_key('fk_bank_reconciliation_items_tenant_id', 'bank_reconciliation_items', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('card_vault'):
        op.create_foreign_key('fk_card_vault_created_by', 'card_vault', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('card_vault'):
        op.create_foreign_key('fk_card_vault_customer_id', 'card_vault', 'customers', ['customer_id'], ['id'])
    with op.batch_alter_table('card_vault'):
        op.create_foreign_key('fk_card_vault_tenant_id', 'card_vault', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_leads'):
        op.create_foreign_key('fk_crm_leads_assigned_user_id', 'crm_leads', 'users', ['assigned_user_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('crm_leads'):
        op.create_foreign_key('fk_crm_leads_branch_id', 'crm_leads', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('crm_leads'):
        op.create_foreign_key('fk_crm_leads_customer_id', 'crm_leads', 'customers', ['customer_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('crm_leads'):
        op.create_foreign_key('fk_crm_leads_stage_id', 'crm_leads', 'crm_stages', ['stage_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('crm_leads'):
        op.create_foreign_key('fk_crm_leads_team_id', 'crm_leads', 'crm_teams', ['team_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('crm_leads'):
        op.create_foreign_key('fk_crm_leads_tenant_id', 'crm_leads', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('depreciation_schedules'):
        op.create_foreign_key('fk_depreciation_schedules_asset_id', 'depreciation_schedules', 'fixed_assets', ['asset_id'], ['id'])
    with op.batch_alter_table('depreciation_schedules'):
        op.create_foreign_key('fk_depreciation_schedules_journal_entry_id', 'depreciation_schedules', 'gl_journal_entries', ['journal_entry_id'], ['id'])
    with op.batch_alter_table('depreciation_schedules'):
        op.create_foreign_key('fk_depreciation_schedules_tenant_id', 'depreciation_schedules', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('email_subscribers'):
        op.create_foreign_key('fk_email_subscribers_customer_id', 'email_subscribers', 'customers', ['customer_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('email_subscribers'):
        op.create_foreign_key('fk_email_subscribers_list_id', 'email_subscribers', 'email_lists', ['list_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('email_subscribers'):
        op.create_foreign_key('fk_email_subscribers_tenant_id', 'email_subscribers', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('hr_contracts'):
        op.create_foreign_key('fk_hr_contracts_branch_id', 'hr_contracts', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('hr_contracts'):
        op.create_foreign_key('fk_hr_contracts_department_id', 'hr_contracts', 'departments', ['department_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('hr_contracts'):
        op.create_foreign_key('fk_hr_contracts_job_id', 'hr_contracts', 'job_positions', ['job_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('hr_contracts'):
        op.create_foreign_key('fk_hr_contracts_tenant_id', 'hr_contracts', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('hr_contracts'):
        op.create_foreign_key('fk_hr_contracts_user_id', 'hr_contracts', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('partner_transactions'):
        op.create_foreign_key('fk_partner_transactions_created_by', 'partner_transactions', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('partner_transactions'):
        op.create_foreign_key('fk_partner_transactions_distribution_id', 'partner_transactions', 'partner_profit_distributions', ['distribution_id'], ['id'])
    with op.batch_alter_table('partner_transactions'):
        op.create_foreign_key('fk_partner_transactions_partner_id', 'partner_transactions', 'partners', ['partner_id'], ['id'])
    with op.batch_alter_table('partner_transactions'):
        op.create_foreign_key('fk_partner_transactions_tenant_id', 'partner_transactions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('products'):
        op.create_foreign_key('fk_products_category_id', 'products', 'product_categories', ['category_id'], ['id'])
    with op.batch_alter_table('products'):
        op.create_foreign_key('fk_products_merchant_customer_id', 'products', 'customers', ['merchant_customer_id'], ['id'])
    with op.batch_alter_table('products'):
        op.create_foreign_key('fk_products_tenant_id', 'products', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('projects'):
        op.create_foreign_key('fk_projects_branch_id', 'projects', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('projects'):
        op.create_foreign_key('fk_projects_customer_id', 'projects', 'customers', ['customer_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('projects'):
        op.create_foreign_key('fk_projects_tenant_id', 'projects', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('purchase_returns'):
        op.create_foreign_key('fk_purchase_returns_branch_id', 'purchase_returns', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('purchase_returns'):
        op.create_foreign_key('fk_purchase_returns_processed_by', 'purchase_returns', 'users', ['processed_by'], ['id'])
    with op.batch_alter_table('purchase_returns'):
        op.create_foreign_key('fk_purchase_returns_purchase_id', 'purchase_returns', 'purchases', ['purchase_id'], ['id'])
    with op.batch_alter_table('purchase_returns'):
        op.create_foreign_key('fk_purchase_returns_supplier_id', 'purchase_returns', 'suppliers', ['supplier_id'], ['id'])
    with op.batch_alter_table('purchase_returns'):
        op.create_foreign_key('fk_purchase_returns_tenant_id', 'purchase_returns', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('purchase_returns'):
        op.create_foreign_key('fk_purchase_returns_warehouse_id', 'purchase_returns', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('sales'):
        op.create_foreign_key('fk_sales_branch_id', 'sales', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('sales'):
        op.create_foreign_key('fk_sales_customer_id', 'sales', 'customers', ['customer_id'], ['id'])
    with op.batch_alter_table('sales'):
        op.create_foreign_key('fk_sales_pos_session_id', 'sales', 'pos_sessions', ['pos_session_id'], ['id'])
    with op.batch_alter_table('sales'):
        op.create_foreign_key('fk_sales_sales_rep_id', 'sales', 'users', ['sales_rep_id'], ['id'])
    with op.batch_alter_table('sales'):
        op.create_foreign_key('fk_sales_seller_id', 'sales', 'users', ['seller_id'], ['id'])
    with op.batch_alter_table('sales'):
        op.create_foreign_key('fk_sales_table_id', 'sales', 'pos_tables', ['table_id'], ['id'])
    with op.batch_alter_table('sales'):
        op.create_foreign_key('fk_sales_tenant_id', 'sales', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('sales'):
        op.create_foreign_key('fk_sales_warehouse_id', 'sales', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('shop_customer_accounts'):
        op.create_foreign_key('fk_shop_customer_accounts_customer_id', 'shop_customer_accounts', 'customers', ['customer_id'], ['id'])
    with op.batch_alter_table('shop_customer_accounts'):
        op.create_foreign_key('fk_shop_customer_accounts_tenant_id', 'shop_customer_accounts', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('tax_calculation_rules'):
        op.create_foreign_key('fk_tax_calculation_rules_tax_id', 'tax_calculation_rules', 'customs_taxes', ['tax_id'], ['id'])
    with op.batch_alter_table('tax_calculation_rules'):
        op.create_foreign_key('fk_tax_calculation_rules_tenant_id', 'tax_calculation_rules', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('tickets'):
        op.create_foreign_key('fk_tickets_assigned_user_id', 'tickets', 'users', ['assigned_user_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tickets'):
        op.create_foreign_key('fk_tickets_branch_id', 'tickets', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tickets'):
        op.create_foreign_key('fk_tickets_category_id', 'tickets', 'ticket_categories', ['category_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tickets'):
        op.create_foreign_key('fk_tickets_customer_id', 'tickets', 'customers', ['customer_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tickets'):
        op.create_foreign_key('fk_tickets_priority_id', 'tickets', 'ticket_priorities', ['priority_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tickets'):
        op.create_foreign_key('fk_tickets_tenant_id', 'tickets', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('azad_platform_fees'):
        op.create_foreign_key('fk_azad_platform_fees_payment_id', 'azad_platform_fees', 'payments', ['payment_id'], ['id'])
    with op.batch_alter_table('azad_platform_fees'):
        op.create_foreign_key('fk_azad_platform_fees_sale_id', 'azad_platform_fees', 'sales', ['sale_id'], ['id'])
    with op.batch_alter_table('azad_platform_fees'):
        op.create_foreign_key('fk_azad_platform_fees_tenant_id', 'azad_platform_fees', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('azad_platform_fees'):
        op.create_foreign_key('fk_azad_platform_fees_vault_id', 'azad_platform_fees', 'payment_vault', ['vault_id'], ['id'])
    with op.batch_alter_table('bank_statement_lines'):
        op.create_foreign_key('fk_bank_statement_lines_bank_account_id', 'bank_statement_lines', 'gl_accounts', ['bank_account_id'], ['id'])
    with op.batch_alter_table('bank_statement_lines'):
        op.create_foreign_key('fk_bank_statement_lines_created_by', 'bank_statement_lines', 'users', ['created_by'], ['id'])
    with op.batch_alter_table('bank_statement_lines'):
        op.create_foreign_key('fk_bank_statement_lines_matched_by', 'bank_statement_lines', 'users', ['matched_by'], ['id'])
    with op.batch_alter_table('bank_statement_lines'):
        op.create_foreign_key('fk_bank_statement_lines_matched_cheque_id', 'bank_statement_lines', 'cheques', ['matched_cheque_id'], ['id'])
    with op.batch_alter_table('bank_statement_lines'):
        op.create_foreign_key('fk_bank_statement_lines_matched_journal_entry_id', 'bank_statement_lines', 'gl_journal_entries', ['matched_journal_entry_id'], ['id'])
    with op.batch_alter_table('bank_statement_lines'):
        op.create_foreign_key('fk_bank_statement_lines_reconciliation_item_id', 'bank_statement_lines', 'bank_reconciliation_items', ['reconciliation_item_id'], ['id'])
    with op.batch_alter_table('bank_statement_lines'):
        op.create_foreign_key('fk_bank_statement_lines_tenant_id', 'bank_statement_lines', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('campaign_logs'):
        op.create_foreign_key('fk_campaign_logs_campaign_id', 'campaign_logs', 'email_campaigns', ['campaign_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('campaign_logs'):
        op.create_foreign_key('fk_campaign_logs_subscriber_id', 'campaign_logs', 'email_subscribers', ['subscriber_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('campaign_logs'):
        op.create_foreign_key('fk_campaign_logs_tenant_id', 'campaign_logs', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_activities'):
        op.create_foreign_key('fk_crm_activities_lead_id', 'crm_activities', 'crm_leads', ['lead_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_activities'):
        op.create_foreign_key('fk_crm_activities_tenant_id', 'crm_activities', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('crm_activities'):
        op.create_foreign_key('fk_crm_activities_user_id', 'crm_activities', 'users', ['user_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('fiscal_position_tax_rules'):
        op.create_foreign_key('fk_fiscal_position_tax_rules_destination_account_id', 'fiscal_position_tax_rules', 'gl_accounts', ['destination_account_id'], ['id'])
    with op.batch_alter_table('fiscal_position_tax_rules'):
        op.create_foreign_key('fk_fiscal_position_tax_rules_destination_tax_id', 'fiscal_position_tax_rules', 'tax_calculation_rules', ['destination_tax_id'], ['id'])
    with op.batch_alter_table('fiscal_position_tax_rules'):
        op.create_foreign_key('fk_fiscal_position_tax_rules_fiscal_position_id', 'fiscal_position_tax_rules', 'fiscal_positions', ['fiscal_position_id'], ['id'])
    with op.batch_alter_table('fiscal_position_tax_rules'):
        op.create_foreign_key('fk_fiscal_position_tax_rules_source_account_id', 'fiscal_position_tax_rules', 'gl_accounts', ['source_account_id'], ['id'])
    with op.batch_alter_table('fiscal_position_tax_rules'):
        op.create_foreign_key('fk_fiscal_position_tax_rules_source_tax_id', 'fiscal_position_tax_rules', 'tax_calculation_rules', ['source_tax_id'], ['id'])
    with op.batch_alter_table('fiscal_position_tax_rules'):
        op.create_foreign_key('fk_fiscal_position_tax_rules_tenant_id', 'fiscal_position_tax_rules', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('pos_kds_orders'):
        op.create_foreign_key('fk_pos_kds_orders_branch_id', 'pos_kds_orders', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('pos_kds_orders'):
        op.create_foreign_key('fk_pos_kds_orders_sale_id', 'pos_kds_orders', 'sales', ['sale_id'], ['id'])
    with op.batch_alter_table('pos_kds_orders'):
        op.create_foreign_key('fk_pos_kds_orders_session_id', 'pos_kds_orders', 'pos_sessions', ['session_id'], ['id'])
    with op.batch_alter_table('pos_kds_orders'):
        op.create_foreign_key('fk_pos_kds_orders_tenant_id', 'pos_kds_orders', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('pos_table_orders'):
        op.create_foreign_key('fk_pos_table_orders_sale_id', 'pos_table_orders', 'sales', ['sale_id'], ['id'])
    with op.batch_alter_table('pos_table_orders'):
        op.create_foreign_key('fk_pos_table_orders_table_id', 'pos_table_orders', 'pos_tables', ['table_id'], ['id'])
    with op.batch_alter_table('pos_table_orders'):
        op.create_foreign_key('fk_pos_table_orders_tenant_id', 'pos_table_orders', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_cost_history'):
        op.create_foreign_key('fk_product_cost_history_product_id', 'product_cost_history', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('product_cost_history'):
        op.create_foreign_key('fk_product_cost_history_tenant_id', 'product_cost_history', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_cost_history'):
        op.create_foreign_key('fk_product_cost_history_warehouse_id', 'product_cost_history', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('product_images'):
        op.create_foreign_key('fk_product_images_product_id', 'product_images', 'products', ['product_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_images'):
        op.create_foreign_key('fk_product_images_tenant_id', 'product_images', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_partners'):
        op.create_foreign_key('fk_product_partners_partner_customer_id', 'product_partners', 'customers', ['partner_customer_id'], ['id'])
    with op.batch_alter_table('product_partners'):
        op.create_foreign_key('fk_product_partners_product_id', 'product_partners', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('product_partners'):
        op.create_foreign_key('fk_product_partners_tenant_id', 'product_partners', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_price_tiers'):
        op.create_foreign_key('fk_product_price_tiers_product_id', 'product_price_tiers', 'products', ['product_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_price_tiers'):
        op.create_foreign_key('fk_product_price_tiers_tenant_id', 'product_price_tiers', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_returns'):
        op.create_foreign_key('fk_product_returns_branch_id', 'product_returns', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('product_returns'):
        op.create_foreign_key('fk_product_returns_customer_id', 'product_returns', 'customers', ['customer_id'], ['id'])
    with op.batch_alter_table('product_returns'):
        op.create_foreign_key('fk_product_returns_processed_by', 'product_returns', 'users', ['processed_by'], ['id'])
    with op.batch_alter_table('product_returns'):
        op.create_foreign_key('fk_product_returns_reverses_invoice_id', 'product_returns', 'sales', ['reverses_invoice_id'], ['id'])
    with op.batch_alter_table('product_returns'):
        op.create_foreign_key('fk_product_returns_sale_id', 'product_returns', 'sales', ['sale_id'], ['id'])
    with op.batch_alter_table('product_returns'):
        op.create_foreign_key('fk_product_returns_tenant_id', 'product_returns', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_warehouse_stock'):
        op.create_foreign_key('fk_product_warehouse_stock_product_id', 'product_warehouse_stock', 'products', ['product_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_warehouse_stock'):
        op.create_foreign_key('fk_product_warehouse_stock_tenant_id', 'product_warehouse_stock', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_warehouse_stock'):
        op.create_foreign_key('fk_product_warehouse_stock_warehouse_id', 'product_warehouse_stock', 'warehouses', ['warehouse_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('project_members'):
        op.create_foreign_key('fk_project_members_project_id', 'project_members', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('project_members'):
        op.create_foreign_key('fk_project_members_tenant_id', 'project_members', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('project_members'):
        op.create_foreign_key('fk_project_members_user_id', 'project_members', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('purchase_lines'):
        op.create_foreign_key('fk_purchase_lines_product_id', 'purchase_lines', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('purchase_lines'):
        op.create_foreign_key('fk_purchase_lines_purchase_id', 'purchase_lines', 'purchases', ['purchase_id'], ['id'], ondelete='RESTRICT')
    with op.batch_alter_table('purchase_lines'):
        op.create_foreign_key('fk_purchase_lines_tenant_id', 'purchase_lines', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('sale_campaigns'):
        op.create_foreign_key('fk_sale_campaigns_campaign_id', 'sale_campaigns', 'campaigns', ['campaign_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('sale_campaigns'):
        op.create_foreign_key('fk_sale_campaigns_sale_id', 'sale_campaigns', 'sales', ['sale_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('sale_campaigns'):
        op.create_foreign_key('fk_sale_campaigns_tenant_id', 'sale_campaigns', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('sale_lines'):
        op.create_foreign_key('fk_sale_lines_product_id', 'sale_lines', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('sale_lines'):
        op.create_foreign_key('fk_sale_lines_sale_id', 'sale_lines', 'sales', ['sale_id'], ['id'], ondelete='RESTRICT')
    with op.batch_alter_table('sale_lines'):
        op.create_foreign_key('fk_sale_lines_tenant_id', 'sale_lines', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_abandoned_carts'):
        op.create_foreign_key('fk_shop_abandoned_carts_account_id', 'shop_abandoned_carts', 'shop_customer_accounts', ['account_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_abandoned_carts'):
        op.create_foreign_key('fk_shop_abandoned_carts_tenant_id', 'shop_abandoned_carts', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_loyalty'):
        op.create_foreign_key('fk_shop_loyalty_account_id', 'shop_loyalty', 'shop_customer_accounts', ['account_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_loyalty'):
        op.create_foreign_key('fk_shop_loyalty_tenant_id', 'shop_loyalty', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_loyalty_transactions'):
        op.create_foreign_key('fk_shop_loyalty_transactions_account_id', 'shop_loyalty_transactions', 'shop_customer_accounts', ['account_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_loyalty_transactions'):
        op.create_foreign_key('fk_shop_loyalty_transactions_sale_id', 'shop_loyalty_transactions', 'sales', ['sale_id'], ['id'])
    with op.batch_alter_table('shop_loyalty_transactions'):
        op.create_foreign_key('fk_shop_loyalty_transactions_tenant_id', 'shop_loyalty_transactions', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_product_variants'):
        op.create_foreign_key('fk_shop_product_variants_product_id', 'shop_product_variants', 'products', ['product_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_product_variants'):
        op.create_foreign_key('fk_shop_product_variants_tenant_id', 'shop_product_variants', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_reviews'):
        op.create_foreign_key('fk_shop_reviews_account_id', 'shop_reviews', 'shop_customer_accounts', ['account_id'], ['id'])
    with op.batch_alter_table('shop_reviews'):
        op.create_foreign_key('fk_shop_reviews_product_id', 'shop_reviews', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('shop_reviews'):
        op.create_foreign_key('fk_shop_reviews_tenant_id', 'shop_reviews', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_saved_payments'):
        op.create_foreign_key('fk_shop_saved_payments_account_id', 'shop_saved_payments', 'shop_customer_accounts', ['account_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_saved_payments'):
        op.create_foreign_key('fk_shop_saved_payments_tenant_id', 'shop_saved_payments', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_stock_alerts'):
        op.create_foreign_key('fk_shop_stock_alerts_product_id', 'shop_stock_alerts', 'products', ['product_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_stock_alerts'):
        op.create_foreign_key('fk_shop_stock_alerts_tenant_id', 'shop_stock_alerts', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('shop_wishlist'):
        op.create_foreign_key('fk_shop_wishlist_account_id', 'shop_wishlist', 'shop_customer_accounts', ['account_id'], ['id'])
    with op.batch_alter_table('shop_wishlist'):
        op.create_foreign_key('fk_shop_wishlist_product_id', 'shop_wishlist', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('shop_wishlist'):
        op.create_foreign_key('fk_shop_wishlist_tenant_id', 'shop_wishlist', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('stock_movements'):
        op.create_foreign_key('fk_stock_movements_product_id', 'stock_movements', 'products', ['product_id'], ['id'], ondelete='RESTRICT')
    with op.batch_alter_table('stock_movements'):
        op.create_foreign_key('fk_stock_movements_tenant_id', 'stock_movements', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('stock_movements'):
        op.create_foreign_key('fk_stock_movements_user_id', 'stock_movements', 'users', ['user_id'], ['id'])
    with op.batch_alter_table('stock_movements'):
        op.create_foreign_key('fk_stock_movements_warehouse_id', 'stock_movements', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('task_stages'):
        op.create_foreign_key('fk_task_stages_project_id', 'task_stages', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('task_stages'):
        op.create_foreign_key('fk_task_stages_tenant_id', 'task_stages', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('ticket_comments'):
        op.create_foreign_key('fk_ticket_comments_tenant_id', 'ticket_comments', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('ticket_comments'):
        op.create_foreign_key('fk_ticket_comments_ticket_id', 'ticket_comments', 'tickets', ['ticket_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('ticket_comments'):
        op.create_foreign_key('fk_ticket_comments_user_id', 'ticket_comments', 'users', ['user_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('partner_commission_entries'):
        op.create_foreign_key('fk_partner_commission_entries_branch_id', 'partner_commission_entries', 'branches', ['branch_id'], ['id'])
    with op.batch_alter_table('partner_commission_entries'):
        op.create_foreign_key('fk_partner_commission_entries_partner_customer_id', 'partner_commission_entries', 'customers', ['partner_customer_id'], ['id'])
    with op.batch_alter_table('partner_commission_entries'):
        op.create_foreign_key('fk_partner_commission_entries_product_id', 'partner_commission_entries', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('partner_commission_entries'):
        op.create_foreign_key('fk_partner_commission_entries_sale_id', 'partner_commission_entries', 'sales', ['sale_id'], ['id'])
    with op.batch_alter_table('partner_commission_entries'):
        op.create_foreign_key('fk_partner_commission_entries_sale_line_id', 'partner_commission_entries', 'sale_lines', ['sale_line_id'], ['id'])
    with op.batch_alter_table('partner_commission_entries'):
        op.create_foreign_key('fk_partner_commission_entries_tenant_id', 'partner_commission_entries', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('partner_commission_entries'):
        op.create_foreign_key('fk_partner_commission_entries_warehouse_id', 'partner_commission_entries', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('product_return_lines'):
        op.create_foreign_key('fk_product_return_lines_product_id', 'product_return_lines', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('product_return_lines'):
        op.create_foreign_key('fk_product_return_lines_return_id', 'product_return_lines', 'product_returns', ['return_id'], ['id'])
    with op.batch_alter_table('product_return_lines'):
        op.create_foreign_key('fk_product_return_lines_sale_line_id', 'product_return_lines', 'sale_lines', ['sale_line_id'], ['id'])
    with op.batch_alter_table('product_return_lines'):
        op.create_foreign_key('fk_product_return_lines_tenant_id', 'product_return_lines', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_serials'):
        op.create_foreign_key('fk_product_serials_product_id', 'product_serials', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('product_serials'):
        op.create_foreign_key('fk_product_serials_purchase_line_id', 'product_serials', 'purchase_lines', ['purchase_line_id'], ['id'])
    with op.batch_alter_table('product_serials'):
        op.create_foreign_key('fk_product_serials_sale_line_id', 'product_serials', 'sale_lines', ['sale_line_id'], ['id'])
    with op.batch_alter_table('product_serials'):
        op.create_foreign_key('fk_product_serials_tenant_id', 'product_serials', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_serials'):
        op.create_foreign_key('fk_product_serials_warehouse_id', 'product_serials', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('product_warehouse_costs'):
        op.create_foreign_key('fk_product_warehouse_costs_product_id', 'product_warehouse_costs', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('product_warehouse_costs'):
        op.create_foreign_key('fk_product_warehouse_costs_tenant_id', 'product_warehouse_costs', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('product_warehouse_costs'):
        op.create_foreign_key('fk_product_warehouse_costs_updated_by_movement_id', 'product_warehouse_costs', 'stock_movements', ['updated_by_movement_id'], ['id'])
    with op.batch_alter_table('product_warehouse_costs'):
        op.create_foreign_key('fk_product_warehouse_costs_warehouse_id', 'product_warehouse_costs', 'warehouses', ['warehouse_id'], ['id'])
    with op.batch_alter_table('purchase_return_lines'):
        op.create_foreign_key('fk_purchase_return_lines_product_id', 'purchase_return_lines', 'products', ['product_id'], ['id'])
    with op.batch_alter_table('purchase_return_lines'):
        op.create_foreign_key('fk_purchase_return_lines_purchase_line_id', 'purchase_return_lines', 'purchase_lines', ['purchase_line_id'], ['id'])
    with op.batch_alter_table('purchase_return_lines'):
        op.create_foreign_key('fk_purchase_return_lines_return_id', 'purchase_return_lines', 'purchase_returns', ['return_id'], ['id'])
    with op.batch_alter_table('purchase_return_lines'):
        op.create_foreign_key('fk_purchase_return_lines_tenant_id', 'purchase_return_lines', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('tasks'):
        op.create_foreign_key('fk_tasks_assigned_user_id', 'tasks', 'users', ['assigned_user_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tasks'):
        op.create_foreign_key('fk_tasks_branch_id', 'tasks', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tasks'):
        op.create_foreign_key('fk_tasks_parent_id', 'tasks', 'tasks', ['parent_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tasks'):
        op.create_foreign_key('fk_tasks_project_id', 'tasks', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('tasks'):
        op.create_foreign_key('fk_tasks_stage_id', 'tasks', 'task_stages', ['stage_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('tasks'):
        op.create_foreign_key('fk_tasks_tenant_id', 'tasks', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('warranty_claims'):
        op.create_foreign_key('fk_warranty_claims_product_id', 'warranty_claims', 'products', ['product_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('warranty_claims'):
        op.create_foreign_key('fk_warranty_claims_sale_id', 'warranty_claims', 'sales', ['sale_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('warranty_claims'):
        op.create_foreign_key('fk_warranty_claims_sale_line_id', 'warranty_claims', 'sale_lines', ['sale_line_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('warranty_claims'):
        op.create_foreign_key('fk_warranty_claims_tenant_id', 'warranty_claims', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('timesheets'):
        op.create_foreign_key('fk_timesheets_branch_id', 'timesheets', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('timesheets'):
        op.create_foreign_key('fk_timesheets_task_id', 'timesheets', 'tasks', ['task_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('timesheets'):
        op.create_foreign_key('fk_timesheets_tenant_id', 'timesheets', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('timesheets'):
        op.create_foreign_key('fk_timesheets_user_id', 'timesheets', 'users', ['user_id'], ['id'], ondelete='CASCADE')
def downgrade():
    op.execute(text("DROP TABLE IF EXISTS timesheets CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS warranty_claims CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS tasks CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS purchase_return_lines CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_warehouse_costs CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_serials CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_return_lines CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS partner_commission_entries CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS ticket_comments CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS task_stages CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS stock_movements CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_wishlist CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_stock_alerts CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_saved_payments CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_reviews CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_product_variants CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_loyalty_transactions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_loyalty CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_abandoned_carts CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS sale_lines CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS sale_campaigns CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS purchase_lines CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS project_members CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_warehouse_stock CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_returns CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_price_tiers CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_partners CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_images CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_cost_history CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS pos_table_orders CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS pos_kds_orders CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS fiscal_position_tax_rules CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS crm_activities CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS campaign_logs CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS bank_statement_lines CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS azad_platform_fees CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS tickets CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS tax_calculation_rules CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_customer_accounts CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS sales CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS purchase_returns CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS projects CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS products CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS partner_transactions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS hr_contracts CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS email_subscribers CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS depreciation_schedules CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS crm_leads CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS card_vault CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS bank_reconciliation_items CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS tenant_stores CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS salary_advances CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS purchases CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS pos_tables CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS payroll_transactions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS payment_transactions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS payment_logs CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS partner_profit_distributions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS leave_requests CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS journal_entry_audits CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS job_positions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS gl_journal_lines CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS gl_account_mappings CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS fixed_assets CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS expenses CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS employee_leaves CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS email_campaigns CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS customs_taxes CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS customers CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS crm_team_members CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS cash_boxes CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS budget_lines CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS bank_reconciliations CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS advanced_expenses CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS warehouses CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS ticket_priorities CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS ticket_categories CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS system_settings CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS suppliers CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS store_coupons CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shop_newsletters CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS shipments CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS security_alerts CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS role_permissions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS profit_centers CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS product_categories CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS print_history CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS pos_sessions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS pos_floors CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS payroll_settings CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS payment_vault CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS partners CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS package_purchases CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS login_history CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS leave_types CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS invoice_settings CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS integration_settings CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS gl_periods CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS gl_journal_entries CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS gl_accounts CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS fiscal_positions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS expense_categories CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS exchange_rates CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS exchange_rate_records CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS error_audit_logs CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS employees CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS email_templates CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS email_lists CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS donations CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS document_verifications CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS document_snapshots CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS document_sequences CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS departments CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS crm_teams CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS crm_stages CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS cost_centers CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS card_payments CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS campaigns CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS budgets CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS azad_subscription_fees CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS audit_logs CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS attendances CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS archived_records CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS api_keys CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS ai_memories CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS ai_interactions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS ai_expertise CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS users CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS tenants CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS store_payment_methods CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS roles CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS receipts CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS permissions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS payments CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS packages CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS industry_field_definitions CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS currencies CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS cheques CASCADE"))
    op.execute(text("DROP TABLE IF EXISTS branches CASCADE"))
