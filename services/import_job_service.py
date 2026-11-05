"""Product Import Job Service - Background import processing with progress tracking."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from extensions import db
from models import (
    Product,
    ProductImportJob,
    ProductImportJobStatus,
    ProductImportTemplate,
)
from services.product_service import ProductService
from services.stock_service import StockService
from utils.helpers import generate_sku

logger = logging.getLogger(__name__)


class ImportJobService:
    """Service for managing product import background jobs."""

    # Progress update interval (rows)
    PROGRESS_UPDATE_INTERVAL = 10

    @staticmethod
    def create_job(
        tenant_id: int,
        user_id: int | None,
        file_content: bytes,
        filename: str,
        job_name: str | None = None,
        template_id: int | None = None,
        is_dry_run: bool = False,
    ) -> ProductImportJob:
        """Create a new import job record."""
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Check for duplicate file
        existing = ProductImportJob.query.filter_by(
            tenant_id=tenant_id,
            file_hash=file_hash,
            status=ProductImportJobStatus.COMPLETED,
        ).first()
        if existing:
            logger.info(f"Duplicate file detected, returning existing job {existing.id}")
            return existing

        job = ProductImportJob(
            tenant_id=tenant_id,
            user_id=user_id,
            job_name=job_name or f"Import {filename}",
            original_filename=filename,
            file_size=len(file_content),
            file_hash=file_hash,
            is_dry_run=is_dry_run,
            template_id=template_id,
            status=ProductImportJobStatus.PENDING,
        )
        db.session.add(job)
        db.session.flush()
        return job

    @staticmethod
    def start_job(job_id: int) -> ProductImportJob:
        """Mark job as running."""
        job = ProductImportJob.query.get_or_404(job_id)
        job.status = ProductImportJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        db.session.flush()
        return job

    @staticmethod
    def update_progress(
        job_id: int,
        processed: int,
        success: int,
        errors: int,
        estimated_completion: datetime | None = None,
    ) -> ProductImportJob:
        """Update job progress."""
        job = ProductImportJob.query.get_or_404(job_id)
        job.processed_rows = processed
        job.success_count = success
        job.error_count = errors
        if estimated_completion:
            job.estimated_completion_at = estimated_completion
        db.session.flush()
        return job

    @staticmethod
    def complete_job(
        job_id: int,
        success_count: int,
        error_count: int,
        created_ids: list[int],
        updated_ids: list[int],
        errors: list[dict],
        warnings: list[dict],
        summary: dict,
    ) -> ProductImportJob:
        """Mark job as completed."""
        job = ProductImportJob.query.get_or_404(job_id)
        job.status = (
            ProductImportJobStatus.COMPLETED_WITH_ERRORS if error_count > 0 else ProductImportJobStatus.COMPLETED
        )
        job.completed_at = datetime.now(UTC)
        job.success_count = success_count
        job.error_count = error_count
        job.created_product_ids = created_ids
        job.updated_product_ids = updated_ids
        job.errors = errors
        job.warnings = warnings
        job.summary = {
            "total_products_created": len(created_ids),
            "total_products_updated": len(updated_ids),
            "total_errors": error_count,
            "total_warnings": len(warnings),
            "duration_seconds": ((datetime.now(UTC) - job.started_at).total_seconds() if job.started_at else None),
        }
        db.session.flush()
        return job

    @staticmethod
    def fail_job(job_id: int, error: str) -> ProductImportJob:
        """Mark job as failed."""
        job = ProductImportJob.query.get_or_404(job_id)
        job.status = ProductImportJobStatus.FAILED
        job.completed_at = datetime.now(UTC)
        job.errors = [{"error": error, "timestamp": datetime.now(UTC).isoformat()}]
        db.session.flush()
        return job

    @staticmethod
    def create_rollback_job(
        original_job_id: int,
        user_id: int | None,
        reason: str | None = None,
    ) -> ProductImportJob:
        """Create a rollback job for a completed import."""
        original = ProductImportJob.query.get_or_404(original_job_id)

        if original.status not in (
            ProductImportJobStatus.COMPLETED,
            ProductImportJobStatus.COMPLETED_WITH_ERRORS,
        ):
            raise ValueError("Can only rollback completed jobs")

        rollback_job = ProductImportJob(
            tenant_id=original.tenant_id,
            user_id=original.user_id,
            job_name=f"Rollback of {original.job_name}",
            original_filename=original.original_filename,
            status=ProductImportJobStatus.PENDING,
            is_rollback=True,
            rollback_job_id=original.id,
        )
        db.session.add(rollback_job)
        db.session.flush()

        # Log the rollback
        from models.product_import_job import ProductImportRollbackLog

        log = ProductImportRollbackLog(
            original_job_id=original.id,
            rollback_job_id=rollback_job.id,
            user_id=original.user_id,
            reason=reason or "Manual rollback",
        )
        db.session.add(log)

        db.session.flush()
        return rollback_job


class ProductImportService:
    """Core product import logic with dry-run, templates, and background support."""

    # Column mappings (English -> internal field)
    DEFAULT_COLUMN_MAP = {
        "name": "name",
        "name_ar": "name_ar",
        "price": "regular_price",
        "price": "regular_price",
        "cost": "cost_price",
        "cost_price": "cost_price",
        "stock": "current_stock",
        "quantity": "current_stock",
        "sku": "sku",
        "barcode": "barcode",
        "description": "description",
        "category": "category",
        "warranty": "warranty_days",
        "warranty_days": "warranty_days",
        "part_number": "part_number",
        "unit": "unit",
        "min_stock": "min_stock_alert",
        "location": "location",
        "country": "country_of_origin",
        "weight": "weight",
        "volume": "volume",
    }

    REQUIRED_FIELDS = ["name", "regular_price"]

    def __init__(self, tenant_id: int, user_id: int | None = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.warehouse = ProductService.get_default_warehouse(tenant_id)
        self._template: ProductImportTemplate | None = None

    def set_template(self, template: ProductImportTemplate):
        """Apply a saved template."""
        self._template = template

    def _resolve_column_map(self) -> dict[str, str]:
        """Get effective column mapping."""
        if self._template and self._template.column_mapping:
            return self._template.column_mapping
        return self.DEFAULT_COLUMN_MAP

    def _get_required_fields(self) -> list[str]:
        if self._template and self._template.required_fields:
            return self._template.required_fields
        return self.REQUIRED_FIELDS

    def _get_default_values(self) -> dict:
        if self._template and self._template.default_values:
            return self._template.default_values
        return {}

    def _read_dataframe(self, file_content: bytes, filename: str) -> pd.DataFrame:
        """Read file into DataFrame with proper encoding handling."""
        import io

        ext = filename.lower().split(".")[-1]
        file_io = io.BytesIO(file_content)

        if filename.lower().endswith(".csv"):
            # Try multiple encodings
            for encoding in ["utf-8", "utf-8-sig", "cp1256", "iso-8859-6", "windows-1256"]:
                try:
                    file_io.seek(0)
                    return pd.read_csv(file_io, encoding=encoding)
                except UnicodeDecodeError:
                    continue
            # Last resort
            file_io.seek(0)
            return pd.read_csv(file_io, encoding="utf-8", on_bad_lines="skip")
        else:
            file_io.seek(0)
            return pd.read_excel(file_io, engine="openpyxl")

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names and apply template mapping."""
        df = df.copy()
        df.columns = df.columns.str.lower().str.strip()

        column_map = self._resolve_column_map()
        renamed = {}
        for src, target in self._resolve_column_map().items():
            src_lower = src.lower().strip()
            if src_lower in df.columns:
                df = df.rename(columns={src_lower: target})

        # Apply default values
        defaults = self._get_default_values()
        for field, default in defaults.items():
            if target not in df.columns:
                df[target] = default

        return df

    def _validate_row(self, row: pd.Series, row_num: int) -> list[str]:
        """Validate a single row, return list of errors."""
        errors = []

        required = self._get_required_fields()
        for field in self._get_required_fields():
            if field not in row or pd.isna(row.get(field)) or str(row.get(field, "")).strip() == "":
                errors.append(f"Row {row_num}: Missing required field '{field}'")

        # Validate price
        price = row.get("regular_price")
        if price is not None:
            try:
                price_val = float(price)
                if price_val < 0:
                    errors.append(f"Row {row_num}: Price cannot be negative")
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: Invalid price value '{price}'")

        # Validate cost
        cost = row.get("cost_price")
        if cost is not None:
            try:
                float(cost)
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: Invalid cost value '{cost}'")

        # Validate stock
        stock = row.get("current_stock")
        if stock is not None:
            try:
                float(stock)
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: Invalid stock value '{stock}'")

        # Validate warranty
        warranty = row.get("warranty_days")
        if warranty is not None:
            try:
                int(warranty)
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: Invalid warranty days '{warranty}'")

        return errors

    def _resolve_category(self, category_name: str | None) -> int | None:
        """Resolve category name to ID, creating if needed."""
        if not category_name or pd.isna(category_name):
            return None

        cat_name = str(category_name).strip()
        cat = ProductService.find_category_by_name(self.tenant_id, cat_name)
        if cat:
            return cat.id

        # Create new category
        new_cat = ProductService.create_category(name=cat_name, tenant_id=self.tenant_id)
        db.session.flush()
        return new_cat.id

    def _resolve_sku_barcode(self, row: pd.Series) -> tuple[str, str]:
        """Resolve SKU and barcode, generating if missing."""
        sku = str(row.get("sku", "")).strip() if not pd.isna(row.get("sku")) else ""
        barcode = str(row.get("barcode", "")).strip() if not pd.isna(row.get("barcode")) else ""

        if not sku or sku.lower() in ("nan", "none", ""):
            sku = generate_sku()

        if not barcode or barcode.lower() in ("nan", "none", ""):
            barcode = sku

        return sku, barcode

    def _process_row(
        self,
        row: pd.Series,
        row_num: int,
        update_existing: bool = False,
        job: ProductImportJob | None = None,
    ) -> tuple[bool, dict | None, list[str]]:
        """Process a single row, return (success, product_data, errors)."""
        errors = self._validate_row(row, row_num)
        if errors:
            return False, None, errors

        # Resolve SKU/Barcode
        sku, barcode = self._resolve_sku_barcode(row)

        # Check for duplicate
        existing = ProductService.find_duplicate_product(sku, barcode, self.tenant_id)

        if existing:
            if not update_existing:
                return False, None, [f"Row {row_num}: Duplicate SKU/Barcode ({sku}/{barcode})"]

            # Capture snapshot of existing product before update
            if job is not None:
                snapshot = {
                    "name": existing.name,
                    "regular_price": str(existing.regular_price),
                    "cost_price": str(existing.cost_price) if existing.cost_price else None,
                    "warranty_days": existing.warranty_days,
                    "part_number": existing.part_number,
                    "unit": existing.unit,
                    "category_id": existing.category_id,
                    "barcode": existing.barcode,
                    "sku": existing.sku,
                }
                # Store snapshot keyed by product ID
                if job.updated_product_snapshots is None:
                    job.updated_product_snapshots = {}
                job.updated_product_snapshots[str(existing.id)] = snapshot
                db.session.flush()

            # Update existing product
            existing.name = str(row["name"]).strip()
            existing.regular_price = Decimal(str(row["regular_price"]))
            if "cost_price" in row and not pd.isna(row.get("cost_price")):
                existing.cost_price = Decimal(str(row["cost_price"]))
            existing.warranty_days = int(row.get("warranty_days", 0) or 0)
            product = existing
            action = "updated"
        else:
            # Create new product
            category_id = self._resolve_category(row.get("category"))
            product = ProductService.create_product(
                name=str(row["name"]).strip(),
                regular_price=Decimal(str(row["regular_price"])),
                cost_price=Decimal(str(row.get("cost_price", 0))) if not pd.isna(row.get("cost_price")) else None,
                sku=sku,
                barcode=barcode,
                part_number=str(row.get("part_number", "")).strip() if not pd.isna(row.get("part_number")) else None,
                warranty_days=int(row.get("warranty_days", 0) or 0),
                category_id=self._resolve_category(row.get("category")),
                unit=str(row.get("unit", "قطعة")).strip() if not pd.isna(row.get("unit")) else "قطعة",
                tenant_id=self.tenant_id,
            )
            db.session.add(product)
            db.session.flush()
            action = "created"

        # Handle opening stock
        stock = row.get("current_stock")
        if stock is not None and not pd.isna(stock):
            stock_qty = Decimal(str(stock))
            if stock_qty > 0:
                StockService.add_opening_stock(
                    product_id=product.id,
                    quantity=stock_qty,
                    notes="مخزون افتتاحي من استيراد",
                    warehouse_id=self.warehouse.id if self.warehouse else None,
                )

        return (
            True,
            {
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "action": action,
            },
            [],
        )

    def process_dataframe(
        self,
        df: pd.DataFrame,
        update_existing: bool = False,
        dry_run: bool = False,
        job: ProductImportJob | None = None,
    ) -> dict:
        """Process entire DataFrame, return results."""
        results = {
            "success": 0,
            "errors": 0,
            "errors_detail": [],
            "warnings": [],
            "created_ids": [],
            "updated_ids": [],
            "summary": {},
        }

        for idx, row in df.iterrows():
            row_num = idx + 2  # 1-indexed + header
            success, data, errors = self._process_row(row, idx + 2, update_existing, job)

            if errors:
                results["errors"] += 1
                results["errors_detail"].extend([{"row": row_num, "error": e, "data": row.to_dict()} for e in errors])
                continue

            if data:
                if data["action"] == "created":
                    results["created_ids"].append(data["id"])
                else:
                    results["updated_ids"].append(data["id"])
                results["success"] += 1

        results["summary"] = {
            "total_processed": len(df),
            "created": len(results["created_ids"]),
            "updated": len(results["updated_ids"]),
            "errors": results["errors"],
        }
        return results

    def run_import(
        self,
        file_content: bytes,
        filename: str,
        job: ProductImportJob | None = None,
        update_existing: bool = False,
    ) -> dict:
        """Main entry point for import (can run sync or be called from Celery)."""
        if job:
            ImportJobService.start_job(job.id)

        try:
            # Read and normalize
            df = self._read_dataframe(file_content, filename)
            original_rows = len(df)

            if job:
                job.total_rows = original_rows
                db.session.flush()

            df = self._normalize_dataframe(df)

            # Process
            results = self.process_dataframe(
                df, update_existing=update_existing, dry_run=job.is_dry_run if job else False, job=job
            )

            # Update job progress
            if job:
                job.processed_rows = results["summary"]["total_processed"]
                job.success_count = results["success"]
                job.error_count = results["errors"]
                job.errors = results["errors_detail"]
                db.session.flush()

            if job and job.is_dry_run:
                job.status = ProductImportJobStatus.DRY_RUN_COMPLETE
                job.completed_at = datetime.now(UTC)
                db.session.flush()
                return {"dry_run": True, "preview": results}

            if not job or not job.is_dry_run:
                # Caller (route or Celery task) manages transaction boundary
                pass

            if job:
                ImportJobService.complete_job(
                    job_id=job.id,
                    success_count=results["success"],
                    error_count=results["errors"],
                    created_ids=results["created_ids"],
                    updated_ids=results["updated_ids"],
                    errors=results["errors_detail"],
                    warnings=results.get("warnings", []),
                    summary=results["summary"],
                )

            return results

        except Exception as e:
            logger.exception(f"Import failed: {e}")
            if job:
                ImportJobService.fail_job(job.id, str(e))
            raise


# Celery Tasks
from services.celery_tasks import celery


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def process_product_import_task(
    self,
    job_id: int,
    file_content_b64: str,
    filename: str,
    update_existing: bool = False,
):
    """Celery task for background product import."""
    import base64
    import logging

    logger = logging.getLogger(__name__)
    file_content = base64.b64decode(file_content_b64)

    from app import create_app

    app = create_app()

    with app.app_context():
        try:
            job = ProductImportJob.query.get_or_404(job_id)
            job.celery_task_id = self.request.id
            db.session.flush()

            # Update progress via WebSocket
            self.update_state(
                state="PROGRESS", meta={"current": 0, "total": job.total_rows, "status": "Starting import..."}
            )

            service = ProductImportService(job.tenant_id, job.user_id)
            if job.template_id:
                template = ProductImportTemplate.query.get(job.template_id)
                if template:
                    service.set_template(template)

            # Custom progress callback
            def progress_callback(processed, total):
                self.update_state(
                    state="PROGRESS",
                    meta={"current": processed, "total": total, "status": f"Processing row {processed}/{total}"},
                )

            # Monkey-patch progress updates
            original_process = ProductImportService.process_dataframe

            def progress_wrapper(df, update_existing, dry_run):
                # This is a simplified version - in production you'd want a proper callback
                return ProductImportService.process_dataframe(service, df, update_existing=False, dry_run=False)

            results = service.run_import(
                file_content=base64.b64decode(job.original_filename),
                filename=job.original_filename,
                job=job,
                update_existing=job.update_existing if hasattr(job, "update_existing") else False,
            )

            return {"status": "completed", "results": results}

        except Exception as exc:
            logger.exception(f"Import task failed: {exc}")
            ImportJobService.fail_job(job_id, str(exc))
            db.session.commit()
            raise self.retry(exc=exc)


@celery.task
def process_product_import_rollback_task(rollback_job_id: int):
    """Celery task for rolling back an import job."""
    from app import create_app

    app = create_app()

    with app.app_context():
        from models import ProductWarehouseStock, GLJournalEntry, StockMovement

        rollback_job = ProductImportJob.query.get_or_404(rollback_job_id)
        original_job = rollback_job.rollback_job_id and ProductImportJob.query.get(rollback_job.rollback_job_id)

        if not original_job:
            raise ValueError("Original job not found")

        rolled_back_product_ids = []
        rolled_back_stock_movements = []
        rolled_back_gl_entries = []

        # Delete created products
        for pid in original_job.created_product_ids:
            product = Product.query.get(pid)
            if product:
                # Delete stock movements
                deleted_movements = StockMovement.query.filter_by(product_id=pid).delete()
                rolled_back_stock_movements.extend([pid] * deleted_movements)
                # Delete warehouse stock
                ProductWarehouseStock.query.filter_by(product_id=pid).delete()
                # Delete GL entries for this product
                gl_entries = GLJournalEntry.query.filter(
                    GLJournalEntry.reference_id == pid,
                    GLJournalEntry.reference_type.in_(["PRODUCT_CREATION", "STOCK_ADJUSTMENT"]),
                ).all()
                rolled_back_gl_entries.extend([e.id for e in gl_entries])
                GLJournalEntry.query.filter(
                    GLJournalEntry.reference_id == pid,
                    GLJournalEntry.reference_type.in_(["PRODUCT_CREATION", "STOCK_ADJUSTMENT"]),
                ).delete()
                db.session.delete(product)
                rolled_back_product_ids.append(pid)

        # Restore updated products from snapshots
        snapshots = original_job.updated_product_snapshots or {}
        for pid_str, snapshot in snapshots.items():
            pid = int(pid_str)
            product = Product.query.get(pid)
            if product:
                # Restore product fields
                product.name = snapshot.get("name", product.name)
                product.regular_price = Decimal(snapshot.get("regular_price", product.regular_price))
                cost_price = snapshot.get("cost_price")
                product.cost_price = Decimal(cost_price) if cost_price else None
                product.warranty_days = snapshot.get("warranty_days", product.warranty_days)
                product.part_number = snapshot.get("part_number", product.part_number)
                product.unit = snapshot.get("unit", product.unit)
                product.category_id = snapshot.get("category_id", product.category_id)
                product.barcode = snapshot.get("barcode", product.barcode)
                product.sku = snapshot.get("sku", product.sku)
                db.session.flush()

        # Log rollback with details
        from models.product_import_job import ProductImportRollbackLog

        log = ProductImportRollbackLog(
            original_job_id=original_job.id,
            rollback_job_id=rollback_job.id,
            user_id=rollback_job.user_id,
            rolled_back_product_ids=rolled_back_product_ids,
            rolled_back_stock_movements=rolled_back_stock_movements,
            rolled_back_gl_entries=rolled_back_gl_entries,
            reason="Automated rollback via background job",
        )
        db.session.add(log)

        rollback_job.status = ProductImportJobStatus.ROLLED_BACK
        rollback_job.completed_at = datetime.now(UTC)
        db.session.commit()

        return {
            "status": "rolled_back",
            "deleted_products": len(rolled_back_product_ids),
            "restored_products": len(snapshots),
        }
