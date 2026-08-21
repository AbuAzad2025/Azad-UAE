"""add purchase po_id grn_id linkage

Revision ID: 9de30f6466b3
Revises: 552bcde29049
Create Date: 2026-08-21 22:00:37.522650

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9de30f6466b3"
down_revision = "552bcde29049"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.add_column(sa.Column("po_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("grn_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_purchases_po_id"), ["po_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_purchases_grn_id"), ["grn_id"], unique=False)
        batch_op.create_foreign_key("fk_purchases_po_id", "purchase_orders", ["po_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_purchases_grn_id", "goods_receipts", ["grn_id"], ["id"], ondelete="SET NULL")


def downgrade():
    with op.batch_alter_table("purchases", schema=None) as batch_op:
        batch_op.drop_constraint("fk_purchases_grn_id", type_="foreignkey")
        batch_op.drop_constraint("fk_purchases_po_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_purchases_grn_id"))
        batch_op.drop_index(batch_op.f("ix_purchases_po_id"))
        batch_op.drop_column("grn_id")
        batch_op.drop_column("po_id")
