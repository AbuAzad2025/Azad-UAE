"""Unit tests for routes/owner/ai_training_advanced.py — guard + upload/progress flows.

The owner_required guard runs for real; service calls are mocked at the
route boundary.
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


class TestAdvancedGuard:
    def test_anonymous_upload_gets_404(self, client):
        assert client.get("/owner/ai-training/upload").status_code == 404

    def test_anonymous_progress_gets_404(self, client):
        assert client.get("/owner/ai-training/progress").status_code == 404

    def test_anonymous_metrics_gets_404(self, client):
        assert client.get("/owner/ai-training/metrics").status_code == 404

    def test_non_owner_upload_gets_404(self, auth_client):
        assert auth_client.get("/owner/ai-training/upload").status_code == 404

    def test_non_owner_progress_gets_404(self, auth_client):
        assert auth_client.get("/owner/ai-training/progress").status_code == 404


class TestUploadPage:
    def test_renders_picker_without_tenant(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.render_template", return_value="ok"),
        ):
            ops.active_ai_tenants.return_value = []
            assert owner_client.get("/owner/ai-training/upload").status_code == 200

    def test_unknown_tenant_404(self, owner_client):
        with patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops:
            ops.get_tenant.return_value = None
            assert owner_client.get("/owner/ai-training/upload?tenant_id=999").status_code == 404

    def test_rejects_bad_extension(self, owner_client):
        with patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops:
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            data = {"file": (io.BytesIO(b"evil"), "evil.exe"), "tenant_id": "7"}
            resp = owner_client.post(
                "/owner/ai-training/upload?tenant_id=7",
                data=data,
                content_type="multipart/form-data",
            )
            assert resp.status_code == 302

    def test_json_upload_success(self, owner_client):
        payload = b'{"training_data": [{"question": "Q?", "answer": "A"}]}'
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.training_importer") as imp,
        ):
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            imp.get_safe_filename.return_value = "t.json"
            imp.import_from_json.return_value = {
                "success": True,
                "processed": 1,
                "total": 1,
            }
            data = {"file": (io.BytesIO(payload), "t.json"), "tenant_id": "7"}
            resp = owner_client.post(
                "/owner/ai-training/upload?tenant_id=7",
                data=data,
                content_type="multipart/form-data",
            )
            assert resp.status_code == 302
            imp.import_from_json.assert_called_once()

    def test_no_file_redirects(self, owner_client):
        with patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops:
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            resp = owner_client.post(
                "/owner/ai-training/upload?tenant_id=7",
                data={"tenant_id": "7"},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 302


class TestProgressPage:
    def test_renders_with_tenant(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.get_training_progress", return_value={}),
            patch("routes.owner.ai_training_advanced.get_training_metrics", return_value={}),
            patch("routes.owner.ai_training_advanced.get_training_health_report", return_value={}),
            patch("routes.owner.ai_training_advanced.get_learning_velocity", return_value={}),
            patch("routes.owner.ai_training_advanced.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            assert owner_client.get("/owner/ai-training/progress?tenant_id=7").status_code == 200


class TestJsonApis:
    def test_metrics_requires_tenant(self, owner_client):
        with patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops:
            ops.get_tenant.return_value = None
            assert owner_client.get("/owner/ai-training/metrics?tenant_id=999").status_code == 404

    def test_metrics_ok(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch(
                "routes.owner.ai_training_advanced.get_training_metrics",
                return_value={"tenant_id": 7},
            ),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.get("/owner/ai-training/metrics?tenant_id=7")
            assert resp.status_code == 200
            assert resp.get_json() == {"tenant_id": 7}

    def test_health_ok(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch(
                "routes.owner.ai_training_advanced.get_training_health_report",
                return_value={"health_score": 90},
            ),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.get("/owner/ai-training/health?tenant_id=7")
            assert resp.status_code == 200

    def test_knowledge_graph_ok(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch(
                "routes.owner.ai_training_advanced.get_knowledge_graph_relationships",
                return_value=[],
            ),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.get("/owner/ai-training/knowledge-graph?tenant_id=7")
            assert resp.status_code == 200
            assert resp.get_json() == {"relationships": []}

    def test_concept_ok(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch(
                "routes.owner.ai_training_advanced.get_concept_details",
                return_value={"found": False},
            ),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.get("/owner/ai-training/concept/vat?tenant_id=7")
            assert resp.status_code == 200

    def test_batches_ok(self, owner_client):
        with (
            patch("routes.owner.ai_training_advanced.OwnerOpsService") as ops,
            patch("routes.owner.ai_training_advanced.render_template", return_value="ok"),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            assert owner_client.get("/owner/ai-training/batches?tenant_id=7").status_code == 200
