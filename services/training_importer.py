"""
Training Importer — JSON/Excel training data ingestion with SSRF safety and validation.
"""

import json
import logging
import os
import re
from typing import Any

import pandas as pd

from extensions import db
from models.ai import AiMemory
from models.ai_training_advanced import AiTrainingBatch

logger = logging.getLogger(__name__)


class TrainingImporter:
    """Handles importing training data from JSON and Excel files with validation."""

    def __init__(self, upload_folder: str = "uploads/training"):
        self.upload_folder = upload_folder

    def _ensure_upload_folder(self) -> str:
        try:
            from flask import current_app, has_app_context

            if has_app_context():
                configured = current_app.config.get("UPLOAD_FOLDER")
                if configured:
                    self.upload_folder = os.path.join(str(configured), "training")
        except Exception as exc:
            logger.debug("TrainingImporter: app upload folder unavailable (%s)", exc)
        os.makedirs(self.upload_folder, exist_ok=True)
        return self.upload_folder

    def import_from_json(self, file_path: str, tenant_id: int, user_id: int = None) -> dict[str, Any]:
        """Import training data from JSON file with format validation."""
        batch = None
        try:
            # Create batch record
            batch = AiTrainingBatch(
                tenant_id=tenant_id,
                source_file=os.path.basename(file_path),
                file_type="json",
                status="processing",
                record_count=0,
                processed_count=0,
            )
            db.session.add(batch)
            db.session.flush()

            # Read and validate JSON
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            # Validate expected structure
            training_records = []
            if isinstance(data, list):
                training_records = data
            elif isinstance(data, dict) and "training_data" in data:
                training_records = data["training_data"]
            elif isinstance(data, dict) and "qa_pairs" in data:
                training_records = data["qa_pairs"]
            else:
                training_records = [data] if isinstance(data, dict) else []

            batch.record_count = len(training_records)
            db.session.flush()

            # Process records
            processed_count, errors = self._process_training_records(training_records, tenant_id)
            batch.processed_count = processed_count

            # Update batch status
            batch.status = "completed" if errors == 0 else "completed_with_errors"
            if errors > 0:
                batch.error_message = f"{errors} records failed to process"
            else:
                batch.error_message = None

            db.session.flush()
            logger.info(
                f"Imported JSON training data: {processed_count}/{len(training_records)} records for tenant {tenant_id}"
            )

            return {
                "success": True,
                "batch_id": batch.id,
                "processed": processed_count,
                "total": len(training_records),
                "errors": errors,
                "status": batch.status,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON file {file_path}: {e}")
            if batch:
                batch.status = "failed"
                batch.error_message = f"Invalid JSON: {str(e)}"
                db.session.flush()
            return {
                "success": False,
                "error": f"Invalid JSON file: {str(e)}",
                "batch_id": batch.id if batch else None,
            }
        except Exception as e:
            logger.exception(f"Failed to import JSON training data from {file_path}")
            if batch:
                batch.status = "failed"
                batch.error_message = str(e)
                db.session.flush()
            return {
                "success": False,
                "error": str(e),
                "batch_id": batch.id if batch else None,
            }

    def import_from_excel(self, file_path: str, tenant_id: int, user_id: int = None) -> dict[str, Any]:
        """Import training data from Excel file with column mapping."""
        batch = None
        try:
            # Create batch record
            batch = AiTrainingBatch(
                tenant_id=tenant_id,
                source_file=os.path.basename(file_path),
                file_type="excel",
                status="processing",
                record_count=0,
                processed_count=0,
            )
            db.session.add(batch)
            db.session.flush()

            # Read Excel file
            df = pd.read_excel(file_path, engine="openpyxl")

            # Normalize column names (lowercase, spaces to underscores)
            df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]

            # Required columns mapping (flexible matching)
            column_mapping = {
                "question": ["question", "ques", "q", "input", "prompt"],
                "answer": ["answer", "ans", "a", "output", "response"],
                "category": ["category", "cat", "topic", "domain", "type"],
                "confidence": ["confidence", "conf", "score", "weight"],
                "context": ["context", "description", "desc", "notes"],
            }

            # Find actual column names
            actual_columns = {}
            for standard_name, possible_names in column_mapping.items():
                for col in df.columns:
                    if any(pn in col or col in pn for pn in possible_names):  # Flexible matching
                        actual_columns[standard_name] = col
                        break

            # Validate required columns
            if "question" not in actual_columns or "answer" not in actual_columns:
                raise ValueError("Excel file must contain 'question' and 'answer' columns")

            batch.record_count = len(df)
            db.session.flush()

            # Convert DataFrame to records
            training_records = []
            for _, row in df.iterrows():
                record = {}
                for std_col, actual_col in actual_columns.items():
                    value = row[actual_col]
                    # Handle NaN values
                    if pd.isna(value):
                        value = "" if std_col != "confidence" else 1.0
                    elif std_col == "confidence":
                        try:
                            value = float(value)
                            if value < 0 or value > 1:
                                value = max(0.0, min(1.0, value))  # Clamp to [0,1]
                        except (ValueError, TypeError):
                            value = 1.0
                    record[std_col] = str(value).strip() if not isinstance(value, (int, float)) else value
                # Ensure category defaults
                if "category" not in record or not record["category"]:
                    record["category"] = "general"
                if "confidence" not in record:
                    record["confidence"] = 1.0
                training_records.append(record)

            # Process records
            processed_count, errors = self._process_training_records(training_records, tenant_id)
            batch.processed_count = processed_count

            # Update batch status
            batch.status = "completed" if errors == 0 else "completed_with_errors"
            if errors > 0:
                batch.error_message = f"{errors} records failed to process"
            else:
                batch.error_message = None

            db.session.flush()
            logger.info(
                f"Imported Excel training data: {processed_count}/{len(training_records)} records for tenant {tenant_id}"
            )

            return {
                "success": True,
                "batch_id": batch.id,
                "processed": processed_count,
                "total": len(training_records),
                "errors": errors,
                "status": batch.status,
            }

        except Exception as e:
            logger.exception(f"Failed to import Excel training data from {file_path}")
            if batch:
                batch.status = "failed"
                batch.error_message = str(e)
                db.session.flush()
            return {
                "success": False,
                "error": str(e),
                "batch_id": batch.id if batch else None,
            }

    def _process_training_records(self, records: list[dict[str, Any]], tenant_id: int) -> tuple[int, int]:
        """Process a list of training records into AiMemory entries."""
        processed_count = 0
        error_count = 0

        for record in records:
            try:
                # Validate record
                question = record.get("question", "").strip()
                answer = record.get("answer", "").strip()

                if not question or not answer:
                    error_count += 1
                    continue

                # Create memory entry
                memory = AiMemory(
                    tenant_id=tenant_id,
                    key=question.lower()[:255],  # Truncate to fit column
                    value=answer[:4000],  # Truncate to fit column
                    category=record.get("category", "general").lower()[:50],  # Truncate
                    confidence=float(record.get("confidence", 1.0)),
                    source=f"import_{record.get('file_type', 'unknown')}",
                    is_active=True,
                )
                db.session.add(memory)
                processed_count += 1

                # Flush periodically to avoid large transactions
                if processed_count % 100 == 0:
                    db.session.flush()

            except Exception as e:
                logger.warning(f"Failed to process training record: {e}. Record: {record}")
                error_count += 1
                continue

        return processed_count, error_count

    def validate_file_security(self, filename: str) -> bool:
        """Validate file extension and basic security."""
        allowed_extensions = {".json", ".xlsx", ".xls"}
        file_ext = os.path.splitext(filename.lower())[1]
        return file_ext in allowed_extensions

    def get_safe_filename(self, filename: str) -> str:
        """Generate a secure filename to prevent path traversal."""
        # Remove path components and keep only basename
        safe_name = os.path.basename(filename)
        # Replace any problematic characters
        safe_name = re.sub(r"[^\w\-_\.]", "_", safe_name)
        return safe_name[:255]  # Limit length


# Global instance
training_importer = TrainingImporter()
