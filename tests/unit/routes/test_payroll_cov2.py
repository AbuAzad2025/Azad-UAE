"""Coverage boost for routes/payroll.py.

Targets: lines 63-68 (branch-mismatched employee form re-render).
Real response path via test client; services/DB mocked only at boundaries.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest


def _mock_employee(**kwargs):
    emp = MagicMock()
    emp.id = kwargs.get("id", 1)
    emp.tenant_id = kwargs.get("tenant_id", 1)
    emp.branch_id = kwargs.get("branch_id", 2)
    emp.name = kwargs.get("name", "Ali")
    emp.is_active = True
    return emp


def _mock_branch(**kwargs):
    branch = MagicMock()
    branch.id = kwargs.get("id", 2)
    branch.tenant_id = kwargs.get("tenant_id", 1)
    branch.is_active = True
    branch.code = "BR01"
    branch.name = "Main"
    return branch


@contextmanager
def _payroll_cov2_patches(**kwargs):
    employee = kwargs.get("employee", _mock_employee())
    branch = kwargs.get("branch", _mock_branch())

    def _session_get(model, pk):
        name = getattr(model, "__name__", str(model))
        if name == "Employee":
            return employee if int(pk) == int(employee.id) else None
        if name == "Branch":
            return branch if int(pk) == int(branch.id) else None
        return None

    with ExitStack() as stack:
        stack.enter_context(patch("routes.payroll.render_template", return_value="ok"))
        stack.enter_context(patch("routes.payroll.get_active_tenant_id", return_value=1))
        stack.enter_context(patch("routes.payroll.branch_scope_id", return_value=kwargs.get("branch_scope")))
        stack.enter_context(patch("routes.payroll.should_show_all_branch_columns", return_value=False))
        stack.enter_context(patch("routes.payroll.db.session.get", side_effect=_session_get))
        stack.enter_context(
            patch(
                "routes.payroll.PayrollService.list_branches_at_scope",
                return_value=[branch],
            )
        )
        stack.enter_context(patch("routes.payroll.PayrollService.list_branch_options", return_value=[branch]))
        stack.enter_context(patch("routes.payroll.PayrollService.create_employee"))
        stack.enter_context(patch("extensions.limiter.limit", return_value=lambda f: f))
        yield {"employee": employee, "branch": branch}


@pytest.fixture
def payroll_cov2_client(app_factory, bypass_permission_auth):
    from routes.payroll import payroll_bp

    app = app_factory(payroll_bp)
    return app.test_client()


class TestAddEmployeeBranchMismatch:
    """Lines 63-68: scoped user posting another branch re-renders the form."""

    def test_branch_mismatch_rerenders_form(self, payroll_cov2_client):
        with (
            _payroll_cov2_patches(branch_scope=2),
            patch("routes.payroll.render_template", return_value="ok") as render,
        ):
            resp = payroll_cov2_client.post(
                "/payroll/employees/add",
                data={"name": "Sara", "branch_id": "9"},
            )
        assert resp.status_code == 200
        assert "payroll/add_employee.html" in render.call_args[0][0]
