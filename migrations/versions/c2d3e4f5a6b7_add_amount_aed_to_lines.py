"""add amount_aed to sale, purchase and quotation lines

Adds an ``amount_aed`` column (Numeric 15,3) to ``sale_lines``,
``purchase_lines`` and ``quotation_lines`` so that the line-level base
currency amount is stored for direct reporting and audit, instead of
being recomputed from the parent document's exchange rate at query time.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "z3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("sale_lines", "purchase_lines", "quotation_lines"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "amount_aed",
                    sa.Numeric(precision=15, scale=3),
                    nullable=False,
                    server_default="0",
                )
            )


def downgrade():
    for table in ("sale_lines", "purchase_lines", "quotation_lines"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("amount_aed")
