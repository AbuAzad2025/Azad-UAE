"""Add amount column to gl_journal_lines for original currency tracking

Revision ID: currency_audit_001
Revises: gl_mapping_002
Create Date: 2026-06-05

Adds 'amount' (Numeric) to GLJournalLine to store the original-currency
net amount (debit - credit) before AED conversion. Existing rows are
backfilled from amount_aed since all historical data was posted in AED.
"""
from alembic import op
import sqlalchemy as sa


revision = 'currency_audit_001'
down_revision = 'gl_mapping_002'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gl_journal_lines', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('amount', sa.Numeric(precision=18, scale=3), nullable=True)
        )
    # Backfill: all existing historical data was in AED, so amount == amount_aed
    op.execute("UPDATE gl_journal_lines SET amount = amount_aed WHERE amount IS NULL")


def downgrade():
    with op.batch_alter_table('gl_journal_lines', schema=None) as batch_op:
        batch_op.drop_column('amount')
