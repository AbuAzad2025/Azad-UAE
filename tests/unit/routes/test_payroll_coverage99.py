"""Coverage-99 boost for routes/payroll.py uncovered lines:
63-68 (branch mismatch), 91/95/110-111 (advance validation + generic exc),
129/136/149-150 (generate_branch validation + generic exc),
155/174-175 (single-process validation + generic exc).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.unit.routes.test_payroll_routes import _payroll_patches


@pytest.fixture
def payroll_client(app_factory, bypass_permission_auth):
    from routes.payroll import payroll_bp

    app = app_factory(payroll_bp)
    return app.test_client()


def test_add_employee_post_no_name(payroll_client):
    """L60-61: missing employee name -> ValueError caught by generic except."""
    with _payroll_patches(branch_scope=2):
        resp = payroll_client.post(
            "/payroll/employees/add",
            data={"branch_id": "9"},
            follow_redirects=False,
        )
    assert resp.status_code == 200


def test_advances_post_missing_employee_id(payroll_client):
    """L91: raise ValueError("معرف الموظف مطلوب")."""
    with _payroll_patches():
        resp = payroll_client.post(
            "/payroll/advances",
            data={"amount": "100", "description": "x"},
        )
    assert resp.status_code == 200


def test_advances_post_missing_amount(payroll_client):
    """L95: raise ValueError("المبلغ مطلوب")."""
    with _payroll_patches():
        resp = payroll_client.post(
            "/payroll/advances",
            data={"employee_id": "1"},
        )
    assert resp.status_code == 200


def test_advances_post_generic_exception_falls_into_outer_except(payroll_client):
    """L110-111: PayrollService.create_advance raises a non-ValueError."""
    with (
        _payroll_patches(),
        patch(
            "routes.payroll.PayrollService.create_advance",
            side_effect=RuntimeError("backend oops"),
        ),
    ):
        resp = payroll_client.post(
            "/payroll/advances",
            data={"employee_id": "1", "amount": "100"},
        )
    assert resp.status_code == 200


def test_process_post_generate_branch_missing_branch_id(payroll_client):
    """L129: raise ValueError("معرف الفرع مطلوب")."""
    with _payroll_patches():
        resp = payroll_client.post(
            "/payroll/process",
            data={"generate_branch": "1", "month": "6", "year": "2026"},
        )
    assert resp.status_code == 200


def test_process_post_generate_branch_missing_month_or_year(payroll_client):
    """L136: raise ValueError("الشهر والسنة مطلوبان")."""
    with _payroll_patches():
        resp = payroll_client.post(
            "/payroll/process",
            data={"generate_branch": "1", "branch_id": "2"},
        )
    assert resp.status_code == 200


def test_process_post_generate_branch_generic_exception(payroll_client):
    """L149-150: PayrollService.generate_branch_payroll raises non-ValueError."""
    with (
        _payroll_patches(),
        patch(
            "routes.payroll.PayrollService.generate_branch_payroll",
            side_effect=RuntimeError("backend oops"),
        ),
    ):
        resp = payroll_client.post(
            "/payroll/process",
            data={
                "generate_branch": "1",
                "branch_id": "2",
                "month": "6",
                "year": "2026",
            },
        )
    assert resp.status_code == 200


def test_process_single_post_missing_employee_id(payroll_client):
    """L155: raise ValueError("معرف الموظف مطلوب") in non-generate_branch path."""
    with _payroll_patches():
        resp = payroll_client.post(
            "/payroll/process",
            data={"month": "6", "year": "2026"},
        )
    assert resp.status_code == 200


def test_process_single_post_generic_exception(payroll_client):
    """L174-175: PayrollService.process_payroll raises non-ValueError."""
    with (
        _payroll_patches(),
        patch(
            "routes.payroll.PayrollService.process_payroll",
            side_effect=RuntimeError("backend oops"),
        ),
    ):
        resp = payroll_client.post(
            "/payroll/process",
            data={
                "employee_id": "1",
                "month": "6",
                "year": "2026",
            },
        )
    assert resp.status_code == 200
