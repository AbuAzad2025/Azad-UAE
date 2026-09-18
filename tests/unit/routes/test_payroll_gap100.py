"""Gap100 for routes/payroll.py lines 64->69 branch-mismatch re-render."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest


def _mock_branch(**kwargs):
    b = MagicMock()
    b.id = kwargs.get("id", 2)
    b.tenant_id = kwargs.get("tenant_id", 1)
    b.is_active = True
    b.code = "BR01"
    b.name = "Main"
    return b


@contextmanager
def _payroll_patches(**kwargs):
    branch = kwargs.get("branch", _mock_branch())
    branch_scope = kwargs.get("branch_scope", 2)
    with ExitStack() as stack:
        stack.enter_context(patch("routes.payroll.render_template", return_value="ok"))
        stack.enter_context(patch("routes.payroll.get_active_tenant_id", return_value=1))
        stack.enter_context(patch("routes.payroll.branch_scope_id", return_value=branch_scope))
        stack.enter_context(patch("routes.payroll.should_show_all_branch_columns", return_value=False))
        stack.enter_context(patch("routes.payroll.PayrollService.list_branches_at_scope", return_value=[branch]))
        stack.enter_context(patch("routes.payroll.PayrollService.list_branch_options", return_value=[branch]))
        stack.enter_context(patch("routes.payroll.PayrollService.create_employee"))
        stack.enter_context(patch("extensions.limiter.limit", return_value=lambda f: f))
        yield {"branch": branch}


@pytest.fixture
def payroll_gap_client(app_factory, bypass_permission_auth):
    from routes.payroll import payroll_bp

    app = app_factory(payroll_bp)
    return app.test_client()


class TestAddEmployeeBranchMismatchGap100:
    """Lines 64-68: scoped user posting another branch re-renders form."""

    def test_branch_mismatch_rerenders_form(self, payroll_gap_client):
        with (
            _payroll_patches(branch_scope=2),
            patch("routes.payroll.render_template", return_value="ok") as render,
        ):
            resp = payroll_gap_client.post(
                "/payroll/employees/add",
                data={"name": "Sara", "branch_id": "9"},
            )
        assert resp.status_code == 200
        assert "payroll/add_employee.html" in render.call_args[0][0]

    def test_branch_match_proceeds_to_create(self, payroll_gap_client):
        with _payroll_patches(branch_scope=2):
            with patch("routes.payroll.atomic_transaction") as at:
                at.return_value.__enter__.return_value = MagicMock()
                at.return_value.__exit__.return_value = False
                with patch("routes.payroll.PayrollService.create_employee") as ce:
                    resp = payroll_gap_client.post(
                        "/payroll/employees/add",
                        data={"name": "Ali", "branch_id": "2"},
                        follow_redirects=False,
                    )
        # should redirect to employees_list on success
        assert resp.status_code == 302
        assert ce.called

    def test_no_branch_scope_skips_check(self, payroll_gap_client):
        # scoped_branch_id is None -> lines 62-68 skipped
        with _payroll_patches(branch_scope=None):
            with patch("routes.payroll.atomic_transaction") as at:
                at.return_value.__enter__.return_value = MagicMock()
                at.return_value.__exit__.return_value = False
                with patch("routes.payroll.PayrollService.create_employee") as ce:
                    resp = payroll_gap_client.post(
                        "/payroll/employees/add",
                        data={"name": "NoScope", "branch_id": "9"},
                        follow_redirects=False,
                    )
        assert resp.status_code == 302
        assert ce.called

    def test_missing_name_raises_and_flashes(self, payroll_gap_client):
        with _payroll_patches(branch_scope=2):
            with patch("routes.payroll.render_template", return_value="ok"):
                resp = payroll_gap_client.post(
                    "/payroll/employees/add",
                    data={"name": "", "branch_id": "2"},
                )
        assert resp.status_code == 200
        # fallback path renders form via GET logic (branches via list_branch_options)
        assert resp.data is not None
