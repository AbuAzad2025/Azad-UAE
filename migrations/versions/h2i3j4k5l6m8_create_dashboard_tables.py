"""create dashboard tables declared by models but missing from the chain

The alembic-vs-create_all parity gate found these two tables in the model
metadata with no revision creating them. Both modules were also missing from
models/__init__.py, which is why the drift hid from a normal boot.

Revision ID: h2i3j4k5l6m8
Revises: h2i3j4k5l6m7
Create Date: 2026-11-17 08:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "h2i3j4k5l6m8"
down_revision = "h2i3j4k5l6m7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboard_widgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("widget_key", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_permission", sa.String(length=50), nullable=True),
        sa.Column("data_source", sa.String(length=100), nullable=True),
        sa.Column("default_size", sa.String(length=20), nullable=True),
        sa.Column("allowed_roles", sa.String(length=255), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("widget_key"),
    )
    with op.batch_alter_table("dashboard_widgets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_dashboard_widgets_widget_key"), ["widget_key"], unique=True)

    op.create_table(
        "user_dashboard_layouts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("layout_json", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user_layout"),
    )
    with op.batch_alter_table("user_dashboard_layouts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_dashboard_layouts_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_dashboard_layouts_user_id"), ["user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("user_dashboard_layouts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_dashboard_layouts_user_id"))
        batch_op.drop_index(batch_op.f("ix_user_dashboard_layouts_tenant_id"))
    op.drop_table("user_dashboard_layouts")
    with op.batch_alter_table("dashboard_widgets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_dashboard_widgets_widget_key"))
    op.drop_table("dashboard_widgets")
