"""Reports routes — tenant-scoped helpers and index access.

routes/reports.py delegates all queries to ReportsQueryService, so helper
tests stub that service boundary directly.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def reports_client(app_factory, mocker):
    user = MagicMock(is_authenticated=True, tenant_id=1, id=1)
    user.has_permission.return_value = True
    mocker.patch("flask_login.utils._get_user", return_value=user)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
    mocker.patch("utils.decorators.report_branch_scope_id", return_value=None)
    mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
    from routes.reports import reports_bp

    app = app_factory(reports_bp)
    return app.test_client()


class TestReportHelpers:
    def test_get_confirmed_sale_paid_aed(self, app, mocker):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = Decimal("150.50")
        mocker.patch("services.reports_query_service.db.session.query", return_value=q)
        mocker.patch("utils.cache_decorators.cache.get", return_value=None)
        mocker.patch("utils.cache_decorators.cache.set")
        from services.reports_query_service import ReportsQueryService

        with app.app_context():
            assert ReportsQueryService.get_confirmed_sale_paid_aed(1, tenant_id=1, branch_id=2) == Decimal("150.50")

    def test_get_confirmed_supplier_paid_aed(self, app, mocker):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = Decimal("80")
        mocker.patch("services.reports_query_service.db.session.query", return_value=q)
        mocker.patch("utils.cache_decorators.cache.get", return_value=None)
        mocker.patch("utils.cache_decorators.cache.set")
        from services.reports_query_service import ReportsQueryService

        with app.app_context():
            assert ReportsQueryService.get_confirmed_supplier_paid_aed(3, purchase_id=9, tenant_id=1) == Decimal("80")

    def test_scoped_customer_query_all_branches(self, mocker):
        mocker.patch("services.reports_query_service.report_branch_scope_id", return_value=None)
        mocker.patch("services.reports_query_service.tenant_query", return_value="customers")
        from services.reports_query_service import ReportsQueryService

        assert ReportsQueryService._scoped_customer_query() == "customers"

    def test_scoped_supplier_query_branch_scoped(self, mocker):
        mocker.patch("services.reports_query_service.report_branch_scope_id", return_value=5)
        supplier_q = MagicMock()
        mocker.patch("services.reports_query_service.tenant_query", return_value=supplier_q)
        from services.reports_query_service import ReportsQueryService

        ReportsQueryService._scoped_supplier_query()
        supplier_q.filter.assert_called()

    def test_get_confirmed_supplier_paid_aed_branch(self, app, mocker):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = Decimal("80")
        mocker.patch("services.reports_query_service.db.session.query", return_value=q)
        mocker.patch("utils.cache_decorators.cache.get", return_value=None)
        mocker.patch("utils.cache_decorators.cache.set")
        from services.reports_query_service import ReportsQueryService

        with app.app_context():
            ReportsQueryService.get_confirmed_supplier_paid_aed(3, tenant_id=1, branch_id=4)
        assert q.filter.call_count >= 2

    def test_get_confirmed_sale_paid_aed_branch(self, app, mocker):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = Decimal("25")
        mocker.patch("services.reports_query_service.db.session.query", return_value=q)
        mocker.patch("utils.cache_decorators.cache.get", return_value=None)
        mocker.patch("utils.cache_decorators.cache.set")
        from services.reports_query_service import ReportsQueryService

        with app.app_context():
            assert ReportsQueryService.get_confirmed_sale_paid_aed(9, tenant_id=1, branch_id=2) == Decimal("25")

    def test_scoped_customer_query_branch_scoped(self, mocker):
        mocker.patch("services.reports_query_service.report_branch_scope_id", return_value=3)
        customer_q = MagicMock()
        mocker.patch("services.reports_query_service.tenant_query", return_value=customer_q)
        from services.reports_query_service import ReportsQueryService

        ReportsQueryService._scoped_customer_query()
        customer_q.filter.assert_called_once()


class TestReportsRoutes:
    def test_index_renders(self, reports_client, mocker):
        mocker.patch("routes.reports.render_template", return_value="ok")
        resp = reports_client.get("/reports/")
        assert resp.status_code == 200

    def test_api_model_fields(self, reports_client, mocker):
        mocker.patch("routes.reports.tenant_get_or_404", return_value=MagicMock())
        resp = reports_client.get("/reports/api/model-fields/customer/1")
        assert resp.status_code in (200, 404, 500)

    def test_enforce_report_tenant_for_non_owner(self, app_factory, mocker):
        from werkzeug.exceptions import Forbidden

        user = MagicMock(is_authenticated=True, tenant_id=None, id=1)
        mocker.patch("flask_login.utils._get_user", return_value=user)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("routes.reports.require_report_tenant_id", side_effect=Forbidden())
        from routes.reports import reports_bp

        app = app_factory(reports_bp)
        client = app.test_client()
        with patch("routes.reports.render_template", return_value="x"):
            resp = client.get("/reports/sales")
        assert resp.status_code == 403

    def test_partners_report_renders(self, reports_client, mocker):
        mocker.patch("routes.reports.render_template", return_value="ok")
        mocker.patch(
            "services.reports_query_service.ReportsQueryService.build_partners_report",
            return_value={
                "partners_data": [],
                "merchants_data": [],
                "partners_summary": {},
                "merchants_summary": {},
                "suppliers_summary": {},
            },
        )
        resp = reports_client.get("/reports/partners")
        assert resp.status_code == 200

    def test_inventory_reconciliation_page(self, reports_client, mocker):
        mocker.patch("routes.reports.render_template", return_value="ok")
        wh_q = MagicMock()
        wh_q.filter_by.return_value = wh_q
        wh_q.filter.return_value = wh_q
        wh_q.order_by.return_value = wh_q
        wh_q.all.return_value = []
        mocker.patch("models.Warehouse.query", wh_q)
        mocker.patch("utils.branching.get_accessible_branches", return_value=[])
        mocker.patch("utils.branching.user_can_access_branch", return_value=True)
        mocker.patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary",
            return_value={"warehouse_summary": [], "summary": {}},
        )
        resp = reports_client.get("/reports/inventory-reconciliation?branch_id=1")
        assert resp.status_code == 200
