"""Change journal entry default status from 'posted' to 'draft'

Revision ID: fin_audit_002
Revises: fin_audit_001
Create Date: 2026-07-05

Financial security audit — changes:
- gl_journal_entries: server_default status from 'posted' to 'draft'
- New entries must be validated before posting (state machine enforcement)

This enforces the DRAFT → VALIDATED → POSTED flow for all new journal entries.
"""
from alembic import op
import sqlalchemy as sa

revision = 'fin_audit_002'
down_revision = 'fin_audit_001'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    """Check column existence using raw SQL."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :tbl AND column_name = :col"
    ), {'tbl': table, 'col': column})
    return result.fetchone() is not None


def upgrade():
    # Change server_default from 'posted' to 'draft'
    if _column_exists('gl_journal_entries', 'status'):
        # For PostgreSQL, we need to drop and recreate the default
        op.execute(sa.text("""
            ALTER TABLE gl_journal_entries
            ALTER COLUMN status SET DEFAULT 'draft'
        """))

        # Update existing draft/error entries to stay as-is
        # Keep 'posted' and 'reversed' entries as-is (they're already validated/posted)
        # This ensures backward compatibility for existing posted entries
        pass


def downgrade():
    # Revert server_default back to 'posted'
    if _column_exists('gl_journal_entries', 'status'):
        op.execute(sa.text("""
            ALTER TABLE gl_journal_entries
            ALTER COLUMN status SET DEFAULT 'posted'
        """))
