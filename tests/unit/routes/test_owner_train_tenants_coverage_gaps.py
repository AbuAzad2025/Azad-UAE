"""Coverage-gap tests for four owner route modules.

Targets (from the combined coverage report):
- routes/owner/ai_training_advanced.py  upload/progress/API/semantic branches
- routes/owner/ai_training.py           no-tenant + exception branches
- routes/owner/tenants.py               create default-users + edit tax/flags
- routes/owner/settings.py              shipping + sms integration branches

Service calls are mocked at the route boundary; the owner_required guard runs
for real through the bypass_owner_auth fixture.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp)
    return app.test_client()


def _tenant_mock(tenant_id=7):
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.is_active = True
    tenant.name = "T7"
    tenant.name_ar = "مستأجر ٧"
    return tenant


# ───────────────────────── ai_training_advanced.py ─────────────────────────


class TestAdvancedUploadBranches:
    def test_empty_filename_redirects(self, owner_client, tmp_path):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.UPLOAD_FOLDER", str(tmp_path)),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            resp = owner_client.post(
                "/owner/ai-training/upload?tenant_id=7",
                data={"file": (io.BytesIO(b"x"), ""), "tenant_id": "7"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        assert list(tmp_path.iterdir()) == []

    def test_no_tenant_after_file_redirects(self, owner_client, tmp_path):
        # No tenant_id means _resolve_training_tenant returns None without
        # aborting, so the POST reaches the `if not tenant:` guard (lines 85-86).
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.UPLOAD_FOLDER", str(tmp_path)),
        ):
            ops.active_ai_tenants.return_value = []
            resp = owner_client.post(
                "/owner/ai-training/upload",
                data={"file": (io.BytesIO(b"x"), "t.json")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_excel_upload_success(self, owner_client, tmp_path):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.training_importer") as imp,
            patch("routes.owner.ai_training_advanced.UPLOAD_FOLDER", str(tmp_path)),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            imp.get_safe_filename.return_value = "t.xlsx"
            imp.import_from_excel.return_value = {"success": True, "processed": 2, "total": 2}
            resp = owner_client.post(
                "/owner/ai-training/upload?tenant_id=7",
                data={"file": (io.BytesIO(b"xlsx"), "t.xlsx"), "tenant_id": "7"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302
        imp.import_from_excel.assert_called_once()

    def test_import_failure_flashes_error(self, owner_client, tmp_path):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.training_importer") as imp,
            patch("routes.owner.ai_training_advanced.UPLOAD_FOLDER", str(tmp_path)),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            imp.get_safe_filename.return_value = "t.json"
            imp.import_from_json.return_value = {"success": False, "error": "bad payload"}
            resp = owner_client.post(
                "/owner/ai-training/upload?tenant_id=7",
                data={"file": (io.BytesIO(b"{}"), "t.json"), "tenant_id": "7"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302

    def test_import_exception_flashes_error(self, owner_client, tmp_path):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.training_importer") as imp,
            patch("routes.owner.ai_training_advanced.UPLOAD_FOLDER", str(tmp_path)),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            imp.get_safe_filename.return_value = "t.json"
            imp.import_from_json.side_effect = RuntimeError("boom")
            resp = owner_client.post(
                "/owner/ai-training/upload?tenant_id=7",
                data={"file": (io.BytesIO(b"{}"), "t.json"), "tenant_id": "7"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 302


class TestAdvancedProgressNoTenant:
    def test_renders_picker_without_tenant(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.render_template", return_value="ok") as rendered,
        ):
            ops.active_ai_tenants.return_value = []
            assert owner_client.get("/owner/ai-training/progress").status_code == 200
        assert rendered.call_args.kwargs["progress_data"] == {}
        assert rendered.call_args.kwargs["metrics_data"] == {}


class TestAdvancedApisNoTenant:
    @pytest.mark.parametrize(
        "url",
        [
            "/owner/ai-training/metrics",
            "/owner/ai-training/concept/vat",
            "/owner/ai-training/knowledge-graph",
            "/owner/ai-training/health",
            "/owner/ai-training/batches",
        ],
    )
    def test_api_without_tenant_404(self, owner_client, url):
        assert owner_client.get(url).status_code == 404


class TestSemanticTrain:
    def test_no_tenant_404(self, owner_client):
        assert owner_client.post("/owner/ai-training/semantic-train", data={}).status_code == 404

    def test_missing_answer_redirects(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/semantic-train?tenant_id=7",
                data={"tenant_id": "7", "question": "Q?", "answer": "   "},
            )
        assert resp.status_code == 302
        assert "/owner/ai-training/progress" in resp.headers["Location"]

    def test_success(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.AdvancedTrainer") as trainer,
            patch("routes.owner.ai_training_advanced.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            trainer.return_value.train_semantic_model.return_value = {"concepts_extracted": 3}
            resp = owner_client.post(
                "/owner/ai-training/semantic-train?tenant_id=7",
                data={"tenant_id": "7", "question": "  Q?  ", "answer": "  A.  "},
            )
        assert resp.status_code == 302
        trainer.return_value.train_semantic_model.assert_called_once_with(7, "Q?", "A.")

    def test_trainer_exception_flashes_error(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.AdvancedTrainer") as trainer,
            patch("routes.owner.ai_training_advanced.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            trainer.return_value.train_semantic_model.side_effect = RuntimeError("boom")
            resp = owner_client.post(
                "/owner/ai-training/semantic-train?tenant_id=7",
                data={"tenant_id": "7", "question": "Q?", "answer": "A."},
            )
        assert resp.status_code == 302


# ──────────────────────────── ai_training.py ───────────────────────────────


class TestTrainingNoTenant:
    @pytest.mark.parametrize(
        ("url", "method"),
        [
            ("/owner/ai-training/qa", "post"),
            ("/owner/ai-training/5/toggle", "post"),
            ("/owner/ai-training/correct", "post"),
        ],
    )
    def test_write_without_tenant_404(self, owner_client, url, method):
        resp = getattr(owner_client, method)(url, data={})
        assert resp.status_code == 404


class TestTrainingExceptionBranches:
    def test_add_qa_generic_exception(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.add_qa", side_effect=RuntimeError("boom")),
            patch("routes.owner.ai_training.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/qa",
                data={"tenant_id": "7", "question": "Q?", "answer": "A."},
            )
        assert resp.status_code == 302

    def test_toggle_generic_exception(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.toggle_memory", side_effect=RuntimeError("boom")),
            patch("routes.owner.ai_training.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/5/toggle",
                data={"tenant_id": "7", "active": "1"},
            )
        assert resp.status_code == 302

    def test_correct_value_error(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.submit_correction", side_effect=ValueError("bad")),
            patch("routes.owner.ai_training.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/correct",
                data={"tenant_id": "7", "question": "Q?", "correct_answer": "A."},
            )
        assert resp.status_code == 302

    def test_correct_generic_exception(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.submit_correction", side_effect=RuntimeError("boom")),
            patch("routes.owner.ai_training.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/correct",
                data={"tenant_id": "7", "question": "Q?", "correct_answer": "A."},
            )
        assert resp.status_code == 302


# ────────────────────────────── tenants.py ─────────────────────────────────


def _tenant_for_edit(tid=2):
    t = MagicMock()
    t.id = tid
    t.name = "Acme"
    t.name_ar = "أكمي"
    t.name_en = "Acme"
    t.slug = "acme"
    t.is_active = True
    t.is_suspended = False
    t.tenant_id = tid
    t.vat_country = "AE"
    t.default_currency = "AED"
    t.business_type = "general"
    t.phone_1 = ""
    t.phone_2 = ""
    t.email = ""
    t.address_ar = ""
    t.max_users = 5
    t.max_products = 1000
    t.max_customers = 500
    t.max_suppliers = 200
    t.max_branches = 3
    t.max_warehouses = 2
    t.max_storage_mb = 1024
    t.max_invoices_per_month = 1000
    t.max_sales_per_month = 5000
    t.data_retention_days = 365
    t.enable_pos_promotions = None
    t.enable_pos_multi_tender = None
    t.enable_pos_returns = None
    t.enable_pos_shifts = None
    return t


def _post_create(client, data, *, role_result="default", user_result=None, enable_maintenance=True):
    role = MagicMock()
    role.id = 5
    role.slug = "super_admin"
    with (
        patch("services.owner_ops_service.OwnerOpsService.active_packages_sorted", return_value=[]),
        patch("services.owner_ops_service.OwnerOpsService.find_tenant_by_slug", return_value=None),
        patch("routes.owner.tenants.Tenant") as tcls,
        patch("routes.owner.tenants.db.session"),
        patch("models.ensure_default_pos_order_types", return_value=None),
        patch("services.gl_service.GLService.ensure_core_accounts", return_value=None),
        patch("services.gl_service.GLService.ensure_gl_mappings", return_value=None),
        patch("models.Role") as role_cls,
        patch("models.User") as user_cls,
    ):
        tcls.return_value = MagicMock(id=11, enable_maintenance=enable_maintenance)
        role_cls.query.filter_by.return_value.first.return_value = role if role_result == "default" else role_result
        user_cls.query.filter_by.return_value.first.return_value = user_result
        return client.post("/owner/tenants/create", data=data)


class TestTenantCreateGaps:
    def test_invalid_vat_country_falls_back(self, owner_client):
        resp = _post_create(
            owner_client,
            {
                "name_ar": "شركة",
                "slug": "gap-co-1",
                "default_currency": "AED",
                "vat_country": "ZZ",
            },
        )
        assert resp.status_code in (200, 302, 303)

    def test_admin_password_creates_default_users(self, owner_client):
        resp = _post_create(
            owner_client,
            {
                "name_ar": "شركة",
                "slug": "gap-co-2",
                "default_currency": "AED",
                "vat_country": "AE",
                "admin_password": "StrongPass123",
                "enable_pos": "on",
                "enable_gl": "on",
            },
        )
        assert resp.status_code in (200, 302, 303)

    def test_default_users_skip_missing_role_and_disabled_features(self, owner_client):
        resp = _post_create(
            owner_client,
            {
                "name_ar": "شركة",
                "slug": "gap-co-3",
                "default_currency": "AED",
                "admin_password": "StrongPass123",
            },
            role_result=None,
            enable_maintenance=False,
        )
        assert resp.status_code in (200, 302, 303)

    def test_default_users_skip_existing_username(self, owner_client):
        resp = _post_create(
            owner_client,
            {
                "name_ar": "شركة",
                "slug": "gap-co-4",
                "default_currency": "AED",
                "admin_password": "StrongPass123",
            },
            user_result=MagicMock(),
        )
        assert resp.status_code in (200, 302, 303)


class TestTenantEditGaps:
    def test_invalid_tax_number(self, owner_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant_for_edit(),
            ),
            patch("routes.owner.tenants.db.session"),
            patch("routes.owner.tenants.render_template", return_value="form"),
        ):
            resp = owner_client.post(
                "/owner/tenants/2/edit",
                data={"name_ar": "أكمي", "vat_country": "AE", "vat_number": "abc"},
            )
        assert resp.status_code in (200, 302, 303)

    def test_invoice_template_and_feature_flags(self, owner_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant_for_edit(),
            ),
            patch("routes.owner.tenants.db.session"),
            patch("routes.owner.tenants.render_template", return_value="form"),
        ):
            resp = owner_client.post(
                "/owner/tenants/2/edit",
                data={
                    "name_ar": "أكمي",
                    "active_invoice_template": "classic",
                    "profile_feature_fields": "1",
                    "enable_pos": "on",
                },
            )
        assert resp.status_code in (200, 302, 303)


# ───────────────────────────── settings.py ─────────────────────────────────


def _post_integration(client, service, data, *, tenant_id=1):
    integration = MagicMock()
    cls = MagicMock()
    cls.get_service_config.return_value = integration
    with (
        patch("routes.owner.settings.IntegrationSettings", cls),
        patch("routes.owner.settings.get_active_tenant_id", return_value=tenant_id),
        patch("routes.owner.settings._invalidate_owner_changes"),
        patch("services.shipping_config_service.ShippingConfigService") as shipping,
    ):
        resp = client.post(f"/owner/integrations/update/{service}", data=data)
    return resp, integration, shipping


class TestIntegrationCarrierBranches:
    def test_shipping_branch_sets_all_carrier_secrets(self, owner_client):
        resp, integration, shipping = _post_integration(
            owner_client,
            "shipping",
            {
                "enabled": "on",
                "dhl_api_key": "dhl-key",
                "fedex_client_id": "fid",
                "fedex_client_secret": "fsecret",
                "aramex_username": "auser",
                "aramex_password": "apass",
                "aramex_account_number": "acct",
                "aramex_pin": "pin",
            },
        )
        assert resp.status_code == 302
        assert shipping.set_carrier_secret.call_count == 7
        integration.set_config.assert_called_once_with({})

    def test_sms_branch_sets_all_sms_secrets(self, owner_client):
        resp, integration, shipping = _post_integration(
            owner_client,
            "sms",
            {
                "enabled": "on",
                "sms_provider": "twilio",
                "sms_account_sid": "sid",
                "sms_auth_token": "token",
                "sms_from_number": "+971500000000",
            },
        )
        assert resp.status_code == 302
        assert shipping.set_sms_secret.call_count == 3
        integration.set_config.assert_called_once_with({"provider": "twilio"})

    @pytest.mark.parametrize("service", ["shipping", "sms"])
    def test_carrier_branch_without_active_tenant(self, owner_client, service):
        resp, _, shipping = _post_integration(owner_client, service, {}, tenant_id=None)
        assert resp.status_code == 400
        if service == "shipping":
            shipping.set_carrier_secret.assert_not_called()
        else:
            shipping.set_sms_secret.assert_not_called()
