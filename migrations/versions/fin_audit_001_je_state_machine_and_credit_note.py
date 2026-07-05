"""Add JE state machine columns + Credit Note FK

Revision ID: fin_audit_001
Revises: 9999_populate_demo_data
Create Date: 2026-07-05

Financial security audit — adds:
- gl_journal_entries: status, validation_errors, validated_at, validated_by
- product_returns: reverses_invoice_id FK

The status column uses server_default='posted' so all existing rows are
automatically set to 'posted' (backward-compatible with is_posted=True).
"""
from alembic import op
import sqlalchemy as sa

revision = 'fin_audit_001'
down_revision = '9999_populate_demo_data'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    """Check column existence using raw SQL — more reliable than
    SQLAlchemy inspect during Alembic migrations on PostgreSQL."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :tbl AND column_name = :col"
    ), {'tbl': table, 'col': column})
    return result.fetchone() is not None


def _index_exists(table, index_name):
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename = :tbl AND indexname = :idx"
    ), {'tbl': table, 'idx': index_name})
    return result.fetchone() is not None


def upgrade():
    # ── gl_journal_entries: state machine columns ──────────────────────────
    if not _column_exists('gl_journal_entries', 'status'):
        op.add_column('gl_journal_entries', sa.Column(
            'status', sa.String(20), nullable=False, server_default='posted',
        ))
    if not _index_exists('gl_journal_entries', 'ix_gl_journal_entries_status'):
        op.create_index(
            'ix_gl_journal_entries_status', 'gl_journal_entries', ['status'],
            unique=False,
        )

    if not _column_exists('gl_journal_entries', 'validation_errors'):
        op.add_column('gl_journal_entries', sa.Column(
            'validation_errors', sa.Text(), nullable=True,
        ))

    if not _column_exists('gl_journal_entries', 'validated_at'):
        op.add_column('gl_journal_entries', sa.Column(
            'validated_at', sa.DateTime(), nullable=True,
        ))

    if not _column_exists('gl_journal_entries', 'validated_by'):
        op.add_column('gl_journal_entries', sa.Column(
            'validated_by', sa.Integer(), nullable=True,
        ))
        op.create_foreign_key(
            'fk_gl_journal_entries_validated_by',
            'gl_journal_entries', 'users',
            ['validated_by'], ['id'],
        )
        op.create_index(
            'ix_gl_journal_entries_validated_by',
            'gl_journal_entries', ['validated_by'], unique=False,
        )

    # Backfill: set status based on existing is_posted/is_reversed columns.
    # Use CAST to handle both PostgreSQL (boolean) and SQLite (integer).
    op.execute(sa.text("""
        UPDATE gl_journal_entries
        SET status = CASE
            WHEN CAST(is_reversed AS INTEGER) = 1 THEN 'reversed'
            WHEN CAST(is_posted AS INTEGER) = 1  THEN 'posted'
            ELSE 'draft'
        END
        WHERE status = 'posted'
    """))

    # ── product_returns: reverses_invoice_id FK ────────────────────────────
    if not _column_exists('product_returns', 'reverses_invoice_id'):
        op.add_column('product_returns', sa.Column(
            'reverses_invoice_id', sa.Integer(), nullable=True,
        ))
        op.create_foreign_key(
            'fk_product_returns_reverses_invoice',
            'product_returns', 'sales',
            ['reverses_invoice_id'], ['id'],
        )
        op.create_index(
            'ix_product_returns_reverses_invoice_id',
            'product_returns', ['reverses_invoice_id'], unique=False,
        )


def downgrade():
    # ── product_returns: drop reverses_invoice_id ──────────────────────────
    if _column_exists('product_returns', 'reverses_invoice_id'):
        op.drop_index('ix_product_returns_reverses_invoice_id', table_name='product_returns')
        op.drop_constraint('fk_product_returns_reverses_invoice', 'product_returns', type_='foreignkey')
        op.drop_column('product_returns', 'reverses_invoice_id')

    # ── gl_journal_entries: drop state machine columns ─────────────────────
    if _column_exists('gl_journal_entries', 'validated_by'):
        op.drop_index('ix_gl_journal_entries_validated_by', table_name='gl_journal_entries')
        op.drop_constraint('fk_gl_journal_entries_validated_by', 'gl_journal_entries', type_='foreignkey')
        op.drop_column('gl_journal_entries', 'validated_by')

    if _column_exists('gl_journal_entries', 'validated_at'):
        op.drop_column('gl_journal_entries', 'validated_at')

    if _column_exists('gl_journal_entries', 'validation_errors'):
        op.drop_column('gl_journal_entries', 'validation_errors')

    if _column_exists('gl_journal_entries', 'status'):
        op.drop_index('ix_gl_journal_entries_status', table_name='gl_journal_entries')
        op.drop_column('gl_journal_entries', 'status')
