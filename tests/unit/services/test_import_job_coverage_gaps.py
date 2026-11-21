"""Coverage gaps for services/import_job_service.py.

Targets the statements the CI-combined coverage report still marks as missed:
job progress/rollback helpers, template-backed column/default resolution, CSV
encoding fallbacks, validation error branches, the existing-product snapshot
path, dry-run/process branches, the job bookkeeping inside ``run_import`` and
both Celery tasks (success, no-template and failure/retry arcs).

All patches are at the service boundary; no production code is changed.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from models.product_import_job import ProductImportJob, ProductImportJobStatus, ProductImportTemplate
from services.import_job_service import (
    ImportJobService,
    ProductImportService,
    process_product_import_rollback_task,
    process_product_import_task,
)


@contextmanager
def _no_op_transaction(*_args, **_kwargs):
    yield


def _fake_app():
    app = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = None
    ctx.__exit__.return_value = False
    app.app_context.return_value = ctx
    return app


@pytest.fixture
def make_job(db_session, sample_tenant):
    def _make(**overrides):
        fields = dict(
            tenant_id=sample_tenant.id,
            user_id=None,
            job_name="Test import",
            original_filename="products.csv",
            status=ProductImportJobStatus.PENDING,
            is_dry_run=False,
        )
        fields.update(overrides)
        job = ProductImportJob(**fields)
        db_session.add(job)
        db_session.flush()
        return job

    return _make


@pytest.fixture
def svc(sample_tenant):
    with patch("services.import_job_service.ProductService.get_default_warehouse", return_value=MagicMock(id=1)):
        instance = ProductImportService(sample_tenant.id)
    return instance


class TestImportJobHelpers:
    def test_update_progress_sets_counts_and_optional_eta(self, make_job, db_session):
        job = make_job()
        eta = datetime(2026, 12, 1, tzinfo=UTC)

        updated = ImportJobService.update_progress(job.id, 7, 5, 2, estimated_completion=eta)
        assert updated.processed_rows == 7
        assert updated.success_count == 5
        assert updated.error_count == 2
        assert updated.estimated_completion_at == eta

        # The no-ETA branch leaves the field untouched.
        ImportJobService.update_progress(job.id, 8, 6, 2)
        assert updated.processed_rows == 8
        assert updated.estimated_completion_at == eta
        db_session.flush()

    def test_create_rollback_job_for_completed_job(self, make_job, sample_user, db_session):
        job = make_job(status=ProductImportJobStatus.COMPLETED, user_id=sample_user.id)

        rollback = ImportJobService.create_rollback_job(job.id, sample_user.id, reason="duplicate")
        assert rollback.is_rollback is True
        assert rollback.rollback_job_id == job.id
        assert rollback.tenant_id == job.tenant_id
        assert rollback.user_id == sample_user.id
        assert rollback.job_name == f"Rollback of {job.job_name}"
        db_session.flush()
        assert rollback.id is not None

    def test_rollback_audit_names_the_actor_not_the_original_importer(
        self, make_job, sample_user, sample_owner, db_session
    ):
        from models.product_import_job import ProductImportRollbackLog

        job = make_job(status=ProductImportJobStatus.COMPLETED, user_id=sample_user.id)
        actor_id = sample_owner.id

        rollback = ImportJobService.create_rollback_job(job.id, actor_id)
        db_session.flush()

        assert rollback.user_id == actor_id
        log = db_session.query(ProductImportRollbackLog).filter_by(rollback_job_id=rollback.id).first()
        assert log.user_id == actor_id

    def test_create_rollback_job_rejects_pending_job(self, make_job):
        job = make_job(status=ProductImportJobStatus.PENDING)
        with pytest.raises(ValueError, match="Can only rollback completed jobs"):
            ImportJobService.create_rollback_job(job.id, None)


class TestTemplateDrivenResolution:
    def test_template_supplies_column_map_required_fields_and_defaults(self, svc, db_session, sample_tenant):
        template = ProductImportTemplate(
            tenant_id=sample_tenant.id,
            name="Mapping",
            column_mapping={"product_name": "name", "price": "regular_price"},
            required_fields=["name", "regular_price", "sku"],
            default_values={"unit": "piece", "category": "General"},
        )
        db_session.add(template)
        db_session.flush()
        svc.set_template(template)

        assert svc._resolve_column_map() == template.column_mapping
        assert svc._get_required_fields() == template.required_fields
        assert svc._get_default_values() == template.default_values

    def test_template_defaults_are_applied_to_missing_columns(self, svc, db_session, sample_tenant):
        template = ProductImportTemplate(
            tenant_id=sample_tenant.id,
            name="Defaults",
            column_mapping={},
            required_fields=[],
            default_values={"unit": "piece", "category": "General"},
        )
        db_session.add(template)
        db_session.flush()
        svc.set_template(template)

        df = svc._normalize_dataframe(pd.DataFrame({"name": ["Widget"]}))
        assert df["unit"].iloc[0] == "piece"
        assert df["category"].iloc[0] == "General"

        # A default never overwrites a column the file already supplied.
        present = svc._normalize_dataframe(pd.DataFrame({"name": ["Widget"], "unit": ["box"]}))
        assert present["unit"].iloc[0] == "box"


class TestDataframeReading:
    def test_utf8_failure_falls_back_to_arabic_encoding(self, svc):
        # 0xE9 is invalid UTF-8 but decodes cleanly in cp1256.
        content = b"name,price\nCaf\xe9,10\n"
        df = svc._read_dataframe(content, "products.csv")
        assert list(df.columns) == ["name", "price"]
        assert len(df) == 1

    def test_all_encodings_fail_uses_skip_bad_lines_last_resort(self, svc):
        expected = pd.DataFrame({"name": ["Widget"]})
        decode_error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        with patch("services.import_job_service.pd.read_csv", side_effect=[decode_error] * 5 + [expected]) as read:
            df = svc._read_dataframe(b"\xff\xfe", "products.csv")
        assert df is expected
        assert read.call_count == 6
        assert read.call_args.kwargs["on_bad_lines"] == "skip"


class TestValidationAndSku:
    def test_validation_error_branches(self, svc):
        negative = pd.Series({"name": "X", "regular_price": -5, "cost_price": None, "current_stock": None})
        assert any("Price cannot be negative" in e for e in svc._validate_row(negative, 2))

        bad_price = pd.Series({"name": "X", "regular_price": "abc"})
        assert any("Invalid price value" in e for e in svc._validate_row(bad_price, 3))

        bad_cost = pd.Series({"name": "X", "regular_price": 10, "cost_price": "abc"})
        assert any("Invalid cost value" in e for e in svc._validate_row(bad_cost, 4))

        bad_stock = pd.Series({"name": "X", "regular_price": 10, "current_stock": "abc"})
        assert any("Invalid stock value" in e for e in svc._validate_row(bad_stock, 5))

    def test_supplied_barcode_skips_generation(self, svc):
        row = pd.Series({"sku": "SKU-1", "barcode": "BC-123"})
        assert svc._resolve_sku_barcode(row) == ("SKU-1", "BC-123")


class TestProcessRowUpdateSnapshot:
    def test_updating_existing_product_stores_snapshot_and_applies_new_values(
        self, svc, sample_product, make_job, db_session
    ):
        job = make_job()
        original_name = sample_product.name
        row = pd.Series(
            {
                "name": "Updated Widget",
                "regular_price": "120.50",
                "cost_price": "60.00",
                "current_stock": float("nan"),
                "warranty_days": "90",
                "part_number": "PN-1",
                "unit": "pcs",
                "sku": sample_product.sku,
                "barcode": sample_product.barcode,
            }
        )
        with patch(
            "services.import_job_service.ProductService.find_duplicate_product",
            return_value=sample_product,
        ):
            ok, data, errors = svc._process_row(row, 2, update_existing=True, job=job)

        assert ok is True and errors == []
        assert data["action"] == "updated"
        assert sample_product.name == "Updated Widget"
        assert sample_product.regular_price == Decimal("120.50")
        snapshot = job.updated_product_snapshots[str(sample_product.id)]
        assert snapshot["name"] == original_name
        assert snapshot["sku"] == sample_product.sku
        db_session.flush()

    def test_snapshot_dict_is_initialized_and_missing_cost_is_tolerated(
        self, svc, sample_product, make_job, db_session
    ):
        job = make_job()
        job.updated_product_snapshots = None
        db_session.flush()
        row = pd.Series(
            {
                "name": "No Cost",
                "regular_price": "30",
                "current_stock": float("nan"),
                "sku": sample_product.sku,
                "barcode": sample_product.barcode,
            }
        )
        with patch(
            "services.import_job_service.ProductService.find_duplicate_product",
            return_value=sample_product,
        ):
            ok, _data, errors = svc._process_row(row, 2, update_existing=True, job=job)
        assert ok is True and errors == []
        assert job.updated_product_snapshots is not None

    def test_update_existing_without_job_skips_snapshot(self, svc, sample_product):
        row = pd.Series(
            {
                "name": "No Job",
                "regular_price": "40",
                "cost_price": "20",
                "current_stock": float("nan"),
                "sku": sample_product.sku,
                "barcode": sample_product.barcode,
            }
        )
        with patch(
            "services.import_job_service.ProductService.find_duplicate_product",
            return_value=sample_product,
        ):
            ok, _data, errors = svc._process_row(row, 2, update_existing=True, job=None)
        assert ok is True and errors == []


class TestProcessDataframeBranches:
    def test_dry_run_reports_validation_errors_without_writing(self, svc):
        df = pd.DataFrame({"name": [None], "regular_price": [None]})
        results = svc.process_dataframe(df, dry_run=True)
        assert results["errors"] == 1
        assert results["errors_detail"]
        assert results["created_ids"] == []

    def test_updated_ids_and_falsy_data_path(self, svc):
        df = pd.DataFrame({"name": ["A", "B"], "regular_price": [10, 20]})
        with patch.object(
            svc,
            "_process_row",
            side_effect=[
                (True, {"id": 7, "name": "A", "sku": "S7", "action": "updated"}, []),
                (True, None, []),
            ],
        ) as process:
            results = svc.process_dataframe(df)
        assert process.call_count == 2
        assert results["updated_ids"] == [7]
        assert results["success"] == 1
        assert results["created_ids"] == []


class TestRunImportJobBookkeeping:
    @staticmethod
    def _results():
        return {
            "success": 2,
            "errors": 0,
            "errors_detail": [],
            "warnings": [],
            "created_ids": [101, 102],
            "updated_ids": [],
            "summary": {"total_processed": 2, "created": 2, "updated": 0, "errors": 0},
        }

    def test_job_is_started_counted_and_completed(self, svc, make_job):
        job = make_job()
        df = pd.DataFrame({"name": ["A", "B"], "regular_price": [10, 20]})
        with (
            patch.object(svc, "_read_dataframe", return_value=df),
            patch.object(svc, "process_dataframe", return_value=self._results()),
        ):
            results = svc.run_import(b"file bytes", "products.csv", job=job)
        assert results == self._results()
        assert job.total_rows == 2
        assert job.processed_rows == 2
        assert job.status == ProductImportJobStatus.COMPLETED
        assert job.started_at is not None

    def test_dry_run_job_returns_preview_and_stops(self, svc, make_job):
        job = make_job(is_dry_run=True)
        df = pd.DataFrame({"name": ["A"], "regular_price": [10]})
        with (
            patch.object(svc, "_read_dataframe", return_value=df),
            patch.object(svc, "process_dataframe", return_value=self._results()),
        ):
            results = svc.run_import(b"file bytes", "products.csv", job=job)
        assert results == {"dry_run": True, "preview": self._results()}
        assert job.status == ProductImportJobStatus.DRY_RUN_COMPLETE

    def test_exception_marks_job_failed_and_reraises(self, svc, make_job):
        job = make_job()
        with (
            patch.object(svc, "_read_dataframe", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            svc.run_import(b"file bytes", "products.csv", job=job)
        assert job.status == ProductImportJobStatus.FAILED
        assert job.errors[0]["error"] == "boom"

    def test_run_import_without_job_returns_results(self, svc):
        df = pd.DataFrame({"name": ["A"], "regular_price": [10]})
        with (
            patch.object(svc, "_read_dataframe", return_value=df),
            patch.object(svc, "process_dataframe", return_value=self._results()),
        ):
            results = svc.run_import(b"file bytes", "products.csv")
        assert results == self._results()

    def test_run_import_without_job_exception_reraises(self, svc):
        with (
            patch.object(svc, "_read_dataframe", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            svc.run_import(b"file bytes", "products.csv")


class TestImportCeleryTask:
    @staticmethod
    def _fake_self():
        fake = MagicMock()
        fake.request.id = "task-123"
        fake.retry.side_effect = RuntimeError("retry requested")
        return fake

    @staticmethod
    def _configure_job(job_cls, job):
        query = job_cls.query.filter_by.return_value
        query.first_or_404.return_value = job
        query.filter_by.return_value.first_or_404.return_value = job

    def test_success_with_tenant_scope_and_template(self):
        fake_self = self._fake_self()
        job = MagicMock()
        job.id = 5
        job.tenant_id = 11
        job.user_id = 3
        job.total_rows = 2
        job.template_id = 9
        job.original_filename = "products.csv"
        template = MagicMock()
        results = {"success": 2}
        content = b"name,price\nWidget,10\n"

        with (
            patch("app.create_app", return_value=_fake_app()),
            patch("utils.db_safety.atomic_transaction", _no_op_transaction),
            patch("services.import_job_service.ProductImportJob") as job_cls,
            patch("services.import_job_service.ProductImportTemplate") as tmpl_cls,
            patch("services.import_job_service.ProductImportService") as svc_cls,
        ):
            self._configure_job(job_cls, job)
            tmpl_cls.query.filter_by.return_value.first.return_value = template
            svc_cls.return_value.run_import.return_value = results

            output = process_product_import_task.run.__func__(
                fake_self,
                5,
                base64.b64encode(content).decode(),
                "products.csv",
                True,
                11,
            )

        assert output == {"status": "completed", "results": results}
        assert job.celery_task_id == "task-123"
        job_cls.query.filter_by.assert_called_once_with(id=5)
        job_cls.query.filter_by.return_value.filter_by.assert_called_once_with(tenant_id=11)
        svc_cls.return_value.set_template.assert_called_once_with(template)
        svc_cls.return_value.run_import.assert_called_once_with(
            file_content=content,
            filename="products.csv",
            job=job,
            update_existing=True,
        )
        fake_self.update_state.assert_called_once()

    def test_success_when_template_row_is_missing(self):
        fake_self = self._fake_self()
        job = MagicMock()
        job.id = 8
        job.tenant_id = 11
        job.user_id = 3
        job.total_rows = 0
        job.template_id = 99
        job.original_filename = "products.csv"

        with (
            patch("app.create_app", return_value=_fake_app()),
            patch("utils.db_safety.atomic_transaction", _no_op_transaction),
            patch("services.import_job_service.ProductImportJob") as job_cls,
            patch("services.import_job_service.ProductImportTemplate") as tmpl_cls,
            patch("services.import_job_service.ProductImportService") as svc_cls,
        ):
            self._configure_job(job_cls, job)
            tmpl_cls.query.filter_by.return_value.first.return_value = None
            svc_cls.return_value.run_import.return_value = {"success": 0}
            output = process_product_import_task.run.__func__(
                fake_self, 8, base64.b64encode(b"x").decode(), "products.csv"
            )

        assert output["status"] == "completed"
        svc_cls.return_value.set_template.assert_not_called()

    def test_success_without_tenant_or_template_uses_job_filename(self):
        fake_self = self._fake_self()
        job = MagicMock()
        job.id = 6
        job.tenant_id = 11
        job.user_id = 3
        job.total_rows = 0
        job.template_id = None
        job.original_filename = "fallback.csv"

        with (
            patch("app.create_app", return_value=_fake_app()),
            patch("utils.db_safety.atomic_transaction", _no_op_transaction),
            patch("services.import_job_service.ProductImportJob") as job_cls,
            patch("services.import_job_service.ProductImportTemplate"),
            patch("services.import_job_service.ProductImportService") as svc_cls,
        ):
            self._configure_job(job_cls, job)
            svc_cls.return_value.run_import.return_value = {"success": 0}
            output = process_product_import_task.run.__func__(
                fake_self, 6, base64.b64encode(b"x").decode(), None, False, None
            )

        assert output["status"] == "completed"
        job_cls.query.filter_by.return_value.filter_by.assert_not_called()
        svc_cls.return_value.set_template.assert_not_called()
        assert svc_cls.return_value.run_import.call_args.kwargs["filename"] == "fallback.csv"

    def test_failure_records_job_error_and_retries(self):
        fake_self = self._fake_self()
        job = MagicMock()
        job.id = 7
        job.tenant_id = 11
        job.user_id = 3
        job.total_rows = 0
        job.template_id = None
        job.original_filename = "products.csv"

        with (
            patch("app.create_app", return_value=_fake_app()),
            patch("utils.db_safety.atomic_transaction", _no_op_transaction),
            patch("services.import_job_service.ProductImportJob") as job_cls,
            patch("services.import_job_service.ProductImportService") as svc_cls,
            patch("services.import_job_service.ImportJobService.fail_job") as fail_job,
            pytest.raises(RuntimeError, match="retry requested"),
        ):
            self._configure_job(job_cls, job)
            svc_cls.return_value.run_import.side_effect = RuntimeError("import exploded")
            process_product_import_task.run.__func__(fake_self, 7, base64.b64encode(b"x").decode(), "products.csv")

        fail_job.assert_called_once_with(7, "import exploded")


class TestRollbackCeleryTask:
    @staticmethod
    def _configure_jobs(job_cls, rollback_job, original_job):
        query = job_cls.query.filter_by.return_value
        query.first_or_404.return_value = rollback_job
        query.first.return_value = original_job

    def test_rollback_deletes_created_and_restores_updated_products(self):
        rollback_job = MagicMock()
        rollback_job.id = 44
        rollback_job.tenant_id = 11
        rollback_job.rollback_job_id = 5
        rollback_job.user_id = 3
        original_job = MagicMock()
        original_job.id = 5
        original_job.created_product_ids = [101]
        snapshot = {
            "name": "Old name",
            "regular_price": "10.00",
            "cost_price": "5.00",
            "warranty_days": 30,
            "part_number": "PN-OLD",
            "unit": "pcs",
            "category_id": 2,
            "barcode": "BC-OLD",
            "sku": "SKU-OLD",
        }
        original_job.updated_product_snapshots = {"202": snapshot}
        created_product = MagicMock()
        restored_product = MagicMock()
        gl_entry_1 = MagicMock()
        gl_entry_1.id = 301
        gl_entry_2 = MagicMock()
        gl_entry_2.id = 302

        with (
            patch("app.create_app", return_value=_fake_app()),
            patch("utils.db_safety.atomic_transaction", _no_op_transaction),
            patch("services.import_job_service.ProductImportJob") as job_cls,
            patch("services.import_job_service.Product") as product_cls,
            patch("services.import_job_service.StockMovement") as movement_cls,
            patch("services.import_job_service.ProductWarehouseStock") as stock_cls,
            patch("services.import_job_service.GLJournalEntry") as gl_cls,
            patch("services.import_job_service.db"),
            patch("models.product_import_job.ProductImportRollbackLog") as log_cls,
        ):
            self._configure_jobs(job_cls, rollback_job, original_job)
            product_cls.query.filter_by.return_value.first.side_effect = [created_product, restored_product]
            movement_cls.query.filter_by.return_value.delete.return_value = 2
            stock_cls.query.filter_by.return_value.delete.return_value = 1
            gl_cls.query.filter.return_value.all.return_value = [gl_entry_1, gl_entry_2]

            result = process_product_import_rollback_task.run(44)

        assert result == {
            "status": "rolled_back",
            "deleted_products": 1,
            "restored_products": 1,
        }
        product_cls.query.filter_by.assert_any_call(id=101, tenant_id=11)
        movement_cls.query.filter_by.assert_called_once_with(product_id=101, tenant_id=11)
        stock_cls.query.filter_by.assert_called_once_with(product_id=101, tenant_id=11)
        gl_cls.query.filter.return_value.delete.assert_called_once()
        product_cls.query.filter_by.return_value.first.assert_called()
        assert restored_product.name == "Old name"
        assert restored_product.sku == "SKU-OLD"
        assert restored_product.regular_price == Decimal("10.00")
        assert restored_product.cost_price == Decimal("5.00")
        assert rollback_job.status == ProductImportJobStatus.ROLLED_BACK
        assert log_cls.call_args.kwargs["rolled_back_gl_entries"] == [301, 302]
        assert log_cls.call_args.kwargs["rolled_back_stock_movements"] == [101, 101]

    def test_missing_original_job_raises(self):
        rollback_job = MagicMock()
        rollback_job.id = 45
        rollback_job.tenant_id = 11
        rollback_job.rollback_job_id = None
        rollback_job.user_id = 3

        with (
            patch("app.create_app", return_value=_fake_app()),
            patch("utils.db_safety.atomic_transaction", _no_op_transaction),
            patch("services.import_job_service.ProductImportJob") as job_cls,
            pytest.raises(ValueError, match="Original job not found"),
        ):
            self._configure_jobs(job_cls, rollback_job, None)
            process_product_import_rollback_task.run(45)

    def test_missing_products_skip_delete_and_restore_loops(self):
        rollback_job = MagicMock()
        rollback_job.id = 46
        rollback_job.tenant_id = 11
        rollback_job.rollback_job_id = 5
        rollback_job.user_id = 3
        original_job = MagicMock()
        original_job.id = 5
        original_job.created_product_ids = [303]
        original_job.updated_product_snapshots = {"404": {"name": "Ghost"}}

        with (
            patch("app.create_app", return_value=_fake_app()),
            patch("utils.db_safety.atomic_transaction", _no_op_transaction),
            patch("services.import_job_service.ProductImportJob") as job_cls,
            patch("services.import_job_service.Product") as product_cls,
            patch("services.import_job_service.db"),
            patch("models.product_import_job.ProductImportRollbackLog") as log_cls,
        ):
            self._configure_jobs(job_cls, rollback_job, original_job)
            product_cls.query.filter_by.return_value.first.return_value = None

            result = process_product_import_rollback_task.run(46)

        assert result["deleted_products"] == 0
        assert result["restored_products"] == 1
        assert log_cls.call_args.kwargs["rolled_back_product_ids"] == []
        assert rollback_job.status == ProductImportJobStatus.ROLLED_BACK
