from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


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


def _mock_balance(**kwargs):
    bal = MagicMock()
    bal.id = kwargs.get("id", 1)
    return bal


def _mock_overtime(**kwargs):
    entry = MagicMock()
    entry.id = kwargs.get("id", 10)
    entry.status = kwargs.get("status", "pending")
    entry.tenant_id = kwargs.get("tenant_id", 1)
    return entry


@contextmanager
def _hr_patches(**kwargs):
    tid = kwargs.get("tid", 1)
    with ExitStack() as stack:
        stack.enter_context(patch("routes.hr.render_template", return_value="ok"))
        stack.enter_context(patch("routes.hr.get_active_tenant_id", return_value=tid))
        stack.enter_context(
            patch(
                "routes.hr.tenant_query",
                side_effect=lambda model: _chain_query(all=kwargs.get("leave_types", [])),
            )
        )
        stack.enter_context(
            patch("routes.hr.HRService.report_attendance", return_value=kwargs.get("records", []))
        )
        stack.enter_context(patch("routes.hr.HRService.list_leaves", return_value=kwargs.get("leaves", [])))
        stack.enter_context(
            patch("routes.hr.HRService.list_departments", return_value=kwargs.get("departments", []))
        )
        stack.enter_context(
            patch("routes.hr.HRService.list_active_users", return_value=kwargs.get("users", []))
        )
        stack.enter_context(patch("routes.hr.HRService.clock_in", return_value=_mock_attendance()))
        stack.enter_context(
            patch("routes.hr.HRService.clock_out", return_value=_mock_attendance(work_hours=7.5))
        )
        stack.enter_context(patch("routes.hr.HRService.request_leave"))
        stack.enter_context(patch("routes.hr.HRService.approve_leave", return_value=_mock_leave()))
        stack.enter_context(patch("routes.hr.HRService.refuse_leave", return_value=_mock_leave()))
        stack.enter_context(patch("routes.hr.HRService.create_department"))
        stack.enter_context(patch("routes.hr.HRService.create_contract"))
        stack.enter_context(
            patch("routes.hr.LeaveBalanceService.list_balances", return_value=kwargs.get("balances", []))
        )
        stack.enter_context(
            patch("routes.hr.LeaveBalanceService.accrue_leave", return_value=_mock_balance())
        )
        stack.enter_context(
            patch("routes.hr.LeaveBalanceService.carry_forward_leave", return_value=_mock_balance())
        )
        stack.enter_context(
            patch("routes.hr.OvertimeService.list_entries", return_value=kwargs.get("overtime", []))
        )
        stack.enter_context(patch("routes.hr.OvertimeService.create_entry", return_value=_mock_overtime()))
        stack.enter_context(patch("routes.hr.OvertimeService.approve_entry", return_value=_mock_overtime()))
        stack.enter_context(patch("routes.hr.OvertimeService.reject_entry", return_value=_mock_overtime()))
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


class TestHrLeaveLedger:
    def test_leave_ledger_without_user(self, hr_client):
        with _hr_patches():
            resp = hr_client.get("/hr/leave-ledger")
        assert resp.status_code == 200

    def test_leave_ledger_with_user_and_year(self, hr_client):
        balances = [_mock_balance()]
        with _hr_patches(balances=balances):
            resp = hr_client.get("/hr/leave-ledger?user_id=42&year=2025")
        assert resp.status_code == 200

    def test_leave_ledger_no_tenant(self, hr_client):
        with _hr_patches(tid=None):
            resp = hr_client.get("/hr/leave-ledger?user_id=1&year=2026")
        assert resp.status_code == 200

    def test_leave_ledger_default_year(self, hr_client):
        with _hr_patches():
            resp = hr_client.get("/hr/leave-ledger?user_id=5")
        assert resp.status_code == 200


class TestHrAccrueLeave:
    def test_accrue_success_with_year_query(self, hr_client):
        with _hr_patches() as _p:
            with patch("routes.hr.LeaveBalanceService.accrue_leave", return_value=_mock_balance()) as mocked:
                resp = hr_client.post(
                    "/hr/leave-ledger/accrue?year=2025",
                    data={"user_id": "10", "leave_type_id": "2", "days": "3"},
                    follow_redirects=False,
                )
        assert resp.status_code == 302
        mocked.assert_called_once()
        call_kwargs = mocked.call_args[0]
        assert call_kwargs[0] == 10
        assert call_kwargs[1] == 2
        assert call_kwargs[2] == 2025

    def test_accrue_success_default_year_and_days(self, hr_client):
        with _hr_patches():
            with patch("routes.hr.LeaveBalanceService.accrue_leave", return_value=_mock_balance()) as mocked:
                resp = hr_client.post(
                    "/hr/leave-ledger/accrue",
                    data={"user_id": "7", "leave_type_id": "1"},
                    follow_redirects=False,
                )
            assert resp.status_code == 302
            mocked.assert_called_once()

    def test_accrue_value_error(self, hr_client):
        with _hr_patches(), patch(
            "routes.hr.LeaveBalanceService.accrue_leave", side_effect=ValueError("bad days")
        ):
            resp = hr_client.post(
                "/hr/leave-ledger/accrue",
                data={"user_id": "7", "leave_type_id": "1", "days": "abc"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_accrue_missing_user_id_key_error(self, hr_client):
        with _hr_patches():
            resp = hr_client.post(
                "/hr/leave-ledger/accrue",
                data={"leave_type_id": "1"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_accrue_invalid_leave_type(self, hr_client):
        with _hr_patches(), patch(
            "routes.hr.LeaveBalanceService.accrue_leave", side_effect=KeyError("leave_type_id")
        ):
            resp = hr_client.post(
                "/hr/leave-ledger/accrue",
                data={"user_id": "1", "leave_type_id": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 302


class TestHrCarryForward:
    def test_carry_forward_success(self, hr_client):
        with _hr_patches():
            with patch("routes.hr.LeaveBalanceService.carry_forward_leave", return_value=_mock_balance()) as mocked:
                resp = hr_client.post(
                    "/hr/leave-ledger/carry-forward",
                    data={"user_id": "5", "leave_type_id": "2", "from_year": "2024"},
                    follow_redirects=False,
                )
            assert resp.status_code == 302
            mocked.assert_called_once_with(5, 2, 2024, 1)

    def test_carry_forward_value_error(self, hr_client):
        with _hr_patches(), patch(
            "routes.hr.LeaveBalanceService.carry_forward_leave", side_effect=ValueError("no balance")
        ):
            resp = hr_client.post(
                "/hr/leave-ledger/carry-forward",
                data={"user_id": "5", "leave_type_id": "2", "from_year": "2024"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_carry_forward_missing_fields(self, hr_client):
        with _hr_patches():
            resp = hr_client.post(
                "/hr/leave-ledger/carry-forward",
                data={"user_id": "5"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_carry_forward_no_tenant(self, hr_client):
        with _hr_patches(tid=None), patch(
            "routes.hr.LeaveBalanceService.carry_forward_leave", return_value=None
        ) as mocked:
            resp = hr_client.post(
                "/hr/leave-ledger/carry-forward",
                data={"user_id": "5", "leave_type_id": "1", "from_year": "2024"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mocked.assert_called_once()


class TestHrOvertime:
    def test_overtime_list_renders(self, hr_client):
        with _hr_patches():
            resp = hr_client.get("/hr/overtime")
        assert resp.status_code == 200

    def test_overtime_list_with_filters(self, hr_client):
        with _hr_patches():
            resp = hr_client.get("/hr/overtime?user_id=3&status=pending")
        assert resp.status_code == 200

    def test_create_overtime_success(self, hr_client):
        with _hr_patches():
            with patch("routes.hr.OvertimeService.create_entry", return_value=_mock_overtime()) as mocked:
                resp = hr_client.post(
                    "/hr/overtime/create",
                    data={
                        "user_id": "10",
                        "overtime_date": "2026-06-26",
                        "hours": "3.5",
                        "rate_multiplier": "1.5",
                        "overtime_type": "weekend",
                        "notes": "urgent",
                    },
                    follow_redirects=False,
                )
            assert resp.status_code == 302
            mocked.assert_called_once()
            assert mocked.call_args[0][0]["user_id"] == "10"

    def test_create_overtime_default_multiplier(self, hr_client):
        with _hr_patches():
            resp = hr_client.post(
                "/hr/overtime/create",
                data={"user_id": "10", "overtime_date": "2026-06-26", "hours": "2"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_overtime_value_error(self, hr_client):
        with _hr_patches(), patch(
            "routes.hr.OvertimeService.create_entry", side_effect=ValueError("hours required")
        ):
            resp = hr_client.post(
                "/hr/overtime/create",
                data={"user_id": "10", "overtime_date": "2026-06-26", "hours": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_overtime_key_error(self, hr_client):
        with _hr_patches(), patch(
            "routes.hr.OvertimeService.create_entry", side_effect=KeyError("user_id")
        ):
            resp = hr_client.post("/hr/overtime/create", data={}, follow_redirects=False)
        assert resp.status_code == 302

    def test_approve_overtime_success(self, hr_client):
        entry = _mock_overtime(status="pending")
        with _hr_patches():
            with patch("routes.hr.tenant_get_or_404", return_value=entry), patch(
                "routes.hr.OvertimeService.approve_entry", return_value=entry
            ) as mocked:
                resp = hr_client.post("/hr/overtime/10/approve", follow_redirects=False)
            assert resp.status_code == 302
            mocked.assert_called_once()

    def test_approve_overtime_value_error(self, hr_client):
        entry = _mock_overtime(status="pending")
        with _hr_patches():
            with patch("routes.hr.tenant_get_or_404", return_value=entry), patch(
                "routes.hr.OvertimeService.approve_entry", side_effect=ValueError("already approved")
            ):
                resp = hr_client.post("/hr/overtime/10/approve", follow_redirects=False)
            assert resp.status_code == 302

    def test_approve_overtime_not_found(self, hr_client):
        with _hr_patches():
            with patch("routes.hr.tenant_get_or_404", side_effect=NotFound()):
                resp = hr_client.post("/hr/overtime/999/approve", follow_redirects=False)
            assert resp.status_code == 404

    def test_reject_overtime_success(self, hr_client):
        entry = _mock_overtime(status="pending")
        with _hr_patches():
            with patch("routes.hr.tenant_get_or_404", return_value=entry), patch(
                "routes.hr.OvertimeService.reject_entry", return_value=entry
            ) as mocked:
                resp = hr_client.post(
                    "/hr/overtime/10/reject", data={"reason": "not needed"}, follow_redirects=False
                )
            assert resp.status_code == 302
            mocked.assert_called_once()

    def test_reject_overtime_value_error(self, hr_client):
        entry = _mock_overtime(status="pending")
        with _hr_patches():
            with patch("routes.hr.tenant_get_or_404", return_value=entry), patch(
                "routes.hr.OvertimeService.reject_entry", side_effect=ValueError("already")
            ):
                resp = hr_client.post("/hr/overtime/10/reject", data={}, follow_redirects=False)
            assert resp.status_code == 302

    def test_reject_overtime_not_found(self, hr_client):
        with _hr_patches():
            with patch("routes.hr.tenant_get_or_404", side_effect=NotFound()):
                resp = hr_client.post("/hr/overtime/999/reject", data={}, follow_redirects=False)
            assert resp.status_code == 404
