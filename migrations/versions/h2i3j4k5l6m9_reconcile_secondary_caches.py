"""Rebuild the two cached columns that had no incremental writer.

``customers.total_purchases`` (VIP classification) and ``cash_boxes.current_balance``
(treasury) were never rebuilt from their source documents. This revision extends
the full historical reconciliation to them.

Revision ID: h2i3j4k5l6m9
Revises: h2i3j4k5l6m8
Create Date: 2026-11-17 09:00:00.000000

"""

import logging

from alembic import op

revision = "h2i3j4k5l6m9"
down_revision = "h2i3j4k5l6m8"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade():
    from utils.balance_reconciliation import reconcile

    report = reconcile(op.get_bind(), apply=True)
    logger.info(
        "Secondary cache reconciliation: %s customers, %s cash boxes corrected",
        len(report["customers"]),
        len(report["cash_boxes"]),
    )


def downgrade():
    # The pre-repair values were stale by construction and cannot be restored.
    pass
