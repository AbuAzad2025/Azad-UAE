"""Add Azad platform fee accruals

Revision ID: security_7_5_002
Revises: security_7_5_001
Create Date: 2026-06-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'security_7_5_002'
down_revision = 'security_7_5_001'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if _table_exists('azad_platform_fees'):
        return

    op.create_table(
        'azad_platform_fees',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=180), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('sale_id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('vault_id', sa.Integer(), nullable=True),
        sa.Column('rate_percent', sa.Numeric(5, 2), nullable=False),
        sa.Column('base_amount_aed', sa.Numeric(15, 3), nullable=False),
        sa.Column('fee_amount_aed', sa.Numeric(15, 3), nullable=False),
        sa.Column('transaction_scope', sa.String(length=30), nullable=False),
        sa.Column('payment_channel', sa.String(length=50), nullable=False),
        sa.Column('gateway_name', sa.String(length=50), nullable=True),
        sa.Column('gateway_reference', sa.String(length=120), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('gl_posted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id']),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
        sa.ForeignKeyConstraint(['vault_id'], ['payment_vault.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_azad_platform_fees_idempotency_key'),
    )
    op.create_index('ix_azad_platform_fees_tenant_id', 'azad_platform_fees', ['tenant_id'], unique=False)
    op.create_index('ix_azad_platform_fees_sale_id', 'azad_platform_fees', ['sale_id'], unique=False)
    op.create_index('ix_azad_platform_fees_payment_id', 'azad_platform_fees', ['payment_id'], unique=False)
    op.create_index('ix_azad_platform_fees_vault_id', 'azad_platform_fees', ['vault_id'], unique=False)
    op.create_index('ix_azad_platform_fees_status', 'azad_platform_fees', ['status'], unique=False)
    op.create_index('ix_azad_platform_fees_tenant_sale', 'azad_platform_fees', ['tenant_id', 'sale_id'], unique=False)


def downgrade():
    if not _table_exists('azad_platform_fees'):
        return

    op.drop_index('ix_azad_platform_fees_tenant_sale', table_name='azad_platform_fees')
    op.drop_index('ix_azad_platform_fees_status', table_name='azad_platform_fees')
    op.drop_index('ix_azad_platform_fees_vault_id', table_name='azad_platform_fees')
    op.drop_index('ix_azad_platform_fees_payment_id', table_name='azad_platform_fees')
    op.drop_index('ix_azad_platform_fees_sale_id', table_name='azad_platform_fees')
    op.drop_index('ix_azad_platform_fees_tenant_id', table_name='azad_platform_fees')
    op.drop_table('azad_platform_fees')
