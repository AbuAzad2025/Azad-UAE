"""Add composite indexes for GL balance queries

Revision ID: perf_gl_balance_001
Revises: fin_audit_002
Create Date: 2026-07-07

Performance optimization — eliminates N+1 query patterns by supporting
the single-aggregate query used by GLService.get_all_account_balances()
and GLAccount.get_balance().

Indexes added:
  - ix_gl_journal_lines_tenant_account  (tenant_id, account_id)
  - ix_gl_journal_entries_tenant_status_date  (tenant_id, status, entry_date)
"""
from alembic import op
import sqlalchemy as sa

revision = 'perf_gl_balance_001'
down_revision = 'fin_audit_002'
branch_labels = None
depends_on = None


def _index_exists(table_name, index_name):
    """Check if an index exists using raw SQL."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename = :tbl AND indexname = :idx"
    ), {'tbl': table_name, 'idx': index_name})
    return result.fetchone() is not None


def upgrade():
    # Composite index for GL balance aggregation on gl_journal_lines
    # Supports: WHERE tenant_id = X AND account_id = Y GROUP BY account_id
    if not _index_exists('gl_journal_lines', 'ix_gl_journal_lines_tenant_account'):
        op.create_index(
            'ix_gl_journal_lines_tenant_account',
            'gl_journal_lines',
            ['tenant_id', 'account_id'],
            unique=False,
        )

    # Composite index for GL journal entries used by balance/date-range queries
    # Supports: WHERE tenant_id = X AND status = 'posted' AND entry_date BETWEEN ...
    if not _index_exists('gl_journal_entries', 'ix_gl_journal_entries_tenant_status_date'):
        op.create_index(
            'ix_gl_journal_entries_tenant_status_date',
            'gl_journal_entries',
            ['tenant_id', 'status', 'entry_date'],
            unique=False,
        )


def downgrade():
    if _index_exists('gl_journal_lines', 'ix_gl_journal_lines_tenant_account'):
        op.drop_index('ix_gl_journal_lines_tenant_account', table_name='gl_journal_lines')

    if _index_exists('gl_journal_entries', 'ix_gl_journal_entries_tenant_status_date'):
        op.drop_index('ix_gl_journal_entries_tenant_status_date', table_name='gl_journal_entries')
