"""AR reconciliation — GL vs operational subledger matching assurance."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestARGLBalance:
    """_gl_balance — tenant/branch scoped debit-minus-credit."""

    def _mock_scalar_chain(self, mocker, debit_val, credit_val):
        debit_q = MagicMock()
        debit_q.filter.return_value = debit_q
        debit_q.join.return_value = debit_q
        debit_q.scalar.return_value = debit_val

        credit_q = MagicMock()
        credit_q.filter.return_value = credit_q
        credit_q.join.return_value = credit_q
        credit_q.scalar.return_value = credit_val

        session = mocker.patch('services.ar_reconciliation_service.db.session')
        session.query.side_effect = [debit_q, credit_q]
        return debit_q, credit_q

    @pytest.mark.parametrize('tenant_id,branch_id,debit,credit,expected', [
        (1, None, '10000', '2500', Decimal('7500')),
        (1, 3, '5000', '5000', Decimal('0')),
        (None, None, '100', '400', Decimal('-300')),
    ])
    def test_gl_balance_scoping(self, mocker, tenant_id, branch_id, debit, credit, expected):
        self._mock_scalar_chain(mocker, debit, credit)
        from services.ar_reconciliation_service import ARReconciliationService
        result = ARReconciliationService._gl_balance(account_id=10, tenant_id=tenant_id, branch_id=branch_id)
        assert result == expected


class TestAROpsUnpaid:
    """_ops_unpaid — partial payments, receipts, overpayment skip."""

    def test_full_payment_zeroes_due(self, mocker):
        sales_q = MagicMock()
        sales_q.filter.return_value = sales_q
        sales_q.join.return_value = sales_q
        sales_q.all.return_value = [(1, Decimal('1000'), 5)]

        pay_q = MagicMock()
        pay_q.filter.return_value = pay_q
        pay_q.scalar.return_value = Decimal('1000')

        rcpt_q = MagicMock()
        rcpt_q.filter.return_value = rcpt_q
        rcpt_q.scalar.return_value = Decimal('0')

        session = mocker.patch('services.ar_reconciliation_service.db.session')
        session.query.side_effect = [sales_q, pay_q, rcpt_q]

        from services.ar_reconciliation_service import ARReconciliationService
        unpaid = ARReconciliationService._ops_unpaid(1, 2, ('regular',))
        assert unpaid == Decimal('0')

    def test_partial_payment_leaves_residual(self, mocker):
        sales_q = MagicMock()
        sales_q.filter.return_value = sales_q
        sales_q.join.return_value = sales_q
        sales_q.all.return_value = [(2, Decimal('2000'), 7)]

        pay_q = MagicMock()
        pay_q.filter.return_value = pay_q
        pay_q.scalar.return_value = Decimal('750')

        rcpt_q = MagicMock()
        rcpt_q.filter.return_value = rcpt_q
        rcpt_q.scalar.return_value = Decimal('250')

        session = mocker.patch('services.ar_reconciliation_service.db.session')
        session.query.side_effect = [sales_q, pay_q, rcpt_q]

        from services.ar_reconciliation_service import ARReconciliationService
        unpaid = ARReconciliationService._ops_unpaid(1, None, ('regular',))
        assert unpaid == Decimal('1000')

    def test_currency_fluctuation_uses_amount_aed(self, mocker):
        """Foreign sale amount_aed is authoritative for ops balance."""
        sales_q = MagicMock()
        sales_q.filter.return_value = sales_q
        sales_q.join.return_value = sales_q
        sales_q.all.return_value = [(3, Decimal('3675.50'), 9)]

        pay_q = MagicMock()
        pay_q.filter.return_value = pay_q
        pay_q.scalar.return_value = Decimal('1000.50')

        rcpt_q = MagicMock()
        rcpt_q.filter.return_value = rcpt_q
        rcpt_q.scalar.return_value = Decimal('0')

        session = mocker.patch('services.ar_reconciliation_service.db.session')
        session.query.side_effect = [sales_q, pay_q, rcpt_q]

        from services.ar_reconciliation_service import ARReconciliationService
        unpaid = ARReconciliationService._ops_unpaid(None, None, ('merchant',))
        assert unpaid == Decimal('2675.00')


class TestARBuildReport:
    """build_report — matched rows, missing GL account, aggregate totals."""

    def _patch_row(self, mocker, gl_bal, ops_bal, account=None):
        from models import GLAccount
        acc = account or MagicMock(id=99)
        acc_q = MagicMock()
        acc_q.filter_by.return_value = acc_q
        acc_q.first.return_value = acc
        mocker.patch.object(GLAccount, 'query', new_callable=mocker.PropertyMock, return_value=acc_q)
        mocker.patch('services.ar_reconciliation_service.scope_gl_accounts', side_effect=lambda q, **kw: q)
        mocker.patch(
            'services.ar_reconciliation_service.ARReconciliationService._gl_balance',
            return_value=Decimal(str(gl_bal)),
        )
        mocker.patch(
            'services.ar_reconciliation_service.ARReconciliationService._ops_unpaid',
            return_value=Decimal(str(ops_bal)),
        )

    def test_all_matched_within_tolerance(self, mocker, app):
        with app.app_context():
            self._patch_row(mocker, 5000, 5000)
            from services.ar_reconciliation_service import ARReconciliationService
            report = ARReconciliationService.build_report(tenant_id=1, branch_id=1)
        assert report['all_matched'] is True
        assert len(report['rows']) == 3
        assert report['account_codes']['receivable'] == '1130'

    def test_mismatch_flags_difference(self, mocker, app):
        with app.app_context():
            self._patch_row(mocker, 10000, 9500)
            from services.ar_reconciliation_service import ARReconciliationService
            report = ARReconciliationService.build_report(tenant_id=1)
        assert report['all_matched'] is False
        assert report['rows'][0]['matched'] is False
        assert report['rows'][0]['difference'] == 500.0

    def test_missing_gl_account_zero_balance(self, mocker, app):
        from models import GLAccount
        acc_q = MagicMock()
        acc_q.filter_by.return_value = acc_q
        acc_q.first.return_value = None
        with app.app_context():
            mocker.patch.object(GLAccount, 'query', new_callable=mocker.PropertyMock, return_value=acc_q)
            mocker.patch('services.ar_reconciliation_service.scope_gl_accounts', side_effect=lambda q, **kw: q)
            mocker.patch(
                'services.ar_reconciliation_service.ARReconciliationService._ops_unpaid',
                return_value=Decimal('100'),
            )
            from services.ar_reconciliation_service import ARReconciliationService
            report = ARReconciliationService.build_report()
        assert report['rows'][0]['gl_balance'] == 0.0
        assert report['total_ops'] == 300.0

    @pytest.mark.parametrize('gl,ops,matched', [
        (1000, 1000, True),
        (1000, 999.00, True),
        (1000, 997, False),
    ])
    def test_one_aed_tolerance_boundary(self, mocker, app, gl, ops, matched):
        with app.app_context():
            self._patch_row(mocker, gl, ops)
            from services.ar_reconciliation_service import ARReconciliationService
            report = ARReconciliationService.build_report(tenant_id=2)
        assert report['rows'][0]['matched'] is matched
