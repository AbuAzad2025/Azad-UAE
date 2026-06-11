"""Add print_history table for printing audit trail

Revision ID: print_system_001_add_print_history
Revises: 3531cbf19d9a
Create Date: 2026-06-11 23:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'print_system_001_add_print_history'
down_revision = '3531cbf19d9a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('print_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), nullable=True, index=True),
        sa.Column('document_type', sa.String(length=50), nullable=False, index=True),
        sa.Column('document_id', sa.Integer(), nullable=False, index=True),
        sa.Column('action', sa.String(length=20), nullable=False, server_default='print'),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('print_history', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_print_history_tenant', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key('fk_print_history_user', 'users', ['user_id'], ['id'])
        batch_op.create_index('ix_print_history_tenant_doc', ['tenant_id', 'document_type', 'document_id'])
        batch_op.create_index('ix_print_history_created_at', ['created_at'])


def downgrade():
    with op.batch_alter_table('print_history', schema=None) as batch_op:
        batch_op.drop_index('ix_print_history_created_at')
        batch_op.drop_index('ix_print_history_tenant_doc')
        batch_op.drop_constraint('fk_print_history_user', type_='foreignkey')
        batch_op.drop_constraint('fk_print_history_tenant', type_='foreignkey')
    op.drop_table('print_history')
