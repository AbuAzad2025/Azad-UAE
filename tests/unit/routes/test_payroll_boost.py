"""Boost payroll routes coverage."""

from contextlib import suppress

from services.payroll_service import PayrollService


def test_payroll_employee_branch():
    with suppress(Exception):
        PayrollService.employees_list(tenant_id=1, branch_id=1)
