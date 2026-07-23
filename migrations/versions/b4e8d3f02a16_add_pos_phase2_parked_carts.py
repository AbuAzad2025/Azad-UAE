"""add pos phase2 parked carts (pos_carts table)

Revision ID: b4e8d3f02a16
Revises: a3f7c2d91e05
Create Date: 2026-07-24 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b4e8d3f02a16"
down_revision = "a3f7c2d91e05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pos_carts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("total_estimate", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("parked_at", sa.DateTime(), nullable=False),
        sa.Column("resumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["pos_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pos_carts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pos_carts_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_carts_session_id"), ["session_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_carts_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pos_carts_status"), ["status"], unique=False)
        batch_op.create_index(
            "idx_pos_cart_user_session_status",
            ["user_id", "session_id", "status"],
            unique=False,
        )
        batch_op.create_index("idx_pos_cart_tenant_status", ["tenant_id", "status"], unique=False)


def downgrade():
    with op.batch_alter_table("pos_carts", schema=None) as batch_op:
        batch_op.drop_index("idx_pos_cart_tenant_status")
        batch_op.drop_index("idx_pos_cart_user_session_status")
        batch_op.drop_index(batch_op.f("ix_pos_carts_status"))
        batch_op.drop_index(batch_op.f("ix_pos_carts_user_id"))
        batch_op.drop_index(batch_op.f("ix_pos_carts_session_id"))
        batch_op.drop_index(batch_op.f("ix_pos_carts_tenant_id"))
    op.drop_table("pos_carts")
