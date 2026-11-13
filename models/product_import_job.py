"""Product Import Job models for background import tracking."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON
from sqlalchemy import Enum as SQLEnum

from extensions import db


class ProductImportJobStatus(StrEnum):
    """Status of a product import job."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DRY_RUN_COMPLETE = "dry_run_complete"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class ProductImportJob(db.Model):
    """Track background product import jobs with progress and rollback support."""

    __tablename__ = "product_import_jobs"

    __table_args__ = (
        db.Index("ix_product_import_jobs_tenant_status", "tenant_id", "status"),
        db.Index("ix_product_import_jobs_tenant_created", "tenant_id", "created_at"),
        db.Index("ix_product_import_jobs_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Job identification
    job_name = db.Column(db.String(200), nullable=True)  # User-friendly name
    original_filename = db.Column(db.String(500), nullable=True)
    file_size = db.Column(db.BigInteger, nullable=True)
    file_hash = db.Column(db.String(64), nullable=True)  # SHA256 for deduplication

    # Job configuration
    status = db.Column(
        SQLEnum(ProductImportJobStatus, native_enum=False),
        default=ProductImportJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    is_dry_run = db.Column(db.Boolean, default=False, nullable=False)
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("product_import_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Progress tracking
    total_rows = db.Column(db.Integer, default=0, nullable=False)
    processed_rows = db.Column(db.Integer, default=0, nullable=False)
    success_count = db.Column(db.Integer, default=0, nullable=False)
    error_count = db.Column(db.Integer, default=0, nullable=False)

    # Timing
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    estimated_completion_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Results storage (JSON for flexibility)
    errors = db.Column(JSON, default=list, nullable=False)  # List of {row, error, data}
    warnings = db.Column(JSON, default=list, nullable=False)
    created_product_ids = db.Column(JSON, default=list, nullable=False)  # For rollback
    updated_product_ids = db.Column(JSON, default=list, nullable=False)  # For rollback
    updated_product_snapshots = db.Column(JSON, default=dict, nullable=False)  # Pre-update snapshots for rollback
    summary = db.Column(JSON, default=dict, nullable=False)  # Final summary stats

    # Rollback support
    rollback_job_id = db.Column(
        db.Integer,
        db.ForeignKey("product_import_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_rollback = db.Column(db.Boolean, default=False, nullable=False)

    # Celery task tracking
    celery_task_id = db.Column(db.String(100), nullable=True, index=True)

    # Import options
    update_existing = db.Column(db.Boolean, default=False, nullable=False)

    # Metadata
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    tenant = db.relationship("Tenant", backref="product_import_jobs")
    user = db.relationship("User", backref="product_import_jobs")
    template = db.relationship("ProductImportTemplate", backref="import_jobs")
    rollback_job = db.relationship(
        "ProductImportJob",
        remote_side=[id],
        backref="original_job",
    )

    def __repr__(self):
        return f"<ProductImportJob {self.id} {self.status} tenant={self.tenant_id}>"

    @property
    def progress_percent(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return min(100.0, (self.processed_rows / self.total_rows) * 100)

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        if self.started_at:
            return (datetime.now(UTC) - self.started_at).total_seconds()
        return None

    def to_dict(self, include_details: bool = False) -> dict:
        data = {
            "id": self.id,
            "job_name": self.job_name,
            "original_filename": self.original_filename,
            "status": self.status.value,
            "is_dry_run": self.is_dry_run,
            "template_id": self.template_id,
            "total_rows": self.total_rows,
            "processed_rows": self.processed_rows,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "progress_percent": round(self.progress_percent, 2),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "estimated_completion_at": self.estimated_completion_at.isoformat()
            if self.estimated_completion_at
            else None,
            "can_rollback": self.status == ProductImportJobStatus.COMPLETED
            and not self.is_rollback
            and self.created_product_ids,
            "celery_task_id": self.celery_task_id,
            "created_at": self.created_at.isoformat(),
        }
        if include_details:
            data.update(
                {
                    "errors": self.errors[:50],  # Limit for response size
                    "warnings": self.warnings[:50],
                    "summary": self.summary,
                }
            )
        return data


class ProductImportTemplate(db.Model):
    """Saved column mapping templates for product imports."""

    __tablename__ = "product_import_templates"

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_import_template_tenant_name"),
        db.Index("ix_import_templates_tenant_default", "tenant_id", "is_default"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    # Column mapping: {source_column: target_field}
    column_mapping = db.Column(JSON, nullable=False, default=dict)
    # Default values for missing columns
    default_values = db.Column(JSON, nullable=False, default=dict)
    # Required fields that must be present
    required_fields = db.Column(JSON, nullable=False, default=list)

    # File format hints
    expected_format = db.Column(db.String(20), default="xlsx")  # xlsx, csv
    header_row = db.Column(db.Integer, default=1)  # 1-indexed
    skip_rows = db.Column(db.Integer, default=0)

    # Usage stats
    use_count = db.Column(db.Integer, default=0, nullable=False)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    tenant = db.relationship("Tenant", backref="product_import_templates")
    user = db.relationship("User", backref="product_import_templates")

    def __repr__(self):
        return f"<ProductImportTemplate {self.id} '{self.name}' tenant={self.tenant_id}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_default": self.is_default,
            "column_mapping": self.column_mapping,
            "default_values": self.default_values,
            "required_fields": self.required_fields,
            "expected_format": self.expected_format,
            "header_row": self.header_row,
            "skip_rows": self.skip_rows,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def to_dict_list(cls, templates: list[ProductImportTemplate]) -> list[dict]:
        return [t.to_dict() for t in templates]

    def apply_to_dataframe(self, df, tenant_id: int):
        """Apply template mapping to a pandas DataFrame."""
        import pandas as pd

        df = df.copy()
        df.columns = df.columns.str.lower().str.strip()

        # Apply column mapping
        mapped_columns = {}
        for source_col, target_field in self.column_mapping.items():
            source_col_lower = source_col.lower().strip()
            if source_col_lower in df.columns:
                mapped_columns[target_field] = df[source_col_lower]

        # Create new dataframe with mapped columns
        result = pd.DataFrame(mapped_columns)

        # Apply default values for missing columns
        for field, default_val in self.default_values.items():
            if field not in result.columns:
                result[field] = default_val

        # Validate required fields
        missing = [f for f in self.required_fields if f not in result.columns or result[f].isna().all()]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        return result


class ProductImportRollbackLog(db.Model):
    """Log of rollback operations for audit trail."""

    __tablename__ = "product_import_rollback_logs"

    id = db.Column(db.Integer, primary_key=True)
    original_job_id = db.Column(
        db.Integer,
        db.ForeignKey("product_import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rollback_job_id = db.Column(
        db.Integer,
        db.ForeignKey("product_import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    rolled_back_product_ids = db.Column(JSON, nullable=False, default=list)
    rolled_back_stock_movements = db.Column(JSON, default=list)
    rolled_back_gl_entries = db.Column(JSON, default=list)

    reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    original_job = db.relationship("ProductImportJob", foreign_keys=[original_job_id])
    rollback_job = db.relationship("ProductImportJob", foreign_keys=[rollback_job_id])
    user = db.relationship("User")
