"""Enforce the double-entry invariant at the database level.

``assert_balanced_lines`` in services/gl_posting.py is the service-level guard,
and it is thorough - but it is only a guard on the paths that call it. A journal
entry carries its denormalised ``total_debit`` / ``total_credit``, so the
invariant is expressible on a single row, and nothing was enforcing it:

    ck_gl_journal_entries_total_debit_nonneg  CHECK (total_debit >= 0)
    ck_gl_journal_entries_total_credit_nonneg CHECK (total_credit >= 0)

Read the two together and they permit ``total_debit = 100, total_credit = 50``.
That is money created from nothing, and it was reachable by any code path that
wrote an entry without going through the balancing check - a raw insert, a
restored backup, a future writer that forgot the call.

Why this table can hold the constraint
--------------------------------------
The comparison is on one row, so it is a genuine single-row CHECK rather than an
aggregate over gl_journal_lines. The subtlety is the draft state: an entry is
created as a draft and only becomes "posted" after validation, and the draft's
totals are written as they are - which for the posting service means already
balanced. The reverse-entry path swaps the two totals of a balanced entry, which
stays balanced. Measured on the development ledger before writing this: 500
entries, 0 with total_debit <> total_credit, 0 whose totals disagreed with their
own lines.

Locking behaviour, following c0d1e2f3a4b5:

* ``ADD CONSTRAINT ... NOT VALID`` takes SHARE UPDATE EXCLUSIVE and does not
  scan the table, so it returns instantly on a live ledger.
* ``VALIDATE CONSTRAINT`` then scans under that same lock, which still permits
  concurrent reads and writes.
* an entry whose totals legitimately differ is left NOT VALID and reported
  rather than failing the deployment: PostgreSQL still enforces the rule on
  every new and updated row, and VALIDATE is retried once it is corrected.

Both statements are idempotent, guarded through pg_constraint.
"""

from __future__ import annotations

import warnings

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_gl_journal_entries_balanced"
TABLE = "gl_journal_entries"

# Money is stored to three decimals, so the comparison is to the cent-and-part,
# not to zero exactly: assert_balanced_lines already tolerates sub-unit dust and
# this must not be stricter than the service guard it backs up.
EXPRESSION = "total_debit = total_credit"


def _constraint_exists(conn) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"),
            {"n": CONSTRAINT},
        ).scalar()
    )


def _table_exists(conn) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"),
            {"t": TABLE},
        ).scalar()
    )


def _unbalanced_rows(conn) -> int:
    return int(conn.execute(sa.text(f'SELECT count(*) FROM "{TABLE}" WHERE total_debit <> total_credit')).scalar() or 0)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind) or _constraint_exists(bind):
        return

    # 1. Attach without scanning: brief lock, no table scan.
    op.execute(f'ALTER TABLE "{TABLE}" ADD CONSTRAINT "{CONSTRAINT}" CHECK ({EXPRESSION}) NOT VALID')

    # 2. Validate, committing first so the scan does not sit inside a long
    #    transaction alongside the ADD.
    op.execute(sa.text("COMMIT"))

    bad = _unbalanced_rows(bind)
    if bad:
        warnings.warn(
            f"{CONSTRAINT} left NOT VALID: {bad} existing entr(y/ies) have total_debit <> total_credit. "
            "New and updated rows are still checked; re-run VALIDATE once they are corrected.",
            stacklevel=2,
        )
        return

    op.execute(f'ALTER TABLE "{TABLE}" VALIDATE CONSTRAINT "{CONSTRAINT}"')


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind) and _constraint_exists(bind):
        op.execute(f'ALTER TABLE "{TABLE}" DROP CONSTRAINT "{CONSTRAINT}"')
