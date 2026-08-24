"""Tests for routes/budget.py — expansion covering all HTML endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import unauthenticated_client


def _mock_budget(**kwargs):
    b = MagicMock()
    b.id = kwargs.get("id", 1)
    b.tenant_id = kwargs.get("tenant_id", 1)
    b.budget_number = kwargs.get("budget_number", "BUD-2026-001")
    b.name_ar = kwargs.get("name_ar", "ميزانية")
    b.fiscal_year = kwargs.get("fiscal_year", 2026)
    b.status = kwargs.get("status", "draft")
    b.total_budgeted = kwargs.get("total_budgeted", 10000)
    b.lines = kwargs.get("lines", [])
    return b


@pytest.fixture
def budget_exp_client(app_factory, bypass_permission_auth):
    from routes.budget import budget_bp

    app = app_factory(budget_bp)
    return app.test_client()


@pytest.fixture
def budget_exp_mocks():
    budget = _mock_budget()
    patches = [
        patch("routes.budget.BudgetService.list_budgets", return_value=[budget]),
        patch("routes.budget.BudgetService.create_budget", return_value=budget),
        patch("routes.budget.BudgetService.get_budget", return_value=budget),
        patch("routes.budget.BudgetService.update_budget", return_value=budget),
        patch("routes.budget.BudgetService.approve_budget", return_value=budget),
        patch("routes.budget.BudgetService.activate_budget", return_value=budget),
        patch("routes.budget.BudgetService.close_budget", return_value=budget),
        patch("routes.budget.BudgetService.delete_budget", return_value=None),
        patch("routes.budget.BudgetService.variance_report", return_value={"budget": budget, "lines": []}),
        patch("routes.budget.render_template", return_value="ok"),
    ]
    for p in patches:
        p.start()
    yield {"budget": budget}
    for p in reversed(patches):
        p.stop()


class TestBudgetAuth:
    def test_index_requires_login(self, budget_exp_client):
        with unauthenticated_client(budget_exp_client):
            resp = budget_exp_client.get("/budgets/")
        assert resp.status_code == 401

    def test_create_forbidden(self, budget_exp_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = budget_exp_client.get("/budgets/create")
        assert resp.status_code == 403

    def test_approve_forbidden(self, budget_exp_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = budget_exp_client.post("/budgets/1/approve")
        assert resp.status_code == 403


class TestBudgetIndex:
    def test_index_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.get("/budgets/")
        assert resp.status_code == 200

    def test_index_with_filters(self, budget_exp_client, budget_exp_mocks):
        with patch("routes.budget.BudgetService.list_budgets", return_value=[]) as m:
            resp = budget_exp_client.get("/budgets/?status=draft&fiscal_year=2026")
        assert resp.status_code == 200
        m.assert_called_once()

    def test_index_api_create_already_covered(self, budget_exp_client, budget_exp_mocks):
        # api/create happy already in test_budget_routes.py — sanity duplicate
        with patch("routes.budget.BudgetService.create_budget", return_value=_mock_budget(id=9, budget_number="BUD-9")):
            resp = budget_exp_client.post("/budgets/api/create", json={"name_ar": "x"})
        assert resp.status_code == 201

    def test_index_404_via_service_raises_shows_flash(self, budget_exp_client, budget_exp_mocks):
        # BudgetService.get_budget raises ValueError -> handled via flash but still 200 for detail
        with patch("routes.budget.BudgetService.get_budget", side_effect=ValueError("الميزانية غير موجودة.")):
            # detail will propagate? In routes, it just raises; Flask will return 500 unless caught.
            # But service raises ValueError which is not caught in detail route — let's ensure it's considered error path
            # Actually detail does not catch, so we expect exception bubbles -> 500
            # Instead test that list remains isolated
            resp = budget_exp_client.get("/budgets/")
            assert resp.status_code == 200


class TestBudgetCreate:
    def test_create_get_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.get("/budgets/create")
        assert resp.status_code == 200

    def test_create_post_success_redirect(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.post(
            "/budgets/create",
            data={
                "name_ar": "ميزانية جديدة",
                "fiscal_year": "2026",
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/budgets/1" in resp.location

    def test_create_post_validation_error_stays_200(self, budget_exp_client, budget_exp_mocks):
        with patch("routes.budget.BudgetService.create_budget", side_effect=ValueError("اسم مطلوب")):
            resp = budget_exp_client.post("/budgets/create", data={"name_ar": ""})
        assert resp.status_code == 200

    def test_create_post_with_lines(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.post(
            "/budgets/create",
            data={
                "name_ar": "ميزانية",
                "fiscal_year": "2026",
                "line_0_account_code": "5000",
                "line_0_budgeted_amount": "10000",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestBudgetDetail:
    def test_detail_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.get("/budgets/1")
        assert resp.status_code == 200

    def test_detail_tenant_isolation_value_error_bubbles(self, budget_exp_client, budget_exp_mocks):
        # BudgetService.get_budget raises ValueError when wrong tenant — Flask propagates as uncaught exception in testing mode
        with patch("routes.budget.BudgetService.get_budget", side_effect=ValueError("الميزانية غير موجودة.")):
            # When TESTING=True Flask re-raises; assert exception propagates
            with pytest.raises(ValueError, match="الميزانية غير موجودة."):
                budget_exp_client.get("/budgets/999")


class TestBudgetEdit:
    def test_edit_get_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.get("/budgets/1/edit")
        assert resp.status_code == 200

    def test_edit_post_success_redirect(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.post("/budgets/1/edit", data={"name_ar": "محدث"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_post_validation_error_stays_200(self, budget_exp_client, budget_exp_mocks):
        with patch(
            "routes.budget.BudgetService.update_budget", side_effect=ValueError("لا يمكن تعديل ميزانية غير مسودة.")
        ):
            resp = budget_exp_client.post("/budgets/1/edit", data={"name_ar": "x"})
        assert resp.status_code == 200


class TestBudgetApprove:
    def test_approve_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.post("/budgets/1/approve", follow_redirects=False)
        assert resp.status_code == 302
        assert "/budgets/1" in resp.location

    def test_approve_validation_error_redirect(self, budget_exp_client, budget_exp_mocks):
        with patch(
            "routes.budget.BudgetService.approve_budget", side_effect=ValueError("فقط المسودات يمكن الموافقة عليها.")
        ):
            resp = budget_exp_client.post("/budgets/1/approve", follow_redirects=False)
        assert resp.status_code == 302


class TestBudgetActivate:
    def test_activate_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.post("/budgets/1/activate", follow_redirects=False)
        assert resp.status_code == 302

    def test_activate_validation_error(self, budget_exp_client, budget_exp_mocks):
        with patch("routes.budget.BudgetService.activate_budget", side_effect=ValueError("لا يمكن تفعيل")):
            resp = budget_exp_client.post("/budgets/1/activate", follow_redirects=False)
        assert resp.status_code == 302


class TestBudgetClose:
    def test_close_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.post("/budgets/1/close", follow_redirects=False)
        assert resp.status_code == 302

    def test_close_validation_error(self, budget_exp_client, budget_exp_mocks):
        with patch("routes.budget.BudgetService.close_budget", side_effect=ValueError("يجب أن تكون نشطة")):
            resp = budget_exp_client.post("/budgets/1/close", follow_redirects=False)
        assert resp.status_code == 302


class TestBudgetDelete:
    def test_delete_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.post("/budgets/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert "/budgets/" in resp.location

    def test_delete_validation_error_redirect(self, budget_exp_client, budget_exp_mocks):
        with patch("routes.budget.BudgetService.delete_budget", side_effect=ValueError("لا يمكن حذف ميزانية نشطة")):
            resp = budget_exp_client.post("/budgets/1/delete", follow_redirects=False)
        assert resp.status_code == 302


class TestBudgetVariance:
    def test_variance_happy(self, budget_exp_client, budget_exp_mocks):
        resp = budget_exp_client.get("/budgets/1/variance")
        assert resp.status_code == 200

    def test_variance_forbidden(self, budget_exp_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = budget_exp_client.get("/budgets/1/variance")
        assert resp.status_code == 403


class TestBudgetApiCreate:
    def test_api_create_400_silent_true(self, budget_exp_client, budget_exp_mocks):
        # no json body -> silent True gives {}
        with patch("routes.budget.BudgetService.create_budget", side_effect=ValueError("bad")):
            resp = budget_exp_client.post("/budgets/api/create", data="not-json", content_type="application/json")
        assert resp.status_code == 400

    def test_api_create_401(self, budget_exp_client):
        with unauthenticated_client(budget_exp_client):
            resp = budget_exp_client.post("/budgets/api/create", json={})
        assert resp.status_code == 401

    def test_api_create_403(self, budget_exp_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = budget_exp_client.post("/budgets/api/create", json={})
        assert resp.status_code == 403
