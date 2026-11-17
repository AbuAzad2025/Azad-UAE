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
    # Rebuilding the cached balances is a one-way repair: the pre-repair
    # values were wrong by construction and cannot be reconstructed.
    pass
