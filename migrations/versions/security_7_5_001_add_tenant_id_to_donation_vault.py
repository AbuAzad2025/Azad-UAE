"""Add tenant_id to donations and payment_vault tables

Revision ID: security_7_5_001
Revises: phase5_001
Create Date: 2026-06-06

Adds optional tenant scope to Donation and PaymentVault models.
Existing NULL rows remain Azad/platform records.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'security_7_5_001'
down_revision = 'phase5_001'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in cols


def upgrade():
    # ── donations ──
    if _table_exists('donations') and not _column_exists('donations', 'tenant_id'):
        op.add_column('donations', sa.Column('tenant_id', sa.Integer(), nullable=True))
        op.create_index('ix_donations_tenant_id', 'donations', ['tenant_id'])
        op.create_foreign_key('fk_donations_tenant_id', 'donations', 'tenants', ['tenant_id'], ['id'])

    # ── payment_vault ──
    if _table_exists('payment_vault') and not _column_exists('payment_vault', 'tenant_id'):
        op.add_column('payment_vault', sa.Column('tenant_id', sa.Integer(), nullable=True))
        op.create_index('ix_payment_vault_tenant_id', 'payment_vault', ['tenant_id'], unique=True)
        op.create_foreign_key('fk_payment_vault_tenant_id', 'payment_vault', 'tenants', ['tenant_id'], ['id'])


def downgrade():
    if _table_exists('payment_vault') and _column_exists('payment_vault', 'tenant_id'):
        op.drop_constraint('fk_payment_vault_tenant_id', 'payment_vault', type_='foreignkey')
        op.drop_index('ix_payment_vault_tenant_id', table_name='payment_vault')
        op.drop_column('payment_vault', 'tenant_id')

    if _table_exists('donations') and _column_exists('donations', 'tenant_id'):
        op.drop_constraint('fk_donations_tenant_id', 'donations', type_='foreignkey')
        op.drop_index('ix_donations_tenant_id', table_name='donations')
        op.drop_column('donations', 'tenant_id')
