"""IL mandatory pension — benefits components, gated by tenant switch."""

from decimal import Decimal

from services.payroll_service import PayrollService


def _run_payroll(emp, sample_tenant, db_session):
    from unittest.mock import patch

    gl_entry = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(id=88)
    patches = [
        patch("services.payroll_service.GLService.ensure_core_accounts"),
        patch("services.payroll_service.GLService.get_default_liquidity_account", return_value="1100"),
        patch("services.payroll_service.GLService.get_account_code_for_concept", return_value="6100"),
        patch("services.payroll_service.post_or_fail", return_value=gl_entry),
        patch("services.payroll_service.PayrollService.post_payroll_accruals"),
        patch("services.payroll_service.db.session.flush"),
    ]
    for p in patches:
        p.start()
    try:
        return PayrollService.process_payroll(
            employee_id=emp.id,
            month=3,
            year=2026,
            days_worked=0,
            allowances=0,
            deductions=0,
            user_id=1,
        )
    finally:
        for p in reversed(patches):
            p.stop()


class TestIlPension:
    def test_pension_deducted_when_enabled(self, db_session, sample_branch, sample_tenant):
        tenant = sample_tenant
        tenant.vat_country = "IL"
        tenant.enable_tax = True
        tenant.enable_il_pension = True
        db_session.commit()
        from models import Employee

        emp = Employee(
            tenant_id=tenant.id,
            branch_id=sample_branch.id,
            name="IL Worker",
            basic_salary=Decimal("6000"),
            employment_type="salary",
            is_national=False,
        )
        db_session.add(emp)
        db_session.commit()

        txn = _run_payroll(emp, tenant, db_session)
        assert txn.pension_amount == Decimal("360.000")  # 6% of 6000
        assert txn.pension_employer_amount == Decimal("390.000")  # 6.5% of 6000
        # tax = 72000 annual -> 7200 - 6534 credit = 666/12 = 55.5
        assert txn.income_tax_amount == Decimal("55.500")
        assert txn.net_salary == Decimal("6000") - Decimal("210.000") - Decimal("360.000") - Decimal("55.500")

    def test_pension_zero_when_disabled(self, db_session, sample_branch, sample_tenant):
        tenant = sample_tenant
        tenant.vat_country = "IL"
        tenant.enable_tax = True
        tenant.enable_il_pension = False
        db_session.commit()
        from models import Employee

        emp = Employee(
            tenant_id=tenant.id,
            branch_id=sample_branch.id,
            name="IL Worker 2",
            basic_salary=Decimal("6000"),
            employment_type="salary",
        )
        db_session.add(emp)
        db_session.commit()

        txn = _run_payroll(emp, tenant, db_session)
        assert txn.pension_amount == Decimal("0")
        assert txn.pension_employer_amount == Decimal("0")
