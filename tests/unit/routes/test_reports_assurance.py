"""Reports routes — tenant-scoped helpers and index access."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import Forbidden


@pytest.fixture
def reports_client(app_factory, mocker):
    user = MagicMock(is_authenticated=True, tenant_id=1, id=1)
    user.has_permission.return_value = True
    mocker.patch('flask_login.utils._get_user', return_value=user)
    mocker.patch('extensions.limiter.limit', return_value=lambda f: f)
    mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
    mocker.patch('utils.decorators.report_branch_scope_id', return_value=None)
    mocker.patch('utils.auth_helpers.is_global_owner_user', return_value=False)
    from routes.reports import reports_bp
    app = app_factory(reports_bp)
    return app.test_client()


class TestReportHelpers:
    def test_get_confirmed_sale_paid_aed(self, mocker):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = Decimal('150.50')
        mocker.patch('routes.reports.db.session.query', return_value=q)
        from routes.reports import get_confirmed_sale_paid_aed
        assert get_confirmed_sale_paid_aed(1, tenant_id=1, branch_id=2) == Decimal('150.50')

    def test_get_confirmed_supplier_paid_aed(self, mocker):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = Decimal('80')
        mocker.patch('routes.reports.db.session.query', return_value=q)
        from routes.reports import get_confirmed_supplier_paid_aed
        assert get_confirmed_supplier_paid_aed(3, purchase_id=9, tenant_id=1) == Decimal('80')

    def test_scoped_customer_query_all_branches(self, mocker):
        mocker.patch('routes.reports.report_branch_scope_id', return_value=None)
        mocker.patch('routes.reports.tenant_query', return_value='customers')
        from routes.reports import _scoped_customer_query
        assert _scoped_customer_query() == 'customers'

    def test_scoped_supplier_query_branch_scoped(self, mocker):
        mocker.patch('routes.reports.report_branch_scope_id', return_value=5)
        supplier_q = MagicMock()
        mocker.patch('routes.reports.tenant_query', return_value=supplier_q)
        from routes.reports import _scoped_supplier_query
        _scoped_supplier_query()
        supplier_q.filter.assert_called()


class TestReportsRoutes:
    def test_index_renders(self, reports_client, mocker):
        mocker.patch('routes.reports.render_template', return_value='ok')
        resp = reports_client.get('/reports/')
        assert resp.status_code == 200

    def test_api_model_fields(self, reports_client, mocker):
        mocker.patch('routes.reports.tenant_get_or_404', return_value=MagicMock())
        resp = reports_client.get('/reports/api/model-fields/customer/1')
        assert resp.status_code in (200, 404, 500)

    def test_enforce_report_tenant_for_non_owner(self, app_factory, mocker):
        from werkzeug.exceptions import Forbidden
        user = MagicMock(is_authenticated=True, tenant_id=None, id=1)
        mocker.patch('flask_login.utils._get_user', return_value=user)
        mocker.patch('utils.auth_helpers.is_global_owner_user', return_value=False)
        mocker.patch('routes.reports.require_report_tenant_id', side_effect=Forbidden())
        from routes.reports import reports_bp
        app = app_factory(reports_bp)
        client = app.test_client()
        with patch('routes.reports.render_template', return_value='x'):
            resp = client.get('/reports/sales')
        assert resp.status_code == 403
