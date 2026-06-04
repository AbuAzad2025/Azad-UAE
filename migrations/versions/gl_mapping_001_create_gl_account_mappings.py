"""Phase 1E: create GL account mappings table

Revision ID: gl_mapping_001
Revises: merge_batch5_audit_heads_001
Create Date: 2026-06-04 11:15:00.000000

Additive-only migration. Creates the mapping table for dynamic GL concept
mapping and performs no seed, backfill, data update, or posting behavior change.
"""
from alembic import op
import sqlalchemy as sa


revision = 'gl_mapping_001'
down_revision = 'merge_batch5_audit_heads_001'
branch_labels = None
depends_on = None


GL_CONCEPT_CODES = (
    'AR',
    'AP',
    'CASH',
    'BANK',
    'INVENTORY_ASSET',
    'COGS',
    'COGS_REVERSAL',
    'SALES_REVENUE',
    'SALES_RETURNS',
    'SALES_DISCOUNT',
    'VAT_INPUT',
    'VAT_OUTPUT',
    'FX_GAIN',
    'FX_LOSS',
    'CHEQUES_UNDER_COLLECTION',
    'INVENTORY_ADJUSTMENT_GAIN',
    'INVENTORY_ADJUSTMENT_LOSS',
    'FREIGHT_IN',
    'CUSTOMS_DUTY',
)

GL_CONCEPT_CODE_CHECK = "concept_code IN ({})".format(
    ", ".join(f"'{code}'" for code in GL_CONCEPT_CODES)
)


def upgrade():
    op.create_table(
        'gl_account_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('concept_code', sa.String(length=50), nullable=False),
        sa.Column('gl_account_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_gl_account_mappings'),
        sa.ForeignKeyConstraint(
            ['tenant_id'],
            ['tenants.id'],
            name='fk_gl_account_mappings_tenant_id_tenants',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['gl_account_id'],
            ['gl_accounts.id'],
            name='fk_gl_account_mappings_gl_account_id_gl_accounts',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['branch_id'],
            ['branches.id'],
            name='fk_gl_account_mappings_branch_id_branches',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            GL_CONCEPT_CODE_CHECK,
            name='ck_gl_account_mappings_concept_code',
        ),
    )

    op.create_index(
        'ix_gl_account_mappings_tenant_id',
        'gl_account_mappings',
        ['tenant_id'],
        unique=False,
    )
    op.create_index(
        'ix_gl_account_mappings_concept_code',
        'gl_account_mappings',
        ['concept_code'],
        unique=False,
    )
    op.create_index(
        'ix_gl_account_mappings_gl_account_id',
        'gl_account_mappings',
        ['gl_account_id'],
        unique=False,
    )
    op.create_index(
        'ix_gl_account_mappings_branch_id',
        'gl_account_mappings',
        ['branch_id'],
        unique=False,
    )
    op.create_index(
        'ix_gl_account_mappings_tenant_concept_active',
        'gl_account_mappings',
        ['tenant_id', 'concept_code', 'is_active'],
        unique=False,
    )
    op.create_index(
        'uq_gl_account_mappings_tenant_concept_default',
        'gl_account_mappings',
        ['tenant_id', 'concept_code'],
        unique=True,
        postgresql_where=sa.text('branch_id IS NULL'),
        sqlite_where=sa.text('branch_id IS NULL'),
    )
    op.create_index(
        'uq_gl_account_mappings_tenant_concept_branch',
        'gl_account_mappings',
        ['tenant_id', 'concept_code', 'branch_id'],
        unique=True,
        postgresql_where=sa.text('branch_id IS NOT NULL'),
        sqlite_where=sa.text('branch_id IS NOT NULL'),
    )


def downgrade():
    op.drop_index(
        'uq_gl_account_mappings_tenant_concept_branch',
        table_name='gl_account_mappings',
    )
    op.drop_index(
        'uq_gl_account_mappings_tenant_concept_default',
        table_name='gl_account_mappings',
    )
    op.drop_index(
        'ix_gl_account_mappings_tenant_concept_active',
        table_name='gl_account_mappings',
    )
    op.drop_index(
        'ix_gl_account_mappings_branch_id',
        table_name='gl_account_mappings',
    )
    op.drop_index(
        'ix_gl_account_mappings_gl_account_id',
        table_name='gl_account_mappings',
    )
    op.drop_index(
        'ix_gl_account_mappings_concept_code',
        table_name='gl_account_mappings',
    )
    op.drop_index(
        'ix_gl_account_mappings_tenant_id',
        table_name='gl_account_mappings',
    )
    op.drop_table('gl_account_mappings')
