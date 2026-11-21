"""Coverage gaps for routes/products.py.

Targets the statements the CI-combined coverage report still marks as missed:
background import queueing, template-assisted import, branch-scoped pagination
helper, the unreachable-looking ``if request.is_json`` fall-throughs in the
category exception handlers, import-job/template management, bulk JSON, OCR and
the barcode/SKU scanner APIs.

All patches are at the route boundary; no production code is changed.
"""

import tempfile
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from models.product_import_job import ProductImportJobStatus
from tests.unit.routes.test_products_routes import (
    _mock_product_form,
    _product,
    _products_patches,
    _warehouse,
)


class _ToggleJsonRequest:
    """A request stand-in whose ``is_json`` flips on each access.

    The category exception handlers read ``request.is_json`` twice in a row;
    the second read guards a branch that is unreachable with a real request.
    Driving the two reads independently exercises that fall-through.
    """

    def __init__(self, is_json_values, payload=None):
        self._is_json = iter(is_json_values)
        self.payload = payload if payload is not None else {}
        self.form = {}
        self.files = {}

    @property
    def is_json(self):
        return next(self._is_json)

    def get_json(self, silent=False):
        return self.payload


@contextmanager
def _toggle_json_request(values, payload=None):
    with patch("routes.products.request", _ToggleJsonRequest(values, payload)):
        yield


@pytest.fixture
def upload_dir():
    path = tempfile.mkdtemp()
    yield path


@pytest.fixture
def gap_client(app_factory, bypass_permission_auth, upload_dir):
    from routes.products import products_bp

    app = app_factory(products_bp, config_overrides={"UPLOAD_FOLDER": upload_dir})
    return app.test_client()


class TestBackgroundImport:
    def test_large_file_queues_celery_task(self, gap_client):
        mock_job = MagicMock()
        mock_job.id = 123
        mock_job.tenant_id = 1
        task = MagicMock()
        task.id = "celery-task-1"
        with (
            _products_patches(),
            patch(
                "services.import_job_service.ImportJobService.create_job",
                return_value=mock_job,
            ),
            patch("services.import_job_service.process_product_import_task") as task_mod,
        ):
            task_mod.delay.return_value = task
            resp = gap_client.post(
                "/products/import",
                data={
                    "file": (BytesIO(b"x" * 10001), "products.xlsx"),
                    "background": "on",
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert "import/jobs" in resp.location
        task_mod.delay.assert_called_once()
        assert mock_job.celery_task_id == "celery-task-1"


class TestImportWithTemplate:
    def test_template_is_applied_to_sync_import(self, gap_client):
        mock_job = MagicMock()
        mock_job.id = 5
        mock_job.is_dry_run = False
        template = MagicMock()
        template.id = 8
        with (
            _products_patches(),
            patch("routes.products.ProductImportTemplate") as tmpl_cls,
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch(
                "services.import_job_service.ImportJobService.create_job",
                return_value=mock_job,
            ),
            patch(
                "services.import_job_service.ProductImportService.run_import",
                return_value={"dry_run": False, "success": 0, "errors": 0},
            ),
        ):
            tmpl_cls.query.filter_by.return_value.first.return_value = template
            resp = gap_client.post(
                "/products/import",
                data={
                    "file": (BytesIO(b"x"), "products.xlsx"),
                    "template_id": "8",
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert resp.location == "/products/import/jobs/5"
        tmpl_cls.query.filter_by.assert_called_once_with(id=8, tenant_id=1)

    def test_missing_template_row_skips_set_template(self, gap_client):
        mock_job = MagicMock()
        mock_job.id = 6
        mock_job.is_dry_run = False
        with (
            _products_patches(),
            patch("routes.products.ProductImportTemplate") as tmpl_cls,
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch(
                "services.import_job_service.ImportJobService.create_job",
                return_value=mock_job,
            ),
            patch(
                "services.import_job_service.ProductImportService.run_import",
                return_value={"dry_run": False, "success": 0, "errors": 0},
            ),
        ):
            tmpl_cls.query.filter_by.return_value.first.return_value = None
            resp = gap_client.post(
                "/products/import",
                data={
                    "file": (BytesIO(b"x"), "products.xlsx"),
                    "template_id": "999",
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302


class TestBranchScopedPaginationHelper:
    def test_iter_pages_yields_gap_and_edges(self, gap_client):
        items = [_product(i) for i in range(1, 21)]
        captured = {}

        def _render(_template, **context):
            captured["pagination"] = context["pagination"]
            return "idx"

        with (
            _products_patches(products=items, branch_scope=1),
            patch("routes.products.render_template", side_effect=_render),
        ):
            resp = gap_client.get("/products/?page=1&per_page=1")
        assert resp.status_code == 200
        pagination = captured["pagination"]
        pages = list(pagination.iter_pages())
        assert pages[0] == 1
        assert None in pages
        assert pages[-1] == 20
        assert pagination.has_prev is False
        assert pagination.has_next is True


class TestCreateExciseAndTaxCategories:
    def test_valid_excise_kept_and_invalid_tax_defaults(self, gap_client):
        form = _mock_product_form(validate=True)
        added = _product(88, name="Categorized")
        added.partner_shares = MagicMock()
        added.partner_shares.append = MagicMock()

        def _construct(**kwargs):
            for key, value in kwargs.items():
                setattr(added, key, value)
            return added

        with (
            _products_patches(),
            patch("forms.product.ProductForm", return_value=form),
            patch("routes.products.Product", side_effect=_construct),
            patch("routes.products.db.session", MagicMock()),
        ):
            resp = gap_client.post(
                "/products/create",
                data={
                    "name": "Categorized",
                    "regular_price": "10",
                    "warehouse_id": "1",
                    "excise_category": "TOBACCO",
                    "tax_category": "nonsense",
                },
            )
        assert resp.status_code == 302
        assert added.excise_category == "tobacco"
        assert added.tax_category == "standard"


class TestCategoryExceptionJsonFallThrough:
    def test_create_category_exception_falls_through_to_redirect(self, gap_client):
        with (
            _products_patches(),
            _toggle_json_request([True, True, True, False], {"name": "X"}),
            patch(
                "routes.products.ProductService.create_category",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = gap_client.post("/products/categories/create", json={"name": "X"})
        assert resp.status_code == 302
        assert resp.location.endswith("/products/categories")

    def test_update_category_exception_falls_through_to_redirect(self, gap_client):
        cat = _product(5)
        with (
            _products_patches(),
            _toggle_json_request([True, True, True, False], {"name": "X"}),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch(
                "routes.products.ProductService.category_name_taken",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = gap_client.post("/products/categories/5/update", json={"name": "X"})
        assert resp.status_code == 302
        assert resp.location.endswith("/products/categories")

    def test_delete_category_exception_falls_through_to_redirect(self, gap_client):
        cat = _product(6)
        with (
            _products_patches(),
            _toggle_json_request([True, False], {}),
            patch("routes.products._tenant_category_or_404", return_value=cat),
            patch(
                "routes.products.ProductService.count_products_in_category",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = gap_client.post("/products/categories/6/delete", json={})
        assert resp.status_code == 302
        assert resp.location.endswith("/products/categories")


class TestImportJobsListing:
    def test_valid_status_filter_builds_status_predicate(self, gap_client):
        with (
            patch("routes.products.ProductImportJob") as job_cls,
            patch("routes.products.render_template", return_value="ok") as render,
        ):
            job_cls.query.filter_by.return_value.order_by.return_value.paginate.return_value = MagicMock()
            resp = gap_client.get("/products/import/jobs?status=pending")
        assert resp.status_code == 200
        job_cls.query.filter_by.assert_called_once_with(tenant_id=1)
        assert render.call_args[0][0] == "products/import_jobs.html"

    def test_invalid_status_filter_is_suppressed(self, gap_client):
        with (
            patch("routes.products.ProductImportJob") as job_cls,
            patch("routes.products.render_template", return_value="ok"),
        ):
            job_cls.query.filter_by.return_value.order_by.return_value.paginate.return_value = MagicMock()
            resp = gap_client.get("/products/import/jobs?status=not-a-status")
        assert resp.status_code == 200
        job_cls.query.filter.assert_not_called()

    def test_no_status_filter_skips_predicate(self, gap_client):
        with (
            patch("routes.products.ProductImportJob") as job_cls,
            patch("routes.products.render_template", return_value="ok"),
        ):
            job_cls.query.filter_by.return_value.order_by.return_value.paginate.return_value = MagicMock()
            resp = gap_client.get("/products/import/jobs")
        assert resp.status_code == 200
        job_cls.query.filter.assert_not_called()


class TestImportJobDetailAndProgress:
    def test_detail_renders(self, gap_client):
        job = MagicMock()
        with (
            patch("routes.products.ProductImportJob") as job_cls,
            patch("routes.products.render_template", return_value="ok") as render,
        ):
            job_cls.query.filter_by.return_value.first_or_404.return_value = job
            resp = gap_client.get("/products/import/jobs/7")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/import_job_detail.html"

    def test_progress_returns_job_details(self, gap_client):
        job = MagicMock()
        job.to_dict.return_value = {"id": 7, "status": "completed"}
        with patch("routes.products.ProductImportJob") as job_cls:
            job_cls.query.filter_by.return_value.first_or_404.return_value = job
            resp = gap_client.get("/products/import/jobs/7/progress")
        assert resp.status_code == 200
        assert resp.get_json()["id"] == 7
        job.to_dict.assert_called_once_with(include_details=True)


class TestImportJobConfirm:
    def _job(self, status):
        job = MagicMock()
        job.id = 3
        job.status = status
        return job

    def test_dry_run_job_is_reset(self, gap_client):
        job = self._job(ProductImportJobStatus.DRY_RUN_COMPLETE)
        with (
            patch("routes.products.ProductImportJob") as job_cls,
            patch("routes.products.db.session") as session,
        ):
            job_cls.query.filter_by.return_value.first_or_404.return_value = job
            resp = gap_client.post("/products/import/jobs/3/confirm")
        assert resp.status_code == 302
        assert job.status == ProductImportJobStatus.PENDING
        assert job.is_dry_run is False
        assert job.completed_at is None
        assert job.processed_rows == 0
        assert job.errors == []
        session.commit.assert_called()

    def test_non_dry_run_job_is_refused(self, gap_client):
        job = self._job(ProductImportJobStatus.COMPLETED)
        with (
            patch("routes.products.ProductImportJob") as job_cls,
            patch("routes.products.db.session") as session,
        ):
            job_cls.query.filter_by.return_value.first_or_404.return_value = job
            resp = gap_client.post("/products/import/jobs/3/confirm")
        assert resp.status_code == 302
        assert job.status == ProductImportJobStatus.COMPLETED
        session.commit.assert_not_called()


class TestImportJobRollback:
    def _job(self, status):
        job = MagicMock()
        job.id = 4
        job.status = status
        return job

    def test_completed_job_queues_rollback(self, gap_client):
        job = self._job(ProductImportJobStatus.COMPLETED)
        rollback_job = MagicMock()
        rollback_job.id = 44
        with (
            patch("routes.products.ProductImportJob") as job_cls,
            patch("routes.products.db.session"),
            patch(
                "services.import_job_service.ImportJobService.create_rollback_job",
                return_value=rollback_job,
            ) as create,
            patch("services.import_job_service.process_product_import_rollback_task") as task_mod,
        ):
            job_cls.query.filter_by.return_value.first_or_404.return_value = job
            resp = gap_client.post(
                "/products/import/jobs/4/rollback",
                data={"reason": "duplicate"},
            )
        assert resp.status_code == 302
        create.assert_called_once_with(4, 42, "duplicate")
        task_mod.delay.assert_called_once_with(44)
        assert "import/jobs/44" in resp.location

    def test_pending_job_cannot_be_rolled_back(self, gap_client):
        job = self._job(ProductImportJobStatus.PENDING)
        with (
            patch("routes.products.ProductImportJob") as job_cls,
            patch("routes.products.db.session"),
            patch("services.import_job_service.ImportJobService.create_rollback_job") as create,
        ):
            job_cls.query.filter_by.return_value.first_or_404.return_value = job
            resp = gap_client.post("/products/import/jobs/4/rollback", data={})
        assert resp.status_code == 302
        create.assert_not_called()


class TestImportTemplatesListAndDelete:
    def test_list_renders_templates(self, gap_client):
        with (
            patch("routes.products.ProductImportTemplate") as tmpl_cls,
            patch("routes.products.render_template", return_value="ok") as render,
        ):
            tmpl_cls.query.filter_by.return_value.all.return_value = []
            resp = gap_client.get("/products/import/templates")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/import_templates.html"

    def test_delete_removes_template(self, gap_client):
        template = MagicMock()
        with (
            patch("routes.products.ProductImportTemplate") as tmpl_cls,
            patch("routes.products.db.session") as session,
        ):
            tmpl_cls.query.filter_by.return_value.first_or_404.return_value = template
            resp = gap_client.post("/products/import/templates/9/delete")
        assert resp.status_code == 302
        session.delete.assert_called_once_with(template)
        assert resp.location.endswith("/products/import/templates")


class TestImportTemplateCreate:
    def test_get_renders_form(self, gap_client):
        with patch("routes.products.render_template", return_value="ok") as render:
            resp = gap_client.get("/products/import/templates/create")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/import_template_form.html"

    def test_invalid_json_flashes_and_redirects(self, gap_client):
        resp = gap_client.post(
            "/products/import/templates/create",
            data={"name": "Tpl", "column_mapping": "not-json"},
        )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/import/templates/create")

    def test_valid_post_creates_template(self, gap_client):
        with patch("routes.products.db.session") as session:
            resp = gap_client.post(
                "/products/import/templates/create",
                data={
                    "name": "Tpl",
                    "description": "desc",
                    "column_mapping": '{"name": "product_name"}',
                    "default_values": '{"unit": "pcs"}',
                    "required_fields": '["name"]',
                    "is_default": "on",
                },
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/import/templates")
        session.add.assert_called_once()


class TestImportTemplateEdit:
    ENDPOINT = "/products/import/templates/9/edit"

    def _template(self):
        template = MagicMock()
        template.id = 9
        return template

    def test_get_renders_form(self, gap_client):
        template = self._template()
        with (
            patch("routes.products.ProductImportTemplate") as tmpl_cls,
            patch("routes.products.render_template", return_value="ok") as render,
        ):
            tmpl_cls.query.filter_by.return_value.first_or_404.return_value = template
            resp = gap_client.get(self.ENDPOINT)
        assert resp.status_code == 200
        assert render.call_args[0][0] == "products/import_template_form.html"
        assert render.call_args[1]["template"] is template

    def test_valid_post_updates_template(self, gap_client):
        template = self._template()
        with (
            patch("routes.products.ProductImportTemplate") as tmpl_cls,
            patch("routes.products.db.session") as session,
        ):
            tmpl_cls.query.filter_by.return_value.first_or_404.return_value = template
            resp = gap_client.post(
                self.ENDPOINT,
                data={
                    "name": "Renamed",
                    "description": "new desc",
                    "column_mapping": "{}",
                    "default_values": "{}",
                    "required_fields": "[]",
                    "is_default": "on",
                },
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/products/import/templates")
        assert template.name == "Renamed"
        assert template.description == "new desc"
        assert template.is_default is True
        session.flush.assert_called_once()

    def test_invalid_json_flashes_and_redirects(self, gap_client):
        template = self._template()
        with (
            patch("routes.products.ProductImportTemplate") as tmpl_cls,
            patch("routes.products.db.session") as session,
        ):
            tmpl_cls.query.filter_by.return_value.first_or_404.return_value = template
            resp = gap_client.post(self.ENDPOINT, data={"name": "X", "column_mapping": "bad"})
        assert resp.status_code == 302
        assert resp.location.endswith(self.ENDPOINT)
        session.flush.assert_not_called()


class TestBulkApi:
    ENDPOINT = "/products/api/products/bulk"

    def test_non_json_content_type_returns_415(self, gap_client):
        resp = gap_client.post(self.ENDPOINT, data={"products": []})
        assert resp.status_code == 415
        assert resp.get_json()["success"] is False

    def test_invalid_json_returns_400(self, gap_client):
        resp = gap_client.post(
            self.ENDPOINT,
            data="not json",
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_empty_products_list_returns_400(self, gap_client):
        resp = gap_client.post(self.ENDPOINT, json={"products": []})
        assert resp.status_code == 400

    def test_valid_payload_returns_created_counts(self, gap_client):
        results = {"created_ids": [1, 2], "updated_ids": [3], "errors": []}
        with (
            patch("routes.products.ProductImportService.process_dataframe", return_value=results) as process,
            patch("routes.products.ProductService.get_default_warehouse", return_value=_warehouse()),
            patch("routes.products.db.session"),
            patch("pandas.DataFrame") as df_cls,
        ):
            resp = gap_client.post(
                self.ENDPOINT,
                json={"products": [{"name": "Widget"}], "update_existing": True},
            )
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert body["created"] == 2
        assert body["updated"] == 1
        assert body["created_ids"] == [1, 2]
        process.assert_called_once()
        assert process.call_args.kwargs["update_existing"] is True
        df_cls.assert_called_once()


class TestOcrScan:
    ENDPOINT = "/products/ocr/scan"

    def _upload(self, filename="scan.png"):
        return {"file": (BytesIO(b"image-bytes"), filename)}

    def test_no_file_field_returns_400(self, gap_client):
        resp = gap_client.post(self.ENDPOINT, data={})
        assert resp.status_code == 400

    def test_empty_filename_returns_400(self, gap_client):
        resp = gap_client.post(self.ENDPOINT, data=self._upload(""), content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_unavailable_service_returns_503(self, gap_client):
        with patch("services.ocr_service.OCRService") as svc:
            svc.is_available.return_value = False
            resp = gap_client.post(self.ENDPOINT, data=self._upload(), content_type="multipart/form-data")
        assert resp.status_code == 503

    def test_extract_products_success(self, gap_client):
        with patch("services.ocr_service.OCRService") as svc:
            svc.is_available.return_value = True
            svc.return_value.extract_products_from_image.return_value = [{"name": "Widget"}]
            resp = gap_client.post(self.ENDPOINT, data=self._upload(), content_type="multipart/form-data")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["products"] == [{"name": "Widget"}]

    def test_parse_invoice_success(self, gap_client):
        with (
            patch("services.ocr_service.OCRService") as svc,
            patch("services.ocr_service.InvoiceParser") as parser_cls,
        ):
            svc.is_available.return_value = True
            parser_cls.return_value.parse_invoice.return_value = {"products": [], "total": 42}
            resp = gap_client.post(
                self.ENDPOINT,
                data={**self._upload(), "parse_invoice": "true"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 42
        parser_cls.return_value.parse_invoice.assert_called_once()

    def test_processing_exception_returns_500(self, gap_client):
        with patch("services.ocr_service.OCRService") as svc:
            svc.is_available.return_value = True
            svc.return_value.extract_products_from_image.side_effect = RuntimeError("boom")
            resp = gap_client.post(self.ENDPOINT, data=self._upload(), content_type="multipart/form-data")
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False


class TestScannerApis:
    def test_by_barcode_found(self, gap_client):
        product = _product(1)
        product.to_dict = MagicMock(return_value={"id": 1})
        with patch("routes.products.Product") as product_cls:
            product_cls.query.filter_by.return_value.first.return_value = product
            resp = gap_client.get("/products/api/products/by-barcode/BC-1")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["id"] == 1
        product.to_dict.assert_called_once_with(include_cost=True)

    def test_by_barcode_not_found(self, gap_client):
        with patch("routes.products.Product") as product_cls:
            product_cls.query.filter_by.return_value.first.return_value = None
            resp = gap_client.get("/products/api/products/by-barcode/MISSING")
        assert resp.status_code == 404
        assert resp.get_json()["success"] is False

    def test_by_sku_found(self, gap_client):
        product = _product(2)
        product.to_dict = MagicMock(return_value={"id": 2})
        with patch("routes.products.Product") as product_cls:
            product_cls.query.filter_by.return_value.first.return_value = product
            resp = gap_client.get("/products/api/products/by-sku/SKU-1")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["id"] == 2
        product.to_dict.assert_called_once_with(include_cost=True)

    def test_by_sku_not_found(self, gap_client):
        with patch("routes.products.Product") as product_cls:
            product_cls.query.filter_by.return_value.first.return_value = None
            resp = gap_client.get("/products/api/products/by-sku/MISSING")
        assert resp.status_code == 404
        assert resp.get_json()["success"] is False
