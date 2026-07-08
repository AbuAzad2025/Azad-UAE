"""Create document_snapshots table for immutable document snapshots

Revision ID: doc_snapshot_001_create_document_snapshots
Revises: tenant_scope_004
Create Date: 2026-07-08 21:56:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'doc_snapshot_001'
down_revision = 'tenant_scope_004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'document_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False, index=True),
        sa.Column('document_type', sa.String(length=50), nullable=False, index=True),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_data', sa.JSON(), nullable=False),
        sa.Column('branding_snapshot', sa.JSON(), nullable=True),
        sa.Column('snapshot_reason', sa.String(length=20), nullable=False, server_default='print'),
        sa.Column('created_at', sa.DateTime(), nullable=False, index=True,
                  server_default=sa.func.now()),
        sa.Column('created_by', sa.Integer(), nullable=True, index=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('document_snapshots', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_document_snapshots_tenant', 'tenants', ['tenant_id'], ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_foreign_key(
            'fk_document_snapshots_user', 'users', ['created_by'], ['id'],
        )
        batch_op.create_index(
            'ix_doc_snapshots_tenant_doc_type',
            ['tenant_id', 'document_type', 'document_id'],
        )


def downgrade():
    with op.batch_alter_table('document_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_doc_snapshots_tenant_doc_type')
        batch_op.drop_constraint('fk_document_snapshots_user', type_='foreignkey')
        batch_op.drop_constraint('fk_document_snapshots_tenant', type_='foreignkey')
    op.drop_table('document_snapshots')
