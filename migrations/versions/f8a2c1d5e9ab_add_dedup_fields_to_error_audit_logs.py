"""Add dedup fields to error_audit_logs

Revision ID: f8a2c1d5e9ab
Revises: ebc4f18e3b12
Create Date: 2026-06-03 11:30:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f8a2c1d5e9ab"
down_revision = "ebc4f18e3b12"
branch_labels = None
depends_on = None


def upgrade():
    # Fingerprint
    op.add_column("error_audit_logs", sa.Column("fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_error_audit_logs_fingerprint", "error_audit_logs", ["fingerprint"])

    # Deduplication counters
    op.add_column("error_audit_logs", sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("error_audit_logs", sa.Column("first_seen_at", sa.DateTime(), nullable=True))
    op.add_column("error_audit_logs", sa.Column("last_seen_at", sa.DateTime(), nullable=True))

    # Request ID for tracing
    op.add_column("error_audit_logs", sa.Column("request_id", sa.String(length=36), nullable=True))
    op.create_index("ix_error_audit_logs_request_id", "error_audit_logs", ["request_id"])

    # Environment tracking
    op.add_column("error_audit_logs", sa.Column("environment", sa.String(length=20), nullable=True))
    op.add_column("error_audit_logs", sa.Column("app_version", sa.String(length=30), nullable=True))

    # Backfill existing rows with a generated fingerprint and timestamps
    op.execute(
        """
        UPDATE error_audit_logs
        SET fingerprint = md5(category || COALESCE(exception_type, '') || source || COALESCE(url, '')),
            first_seen_at = created_at,
            last_seen_at = created_at,
            environment = 'production'
        """
    )

    # Make fingerprint non-nullable after backfill
    op.alter_column("error_audit_logs", "fingerprint", nullable=False)
    op.alter_column("error_audit_logs", "first_seen_at", nullable=False)
    op.alter_column("error_audit_logs", "last_seen_at", nullable=False)


def downgrade():
    op.drop_column("error_audit_logs", "app_version")
    op.drop_column("error_audit_logs", "environment")
    op.drop_index("ix_error_audit_logs_request_id", table_name="error_audit_logs")
    op.drop_column("error_audit_logs", "request_id")
    op.drop_column("error_audit_logs", "last_seen_at")
    op.drop_column("error_audit_logs", "first_seen_at")
    op.drop_column("error_audit_logs", "occurrence_count")
    op.drop_index("ix_error_audit_logs_fingerprint", table_name="error_audit_logs")
    op.drop_column("error_audit_logs", "fingerprint")
