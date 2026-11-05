"""add_product_import_jobs_and_templates

Revision ID: 0c8596234965
Revises: c3d9e1f7a204
Create Date: 2026-11-05 08:24:13.596955

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0c8596234965"
down_revision = "c3d9e1f7a204"
branch_labels = None
depends_on = None


def upgrade():
    # Create product_import_templates table first (referenced by product_import_jobs)
    op.create_table(
        "product_import_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), default=False, nullable=False),
        sa.Column("column_mapping", sa.JSON(), nullable=False, default={}),
        sa.Column("default_values", sa.JSON(), nullable=False, default={}),
        sa.Column("required_fields", sa.JSON(), nullable=False, default=[]),
        sa.Column("expected_format", sa.String(20), default="xlsx"),
        sa.Column("header_row", sa.Integer(), default=1),
        sa.Column("skip_rows", sa.Integer(), default=0),
        sa.Column("use_count", sa.Integer(), default=0, nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_import_template_tenant_name"),
    )
    op.create_index("ix_import_templates_tenant_default", "product_import_templates", ["tenant_id", "is_default"])
    op.create_index("ix_import_templates_tenant_created", "product_import_templates", ["tenant_id", "created_at"])

    # Create product_import_jobs table
    op.create_table(
        "product_import_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("job_name", sa.String(200), nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(50), default="pending", nullable=False),
        sa.Column("is_dry_run", sa.Boolean(), default=False, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("total_rows", sa.Integer(), default=0, nullable=False),
        sa.Column("processed_rows", sa.Integer(), default=0, nullable=False),
        sa.Column("success_count", sa.Integer(), default=0, nullable=False),
        sa.Column("error_count", sa.Integer(), default=0, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_completion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("errors", sa.JSON(), default=[], nullable=False),
        sa.Column("warnings", sa.JSON(), default=[], nullable=False),
        sa.Column("created_product_ids", sa.JSON(), default=[], nullable=False),
        sa.Column("updated_product_ids", sa.JSON(), default=[], nullable=False),
        sa.Column("updated_product_snapshots", sa.JSON(), default={}, nullable=False),
        sa.Column("summary", sa.JSON(), default={}, nullable=False),
        sa.Column("rollback_job_id", sa.Integer(), nullable=True),
        sa.Column("is_rollback", sa.Boolean(), default=False, nullable=False),
        sa.Column("celery_task_id", sa.String(100), nullable=True),
        sa.Column("update_existing", sa.Boolean(), default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["product_import_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rollback_job_id"], ["product_import_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_import_jobs_tenant_status", "product_import_jobs", ["tenant_id", "status"])
    op.create_index("ix_product_import_jobs_tenant_created", "product_import_jobs", ["tenant_id", "created_at"])
    op.create_index("ix_product_import_jobs_user_created", "product_import_jobs", ["user_id", "created_at"])
    op.create_index("ix_product_import_jobs_celery_task_id", "product_import_jobs", ["celery_task_id"])

    # Create product_import_rollback_logs table
    op.create_table(
        "product_import_rollback_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_job_id", sa.Integer(), nullable=False),
        sa.Column("rollback_job_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("rolled_back_product_ids", sa.JSON(), nullable=False, default=[]),
        sa.Column("rolled_back_stock_movements", sa.JSON(), nullable=False, default=[]),
        sa.Column("rolled_back_gl_entries", sa.JSON(), nullable=False, default=[]),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["original_job_id"], ["product_import_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rollback_job_id"], ["product_import_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_rollback_logs_original_job", "product_import_rollback_logs", ["original_job_id"])
    op.create_index("ix_import_rollback_logs_rollback_job", "product_import_rollback_logs", ["rollback_job_id"])


def downgrade():
    op.drop_index("ix_import_rollback_logs_rollback_job", table_name="product_import_rollback_logs")
    op.drop_index("ix_import_rollback_logs_original_job", table_name="product_import_rollback_logs")
    op.drop_table("product_import_rollback_logs")

    op.drop_index("ix_product_import_jobs_celery_task_id", table_name="product_import_jobs")
    op.drop_index("ix_product_import_jobs_user_created", table_name="product_import_jobs")
    op.drop_index("ix_product_import_jobs_tenant_created", table_name="product_import_jobs")
    op.drop_index("ix_product_import_jobs_tenant_status", table_name="product_import_jobs")
    op.drop_table("product_import_jobs")

    op.drop_index("ix_import_templates_tenant_created", table_name="product_import_templates")
    op.drop_index("ix_import_templates_tenant_default", table_name="product_import_templates")
    op.drop_table("product_import_templates")
