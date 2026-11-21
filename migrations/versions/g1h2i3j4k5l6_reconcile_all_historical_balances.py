"""Reconcile every historical document against the stored sub-ledger balances.

The first repair revision (f5a6b7c8d9e0) covered maintenance movements only.
This revision walks ALL source documents - sales, payments, receipts, returns,
maintenance money movements, purchases, supplier payments and partner ledger
rows - and rebuilds the cached balances so the customer card, supplier card
and partner statement agree with their documents after an upgrade.

Revision ID: g1h2i3j4k5l6
Revises: f5a6b7c8d9e0
"""

from __future__ import annotations

import logging

from alembic import op

revision = "g1h2i3j4k5l6"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade():
    from utils.balance_reconciliation import reconcile

    report = reconcile(op.get_bind(), apply=True)
    logger.info(
        "Historical balance reconciliation: %s customers, %s suppliers, %s partners corrected",
        len(report["customers"]),
        len(report["suppliers"]),
        len(report["partners"]),
    )


def downgrade():
    """Deliberately one-way: rebuilt cached balances have no prior value to restore.

    Like ``f5a6b7c8d9e0`` before it, this revision recomputes the stored
    customer/supplier/partner balances from every source document. The old
    cached numbers were wrong by construction and were never snapshotted, so a
    downgrade could only reinstate stale, document-disagreeing values. The
    reconciliation is data-only — no schema is added or removed — so there is
    nothing structural to roll back either.
    """
    pass
