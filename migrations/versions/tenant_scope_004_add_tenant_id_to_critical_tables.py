"""Add tenant_id to 5 critical tables for data isolation

Revision ID: tenant_scope_004
Revises: perf_gl_balance_001
Create Date: 2026-07-07

Tables scoped:
  - integration_settings  (platform-global → per-tenant)
  - card_payments         (standalone → per-tenant)
  - crm_team_members      (junction → inherits from CRMTeam)
  - payment_transactions  (child of payment_vault → inherits tenant_id)
  - payment_logs          (child of payment_vault → inherits tenant_id)

Backfill strategy:
  - Tables with parent FK to tenant_id-scoped model: inherit from parent
  - Standalone tables: default to tenant_id=1 (platform owner)
"""
from alembic import op
import sqlalchemy as sa

revision = 'tenant_scope_004'
down_revision = 'perf_gl_balance_001'
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = 1


def _column_exists(table, column):
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :tbl AND column_name = :col"
    ), {'tbl': table, 'col': column})
    return result.fetchone() is not None


def _index_exists(table_name, index_name):
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename = :tbl AND indexname = :idx"
    ), {'tbl': table_name, 'idx': index_name})
    return result.fetchone() is not None


def _constraint_exists(table_name, constraint_name):
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT conname FROM pg_constraint "
        "WHERE conname = :cdef AND conrelid = :tbl::regclass"
    ), {'cdef': constraint_name, 'tbl': table_name})
    return result.fetchone() is not None


def upgrade():
    # ──────────────────────────────────────────────────────────────────────
    # 1. integration_settings  (standalone, no parent FK → default tenant)
    # ──────────────────────────────────────────────────────────────────────
    if not _column_exists('integration_settings', 'tenant_id'):
        op.add_column('integration_settings', sa.Column(
            'tenant_id', sa.Integer(),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=True,  # nullable first for safe backfill
        ))
        op.execute(sa.text(
            "UPDATE integration_settings SET tenant_id = :tid WHERE tenant_id IS NULL"
        )).bindparams(tid=DEFAULT_TENANT_ID)

    # Drop old service_name unique, add composite (tenant_id, service_name)
    if _constraint_exists('integration_settings', 'integration_settings_service_name_key'):
        op.drop_constraint(
            'integration_settings_service_name_key',
            'integration_settings',
            type_='unique',
        )
    op.create_unique_constraint(
        'uq_integration_settings_tenant_service',
        'integration_settings',
        ['tenant_id', 'service_name'],
    )

    if not _index_exists('integration_settings', 'ix_integration_settings_tenant_id'):
        op.create_index(
            'ix_integration_settings_tenant_id',
            'integration_settings',
            ['tenant_id'],
        )

    # Now enforce NOT NULL
    op.alter_column('integration_settings', 'tenant_id', nullable=False)

    # ──────────────────────────────────────────────────────────────────────
    # 2. card_payments  (standalone, no parent FK → default tenant)
    # ──────────────────────────────────────────────────────────────────────
    if not _column_exists('card_payments', 'tenant_id'):
        op.add_column('card_payments', sa.Column(
            'tenant_id', sa.Integer(),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=True,
        ))
        op.execute(sa.text(
            "UPDATE card_payments SET tenant_id = :tid WHERE tenant_id IS NULL"
        )).bindparams(tid=DEFAULT_TENANT_ID)

    if not _index_exists('card_payments', 'ix_card_payments_tenant_id'):
        op.create_index(
            'ix_card_payments_tenant_id',
            'card_payments',
            ['tenant_id'],
        )
    if not _index_exists('card_payments', 'ix_card_payments_tenant_created'):
        op.create_index(
            'ix_card_payments_tenant_created',
            'card_payments',
            ['tenant_id', 'created_at'],
        )

    op.alter_column('card_payments', 'tenant_id', nullable=False)

    # ──────────────────────────────────────────────────────────────────────
    # 3. crm_team_members  (junction → inherit from crm_teams.tenant_id)
    # ──────────────────────────────────────────────────────────────────────
    if not _column_exists('crm_team_members', 'tenant_id'):
        op.add_column('crm_team_members', sa.Column(
            'tenant_id', sa.Integer(),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=True,
        ))
        # Backfill from parent CRMTeam
        op.execute(sa.text("""
            UPDATE crm_team_members ctm
            SET tenant_id = ct.tenant_id
            FROM crm_teams ct
            WHERE ctm.team_id = ct.id AND ctm.tenant_id IS NULL
        """))
        # Fallback for any orphaned rows
        op.execute(sa.text(
            "UPDATE crm_team_members SET tenant_id = :tid WHERE tenant_id IS NULL"
        )).bindparams(tid=DEFAULT_TENANT_ID)

    # Update unique constraint to include tenant_id
    if _constraint_exists('crm_team_members', 'uq_crm_team_member'):
        op.drop_constraint('uq_crm_team_member', 'crm_team_members', type_='unique')
    op.create_unique_constraint(
        'uq_crm_team_member_tenant',
        'crm_team_members',
        ['tenant_id', 'team_id', 'user_id'],
    )

    if not _index_exists('crm_team_members', 'ix_crm_team_members_tenant_id'):
        op.create_index(
            'ix_crm_team_members_tenant_id',
            'crm_team_members',
            ['tenant_id'],
        )

    op.alter_column('crm_team_members', 'tenant_id', nullable=False)

    # ──────────────────────────────────────────────────────────────────────
    # 4. payment_transactions  (child of payment_vault → inherit)
    # ──────────────────────────────────────────────────────────────────────
    if not _column_exists('payment_transactions', 'tenant_id'):
        op.add_column('payment_transactions', sa.Column(
            'tenant_id', sa.Integer(),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=True,
        ))
        # Backfill from parent PaymentVault
        op.execute(sa.text("""
            UPDATE payment_transactions pt
            SET tenant_id = pv.tenant_id
            FROM payment_vault pv
            WHERE pt.vault_id = pv.id AND pt.tenant_id IS NULL
        """))
        op.execute(sa.text(
            "UPDATE payment_transactions SET tenant_id = :tid WHERE tenant_id IS NULL"
        )).bindparams(tid=DEFAULT_TENANT_ID)

    if not _index_exists('payment_transactions', 'ix_payment_transactions_tenant_id'):
        op.create_index(
            'ix_payment_transactions_tenant_id',
            'payment_transactions',
            ['tenant_id'],
        )
    if not _index_exists('payment_transactions', 'ix_payment_transactions_tenant_created'):
        op.create_index(
            'ix_payment_transactions_tenant_created',
            'payment_transactions',
            ['tenant_id', 'created_at'],
        )

    op.alter_column('payment_transactions', 'tenant_id', nullable=False)

    # ──────────────────────────────────────────────────────────────────────
    # 5. payment_logs  (child of payment_vault → inherit)
    # ──────────────────────────────────────────────────────────────────────
    if not _column_exists('payment_logs', 'tenant_id'):
        op.add_column('payment_logs', sa.Column(
            'tenant_id', sa.Integer(),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=True,
        ))
        # Backfill from parent PaymentVault
        op.execute(sa.text("""
            UPDATE payment_logs pl
            SET tenant_id = pv.tenant_id
            FROM payment_vault pv
            WHERE pl.vault_id = pv.id AND pl.tenant_id IS NULL
        """))
        op.execute(sa.text(
            "UPDATE payment_logs SET tenant_id = :tid WHERE tenant_id IS NULL"
        )).bindparams(tid=DEFAULT_TENANT_ID)

    if not _index_exists('payment_logs', 'ix_payment_logs_tenant_id'):
        op.create_index(
            'ix_payment_logs_tenant_id',
            'payment_logs',
            ['tenant_id'],
        )
    if not _index_exists('payment_logs', 'ix_payment_logs_tenant_created'):
        op.create_index(
            'ix_payment_logs_tenant_created',
            'payment_logs',
            ['tenant_id', 'created_at'],
        )

    op.alter_column('payment_logs', 'tenant_id', nullable=False)


def downgrade():
    # Drop indexes and constraints, then drop columns (in reverse order)
    op.drop_index('ix_payment_logs_tenant_created', table_name='payment_logs')
    op.drop_index('ix_payment_logs_tenant_id', table_name='payment_logs')
    op.drop_column('payment_logs', 'tenant_id')

    op.drop_index('ix_payment_transactions_tenant_created', table_name='payment_transactions')
    op.drop_index('ix_payment_transactions_tenant_id', table_name='payment_transactions')
    op.drop_column('payment_transactions', 'tenant_id')

    op.drop_constraint('uq_crm_team_member_tenant', 'crm_team_members', type_='unique')
    op.drop_index('ix_crm_team_members_tenant_id', table_name='crm_team_members')
    op.drop_column('crm_team_members', 'tenant_id')
    op.create_unique_constraint('uq_crm_team_member', 'crm_team_members', ['team_id', 'user_id'])

    op.drop_index('ix_card_payments_tenant_created', table_name='card_payments')
    op.drop_index('ix_card_payments_tenant_id', table_name='card_payments')
    op.drop_column('card_payments', 'tenant_id')

    op.drop_constraint('uq_integration_settings_tenant_service', 'integration_settings', type_='unique')
    op.drop_index('ix_integration_settings_tenant_id', table_name='integration_settings')
    op.drop_column('integration_settings', 'tenant_id')
    op.create_unique_constraint('integration_settings_service_name_key', 'integration_settings', ['service_name'])
