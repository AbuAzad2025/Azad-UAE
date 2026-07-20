from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import (
    _chain_query,
    unauthenticated_client,
)


def _mock_attendance(**kwargs):
    att = MagicMock()
    att.check_in = kwargs.get("check_in", datetime(2026, 6, 26, 9, 0))
    att.work_hours = kwargs.get("work_hours", 8)
    return att


def _mock_leave(**kwargs):
    leave = MagicMock()
    leave.id = kwargs.get("id", 1)
    leave.tenant_id = kwargs.get("tenant_id", 1)
    return leave


@contextmanager
def _hr_patches(**kwargs):
    kwargs.get("tid", 1)
    user_q = _chain_query(all=kwargs.get("users", []))

    with ExitStack() as stack:
        stack.enter_context(patch("routes.hr.render_template", return_value="ok"))
        stack.enter_context(patch("routes.hr.get_active_tenant_id", return_value=kwargs.get("tid", 1)))
        stack.enter_context(
            patch(
                "routes.hr.tenant_query",
                side_effect=lambda model: _chain_query(all=kwargs.get("leave_types", [])),
            )
        )
        stack.enter_context(
            patch(
                "routes.hr.HRService.report_attendance",
                return_value=kwargs.get("records", []),
            )
        )
        stack.enter_context(patch("routes.hr.HRService.list_leaves", return_value=kwargs.get("leaves", [])))
        stack.enter_context(
            patch(
                "routes.hr.HRService.list_departments",
                return_value=kwargs.get("departments", []),
            )
        )
        stack.enter_context(patch("routes.hr.HRService.clock_in", return_value=_mock_attendance()))
        stack.enter_context(
            patch(
                "routes.hr.HRService.clock_out",
                return_value=_mock_attendance(work_hours=7.5),
            )
        )
        stack.enter_context(patch("routes.hr.HRService.request_leave"))
        stack.enter_context(patch("routes.hr.HRService.approve_leave", return_value=_mock_leave()))
        stack.enter_context(patch("routes.hr.HRService.refuse_leave", return_value=_mock_leave()))
        stack.enter_context(patch("routes.hr.HRService.create_department"))
        stack.enter_context(patch("routes.hr.HRService.create_contract"))
        stack.enter_context(patch("routes.hr.User.query", user_q))
        stack.enter_context(patch("routes.hr.tenant_get_or_404", return_value=_mock_leave()))
        stack.enter_context(patch("extensions.limiter.limit", return_value=lambda f: f))
        yield


@pytest.fixture
def hr_client(app_factory, bypass_permission_auth):
    from routes.hr import hr_bp

    app = app_factory(hr_bp)
    return app.test_client()


class TestHrAuth:
    def test_attendance_requires_login(self, hr_client):
        with _hr_patches(), unauthenticated_client(hr_client):
            resp = hr_client.get("/hr/attendance")
        assert resp.status_code == 401

    def test_attendance_forbidden_without_permission(self, hr_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_super_admin.return_value = False
        with (
            _hr_patches(),
            patch("utils.decorators.is_global_owner_user", return_value=False),
        ):
            resp = hr_client.get("/hr/attendance")
        assert resp.status_code == 403


class TestHrAttendance:
    def test_attendance_renders(self, hr_client):
        with _hr_patches(records=[_mock_attendance()]):
            resp = hr_client.get("/hr/attendance")
        assert resp.status_code == 200

    def test_attendance_with_filters(self, hr_client):
        with _hr_patches():
            resp = hr_client.get("/hr/attendance?user_id=3&date_from=2026-01-01&date_to=2026-06-30")
        assert resp.status_code == 200

    def test_clock_in_success(self, hr_client):
        with _hr_patches():
            resp = hr_client.post(
                "/hr/attendance/clock-in",
                data={"branch_id": "2"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_clock_in_error(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.HRService.clock_in", side_effect=ValueError("already")),
        ):
            resp = hr_client.post("/hr/attendance/clock-in")
        assert resp.status_code == 302

    def test_clock_out_success(self, hr_client):
        with _hr_patches():
            resp = hr_client.post("/hr/attendance/clock-out")
        assert resp.status_code == 302

    def test_clock_out_error(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.HRService.clock_out", side_effect=ValueError("no session")),
        ):
            resp = hr_client.post("/hr/attendance/clock-out")
        assert resp.status_code == 302


class TestHrLeaves:
    def test_leaves_list(self, hr_client):
        with _hr_patches():
            resp = hr_client.get("/hr/leaves?state=draft")
        assert resp.status_code == 200

    def test_leaves_list_no_tenant(self, hr_client):
        with _hr_patches(tid=None):
            resp = hr_client.get("/hr/leaves")
        assert resp.status_code == 200

    def test_request_leave_get(self, hr_client):
        with _hr_patches():
            resp = hr_client.get("/hr/leaves/request")
        assert resp.status_code == 200

    def test_request_leave_post_success(self, hr_client):
        with _hr_patches():
            resp = hr_client.post(
                "/hr/leaves/request",
                data={
                    "leave_type_id": "1",
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-05",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_request_leave_post_error(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.HRService.request_leave", side_effect=ValueError("overlap")),
        ):
            resp = hr_client.post("/hr/leaves/request", data={})
        assert resp.status_code == 200

    def test_approve_leave_success(self, hr_client):
        with _hr_patches():
            resp = hr_client.post("/hr/leaves/5/approve")
        assert resp.status_code == 302

    def test_approve_leave_cross_tenant(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.tenant_get_or_404", side_effect=NotFound()),
        ):
            resp = hr_client.post("/hr/leaves/99/approve")
        assert resp.status_code == 404

    def test_approve_leave_value_error(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.HRService.approve_leave", side_effect=ValueError("not draft")),
        ):
            resp = hr_client.post("/hr/leaves/5/approve")
        assert resp.status_code == 302

    def test_refuse_leave_success(self, hr_client):
        with _hr_patches():
            resp = hr_client.post("/hr/leaves/5/refuse", data={"rejected_reason": "busy"})
        assert resp.status_code == 302

    def test_refuse_leave_cross_tenant(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.tenant_get_or_404", side_effect=NotFound()),
        ):
            resp = hr_client.post("/hr/leaves/8/refuse", data={"rejected_reason": "x"})
        assert resp.status_code == 404

    def test_refuse_leave_value_error(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.HRService.refuse_leave", side_effect=ValueError("gone")),
        ):
            resp = hr_client.post("/hr/leaves/5/refuse", data={"rejected_reason": "x"})
        assert resp.status_code == 302


class TestHrDepartments:
    def test_departments_list(self, hr_client):
        with _hr_patches():
            resp = hr_client.get("/hr/departments")
        assert resp.status_code == 200

    def test_create_department_success(self, hr_client):
        with _hr_patches():
            resp = hr_client.post("/hr/departments/create", data={"name": "Sales"})
        assert resp.status_code == 302

    def test_create_department_error(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.HRService.create_department", side_effect=ValueError("dup")),
        ):
            resp = hr_client.post("/hr/departments/create", data={})
        assert resp.status_code == 302

    def test_create_contract_success(self, hr_client):
        with _hr_patches():
            resp = hr_client.post(
                "/hr/contracts/create",
                data={
                    "user_id": "1",
                    "date_start": "2026-06-01",
                },
            )
        assert resp.status_code == 302

    def test_create_contract_error(self, hr_client):
        with (
            _hr_patches(),
            patch("routes.hr.HRService.create_contract", side_effect=KeyError("user_id")),
        ):
            resp = hr_client.post("/hr/contracts/create", data={})
        assert resp.status_code == 302
