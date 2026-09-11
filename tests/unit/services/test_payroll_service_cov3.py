"""Coverage boost for services/payroll_service.py.

DB-free tests: real PayrollService methods run with query/session/GL
boundaries mocked. Targets helper guards, EOS/leave math, EOSB branches,
accrual posting, termination flow, branch generation, and list/page helpers.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.payroll_service import PayrollService

MOD = "services.payroll_service"


def _chain(*, all_result=None, first_result=None, count_result=0):
    q = MagicMock()
    q.filter.return_value = q
    q.filter_by.return_value = q
    q.order_by.return_value = q
    q.join.return_value = q
    q.limit.return_value = q
    q.all.return_value = all_result if all_result is not None else []
    q.first.return_value = first_result
    q.count.return_value = count_result
    return q


class TestHelpers:
    def test_branch_tenant_id_missing_branch(self):
        with patch(f"{MOD}.db.session.get", return_value=None):
            try:
                PayrollService._branch_tenant_id(4242)
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_branch_tenant_id_no_tenant(self):
        with patch(f"{MOD}.db.session.get", return_value=SimpleNamespace(tenant_id=None)):
            try:
                PayrollService._branch_tenant_id(1)
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_branch_tenant_id_ok(self):
        with patch(f"{MOD}.db.session.get", return_value=SimpleNamespace(tenant_id=9)):
            assert PayrollService._branch_tenant_id(3) == 9

    def test_require_employee_tenant_missing(self):
        try:
            PayrollService._require_employee_tenant_id(SimpleNamespace(tenant_id=None))
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_require_employee_tenant_ok(self):
        assert PayrollService._require_employee_tenant_id(SimpleNamespace(tenant_id=4)) == 4


class TestCreateEmployee:
    def test_success_with_joined_date(self):
        with (
            patch(f"{MOD}.PayrollService._branch_tenant_id", return_value=7),
            patch(f"{MOD}.db.session"),
        ):
            emp = PayrollService.create_employee(
                {"name": "Sara", "branch_id": 2, "basic_salary": "4000", "joined_date": "2024-03-01"}
            )
        assert emp.tenant_id == 7
        assert emp.branch_id == 2
        assert emp.joined_date == datetime(2024, 3, 1)

    def test_requires_branch(self):
        try:
            PayrollService.create_employee({"name": "X"})
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_flush_failure_propagates(self):
        with (
            patch(f"{MOD}.PayrollService._branch_tenant_id", return_value=7),
            patch(f"{MOD}.db.session") as session,
        ):
            session.flush.side_effect = RuntimeError("db")
            try:
                PayrollService.create_employee({"name": "F", "branch_id": 2, "basic_salary": "10"})
            except RuntimeError:
                pass
            else:
                raise AssertionError("expected RuntimeError")


class TestEosLeaveMath:
    def test_eos_zero_salary(self):
        assert PayrollService._calculate_eos_monthly_provision(0) == Decimal("0")
        assert PayrollService._calculate_eos_monthly_provision(None) == Decimal("0")

    def test_eos_limited(self):
        assert PayrollService._calculate_eos_monthly_provision(Decimal("3000")) == Decimal("175.000")

    def test_eos_unlimited(self):
        assert PayrollService._calculate_eos_monthly_provision(Decimal("3000"), "unlimited") == Decimal("250.000")

    def test_leave_zero_salary(self):
        assert PayrollService._calculate_leave_monthly_accrual(0) == Decimal("0")

    def test_leave_positive(self):
        assert PayrollService._calculate_leave_monthly_accrual(Decimal("3000"), 30) == Decimal("250.000")


class TestCalculateEosb:
    def _emp(self, **kw):
        base = {
            "basic_salary": Decimal("3000"),
            "joined_date": date(2020, 1, 1),
            "termination_date": date(2023, 1, 1),
            "contract_type": "limited",
        }
        base.update(kw)
        return SimpleNamespace(**base)

    def test_no_dates_returns_zero(self):
        assert PayrollService.calculate_eosb(self._emp(joined_date=None)) == Decimal("0")
        assert PayrollService.calculate_eosb(self._emp(termination_date=None)) == Decimal("0")

    def test_zero_salary_returns_zero(self):
        assert PayrollService.calculate_eosb(self._emp(basic_salary=Decimal("0"))) == Decimal("0")

    def test_limited_three_years(self):
        # daily 100 * 3*21 = 6300
        assert PayrollService.calculate_eosb(self._emp()) == Decimal("6300.00")

    def test_unlimited_under_one_year_returns_zero(self):
        emp = self._emp(
            contract_type="unlimited",
            joined_date=date(2022, 6, 1),
            termination_date=date(2022, 12, 1),
        )
        assert PayrollService.calculate_eosb(emp) == Decimal("0")

    def test_capped_at_two_years_salary(self):
        emp = self._emp(joined_date=date(1980, 1, 1), termination_date=date(2025, 1, 1))
        assert PayrollService.calculate_eosb(emp) == Decimal("73000.00")

    def test_after_five_years_uses_30_days(self):
        emp = self._emp(joined_date=date(2015, 1, 1), termination_date=date(2023, 1, 1))
        # eligible 8: 5*21 + 3*30 = 195 days * 100
        assert PayrollService.calculate_eosb(emp) == Decimal("19500.00")


class TestAccruals:
    def _emp(self, salary="5000"):
        return SimpleNamespace(
            id=1,
            name="Ali",
            tenant_id=2,
            branch_id=3,
            basic_salary=Decimal(salary),
            contract_type="limited",
            annual_leave_days=30,
        )

    def test_none_when_zero(self):
        with patch(f"{MOD}.GLService") as gl:
            assert PayrollService.post_payroll_accruals(self._emp("0"), 1, 2026, 9) is None
            gl.ensure_core_accounts.assert_not_called()

    def test_posts_both_lines(self):
        entry = MagicMock(id=55)
        with (
            patch(f"{MOD}.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=entry) as post,
        ):
            gl.get_account_code_for_concept.side_effect = lambda code, **kw: code
            out = PayrollService.post_payroll_accruals(self._emp(), 2, 2026, 9)
        assert out is entry
        lines = post.call_args.args[0]
        assert len(lines) == 4
        assert lines[0]["debit"] == Decimal("291.667")
        assert lines[2]["debit"] == Decimal("416.667")

    def test_requires_employee_tenant(self):
        emp = SimpleNamespace(tenant_id=None, basic_salary=Decimal("9"))
        try:
            PayrollService.post_payroll_accruals(emp, 1, 2026, 9)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_eos_only_when_leave_non_positive(self):
        # negative leave days -> leave accrual <= 0 while EOS > 0 (437->467)
        emp = self._emp()
        emp.annual_leave_days = -30
        entry = MagicMock(id=56)
        with (
            patch(f"{MOD}.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=entry) as post,
        ):
            gl.get_account_code_for_concept.side_effect = lambda code, **kw: code
            out = PayrollService.post_payroll_accruals(emp, 2, 2026, 9)
        assert out is entry
        lines = post.call_args.args[0]
        assert len(lines) == 2
        assert {ln["concept_code"] for ln in lines} == {
            "END_OF_SERVICE_PROVISION",
            "END_OF_SERVICE_LIABILITY",
        }


class TestSettleEosb:
    def test_zero_raises(self):
        emp = SimpleNamespace(
            id=1,
            name="A",
            tenant_id=2,
            branch_id=3,
            basic_salary=Decimal("0"),
            joined_date=None,
            termination_date=None,
            contract_type="limited",
        )
        with patch(f"{MOD}.Employee.query") as query:
            query.get_or_404.return_value = emp
            try:
                PayrollService.settle_eosb(1, 9)
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_success_posts_gl(self):
        emp = SimpleNamespace(
            id=1,
            name="A",
            tenant_id=2,
            branch_id=3,
            basic_salary=Decimal("3000"),
            joined_date=date(2020, 1, 1),
            termination_date=date(2023, 1, 1),
            contract_type="limited",
        )
        entry = MagicMock(id=61)
        with (
            patch(f"{MOD}.Employee.query") as query,
            patch(f"{MOD}.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=entry) as post,
        ):
            query.get_or_404.return_value = emp
            gl.get_account_code_for_concept.side_effect = lambda code, **kw: code
            out = PayrollService.settle_eosb(1, 9)
        assert out["eosb_amount"] == Decimal("6300.00")
        assert out["gl_entry_id"] == 61
        assert post.call_args.args[0][0]["debit"] == Decimal("6300.00")


class TestCreateAdvanceActorPaths:
    def _emp(self):
        return SimpleNamespace(id=1, name="A", tenant_id=2, branch_id=3)

    def test_global_owner_skips_scope_checks(self):
        entry = MagicMock(id=77)
        with (
            patch(f"{MOD}.Employee.query") as query,
            patch("utils.auth_helpers.is_global_owner_user", return_value=True),
            patch(f"{MOD}.GLService"),
            patch(f"{MOD}.post_or_fail", return_value=entry),
            patch(f"{MOD}.db.session"),
        ):
            query.get_or_404.return_value = self._emp()
            adv = PayrollService.create_advance(1, "500", "loan", user_id=1, actor_user=MagicMock())
        assert adv.gl_entry_id == 77

    def test_matching_scope_and_no_active_tenant_proceeds(self):
        entry = MagicMock(id=78)
        actor = MagicMock()
        with (
            patch(f"{MOD}.Employee.query") as query,
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.branching.branch_scope_id_for", return_value=3),
            patch("utils.tenanting.get_active_tenant_id", return_value=None),
            patch(f"{MOD}.GLService"),
            patch(f"{MOD}.post_or_fail", return_value=entry),
            patch(f"{MOD}.db.session"),
        ):
            query.get_or_404.return_value = self._emp()
            adv = PayrollService.create_advance(1, "500", "loan", user_id=1, actor_user=actor)
        assert adv.gl_entry_id == 78

    def test_final_flush_failure_raises(self):
        with (
            patch(f"{MOD}.Employee.query") as query,
            patch(f"{MOD}.GLService"),
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=1)),
            patch(f"{MOD}.db.session") as session,
        ):
            query.get_or_404.return_value = self._emp()
            session.flush.side_effect = [None, RuntimeError("db")]
            try:
                PayrollService.create_advance(1, "500", "loan", user_id=1)
            except RuntimeError:
                pass
            else:
                raise AssertionError("expected RuntimeError")


class TestProcessPayrollActorPaths:
    def _pay_emp(self):
        return SimpleNamespace(
            id=1,
            name="A",
            tenant_id=2,
            branch_id=3,
            employment_type="salary",
            basic_salary=Decimal("0"),
        )

    def _run(self, actor_patches, flush_side=None):
        from contextlib import ExitStack

        entry = MagicMock(id=80)
        with (
            patch(f"{MOD}.Employee.query") as query,
            patch(f"{MOD}.SalaryAdvance.query") as aquery,
            patch(f"{MOD}.PayrollTransaction.query") as tquery,
            patch(f"{MOD}.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=entry),
            patch(f"{MOD}.db.session") as session,
        ):
            with ExitStack() as stack:
                for p in actor_patches:
                    stack.enter_context(p)
                query.get_or_404.return_value = self._pay_emp()
                aquery.filter_by.return_value = MagicMock(all=MagicMock(return_value=[]))
                tquery.filter_by.return_value = MagicMock(first=MagicMock(return_value=None))
                gl.get_account_code_for_concept.side_effect = lambda code, **kw: code
                gl.get_default_liquidity_account.return_value = "1100"
                if flush_side is not None:
                    session.flush.side_effect = flush_side
                return PayrollService.process_payroll(1, 9, 2026, 0, 100, 10, 9, actor_user=MagicMock())

    def test_global_owner_proceeds(self):
        txn = self._run([patch("utils.auth_helpers.is_global_owner_user", return_value=True)])
        assert txn.net_salary == Decimal("90")

    def test_matching_scope_no_active_tenant_proceeds(self):
        txn = self._run(
            [
                patch("utils.auth_helpers.is_global_owner_user", return_value=False),
                patch("utils.branching.branch_scope_id_for", return_value=3),
                patch("utils.tenanting.get_active_tenant_id", return_value=None),
            ]
        )
        assert txn.net_salary == Decimal("90")

    def test_final_flush_failure_raises(self):
        try:
            self._run(
                [patch("utils.auth_helpers.is_global_owner_user", return_value=True)],
                flush_side=[None, RuntimeError("db")],
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError")


class TestTermination:
    def _emp(self, active=True):
        return SimpleNamespace(
            id=1,
            name="A",
            tenant_id=2,
            branch_id=3,
            basic_salary=Decimal("3000"),
            joined_date=date(2020, 1, 1),
            termination_date=None,
            is_active=active,
            termination_reason=None,
            contract_type="limited",
        )

    def test_inactive_raises(self):
        with patch(f"{MOD}.Employee.query") as query:
            query.get_or_404.return_value = self._emp(active=False)
            try:
                PayrollService.process_termination(1, "2024-05-01", "resigned", 9)
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_success_clears_advances_and_settles(self):
        emp = self._emp()
        adv = SimpleNamespace(
            remaining_amount=Decimal("400"),
            total_amount=Decimal("400"),
            deducted_amount=Decimal("0"),
            is_deducted=False,
            fully_deducted_at=None,
        )
        exhausted = SimpleNamespace(
            remaining_amount=Decimal("0"),
            total_amount=Decimal("100"),
            deducted_amount=Decimal("100"),
            is_deducted=True,
            fully_deducted_at=None,
        )
        with (
            patch(f"{MOD}.Employee.query") as equery,
            patch(f"{MOD}.SalaryAdvance.query") as aquery,
            patch(f"{MOD}.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=70)),
            patch(f"{MOD}.db.session"),
        ):
            equery.get_or_404.return_value = emp
            afilter = MagicMock()
            afilter.filter_by.return_value = afilter
            afilter.all.return_value = [adv, exhausted]
            # SalaryAdvance.query.filter_by(...) chain
            aquery.filter_by.return_value = MagicMock(all=MagicMock(return_value=[adv, exhausted]))
            gl.get_account_code_for_concept.side_effect = lambda code, **kw: code
            out = PayrollService.process_termination(1, "2024-05-01", "resigned", 9)
        assert emp.is_active is False
        assert str(out["termination_date"]) == "2024-05-01"
        assert out["advances_cleared"] == Decimal("400")
        assert adv.is_deducted is True
        assert out["eosb"] is not None

    def test_eosb_failure_yields_none(self):
        emp = self._emp()
        emp.basic_salary = Decimal("0")
        emp.joined_date = None
        with (
            patch(f"{MOD}.Employee.query") as equery,
            patch(f"{MOD}.SalaryAdvance.query") as aquery,
            patch(f"{MOD}.db.session"),
        ):
            equery.get_or_404.return_value = emp
            aquery.filter_by.return_value = MagicMock(all=MagicMock(return_value=[]))
            out = PayrollService.process_termination(1, date(2024, 5, 1), "end", 9)
        assert out["eosb"] is None
        assert out["advances_cleared"] == Decimal("0")

    def test_advance_fallback_balance_used(self):
        # 622->624: remaining_amount empty but total-deducted > 0
        emp = self._emp()
        fallback_adv = SimpleNamespace(
            remaining_amount=Decimal("0"),
            total_amount=Decimal("400"),
            deducted_amount=Decimal("50"),
            is_deducted=False,
            fully_deducted_at=None,
        )
        with (
            patch(f"{MOD}.Employee.query") as equery,
            patch(f"{MOD}.SalaryAdvance.query") as aquery,
            patch(f"{MOD}.GLService") as gl,
            patch(f"{MOD}.post_or_fail", return_value=MagicMock(id=70)),
            patch(f"{MOD}.db.session"),
        ):
            equery.get_or_404.return_value = emp
            aquery.filter_by.return_value = MagicMock(all=MagicMock(return_value=[fallback_adv]))
            gl.get_account_code_for_concept.side_effect = lambda code, **kw: code
            out = PayrollService.process_termination(1, date(2024, 5, 1), "end", 9)
        assert out["advances_cleared"] == Decimal("350")
        assert fallback_adv.is_deducted is True


class TestGenerateBranch:
    def test_skips_existing_and_daily(self):
        emp_done = SimpleNamespace(id=1, employment_type="salary")
        emp_salary = SimpleNamespace(id=2, employment_type="salary")
        emp_daily = SimpleNamespace(id=3, employment_type="daily")
        with (
            patch(f"{MOD}.PayrollService._branch_tenant_id", return_value=5),
            patch(f"{MOD}.Employee.query") as equery,
            patch(f"{MOD}.PayrollTransaction.query") as tquery,
            patch(f"{MOD}.PayrollService.process_payroll") as proc,
        ):
            equery.filter_by.return_value = MagicMock(all=MagicMock(return_value=[emp_done, emp_salary, emp_daily]))
            tquery.filter_by.return_value = MagicMock(first=MagicMock(side_effect=[MagicMock(id=9), None, None]))
            gen, skip = PayrollService.generate_branch_payroll(3, 9, 2026, 9)
        assert (gen, skip) == (1, 2)
        proc.assert_called_once()

    def test_empty_branch(self):
        with (
            patch(f"{MOD}.PayrollService._branch_tenant_id", return_value=5),
            patch(f"{MOD}.Employee.query") as equery,
        ):
            equery.filter_by.return_value = MagicMock(all=MagicMock(return_value=[]))
            assert PayrollService.generate_branch_payroll(3, 9, 2026, 9) == (0, 0)


class TestListHelpers:
    def test_list_employees_scoped(self):
        q = _chain(all_result=["e"])
        with patch(f"{MOD}.Employee.query", new=q):
            assert PayrollService.list_employees(tenant_id=1, branch_id=2) == ["e"]
        assert q.filter.call_count == 2

    def test_list_employees_unscoped(self):
        q = _chain(all_result=[])
        with patch(f"{MOD}.Employee.query", new=q):
            assert PayrollService.list_employees() == []

    def test_list_branches_at_scope(self):
        with patch("models.Branch") as branch:
            q = _chain(all_result=["b"])
            branch.query.filter_by.return_value = q
            out = PayrollService.list_branches_at_scope(1, 2)
        assert out == ["b"]

    def test_list_branch_options_scoped_and_unscoped(self):
        with patch("models.Branch") as branch:
            q = _chain(all_result=[])
            branch.query.filter_by.return_value = q
            assert PayrollService.list_branch_options(tenant_id=1, scoped_branch_id=2) == []
            assert PayrollService.list_branch_options() == []

    def test_list_active_employees(self):
        q = _chain(all_result=[])
        with patch(f"{MOD}.Employee.query", new=q):
            assert PayrollService.list_active_employees(tenant_id=1, branch_id=2) == []

    def test_advance_page_data(self):
        with patch("models.Employee") as employee, patch("models.SalaryAdvance") as adv:
            eq = _chain(all_result=["e"])
            aq = _chain(all_result=["a"])
            employee.query.filter_by.return_value = eq
            adv.query.join.return_value = aq
            emps, advs = PayrollService.advance_page_data(tenant_id=1, scoped_branch_id=2)
        assert (emps, advs) == (["e"], ["a"])

    def test_process_page_data(self):
        with (
            patch("models.Employee") as employee,
            patch("models.Branch") as branch,
            patch("models.PayrollTransaction") as txn,
        ):
            employee.query.filter_by.return_value = _chain(all_result=["e"])
            branch.query.filter_by.return_value = _chain(all_result=["b"])
            txn.query = _chain(all_result=["t"])
            emps, branches, txns = PayrollService.process_page_data(tenant_id=1, scoped_branch_id=2)
        assert (emps, branches, txns) == (["e"], ["b"], ["t"])

    def test_get_or_404_helpers(self):
        with patch("models.PayrollTransaction") as txn:
            q = MagicMock()
            txn.query.filter_by.return_value = q
            PayrollService.get_transaction_or_404(1, tenant_id=2)
            assert q.filter.call_count == 1
            PayrollService.get_transaction_or_404(1)
        with patch("models.Employee") as employee:
            q = MagicMock()
            employee.query.filter_by.return_value = q
            PayrollService.get_employee_or_404(1, tenant_id=2)
            assert q.filter.call_count == 1

    def test_employee_statement_records(self):
        with patch("models.SalaryAdvance") as adv, patch("models.PayrollTransaction") as txn:
            aq = _chain(all_result=["a"])
            tq = _chain(all_result=["t"])
            adv.query.filter_by.return_value = aq
            txn.query.filter_by.return_value = tq
            assert PayrollService.employee_statement_records(1, tenant_id=2) == (["a"], ["t"])
            assert PayrollService.employee_statement_records(1) == (["a"], ["t"])

    def test_get_wps_rows(self):
        emp = SimpleNamespace(id=7, name="W", iban="IB1", bank_code="B1", currency=None)
        txn = SimpleNamespace(
            basic_amount=Decimal("100"),
            allowances=Decimal("10"),
            net_salary=Decimal("110"),
            payment_date=date(2026, 9, 1),
        )
        session_q = MagicMock()
        session_q.join.return_value = session_q
        session_q.filter.return_value = session_q
        session_q.all.return_value = [(emp, txn)]
        with patch(f"{MOD}.db.session") as session:
            session.query.return_value = session_q
            rows = PayrollService.get_wps_rows(1, 9, 2026)
        assert len(rows) == 1
        assert rows[0]["wps_id"] == "00000007"
        assert rows[0]["currency"] == "AED"
        assert rows[0]["payment_date"] == "2026-09-01"

    def test_get_wps_rows_empty_payment_date(self):
        emp = SimpleNamespace(id=8, name="W", iban="IB1", bank_code="B1", currency="USD")
        txn = SimpleNamespace(
            basic_amount=Decimal("100"), allowances=Decimal("0"), net_salary=Decimal("100"), payment_date=None
        )
        session_q = MagicMock()
        session_q.join.return_value = session_q
        session_q.filter.return_value = session_q
        session_q.all.return_value = [(emp, txn)]
        with patch(f"{MOD}.db.session") as session:
            session.query.return_value = session_q
            rows = PayrollService.get_wps_rows(1, 9, 2026)
        assert rows[0]["payment_date"] == ""
        assert rows[0]["currency"] == "USD"
