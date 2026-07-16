from __future__ import annotations

from contextlib import ExitStack, contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_permission_auth, mock_user, unauthenticated_client


def _mock_return(**kwargs):
    pr = MagicMock()
    pr.id = kwargs.get('id', 1)
    pr.return_number = kwargs.get('return_number', 'RET-001')
    pr.sale_id = kwargs.get('sale_id', 10)
    pr.refund_amount = kwargs.get('refund_amount', Decimal('50'))
    pr.amount_aed = kwargs.get('amount_aed', Decimal('50'))
    pr.tenant_id = kwargs.get('tenant_id', 1)
    return pr


@contextmanager
def _returns_patches(**kwargs):
    returns_q = kwargs.get('returns_q', _chain_query(all=[_mock_return()]))
    with ExitStack() as stack:
        stack.enter_context(patch('routes.returns.render_template', return_value='ok'))
        stack.enter_context(patch('routes.returns.get_active_tenant_id', return_value=kwargs.get('tenant_id', 1)))
        stack.enter_context(patch('routes.returns.is_platform_owner', return_value=kwargs.get('is_platform_owner', False)))
        stack.enter_context(patch('routes.returns.branch_scope_id', return_value=kwargs.get('branch_scope')))
        stack.enter_context(patch('routes.returns.should_show_all_branch_columns', return_value=False))
        stack.enter_context(patch('routes.returns.ProductReturn.query', returns_q))
        stack.enter_context(patch('routes.returns.LoggingCore.log_audit'))
        stack.enter_context(patch('extensions.limiter.limit', return_value=lambda f: f))
        yield


@pytest.fixture
def returns_client(app_factory, bypass_permission_auth):
    from routes.returns import returns_bp
    app = app_factory(returns_bp)
    return app.test_client()


class TestReturnsScopedQuery:
    def test_scoped_query_seller_filter(self, bypass_permission_auth):
        from routes.returns import _scoped_returns_query
        bypass_permission_auth.is_seller.return_value = True
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        with patch('routes.returns.ProductReturn.query', q), \
             patch('routes.returns.get_active_tenant_id', return_value=1), \
             patch('routes.returns.branch_scope_id', return_value=None), \
             patch('routes.returns.is_platform_owner', return_value=False):
            result = _scoped_returns_query()
        assert result is q
        q.filter.assert_called()

    def test_scoped_query_platform_owner_no_tenant(self, bypass_permission_auth):
        from routes.returns import _scoped_returns_query
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        with patch('routes.returns.ProductReturn.query', q), \
             patch('routes.returns.get_active_tenant_id', return_value=None), \
             patch('routes.returns.is_platform_owner', return_value=True), \
             patch('routes.returns.branch_scope_id', return_value=None):
            _scoped_returns_query()
        q.filter.assert_called()

    def test_scoped_query_non_owner_no_tenant(self, bypass_permission_auth):
        from routes.returns import _scoped_returns_query
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        with patch('routes.returns.ProductReturn.query', q), \
             patch('routes.returns.get_active_tenant_id', return_value=None), \
             patch('routes.returns.is_platform_owner', return_value=False), \
             patch('routes.returns.branch_scope_id', return_value=None):
            _scoped_returns_query()
        q.filter.assert_called()

    def test_scoped_query_branch_filter(self, bypass_permission_auth):
        from routes.returns import _scoped_returns_query
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        with patch('routes.returns.ProductReturn.query', q), \
             patch('routes.returns.get_active_tenant_id', return_value=1), \
             patch('routes.returns.is_platform_owner', return_value=False), \
             patch('routes.returns.branch_scope_id', return_value=7):
            _scoped_returns_query()
        assert q.filter.call_count >= 2


class TestReturnsAuth:
    def test_index_requires_login(self, returns_client):
        with _returns_patches(), unauthenticated_client(returns_client):
            resp = returns_client.get('/returns/')
        assert resp.status_code == 401

    def test_index_no_permission(self, returns_client, mock_user):
        mock_user.has_permission.return_value = False
        with _returns_patches(), patch('utils.decorators.is_global_owner_user', return_value=False):
            resp = returns_client.get('/returns/')
        assert resp.status_code == 403


class TestReturnsIndex:
    def test_index_renders(self, returns_client):
        with _returns_patches():
            resp = returns_client.get('/returns/')
        assert resp.status_code == 200

    def test_index_with_pagination(self, returns_client):
        with _returns_patches():
            resp = returns_client.get('/returns/?page=2&per_page=10')
        assert resp.status_code == 200


class TestReturnsView:
    def test_view_found(self, returns_client):
        pr = _mock_return()
        with _returns_patches(), \
             patch('routes.returns._scoped_returns_query') as scoped:
            scoped.return_value.filter.return_value.first.return_value = pr
            resp = returns_client.get('/returns/view/1')
        assert resp.status_code == 200

    def test_view_not_found(self, returns_client):
        with _returns_patches(), \
             patch('routes.returns._scoped_returns_query') as scoped:
            scoped.return_value.filter.return_value.first.return_value = None
            resp = returns_client.get('/returns/view/999')
        assert resp.status_code == 404


class TestReturnsApiCreate:
    def test_create_missing_body(self, returns_client):
        with _returns_patches():
            resp = returns_client.post('/returns/api/create', json=None)
        assert resp.status_code == 400

    def test_create_missing_sale_or_lines(self, returns_client):
        with _returns_patches():
            resp = returns_client.post('/returns/api/create', json={'sale_id': 1})
        assert resp.status_code == 400

    def test_create_success(self, returns_client):
        result = _mock_return(id=5, return_number='RET-005')
        with _returns_patches(), \
             patch('utils.tenanting.tenant_get_or_404'), \
             patch('routes.returns.ReturnService.create_return', return_value=result):
            resp = returns_client.post('/returns/api/create', json={
                'sale_id': 10,
                'lines': [{'sale_line_id': 1, 'quantity': 1}],
            })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['return_number'] == 'RET-005'

    def test_create_value_error(self, returns_client):
        with _returns_patches(), \
             patch('utils.tenanting.tenant_get_or_404'), \
             patch('routes.returns.ReturnService.create_return', side_effect=ValueError('bad')):
            resp = returns_client.post('/returns/api/create', json={
                'sale_id': 10,
                'lines': [{'sale_line_id': 1, 'quantity': 1}],
            })
        assert resp.status_code == 400

    def test_create_server_error(self, returns_client):
        with _returns_patches(), \
             patch('utils.tenanting.tenant_get_or_404'), \
             patch('routes.returns.ReturnService.create_return', side_effect=RuntimeError('db')):
            resp = returns_client.post('/returns/api/create', json={
                'sale_id': 10,
                'lines': [{'sale_line_id': 1, 'quantity': 1}],
            })
        assert resp.status_code == 500

    def test_create_with_manual_refund(self, returns_client):
        result = _mock_return()
        with _returns_patches(), \
             patch('utils.tenanting.tenant_get_or_404'), \
             patch('routes.returns.ReturnService.create_return', return_value=result) as create:
            returns_client.post('/returns/api/create', json={
                'sale_id': 10,
                'lines': [{'sale_line_id': 1, 'quantity': 1}],
                'manual_refund_amount': 25,
            })
        assert create.call_args.kwargs['manual_refund_amount'] == 25
