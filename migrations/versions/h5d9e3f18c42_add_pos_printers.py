"""add pos_printers (role-based ticket routing)

POS hardware wave — per-tenant printer registry for split printing:
customer receipts, kitchen tickets, and warehouse pick slips, each with
its own connection (agent network/serial, or direct browser webusb/
webserial) and an optional category filter for line routing.

Additive only; no existing table is altered.

Revision ID: h5d9e3f18c42
Revises: g8c4b2d91e10
Create Date: 2026-07-25 14:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "h5d9e3f18c42"
down_revision = "g8c4b2d91e10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pos_printers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="customer"),
        sa.Column("connection_type", sa.String(length=20), nullable=False, server_default="agent_network"),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("serial_port", sa.String(length=40), nullable=True),
        sa.Column("baud_rate", sa.Integer(), nullable=True),
        sa.Column("encoding", sa.String(length=20), nullable=False, server_default="cp864"),
        sa.Column("category_ids", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_pos_printers_tenant_id", "pos_printers", ["tenant_id"])
    op.create_index("ix_pos_printers_branch_id", "pos_printers", ["branch_id"])


def downgrade():
    op.drop_index("ix_pos_printers_branch_id", table_name="pos_printers")
    op.drop_index("ix_pos_printers_tenant_id", table_name="pos_printers")
    op.drop_table("pos_printers")
