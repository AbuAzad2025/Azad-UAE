"""add promotion engine phase1 (campaigns pos fields + sale promotion discount)

Revision ID: a3f7c2d91e05
Revises: 21b19821edf8
Create Date: 2026-07-23 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a3f7c2d91e05"
down_revision = "21b19821edf8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.add_column(sa.Column("applies_to_pos", sa.Boolean(), server_default=sa.false(), nullable=True))
        batch_op.add_column(sa.Column("branch_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("rule_config", sa.JSON(), nullable=True))
        batch_op.create_index(batch_op.f("ix_campaigns_applies_to_pos"), ["applies_to_pos"], unique=False)
        batch_op.create_index(batch_op.f("ix_campaigns_branch_id"), ["branch_id"], unique=False)
        batch_op.create_foreign_key(None, "branches", ["branch_id"], ["id"], ondelete="CASCADE")

    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("promotion_discount_amount", sa.Numeric(precision=15, scale=3), server_default="0", nullable=True)
        )

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_column("promotion_discount_amount")

    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.drop_constraint(None, type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_campaigns_branch_id"))
        batch_op.drop_index(batch_op.f("ix_campaigns_applies_to_pos"))
        batch_op.drop_column("rule_config")
        batch_op.drop_column("branch_id")
        batch_op.drop_column("applies_to_pos")

    # ### end Alembic commands ###
