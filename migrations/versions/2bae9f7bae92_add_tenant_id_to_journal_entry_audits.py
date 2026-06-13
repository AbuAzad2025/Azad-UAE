"""add tenant_id to journal_entry_audits

Revision ID: 2bae9f7bae92
Revises: add_missing_customers_country_001
Create Date: 2026-06-13 21:48:45.915869

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2bae9f7bae92'
down_revision = 'add_missing_customers_country_001'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('journal_entry_audits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_journal_entry_audits_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(None, 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')


def downgrade():
    with op.batch_alter_table('journal_entry_audits', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_journal_entry_audits_tenant_id'))
        batch_op.drop_column('tenant_id')
