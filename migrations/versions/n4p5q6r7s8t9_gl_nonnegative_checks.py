"""Align GL check constraints with the SQLAlchemy models.

The model now declares the two non-negative entry-total constraints that the
legacy migration already installed, plus non-negative debit/credit constraints
on journal lines that existed in neither fresh ``create_all()`` databases nor
migrated ones. This revision brings both paths to the same schema.

The new service-level validator rejects negative line sides; this constraint
backs it up for raw writers and restored data.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "n4p5q6r7s8t9"
down_revision = "k1m2n3o4p5q6"
branch_labels = None
depends_on = None

CHECKS = (
    ("gl_journal_entries", "ck_gl_journal_entries_total_debit_nonneg", "total_debit >= 0"),
    ("gl_journal_entries", "ck_gl_journal_entries_total_credit_nonneg", "total_credit >= 0"),
    ("gl_journal_lines", "ck_gl_journal_lines_debit_nonneg", "debit >= 0"),
    ("gl_journal_lines", "ck_gl_journal_lines_credit_nonneg", "credit >= 0"),
)


def _existing(conn) -> set[str]:
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    return {
        check["name"]
        for table in {name for name, _, _ in CHECKS if name in tables}
        for check in inspector.get_check_constraints(table)
        if check.get("name")
    }


def upgrade() -> None:
    conn = op.get_bind()
    present = _existing(conn)
    tables = set(sa.inspect(conn).get_table_names())

    # The old code accepted negative line sides (finding P2-14). Refuse to
    # install a constraint over rows that already violate it: fail with an
    # actionable count instead of a cryptic database error, and never silently
    # skip the constraint because that would leave model/DB parity broken.
    if "gl_journal_lines" in tables:
        bad = conn.execute(sa.text("SELECT COUNT(*) FROM gl_journal_lines WHERE debit < 0 OR credit < 0")).scalar_one()
        if bad:
            raise RuntimeError(
                f"Cannot install the non-negative GL line constraints: {bad} existing "
                "gl_journal_lines row(s) have a negative debit or credit. Clean those "
                "malformed postings before deploying this migration."
            )

    for table, name, expression in CHECKS:
        if table not in tables or name in present:
            continue
        with op.batch_alter_table(table) as batch:
            batch.create_check_constraint(name, expression)


def downgrade() -> None:
    conn = op.get_bind()
    present = _existing(conn)
    tables = set(sa.inspect(conn).get_table_names())
    for table, name, _expression in CHECKS:
        if table not in tables or name not in present:
            continue
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="check")
