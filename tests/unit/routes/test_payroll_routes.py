from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_permission_auth, unauthenticated_client


def _mock_employee(**kwargs):
    emp = MagicMock()
    emp.id = kwargs.get('id', 1)
    emp.tenant_id = kwargs.get('tenant_id', 1)
    emp.branch_id = kwargs.get('branch_id', 2)
    emp.name = kwargs.get('name', 'Ali')
    emp.is_active = True
    return emp


def _mock_branch(**kwargs):
    branch = MagicMock()
    branch.id = kwargs.get('id', 2)
    branch.tenant_id = kwargs.get('tenant_id', 1)
    branch.is_active = True
    branch.code = 'BR01'
    branch.name = 'Main'
    return branch


def _mock_transaction(**kwargs):
    txn = MagicMock()
    txn.id = kwargs.get('id', 10)
    txn.tenant_id = kwargs.get('tenant_id', 1)
    txn.branch_id = kwargs.get('branch_id', 2)
    txn.employee_id = kwargs.get('employee_id', 1)
    txn.net_salary = Decimal('5000')
    txn.month = 6
    txn.year = 2026
    txn.payment_date = datetime(2026, 6, 1)
    return txn


def _mock_advance(**_kwargs):
    adv = MagicMock()
    adv.date = datetime(2026, 5, 1)
    adv.amount = Decimal('200')
    adv.description = 'loan'
    return adv


@contextmanager
def _payroll_patches(**kwargs):
    employee = kwargs.get('employee', _mock_employee())
    branch = kwargs.get('branch', _mock_branch())
    txn = kwargs.get('transaction', _mock_transaction())

    def _session_get(model, pk):
        name = getattr(model, '__name__', str(model))
        if name == 'Employee':
            return employee if int(pk) == int(employee.id) else None
        if name == 'Branch':
            return branch if int(pk) == int(branch.id) else None
        return None

    emp_q = _chain_query(all=kwargs.get('employees', [employee]))
    branch_q = _chain_query(all=kwargs.get('branches', [branch]))
    txn_q = _chain_query(first=txn, all=kwargs.get('transactions', [txn]))
    adv_q = _chain_query(all=kwargs.get('advances', [_mock_advance()]))

    with ExitStack() as stack:
        stack.enter_context(patch('routes.payroll.render_template', return_value='ok'))
        stack.enter_context(patch('routes.payroll.get_active_tenant_id', return_value=kwargs.get('tid', 1)))
        stack.enter_context(patch('routes.payroll.branch_scope_id', return_value=kwargs.get('branch_scope')))
        stack.enter_context(patch('routes.payroll.should_show_all_branch_columns', return_value=False))
        stack.enter_context(patch('routes.payroll.db.session.get', side_effect=_session_get))
        stack.enter_context(patch('routes.payroll.Employee.query', emp_q))
        stack.enter_context(patch('routes.payroll.Branch.query', branch_q))
        stack.enter_context(patch('routes.payroll.PayrollTransaction.query', txn_q))
        stack.enter_context(patch('routes.payroll.SalaryAdvance.query', adv_q))
        stack.enter_context(patch('routes.payroll.PayrollService.create_employee'))
        stack.enter_context(patch('routes.payroll.PayrollService.create_advance'))
        stack.enter_context(patch('routes.payroll.PayrollService.process_payroll', return_value=txn))
        stack.enter_context(patch('routes.payroll.PayrollService.generate_branch_payroll', return_value=(3, 1)))
        stack.enter_context(patch('extensions.limiter.limit', return_value=lambda f: f))
        yield {'employee': employee, 'branch': branch, 'transaction': txn}


@pytest.fixture
def payroll_client(app_factory, bypass_permission_auth):
    from routes.payroll import payroll_bp
    app = app_factory(payroll_bp)
    return app.test_client()


class TestPayrollAuth:
    def test_employees_requires_login(self, payroll_client):
        with _payroll_patches(), unauthenticated_client(payroll_client):
            resp = payroll_client.get('/payroll/employees')
        assert resp.status_code == 401

    def test_employees_forbidden_without_permission(self, payroll_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_super_admin.return_value = False
        with _payroll_patches(), patch('utils.decorators.is_global_owner_user', return_value=False):
            resp = payroll_client.get('/payroll/employees')
        assert resp.status_code == 403


class TestPayrollEmployees:
    def test_employees_list(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.get('/payroll/employees')
        assert resp.status_code == 200

    def test_employees_list_branch_scope(self, payroll_client):
        with _payroll_patches(branch_scope=2):
            resp = payroll_client.get('/payroll/employees')
        assert resp.status_code == 200


class TestPayrollAddEmployee:
    def test_add_get(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.get('/payroll/employees/add')
        assert resp.status_code == 200

    def test_add_get_branch_scoped(self, payroll_client):
        with _payroll_patches(branch_scope=2):
            resp = payroll_client.get('/payroll/employees/add')
        assert resp.status_code == 200

    def test_add_post_success(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.post('/payroll/employees/add', data={
                'name': 'Sara',
                'branch_id': '2',
                'basic_salary': '4000',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_add_post_branch_mismatch(self, payroll_client):
        with _payroll_patches(branch_scope=2):
            resp = payroll_client.post('/payroll/employees/add', data={'branch_id': '9'})
        assert resp.status_code == 200

    def test_add_post_service_error(self, payroll_client):
        with _payroll_patches(), patch('routes.payroll.PayrollService.create_employee', side_effect=ValueError('bad')):
            resp = payroll_client.post('/payroll/employees/add', data={'branch_id': '2'})
        assert resp.status_code == 200


class TestPayrollAdvances:
    def test_advances_get(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.get('/payroll/advances')
        assert resp.status_code == 200

    def test_advances_post_success(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.post('/payroll/advances', data={
                'employee_id': '1',
                'amount': '100',
                'description': 'advance',
            })
        assert resp.status_code == 200

    def test_advances_post_missing_employee(self, payroll_client):
        with _payroll_patches(employee=_mock_employee(id=99)):
            resp = payroll_client.post('/payroll/advances', data={'employee_id': '1', 'amount': '50'})
        assert resp.status_code == 200

    def test_advances_post_wrong_tenant(self, payroll_client):
        emp = _mock_employee(tenant_id=99)
        with _payroll_patches(employee=emp):
            resp = payroll_client.post('/payroll/advances', data={'employee_id': '1', 'amount': '50'})
        assert resp.status_code == 200

    def test_advances_post_wrong_branch(self, payroll_client):
        emp = _mock_employee(branch_id=9)
        with _payroll_patches(employee=emp, branch_scope=2):
            resp = payroll_client.post('/payroll/advances', data={'employee_id': '1', 'amount': '50'})
        assert resp.status_code == 200


class TestPayrollProcess:
    def test_process_get(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.get('/payroll/process')
        assert resp.status_code == 200

    def test_process_single_success(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.post('/payroll/process', data={
                'employee_id': '1',
                'month': '6',
                'year': '2026',
                'days_worked': '22',
                'allowances': '100',
                'deductions': '50',
            })
        assert resp.status_code == 200

    def test_process_single_wrong_tenant(self, payroll_client):
        emp = _mock_employee(tenant_id=88)
        with _payroll_patches(employee=emp):
            resp = payroll_client.post('/payroll/process', data={
                'employee_id': '1', 'month': '6', 'year': '2026',
            })
        assert resp.status_code == 200

    def test_process_branch_batch(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.post('/payroll/process', data={
                'generate_branch': '1',
                'branch_id': '2',
                'month': '6',
                'year': '2026',
            })
        assert resp.status_code == 200

    def test_process_branch_wrong_scope(self, payroll_client):
        branch = _mock_branch(id=9, tenant_id=1)
        with _payroll_patches(branch=branch, branch_scope=2):
            resp = payroll_client.post('/payroll/process', data={
                'generate_branch': '1',
                'branch_id': '9',
                'month': '6',
                'year': '2026',
            })
        assert resp.status_code == 200

    def test_process_branch_wrong_tenant(self, payroll_client):
        branch = _mock_branch(id=2, tenant_id=99)
        with _payroll_patches(branch=branch):
            resp = payroll_client.post('/payroll/process', data={
                'generate_branch': '1',
                'branch_id': '2',
                'month': '6',
                'year': '2026',
            })
        assert resp.status_code == 200

    def test_process_branch_missing(self, payroll_client):
        with _payroll_patches(branch=_mock_branch(id=99)):
            resp = payroll_client.post('/payroll/process', data={
                'generate_branch': '1',
                'branch_id': '2',
                'month': '6',
                'year': '2026',
            })
        assert resp.status_code == 200

    def test_process_service_error(self, payroll_client):
        with _payroll_patches(), patch('routes.payroll.PayrollService.process_payroll', side_effect=ValueError('dup')):
            resp = payroll_client.post('/payroll/process', data={
                'employee_id': '1', 'month': '6', 'year': '2026',
            })
        assert resp.status_code == 200


class TestPayrollSlipAndStatement:
    def test_salary_slip(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.get('/payroll/slip/10')
        assert resp.status_code == 200

    def test_salary_slip_branch_forbidden(self, payroll_client):
        txn = _mock_transaction(branch_id=9)
        with _payroll_patches(transaction=txn, branch_scope=2):
            resp = payroll_client.get('/payroll/slip/10')
        assert resp.status_code == 403

    def test_salary_slip_not_found(self, payroll_client):
        txn_q = _chain_query(first=None)
        txn_q.filter_by.return_value.filter.return_value.first_or_404.side_effect = NotFound()
        with _payroll_patches(), patch('routes.payroll.PayrollTransaction.query', txn_q):
            resp = payroll_client.get('/payroll/slip/999')
        assert resp.status_code == 404

    def test_statement(self, payroll_client):
        with _payroll_patches():
            resp = payroll_client.get('/payroll/statement/1')
        assert resp.status_code == 200

    def test_statement_branch_forbidden(self, payroll_client):
        emp = _mock_employee(branch_id=9)
        with _payroll_patches(employee=emp, branch_scope=2):
            resp = payroll_client.get('/payroll/statement/1')
        assert resp.status_code == 403

    def test_statement_not_found(self, payroll_client):
        emp_q = _chain_query(first=None)
        emp_q.filter_by.return_value.filter.return_value.first_or_404.side_effect = NotFound()
        with _payroll_patches(), patch('routes.payroll.Employee.query', emp_q):
            resp = payroll_client.get('/payroll/statement/404')
        assert resp.status_code == 404
