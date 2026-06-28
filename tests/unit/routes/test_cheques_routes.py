from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_admin_auth, bypass_permission_auth, unauthenticated_client


def _mock_cheque(**kwargs):
    c = MagicMock()
    c.id = kwargs.get('id', 1)
    c.tenant_id = kwargs.get('tenant_id', 1)
    c.branch_id = kwargs.get('branch_id', 1)
    c.cheque_number = kwargs.get('cheque_number', 'CHQ-001')
    c.cheque_bank_number = kwargs.get('cheque_bank_number', 'BNK-001')
    c.cheque_type = kwargs.get('cheque_type', 'incoming')
    c.status = kwargs.get('status', 'pending')
    c.amount = kwargs.get('amount', Decimal('1000'))
    c.currency = kwargs.get('currency', 'AED')
    c.currency_gain_loss = kwargs.get('currency_gain_loss', Decimal('0'))
    c.is_active = kwargs.get('is_active', True)
    c.receipt_id = kwargs.get('receipt_id')
    c.payment_id = kwargs.get('payment_id')
    c.sale_id = kwargs.get('sale_id')
    c.purchase_id = kwargs.get('purchase_id')
    c.expense_id = kwargs.get('expense_id')
    c.update_status_based_on_date = MagicMock()
    c.archive = MagicMock()
    c.restore = MagicMock()
    c.to_dict = MagicMock(return_value={'id': c.id})
    return c


@contextmanager
def _cheque_patches(**kwargs):
    cheque = kwargs.get('cheque', _mock_cheque())
    cq = _chain_query(all=kwargs.get('cheques', [cheque]))
    cq.filter_by.return_value = cq
    cq.filter.return_value = cq
    with ExitStack() as stack:
        stack.enter_context(patch('routes.cheques.render_template', return_value='ok'))
        stack.enter_context(patch('routes.cheques.Cheque.query', cq))
        stack.enter_context(patch('routes.cheques.Cheque.update_all_statuses'))
        stack.enter_context(patch('routes.cheques.Cheque.get_statistics', return_value={'total': 1}))
        stack.enter_context(patch('routes.cheques.Cheque.get_due_soon_cheques', return_value=[]))
        stack.enter_context(patch('routes.cheques.Cheque.get_overdue_cheques', return_value=[]))
        stack.enter_context(patch('routes.cheques.get_active_tenant_id', return_value=1))
        stack.enter_context(patch('routes.cheques.branch_scope_id', return_value=kwargs.get('branch_scope')))
        stack.enter_context(patch('routes.cheques.should_show_all_branch_columns', return_value=False))
        stack.enter_context(patch('utils.tenanting.tenant_get_or_404', return_value=cheque))
        stack.enter_context(patch('routes.cheques._get_cheque_or_404', return_value=cheque))
        stack.enter_context(patch('routes.cheques._ensure_cheque_scope', return_value=kwargs.get('in_scope', True)))
        stack.enter_context(patch('routes.cheques._scoped_customers_query', return_value=_chain_query(all=[])))
        stack.enter_context(patch('routes.cheques._scoped_suppliers_query', return_value=_chain_query(all=[])))
        stack.enter_context(patch('routes.cheques.resolve_default_currency', return_value='AED'))
        stack.enter_context(patch('routes.cheques.get_system_default_currency', return_value='AED'))
        stack.enter_context(patch('routes.cheques.CurrencyService.get_all_rates', return_value={}))
        stack.enter_context(patch('routes.cheques._resolve_transaction_rate', return_value=Decimal('1')))
        stack.enter_context(patch('routes.cheques.generate_number', return_value='CHQ-NEW'))
        stack.enter_context(patch('routes.cheques.calculate_amount_aed'))
        stack.enter_context(patch('routes.cheques.process_cheque_receive'))
        stack.enter_context(patch('routes.cheques.process_cheque_issue'))
        stack.enter_context(patch('routes.cheques.process_cheque_deposit'))
        stack.enter_context(patch('routes.cheques.process_cheque_clear'))
        stack.enter_context(patch('routes.cheques.process_cheque_bounce'))
        stack.enter_context(patch('routes.cheques.process_cheque_cancel'))
        stack.enter_context(patch('routes.cheques.LoggingCore.log_audit'))
        stack.enter_context(patch('extensions.limiter.limit', return_value=lambda f: f))
        stack.enter_context(patch('extensions.db.session'))
        yield {'cheque': cheque, 'query': cq}


@pytest.fixture
def cheques_client(app_factory, bypass_permission_auth):
    from routes.cheques import cheques_bp
    app = app_factory(cheques_bp)
    return app.test_client()


@pytest.fixture
def cheques_admin_client(app_factory, bypass_admin_auth):
    from routes.cheques import cheques_bp
    app = app_factory(cheques_bp)
    return app.test_client()


class TestChequesHelpers:
    def test_resolve_transaction_rate(self):
        from routes.cheques import _resolve_transaction_rate
        with patch('routes.cheques.ExchangeRateService.resolve_exchange_rate_for_transaction', return_value={'rate': '3.67'}):
            assert _resolve_transaction_rate('USD') == Decimal('3.67')

    def test_ensure_cheque_scope_mismatch(self, bypass_permission_auth):
        from routes.cheques import _ensure_cheque_scope
        cheque = _mock_cheque(tenant_id=99)
        with patch('routes.cheques.get_active_tenant_id', return_value=1), \
             patch('routes.cheques.branch_scope_id', return_value=None):
            assert _ensure_cheque_scope(cheque) is False

    def test_ensure_cheque_scope_branch_mismatch(self, bypass_permission_auth):
        from routes.cheques import _ensure_cheque_scope
        cheque = _mock_cheque(branch_id=5)
        with patch('routes.cheques.get_active_tenant_id', return_value=1), \
             patch('routes.cheques.branch_scope_id', return_value=2):
            assert _ensure_cheque_scope(cheque) is False

    def test_get_cheque_or_404(self):
        cheque = _mock_cheque(id=99)
        with patch('utils.tenanting.tenant_get_or_404', return_value=cheque) as tg:
            from routes.cheques import _get_cheque_or_404
            assert _get_cheque_or_404(99) is cheque
        tg.assert_called_once()

    def test_scoped_customers_with_branch(self):
        from routes.cheques import _scoped_customers_query
        cq = MagicMock()
        cq.filter.return_value = cq
        with patch('routes.cheques.Customer.query', cq), \
             patch('routes.cheques.get_active_tenant_id', return_value=1), \
             patch('routes.cheques.branch_scope_id', return_value=2), \
             patch('sqlalchemy.select', return_value=MagicMock(where=MagicMock(return_value=MagicMock()))):
            result = _scoped_customers_query()
        assert result is cq

    def test_scoped_suppliers_with_branch(self):
        from routes.cheques import _scoped_suppliers_query
        sq = MagicMock()
        sq.filter.return_value = sq
        with patch('routes.cheques.Supplier.query', sq), \
             patch('routes.cheques.get_active_tenant_id', return_value=1), \
             patch('routes.cheques.branch_scope_id', return_value=2), \
             patch('sqlalchemy.select', return_value=MagicMock(where=MagicMock(return_value=MagicMock()))):
            result = _scoped_suppliers_query()
        assert result is sq

    def test_scoped_customers_no_branch(self):
        from routes.cheques import _scoped_customers_query
        cq = MagicMock()
        cq.filter.return_value = cq
        with patch('routes.cheques.Customer.query', cq), \
             patch('routes.cheques.get_active_tenant_id', return_value=1), \
             patch('routes.cheques.branch_scope_id', return_value=None):
            result = _scoped_customers_query()
        assert result is cq

    def test_scoped_suppliers_no_branch(self):
        from routes.cheques import _scoped_suppliers_query
        sq = MagicMock()
        sq.filter.return_value = sq
        with patch('routes.cheques.Supplier.query', sq), \
             patch('routes.cheques.get_active_tenant_id', return_value=1), \
             patch('routes.cheques.branch_scope_id', return_value=None):
            result = _scoped_suppliers_query()
        assert result is sq

    def test_scoped_cheques_branch_filter(self):
        from routes.cheques import _scoped_cheques_query
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        with patch('routes.cheques.Cheque.query', q), \
             patch('routes.cheques.get_active_tenant_id', return_value=1), \
             patch('routes.cheques.branch_scope_id', return_value=3):
            _scoped_cheques_query()
        q.filter.assert_called()


class TestChequesAuth:
    def test_index_requires_login(self, cheques_client):
        with _cheque_patches(), unauthenticated_client(cheques_client):
            resp = cheques_client.get('/cheques/')
        assert resp.status_code == 401


class TestChequesListPages:
    def test_index(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.get('/cheques/?type=incoming&status=pending&search=bank')
        assert resp.status_code == 200

    def test_incoming(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.get('/cheques/incoming?status=pending')
        assert resp.status_code == 200

    def test_outgoing(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.get('/cheques/outgoing')
        assert resp.status_code == 200

    def test_outgoing_with_status(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.get('/cheques/outgoing?status=pending')
        assert resp.status_code == 200

    def test_alerts(self, cheques_client):
        bounced_q = MagicMock()
        bounced_q.all.return_value = []
        with _cheque_patches(), patch('routes.cheques._scoped_cheques_query', return_value=bounced_q):
            resp = cheques_client.get('/cheques/alerts')
        assert resp.status_code == 200

    def test_archived(self, cheques_admin_client):
        with _cheque_patches():
            resp = cheques_admin_client.get('/cheques/archived')
        assert resp.status_code == 200


class TestChequesCreate:
    def test_create_get(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.get('/cheques/create')
        assert resp.status_code == 200

    def test_create_get_currency_fallback(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.resolve_default_currency', side_effect=RuntimeError('no tenant')):
            resp = cheques_client.get('/cheques/create')
        assert resp.status_code == 200

    def test_create_missing_type(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.post('/cheques/create', data={'amount': '100'})
        assert resp.status_code == 200

    def test_create_missing_type_currency_fallback(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.resolve_default_currency', side_effect=RuntimeError('no tenant')):
            resp = cheques_client.post('/cheques/create', data={'amount': '100'})
        assert resp.status_code == 200

    def test_create_incoming_success(self, cheques_client):
        cheque = _mock_cheque(id=20, cheque_type='incoming')
        with _cheque_patches(), patch('routes.cheques.Cheque', return_value=cheque):
            resp = cheques_client.post('/cheques/create', data={
                'cheque_type': 'incoming',
                'amount': '1000',
                'issue_date': '2026-01-01',
                'due_date': '2026-02-01',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_outgoing_success(self, cheques_client):
        cheque = _mock_cheque(id=21, cheque_type='outgoing')
        with _cheque_patches(), patch('routes.cheques.Cheque', return_value=cheque):
            resp = cheques_client.post('/cheques/create', data={
                'cheque_type': 'outgoing',
                'amount': '500',
                'issue_date': '2026-01-01',
                'due_date': '2026-02-01',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_invalid_customer_scope(self, cheques_client):
        customers_q = _chain_query(first=None)
        with _cheque_patches(), patch('routes.cheques._scoped_customers_query', return_value=customers_q):
            resp = cheques_client.post('/cheques/create', data={
                'cheque_type': 'incoming',
                'amount': '100',
                'issue_date': '2026-01-01',
                'due_date': '2026-02-01',
                'customer_id': '5',
            })
        assert resp.status_code == 200

    def test_create_invalid_supplier_scope(self, cheques_client):
        suppliers_q = _chain_query(first=None)
        with _cheque_patches(), patch('routes.cheques._scoped_suppliers_query', return_value=suppliers_q):
            resp = cheques_client.post('/cheques/create', data={
                'cheque_type': 'outgoing',
                'amount': '100',
                'issue_date': '2026-01-01',
                'due_date': '2026-02-01',
                'supplier_id': '8',
            })
        assert resp.status_code == 200

    def test_create_currency_fallback_logs(self, cheques_client):
        cheque = _mock_cheque(id=22)
        with _cheque_patches(), \
             patch('routes.cheques.Cheque', return_value=cheque), \
             patch('routes.cheques.resolve_default_currency', side_effect=RuntimeError('currency fail')), \
             patch('routes.cheques.LoggingCore.log_error') as log_err:
            resp = cheques_client.post('/cheques/create', data={
                'cheque_type': 'incoming',
                'amount': '100',
                'issue_date': '2026-01-01',
                'due_date': '2026-02-01',
            }, follow_redirects=False)
        assert resp.status_code == 302
        log_err.assert_called()

    def test_create_currency_log_error_inner_failure(self, cheques_client):
        cheque = _mock_cheque(id=23)
        with _cheque_patches(), \
             patch('routes.cheques.Cheque', return_value=cheque), \
             patch('routes.cheques.resolve_default_currency', side_effect=RuntimeError('currency fail')), \
             patch('routes.cheques.LoggingCore.log_error', side_effect=RuntimeError('log fail')):
            resp = cheques_client.post('/cheques/create', data={
                'cheque_type': 'incoming',
                'amount': '100',
                'issue_date': '2026-01-01',
                'due_date': '2026-02-01',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_forbidden_scope(self, cheques_client):
        with _cheque_patches(in_scope=False):
            resp = cheques_client.get('/cheques/1/edit')
        assert resp.status_code == 403

    def test_deposit_generic_error(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.process_cheque_deposit', side_effect=RuntimeError('db')):
            resp = cheques_client.post('/cheques/1/deposit', follow_redirects=False)
        assert resp.status_code == 302

    def test_bounce_generic_error(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.process_cheque_bounce', side_effect=RuntimeError('db')):
            resp = cheques_client.post('/cheques/1/bounce', follow_redirects=False)
        assert resp.status_code == 302

    def test_cancel_generic_error(self, cheques_admin_client):
        with _cheque_patches(), patch('routes.cheques.process_cheque_cancel', side_effect=RuntimeError('db')):
            resp = cheques_admin_client.post('/cheques/1/cancel', follow_redirects=False)
        assert resp.status_code == 302

    def test_clear_currency_fallback(self, cheques_client):
        with _cheque_patches(), \
             patch('routes.cheques.resolve_default_currency', side_effect=RuntimeError('no currency')):
            resp = cheques_client.post('/cheques/1/clear', data={'clearance_exchange_rate': '3.67'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_exception(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.generate_number', side_effect=RuntimeError('boom')):
            resp = cheques_client.post('/cheques/create', data={
                'cheque_type': 'incoming',
                'amount': '100',
                'issue_date': '2026-01-01',
                'due_date': '2026-02-01',
            })
        assert resp.status_code == 200


class TestChequesViewEdit:
    def test_view(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.get('/cheques/1')
        assert resp.status_code == 200

    def test_view_forbidden(self, cheques_client):
        with _cheque_patches(in_scope=False):
            resp = cheques_client.get('/cheques/1')
        assert resp.status_code == 403

    def test_edit_get(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.get('/cheques/1/edit')
        assert resp.status_code == 200

    def test_edit_blocked_status(self, cheques_client):
        cheque = _mock_cheque(status='cleared')
        with _cheque_patches(cheque=cheque):
            resp = cheques_client.get('/cheques/1/edit', follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_post_success(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.post('/cheques/1/edit', data={
                'amount': '900',
                'issue_date': '2026-01-01',
                'due_date': '2026-03-01',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_post_error(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques._resolve_transaction_rate', side_effect=RuntimeError('rate')):
            resp = cheques_client.post('/cheques/1/edit', data={
                'amount': '900',
                'issue_date': '2026-01-01',
                'due_date': '2026-03-01',
            })
        assert resp.status_code == 200

    def test_edit_post_currency_fallback(self, cheques_client):
        with _cheque_patches(), \
             patch('routes.cheques.resolve_default_currency', side_effect=RuntimeError('no currency')), \
             patch('routes.cheques.LoggingCore.log_error', side_effect=RuntimeError('log fail')):
            resp = cheques_client.post('/cheques/1/edit', data={
                'amount': '900',
                'issue_date': '2026-01-01',
                'due_date': '2026-03-01',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_get_currency_fallback(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.resolve_default_currency', side_effect=RuntimeError('no tenant')):
            resp = cheques_client.get('/cheques/1/edit')
        assert resp.status_code == 200


class TestChequesActions:
    def test_deposit_success(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.post('/cheques/1/deposit', data={'deposit_date': '2026-02-01'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_deposit_value_error(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.process_cheque_deposit', side_effect=ValueError('bad date')):
            resp = cheques_client.post('/cheques/1/deposit', data={'deposit_date': 'bad'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_deposit_forbidden_scope(self, cheques_client):
        with _cheque_patches(in_scope=False):
            resp = cheques_client.post('/cheques/1/deposit', follow_redirects=False)
        assert resp.status_code == 403

    def test_clear_with_gain(self, cheques_client):
        cheque = _mock_cheque(currency_gain_loss=Decimal('10'))
        with _cheque_patches(cheque=cheque):
            resp = cheques_client.post('/cheques/1/clear', data={'clearance_date': '2026-02-05'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_clear_with_loss(self, cheques_client):
        cheque = _mock_cheque(currency_gain_loss=Decimal('-5'))
        with _cheque_patches(cheque=cheque):
            resp = cheques_client.post('/cheques/1/clear', data={}, follow_redirects=False)
        assert resp.status_code == 302

    def test_clear_value_error(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.process_cheque_clear', side_effect=ValueError('bad state')):
            resp = cheques_client.post('/cheques/1/clear', follow_redirects=False)
        assert resp.status_code == 302

    def test_clear_generic_error(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.process_cheque_clear', side_effect=RuntimeError('db')):
            resp = cheques_client.post('/cheques/1/clear', follow_redirects=False)
        assert resp.status_code == 302

    def test_clear_forbidden_scope(self, cheques_client):
        with _cheque_patches(in_scope=False):
            resp = cheques_client.post('/cheques/1/clear', follow_redirects=False)
        assert resp.status_code == 403

    def test_bounce_with_details(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.post('/cheques/1/bounce', data={
                'bounce_reason': 'NSF',
                'bounce_details': 'Insufficient funds',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_bounce_value_error(self, cheques_client):
        with _cheque_patches(), patch('routes.cheques.process_cheque_bounce', side_effect=ValueError('invalid')):
            resp = cheques_client.post('/cheques/1/bounce', follow_redirects=False)
        assert resp.status_code == 302

    def test_bounce_forbidden_scope(self, cheques_client):
        with _cheque_patches(in_scope=False):
            resp = cheques_client.post('/cheques/1/bounce', follow_redirects=False)
        assert resp.status_code == 403

    def test_cancel_cleared_blocked(self, cheques_admin_client):
        cheque = _mock_cheque(status='cleared')
        with _cheque_patches(cheque=cheque):
            resp = cheques_admin_client.post('/cheques/1/cancel', follow_redirects=False)
        assert resp.status_code == 302

    def test_cancel_success(self, cheques_admin_client):
        with _cheque_patches():
            resp = cheques_admin_client.post('/cheques/1/cancel', data={'cancel_reason': 'mistake'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_cancel_forbidden_scope(self, cheques_admin_client):
        with _cheque_patches(in_scope=False):
            resp = cheques_admin_client.post('/cheques/1/cancel', follow_redirects=False)
        assert resp.status_code == 403

    def test_delete_archive(self, cheques_admin_client):
        cheque = _mock_cheque(status='deposited', receipt_id=5)
        with _cheque_patches(cheque=cheque):
            resp = cheques_admin_client.post('/cheques/1/delete', follow_redirects=False)
        assert resp.status_code == 302
        cheque.archive.assert_called_once()

    def test_delete_hard(self, cheques_admin_client):
        cheque = _mock_cheque(status='pending')
        gl_q = MagicMock()
        with _cheque_patches(cheque=cheque), patch('models.GLJournalEntry.query', gl_q):
            resp = cheques_admin_client.post('/cheques/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_forbidden_scope(self, cheques_admin_client):
        with _cheque_patches(in_scope=False):
            resp = cheques_admin_client.post('/cheques/1/delete', follow_redirects=False)
        assert resp.status_code == 403

    def test_delete_error(self, cheques_admin_client):
        cheque = _mock_cheque(status='pending')
        session = MagicMock()
        session.commit.side_effect = RuntimeError('fk')
        with _cheque_patches(cheque=cheque), patch('extensions.db.session', session):
            resp = cheques_admin_client.post('/cheques/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_restore_success(self, cheques_admin_client):
        with _cheque_patches():
            resp = cheques_admin_client.post('/cheques/1/restore', follow_redirects=False)
        assert resp.status_code == 302

    def test_restore_forbidden_scope(self, cheques_admin_client):
        with _cheque_patches(in_scope=False):
            resp = cheques_admin_client.post('/cheques/1/restore', follow_redirects=False)
        assert resp.status_code == 403

    def test_restore_error(self, cheques_admin_client):
        cheque = _mock_cheque()
        cheque.restore.side_effect = RuntimeError('fail')
        with _cheque_patches(cheque=cheque):
            resp = cheques_admin_client.post('/cheques/1/restore', follow_redirects=False)
        assert resp.status_code == 302


class TestChequesApi:
    def test_api_stats(self, cheques_client):
        with _cheque_patches():
            resp = cheques_client.get('/cheques/api/stats')
        assert resp.status_code == 200

    def test_api_alerts(self, cheques_client):
        due = [_mock_cheque(id=2)]
        with _cheque_patches(), \
             patch('routes.cheques.Cheque.get_due_soon_cheques', return_value=due), \
             patch('routes.cheques.Cheque.get_overdue_cheques', return_value=due):
            resp = cheques_client.get('/cheques/api/alerts')
        data = resp.get_json()
        assert data['due_soon'] == 1
        assert len(data['cheques_due_soon']) == 1
