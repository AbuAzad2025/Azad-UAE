"""add_branch_to_payments_receipts_cheques

Revision ID: 9f3c1a2b7d4e
Revises: payroll_init_001
Create Date: 2026-03-13 23:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f3c1a2b7d4e'
down_revision = 'payroll_init_001'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_payments_branch_id'), ['branch_id'], unique=False)
        batch_op.create_foreign_key(None, 'branches', ['branch_id'], ['id'])

    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_receipts_branch_id'), ['branch_id'], unique=False)
        batch_op.create_foreign_key(None, 'branches', ['branch_id'], ['id'])

    with op.batch_alter_table('cheques', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_cheques_branch_id'), ['branch_id'], unique=False)
        batch_op.create_foreign_key(None, 'branches', ['branch_id'], ['id'])


def downgrade():
    with op.batch_alter_table('cheques', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_cheques_branch_id'))
        batch_op.drop_column('branch_id')

    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_receipts_branch_id'))
        batch_op.drop_column('branch_id')

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_payments_branch_id'))
        batch_op.drop_column('branch_id')
