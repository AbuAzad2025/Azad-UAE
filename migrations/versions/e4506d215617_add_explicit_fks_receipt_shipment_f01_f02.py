"""add explicit FKs for receipt shipment F-01 F-02

Revision ID: e4506d215617
Revises: 24a7043cfc9c
Create Date: 2026-08-31

F-01: Receipt.sale_id explicit FK (SET NULL) with backfill from source_id where source_type in sale-like
F-02: Shipment.sale_id and purchase_return_id explicit FKs
Preserves legacy source_type/source_id columns (zero field loss).
"""

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "e4506d215617"
down_revision = "24a7043cfc9c"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False


def upgrade():
    # Receipt.sale_id
    if not _column_exists("receipts", "sale_id"):
        with op.batch_alter_table("receipts", schema=None) as batch_op:
            batch_op.add_column(sa.Column("sale_id", sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f("ix_receipts_sale_id"), ["sale_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_receipts_sale_id_sales",
                "sales",
                ["sale_id"],
                ["id"],
                ondelete="SET NULL",
            )
        # Backfill: where source_type in sale-like, copy source_id -> sale_id
        op.execute(
            sa.text(
                """
                UPDATE receipts
                SET sale_id = source_id
                WHERE sale_id IS NULL
                  AND source_type IN ('sale', 'refund', 'adjustment')
                  AND source_id IS NOT NULL
                  AND EXISTS (SELECT 1 FROM sales s WHERE s.id = receipts.source_id)
                """
            )
        )

    # Shipment explicit FKs
    if not _column_exists("shipments", "sale_id"):
        with op.batch_alter_table("shipments", schema=None) as batch_op:
            batch_op.add_column(sa.Column("sale_id", sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f("ix_shipments_sale_id"), ["sale_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_shipments_sale_id_sales",
                "sales",
                ["sale_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if not _column_exists("shipments", "purchase_return_id"):
        with op.batch_alter_table("shipments", schema=None) as batch_op:
            batch_op.add_column(sa.Column("purchase_return_id", sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f("ix_shipments_purchase_return_id"), ["purchase_return_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_shipments_purchase_return_id_purchase_returns",
                "purchase_returns",
                ["purchase_return_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # Backfill shipments
    op.execute(
        sa.text(
            """
            UPDATE shipments
            SET sale_id = source_id
            WHERE sale_id IS NULL
              AND source_type = 'sale'
              AND source_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM sales s WHERE s.id = shipments.source_id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE shipments
            SET purchase_return_id = source_id
            WHERE purchase_return_id IS NULL
              AND source_type = 'purchase_return'
              AND source_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM purchase_returns pr WHERE pr.id = shipments.source_id)
            """
        )
    )


def downgrade():
    if _column_exists("shipments", "purchase_return_id"):
        with op.batch_alter_table("shipments", schema=None) as batch_op:
            with contextlib.suppress(Exception):
                batch_op.drop_constraint("fk_shipments_purchase_return_id_purchase_returns", type_="foreignkey")
            batch_op.drop_index(batch_op.f("ix_shipments_purchase_return_id"))
            batch_op.drop_column("purchase_return_id")

    if _column_exists("shipments", "sale_id"):
        with op.batch_alter_table("shipments", schema=None) as batch_op:
            with contextlib.suppress(Exception):
                batch_op.drop_constraint("fk_shipments_sale_id_sales", type_="foreignkey")
            batch_op.drop_index(batch_op.f("ix_shipments_sale_id"))
            batch_op.drop_column("sale_id")

    if _column_exists("receipts", "sale_id"):
        with op.batch_alter_table("receipts", schema=None) as batch_op:
            with contextlib.suppress(Exception):
                batch_op.drop_constraint("fk_receipts_sale_id_sales", type_="foreignkey")
            batch_op.drop_index(batch_op.f("ix_receipts_sale_id"))
            batch_op.drop_column("sale_id")
