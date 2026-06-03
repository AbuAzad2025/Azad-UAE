"""Create error_audit_logs table

Revision ID: ebc4f18e3b12
Revises: fcdac89 (HEAD ~ 1)
Create Date: 2026-06-03 11:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "ebc4f18e3b12"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "error_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("exception_type", sa.String(length=200), nullable=True),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("request_data", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_error_audit_logs_category", "error_audit_logs", ["category"])
    op.create_index("ix_error_audit_logs_created_at", "error_audit_logs", ["created_at"])
    op.create_index("ix_error_audit_logs_is_resolved", "error_audit_logs", ["is_resolved"])
    op.create_index("ix_error_audit_logs_level", "error_audit_logs", ["level"])
    op.create_index("ix_error_audit_logs_source", "error_audit_logs", ["source"])
    op.create_index("ix_error_audit_logs_tenant_id", "error_audit_logs", ["tenant_id"])
    op.create_index("ix_error_audit_logs_user_id", "error_audit_logs", ["user_id"])


def downgrade():
    op.drop_table("error_audit_logs")
