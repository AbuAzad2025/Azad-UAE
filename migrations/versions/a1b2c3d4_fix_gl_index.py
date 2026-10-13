"""Fix gl_journal_entries index strategy: replace simple status index with composite.

The simple (tenant_id, status) index cannot serve ORDER BY entry_date DESC queries,
causing the planner to pick it and add an explicit Sort. This migration replaces it
with a composite (tenant_id, status, entry_date DESC) that serves both status
filtering AND date ordering in a single index scan.

Also ensures the existing (tenant_id, entry_date) index is present for pure
date-ordered queries without status filter.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4"
down_revision = "a3d7f1b9c6e2"
branch_labels = None
depends_on = None


def _index_exists(conn, name: str) -> bool:
    row = op.get_bind().execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
        {"n": name},
    ).scalar()
    return bool(row)


def _table_has_column(conn, table: str, column: str) -> bool:
    row = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
        ),
        {"t": "gl_journal_entries", "c": column},
    ).scalar()
    return bool(row)


def upgrade() -> None:
    # 1) Drop the simple (tenant_id, status) index that cannot serve ORDER BY
    if _index_exists(op.get_bind(), "ix_gl_journal_entries_tenant_status"):
        with op.get_context().autocommit_block():
            op.execute('DROP INDEX CONCURRENTLY IF EXISTS "ix_gl_journal_entries_tenant_status"')

    # 2) Create composite index: (tenant_id, status, entry_date DESC)
    # Serves: WHERE tenant_id=? AND status=? ORDER BY entry_date DESC
    # Also serves: WHERE tenant_id=? AND status=? (equality filter)
    # Can also serve: WHERE tenant_id=? ORDER BY entry_date DESC (with status filter)
    if not _index_exists(op.get_bind(), "ix_gl_journal_entries_tenant_status_entry_date_desc"):
        # Verify columns exist
        conn = op.get_bind()
        if _table_has_column(conn, "gl_journal_entries", "status") and \
           _table_has_column(conn, "gl_journal_entries", "entry_date"):
            with op.get_context().autocommit_block():
                op.execute('''
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS
                    "ix_gl_journal_entries_tenant_status_entry_date_desc"
                    ON "gl_journal_entries" ("tenant_id", "status", "entry_date" DESC)
                ''')

    # 3) Ensure (tenant_id, entry_date) exists for pure date ordering (already exists as idx_gl_entries_tenant_date)
    # Verify it exists
    if not _index_exists(op.get_bind(), "idx_gl_entries_tenant_date"):
        with op.get_context().autocommit_block():
            op.execute('''
                CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_gl_entries_tenant_date"
                ON "gl_journal_entries" ("tenant_id", "entry_date" DESC)
            ''')

    # 3b) The existing (tenant_id, entry_date, status) index is kept as it serves
    # queries that filter by date range then status. It's not harmful.

    # 4) Run ANALYZE to update planner statistics
    with op.get_context().autocommit_block():
        op.execute("ANALYZE gl_journal_entries")


def downgrade() -> None:
    # Restore the simple (tenant_id, status) index
    if not _index_exists(op.get_bind(), "ix_gl_journal_entries_tenant_status"):
        with op.get_context().autocommit_block():
            op.execute('''
                CREATE INDEX CONCURRENTLY IF NOT EXISTS "ix_gl_journal_entries_tenant_status"
                ON "gl_journal_entries" ("tenant_id", "status")
            ''')

    # Drop the composite index
    if _index_exists(op.get_bind(), "ix_gl_journal_entries_tenant_status_entry_date_desc"):
        with op.get_context().autocommit_block():
            op.execute('DROP INDEX CONCURRENTLY IF EXISTS "ix_gl_journal_entries_tenant_status_entry_date_desc"')

    # Run ANALYZE
    with op.get_context().autocommit_block():
        op.execute("ANALYZE gl_journal_entries")


# ─── helpers (defined at module level for both upgrade/downgrade) ───

import sqlalchemy as sa
from alembic import op

def _index_exists(conn, name: str) -> bool:
    row = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
        {"n": name},
    ).scalar()
    return bool(row)


def _table_has_column(conn, table: str, column: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
        ),
        {"t": "gl_journal_entries", "c": column},
    ).scalar()
    return bool(row)