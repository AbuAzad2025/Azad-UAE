"""add_tenant_limits_and_partners

Revision ID: partner_system_001
Revises: treasury_gl_accounts_001
Create Date: 2026-06-03 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'partner_system_001'
down_revision = 'treasury_gl_accounts_001'
branch_labels = None
depends_on = None


def upgrade():
    # ── Tenant: new limit columns ─────────────────────────────
    op.add_column('tenants', sa.Column('max_suppliers', sa.Integer(), nullable=True, server_default='200'))
    op.add_column('tenants', sa.Column('max_branches', sa.Integer(), nullable=True, server_default='3'))
    op.add_column('tenants', sa.Column('max_warehouses', sa.Integer(), nullable=True, server_default='2'))
    op.add_column('tenants', sa.Column('max_invoices_per_month', sa.Integer(), nullable=True, server_default='1000'))
    op.add_column('tenants', sa.Column('max_sales_per_month', sa.Integer(), nullable=True, server_default='5000'))
    op.add_column('tenants', sa.Column('data_retention_days', sa.Integer(), nullable=True, server_default='365'))

    # ── Tenant: new feature flags ────────────────────────────
    op.add_column('tenants', sa.Column('enable_pos', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenants', sa.Column('enable_payroll', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenants', sa.Column('enable_cheques', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenants', sa.Column('enable_expenses', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenants', sa.Column('enable_store', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('tenants', sa.Column('allow_data_export', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenants', sa.Column('allow_custom_integrations', sa.Boolean(), nullable=True, server_default='false'))

    # ── Partners table ────────────────────────────────────────
    op.create_table('partners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('name_en', sa.String(length=200), nullable=True),
        sa.Column('code', sa.String(length=50), nullable=True),
        sa.Column('scope_type', sa.String(length=20), nullable=False, server_default='company'),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('partner_type', sa.String(length=30), nullable=False, server_default='investor'),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('id_number', sa.String(length=100), nullable=True),
        sa.Column('investment_amount', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('share_percentage', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0'),
        sa.Column('fixed_monthly_amount', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('expense_share_percentage', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0'),
        sa.Column('loss_share_percentage', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0'),
        sa.Column('min_profit_threshold', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('current_balance', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('total_profit_received', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('total_loss_borne', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('total_withdrawals', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('total_additional_investment', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_partners_code'), 'partners', ['code'], unique=False)
    op.create_index(op.f('ix_partners_scope_id'), 'partners', ['scope_id'], unique=False)
    op.create_index(op.f('ix_partners_tenant_id'), 'partners', ['tenant_id'], unique=False)

    # ── Partner Profit Distributions table ────────────────────
    op.create_table('partner_profit_distributions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('partner_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('scope_type', sa.String(length=20), nullable=True),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('total_revenue', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('total_cogs', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('total_expenses', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('net_profit', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('share_percentage', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0'),
        sa.Column('share_amount', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('expense_share_percentage', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0'),
        sa.Column('expense_share_amount', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('loss_share_percentage', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0'),
        sa.Column('loss_share_amount', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('fixed_amount', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('net_due', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='draft'),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_partner_profit_distributions_partner_id'), 'partner_profit_distributions', ['partner_id'], unique=False)
    op.create_index(op.f('ix_partner_profit_distributions_tenant_id'), 'partner_profit_distributions', ['tenant_id'], unique=False)

    # ── Partner Transactions table ────────────────────────────
    op.create_table('partner_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('partner_id', sa.Integer(), nullable=False),
        sa.Column('distribution_id', sa.Integer(), nullable=True),
        sa.Column('transaction_type', sa.String(length=30), nullable=False),
        sa.Column('amount', sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=True, server_default='AED'),
        sa.Column('exchange_rate', sa.Numeric(precision=15, scale=6), nullable=True, server_default='1'),
        sa.Column('amount_base', sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=15, scale=3), nullable=True, server_default='0'),
        sa.Column('reference_number', sa.String(length=100), nullable=True),
        sa.Column('reference_type', sa.String(length=30), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['distribution_id'], ['partner_profit_distributions.id'], ),
        sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_partner_transactions_distribution_id'), 'partner_transactions', ['distribution_id'], unique=False)
    op.create_index(op.f('ix_partner_transactions_partner_id'), 'partner_transactions', ['partner_id'], unique=False)
    op.create_index(op.f('ix_partner_transactions_tenant_id'), 'partner_transactions', ['tenant_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_partner_transactions_tenant_id'), table_name='partner_transactions')
    op.drop_index(op.f('ix_partner_transactions_partner_id'), table_name='partner_transactions')
    op.drop_index(op.f('ix_partner_transactions_distribution_id'), table_name='partner_transactions')
    op.drop_table('partner_transactions')

    op.drop_index(op.f('ix_partner_profit_distributions_tenant_id'), table_name='partner_profit_distributions')
    op.drop_index(op.f('ix_partner_profit_distributions_partner_id'), table_name='partner_profit_distributions')
    op.drop_table('partner_profit_distributions')

    op.drop_index(op.f('ix_partners_tenant_id'), table_name='partners')
    op.drop_index(op.f('ix_partners_scope_id'), table_name='partners')
    op.drop_index(op.f('ix_partners_code'), table_name='partners')
    op.drop_table('partners')

    op.drop_column('tenants', 'allow_custom_integrations')
    op.drop_column('tenants', 'allow_data_export')
    op.drop_column('tenants', 'enable_store')
    op.drop_column('tenants', 'enable_expenses')
    op.drop_column('tenants', 'enable_cheques')
    op.drop_column('tenants', 'enable_payroll')
    op.drop_column('tenants', 'enable_pos')
    op.drop_column('tenants', 'data_retention_days')
    op.drop_column('tenants', 'max_sales_per_month')
    op.drop_column('tenants', 'max_invoices_per_month')
    op.drop_column('tenants', 'max_warehouses')
    op.drop_column('tenants', 'max_branches')
    op.drop_column('tenants', 'max_suppliers')
