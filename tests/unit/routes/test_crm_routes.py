from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import (
    _chain_query,
    unauthenticated_client,
)


def _mock_lead(**kwargs):
    lead = MagicMock()
    lead.id = kwargs.get("id", 1)
    lead.tenant_id = kwargs.get("tenant_id", 1)
    lead.name = kwargs.get("name", "Lead A")
    return lead


@contextmanager
def _crm_patches(**kwargs):
    leads = kwargs.get("leads", [])
    with ExitStack() as stack:
        stack.enter_context(patch("routes.crm.render_template", return_value="ok"))
        stack.enter_context(patch("routes.crm.get_active_tenant_id", return_value=kwargs.get("tid", 1)))
        stack.enter_context(patch("routes.crm.CRMLeadService.search_leads", return_value=leads))
        stack.enter_context(patch("routes.crm.CRMStage.query", _chain_query(all=kwargs.get("stages", []))))
        stack.enter_context(patch("routes.crm.CRMTeam.query", _chain_query(all=kwargs.get("teams", []))))
        stack.enter_context(
            patch(
                "routes.crm.Customer.query",
                _chain_query(all=kwargs.get("customers", [])),
            )
        )
        stack.enter_context(patch("routes.crm.User.query", _chain_query(all=kwargs.get("users", []))))
        stack.enter_context(patch("extensions.limiter.limit", return_value=lambda f: f))
        yield


@pytest.fixture
def crm_client(app_factory, bypass_permission_auth):
    from routes.crm import crm_bp

    app = app_factory(crm_bp)
    return app.test_client()


class TestCrmAuth:
    def test_pipeline_requires_login(self, crm_client):
        with _crm_patches(), unauthenticated_client(crm_client):
            resp = crm_client.get("/crm/pipeline")
        assert resp.status_code == 401

    def test_pipeline_forbidden_without_permission(self, crm_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_super_admin.return_value = False
        with (
            _crm_patches(),
            patch("utils.decorators.is_global_owner_user", return_value=False),
        ):
            resp = crm_client.get("/crm/pipeline")
        assert resp.status_code == 403


class TestCrmPipeline:
    def test_pipeline_renders(self, crm_client):
        with _crm_patches(leads=[_mock_lead()]):
            resp = crm_client.get("/crm/pipeline")
        assert resp.status_code == 200

    def test_pipeline_no_tenant(self, crm_client):
        with _crm_patches(tid=None, leads=[]):
            resp = crm_client.get("/crm/pipeline")
        assert resp.status_code == 200


class TestCrmLeadsList:
    def test_leads_list_renders(self, crm_client):
        with _crm_patches(leads=[_mock_lead()]):
            resp = crm_client.get("/crm/leads")
        assert resp.status_code == 200

    def test_leads_list_with_filters(self, crm_client):
        with _crm_patches():
            resp = crm_client.get("/crm/leads?stage_id=2&status=open&search=acme")
        assert resp.status_code == 200


class TestCrmCreateLead:
    def test_create_get(self, crm_client):
        with _crm_patches():
            resp = crm_client.get("/crm/leads/create")
        assert resp.status_code == 200

    def test_create_post_success(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.create_lead", return_value=_mock_lead()),
        ):
            resp = crm_client.post("/crm/leads/create", data={"name": "New Lead"}, follow_redirects=False)
        assert resp.status_code == 302
        assert "/crm/leads" in resp.location

    def test_create_post_error(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.create_lead", side_effect=ValueError("bad")),
        ):
            resp = crm_client.post("/crm/leads/create", data={"name": ""})
        assert resp.status_code == 200


class TestCrmLeadDetail:
    def test_detail_success(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.get_lead", return_value=_mock_lead()),
        ):
            resp = crm_client.get("/crm/leads/5")
        assert resp.status_code == 200

    def test_detail_not_found_redirects(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.get_lead", side_effect=ValueError("missing")),
        ):
            resp = crm_client.get("/crm/leads/99", follow_redirects=False)
        assert resp.status_code == 302
        assert "/crm/leads" in resp.location


class TestCrmEditLead:
    def test_edit_get(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.get_lead", return_value=_mock_lead()),
        ):
            resp = crm_client.get("/crm/leads/3/edit")
        assert resp.status_code == 200

    def test_edit_post_success(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.get_lead", return_value=_mock_lead()),
            patch("routes.crm.CRMLeadService.update_lead", return_value=_mock_lead()),
        ):
            resp = crm_client.post("/crm/leads/3/edit", data={"name": "Updated"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_post_error(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.get_lead", return_value=_mock_lead()),
            patch(
                "routes.crm.CRMLeadService.update_lead",
                side_effect=RuntimeError("fail"),
            ),
        ):
            resp = crm_client.post("/crm/leads/3/edit", data={"name": "X"})
        assert resp.status_code == 200

    def test_edit_missing_lead_redirects(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.get_lead", side_effect=ValueError("gone")),
        ):
            resp = crm_client.get("/crm/leads/404/edit", follow_redirects=False)
        assert resp.status_code == 302


class TestCrmApi:
    def test_move_stage_success(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.move_stage", return_value=_mock_lead()),
        ):
            resp = crm_client.post("/crm/api/move-stage", json={"lead_id": 1, "stage_id": 2})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_move_stage_bad_request(self, crm_client):
        with (
            _crm_patches(),
            patch(
                "routes.crm.CRMLeadService.move_stage",
                side_effect=ValueError("invalid"),
            ),
        ):
            resp = crm_client.post("/crm/api/move-stage", json={"lead_id": 1, "stage_id": 9})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_move_stage_missing_keys(self, crm_client):
        with _crm_patches():
            resp = crm_client.post("/crm/api/move-stage", json={})
        assert resp.status_code == 400

    def test_stats(self, crm_client):
        with (
            _crm_patches(),
            patch(
                "routes.crm.CRMLeadService.get_pipeline_stats",
                return_value=[{"count": 1}],
            ),
        ):
            resp = crm_client.get("/crm/api/stats")
        assert resp.status_code == 200
        assert resp.get_json()[0]["count"] == 1

    def test_add_activity_success(self, crm_client):
        with (
            _crm_patches(),
            patch("routes.crm.CRMLeadService.add_activity", return_value=MagicMock()),
        ):
            resp = crm_client.post("/crm/api/activities", json={"lead_id": 1, "summary": "call"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_add_activity_error(self, crm_client):
        with (
            _crm_patches(),
            patch(
                "routes.crm.CRMLeadService.add_activity",
                side_effect=KeyError("lead_id"),
            ),
        ):
            resp = crm_client.post("/crm/api/activities", json={"summary": "x"})
        assert resp.status_code == 400
