"""engine(phase1): CHECK constraints - unsigned money and prices cannot be negative.

A negative *price* or *amount owed* is never a legitimate row: it is a bug, a bad
import or a mis-keyed decimal. The database is the right place to refuse it, because
an application-level check is bypassed by every bulk path.

What this revision deliberately does NOT constrain
--------------------------------------------------
A first draft swept information_schema for money-ish column names and constrained 85
of them. The suite then failed in 58 places, and every failure was the database being
*correct*:

* ``gl_journal_lines.amount`` / ``amount_aed`` - the model computes
  ``amount = original_debit - original_credit``, so a credit line is legitimately
  negative. Constraining it rejected valid postings.
* ``stock_movements.quantity`` and ``product_warehouse_costs.total_quantity`` - a
  movement is signed by its movement_type; a sale stores a negative quantity.
* ``product_cost_history.old/new_total_quantity`` - a running balance that goes
  negative when a weighted average cost is retrospectively recomputed downward.
* ``bank_statement_lines.amount`` - a bank debit is negative against our books.
* balances, variances, discounts, rates - negative by definition in some states.

So the list below is money that is unsigned by business rule: what a customer paid,
what an invoice totals, what a line is priced at. It was reviewed by hand rather
than pattern-matched, and every entry here is a quantity a user typed as a positive
number.

Locking behaviour - the reason this is written the way it is:

* ``ADD CONSTRAINT ... CHECK (...) NOT VALID`` takes only SHARE UPDATE EXCLUSIVE and
  **does not scan the table**, so it returns instantly on a live ledger.
* ``VALIDATE CONSTRAINT`` then scans under the same lock, which still permits
  concurrent reads and writes, so a deployment never blocks trading.
* the scan runs per table with a commit between tables rather than one long
  transaction holding the lock across the whole ledger.

Both statements are idempotent (guarded through pg_constraint), and a table whose
existing rows violate the rule is left NOT VALID and reported rather than failing the
deployment: PostgreSQL still enforces the rule on every new and updated row, and
VALIDATE is retried once the legacy rows are cleaned up.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "a1b2c3d4"
branch_labels = None
depends_on = None

# (table, column) pairs owned by this revision - reviewed, not swept.
CHECKS: tuple[tuple[str, str], ...] = (
    ("card_payments", "amount"),
    ("cash_boxes", "current_balance"),
    ("cheques", "amount"),
    ("cheques", "amount_aed"),
    ("cheques", "actual_amount_aed"),
    ("donations", "amount_usd"),
    ("donations", "amount_crypto"),
    ("expenses", "amount"),
    ("expenses", "amount_aed"),
    ("fixed_assets", "purchase_price"),
    ("fixed_assets", "disposal_price"),
    ("fixed_assets", "salvage_value"),
    ("fixed_assets", "accumulated_depreciation"),
    ("gl_journal_entries", "total_debit"),
    ("gl_journal_entries", "total_credit"),
    ("payment_vault", "min_donation_amount"),
    ("payment_vault", "max_donation_amount"),
    ("payments", "amount"),
    ("payments", "amount_aed"),
    ("pos_cash_movements", "amount"),
    ("pos_sessions", "total_sales"),
    ("pos_sessions", "total_cash_sales"),
    ("pos_sessions", "total_card_sales"),
    ("pos_sessions", "total_pay_ins"),
    ("pos_sessions", "total_pay_outs"),
    ("product_returns", "total_amount"),
    ("products", "cost_price"),
    ("products", "regular_price"),
    ("products", "merchant_price"),
    ("products", "partner_price"),
    ("purchase_orders", "total_amount"),
    ("purchases", "total_amount"),
    ("receipts", "amount"),
    ("receipts", "amount_aed"),
    ("sales", "total_amount"),
    ("sales", "subtotal"),
    ("sales", "paid_amount"),
    ("sales", "paid_amount_aed"),
    ("sales", "tax_amount"),
    ("sales", "taxable_amount"),
)


def _constraint_name(table: str, column: str) -> str:
    return f"ck_{table}_{column}_nonneg"


def _existing(conn) -> set[str]:
    return {r[0] for r in conn.execute(sa.text("SELECT conname FROM pg_constraint WHERE contype = 'c'"))}


def _columns_present(conn, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def _violations(conn, table: str, column: str) -> int:
    return int(conn.execute(sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" < 0')).scalar() or 0)


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing(bind)
    # 1. Attach without scanning: brief lock, no table scan.
    for table, column in CHECKS:
        if not _columns_present(bind, table, column):
            continue
        name = _constraint_name(table, column)
        if name in existing:
            continue
        op.execute(f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" CHECK ("{column}" >= 0) NOT VALID')

    # 2. Validate per table, committing between tables so no single transaction
    #    holds the scan lock across the ledger.
    for table in sorted({t for t, _ in CHECKS}):
        op.execute(sa.text("COMMIT"))
        for column in sorted(c for t, c in CHECKS if t == table):
            name = _constraint_name(table, column)
            if name not in _existing(bind):
                continue
            bad = _violations(bind, table, column)
            if bad:
                op.get_context().impl.warn(f"{name} left NOT VALID: {bad} existing row(s) have {column} < 0")
                continue
            op.execute(f'ALTER TABLE "{table}" VALIDATE CONSTRAINT "{name}"')


def downgrade() -> None:
    bind = op.get_bind()
    existing = _existing(bind)
    for table, column in CHECKS:
        name = _constraint_name(table, column)
        if name in existing and _columns_present(bind, table, column):
            op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"')
