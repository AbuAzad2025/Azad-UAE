"""Unit tests for routes/owner/ai_training.py — guard + tenant-scoped flows.

The owner_required guard runs for real; service calls are mocked at the
route boundary.
"""

from __future__ import annotations

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


class TestOwnerTrainingGuard:
    def test_anonymous_gets_404(self, client):
        assert client.get("/owner/ai-training").status_code == 404

    def test_anonymous_post_gets_404(self, client):
        assert client.post("/owner/ai-training/qa").status_code == 404

    def test_non_owner_gets_404(self, auth_client):
        assert auth_client.get("/owner/ai-training").status_code == 404


class TestOwnerTrainingDashboard:
    def test_renders_with_tenant(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.list_memories", return_value=[]) as listed,
            patch("routes.owner.ai_training.count_memories", return_value={}),
            patch("routes.owner.ai_training.render_template", return_value="ok") as rendered,
        ):
            ops.get_tenant.return_value = _tenant_mock()
            ops.active_ai_tenants.return_value = []
            resp = owner_client.get("/owner/ai-training?tenant_id=7")
        assert resp.status_code == 200
        listed.assert_called_once_with(7, search="", category="", include_inactive=False)
        assert rendered.call_args.kwargs["tenant"].id == 7

    def test_unknown_tenant_404(self, owner_client):
        with patch("routes.owner.ai_training.OwnerOpsService") as ops:
            ops.get_tenant.return_value = None
            assert owner_client.get("/owner/ai-training?tenant_id=999").status_code == 404

    def test_no_tenant_renders_picker(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.render_template", return_value="ok"),
        ):
            ops.active_ai_tenants.return_value = []
            assert owner_client.get("/owner/ai-training").status_code == 200


class TestOwnerTrainingWrites:
    def test_add_qa_success(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.add_qa") as add_qa,
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/qa",
                data={"tenant_id": "7", "question": "Q?", "answer": "A.", "category": "general"},
            )
        assert resp.status_code == 302
        add_qa.assert_called_once_with("Q?", "A.", "general", 7)

    def test_add_qa_validation_error_redirects(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.add_qa", side_effect=ValueError("bad")),
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/qa",
                data={"tenant_id": "7", "question": "", "answer": ""},
            )
        assert resp.status_code == 302

    def test_toggle_success(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.toggle_memory") as toggled,
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/5/toggle",
                data={"tenant_id": "7", "active": "0"},
            )
        assert resp.status_code == 302
        toggled.assert_called_once_with(5, 7, False)

    def test_correct_success(self, owner_client):
        with (
            patch("routes.owner.ai_training.OwnerOpsService") as ops,
            patch("routes.owner.ai_training.submit_correction") as corrected,
        ):
            ops.get_tenant.return_value = _tenant_mock()
            resp = owner_client.post(
                "/owner/ai-training/correct",
                data={"tenant_id": "7", "question": "Q?", "correct_answer": "Right."},
            )
        assert resp.status_code == 302
        assert corrected.call_count == 1
