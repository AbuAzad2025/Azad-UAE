"""add explicit_account_allowed to gl_journal_lines

Revision ID: dd28ea3aa6cc
Revises: 5542ed4cd59f
Create Date: 2026-09-01

Audit D-C3: fixed-asset disposal/depreciation and record-owned concepts post
directly to their designated account (which may be a header such as 1180).
`explicit_account_allowed` records the caller's explicit grant on each GL line
so `validate_entry` can permit it without weakening the header guard for every
other posting path.
"""

import sqlalchemy as sa
from alembic import op

revision = "dd28ea3aa6cc"
down_revision = "5542ed4cd59f"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        return column in [c["name"] for c in insp.get_columns(table)]
    except Exception:
        return False


def upgrade():
    if not _column_exists("gl_journal_lines", "explicit_account_allowed"):
        with op.batch_alter_table("gl_journal_lines", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "explicit_account_allowed",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                )
            )


def downgrade():
    if _column_exists("gl_journal_lines", "explicit_account_allowed"):
        with op.batch_alter_table("gl_journal_lines", schema=None) as batch_op:
            batch_op.drop_column("explicit_account_allowed")
