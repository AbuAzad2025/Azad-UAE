import io
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from flask import make_response
from werkzeug.exceptions import NotFound


def _configure_user(mock_user):
    mock_user.is_seller.return_value = False
    mock_user.can_see_costs.return_value = True
    mock_user.is_admin.return_value = True
    mock_user.has_permission.return_value = True
    return mock_user


def _anon_user():
    user = MagicMock()
    user.is_authenticated = False
    return user


@contextmanager
def _unauthenticated(reports_client):
    login_manager = MagicMock()
    login_manager.unauthorized.return_value = make_response("unauthorized", 401)
    reports_client.application.login_manager = login_manager
    with patch("flask_login.utils._get_user", return_value=_anon_user()):
        yield


def _send_file_response():
    return make_response("export", 200, {"Content-Type": "application/octet-stream"})


def _entity_mock(name="Test Entity", customer_type="regular"):
    entity = MagicMock()
    entity.id = 7
    entity.name = name
    entity.customer_type = customer_type
    entity.tenant_id = 1
    return entity


def _export_io():
    return io.BytesIO(b"export-data")


class TestReportsIndex:
    def test_index_returns_200(self, reports_client):
        resp = reports_client.get("/reports/")
        assert resp.status_code == 200

    def test_index_unauthenticated_redirects(self, reports_client):
        with _unauthenticated(reports_client):
            resp = reports_client.get("/reports/")
            assert resp.status_code in (302, 401)


class TestReportsPartners:
    def test_partners_returns_200(self, reports_client, mock_user):
        _configure_user(mock_user)
        resp = reports_client.get("/reports/partners")
        assert resp.status_code == 200

    def test_partners_with_date_from_date_to(self, reports_client, mock_user):
        _configure_user(mock_user)
        resp = reports_client.get(
            "/reports/partners",
            query_string={"date_from": "2025-01-01", "date_to": "2025-12-31"},
        )
        assert resp.status_code == 200

    def test_partners_unauthenticated(self, reports_client):
        with _unauthenticated(reports_client):
            resp = reports_client.get("/reports/partners")
            assert resp.status_code in (302, 401)

    def test_partners_renders_template(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.render_template", return_value="partners-page") as render:
            resp = reports_client.get("/reports/partners")
            assert resp.status_code == 200
            assert render.called
            assert "partners.html" in render.call_args[0][0]


class TestReportsSales:
    def test_sales_returns_200(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.Customer") as customer_model, \
             patch("utils.tenanting.scoped_user_query", return_value=_chain_query_stub(all=[])):
            customer_model.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/sales")
            assert resp.status_code == 200

    def test_sales_with_date_from_date_to(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.Customer") as customer_model, \
             patch("utils.tenanting.scoped_user_query", return_value=_chain_query_stub(all=[])):
            customer_model.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get(
                "/reports/sales",
                query_string={"date_from": "2025-06-01", "date_to": "2025-06-30"},
            )
            assert resp.status_code == 200

    def test_sales_with_customer_and_seller_filters(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.Customer") as customer_model, \
             patch("utils.tenanting.scoped_user_query", return_value=_chain_query_stub(all=[])):
            customer_model.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get(
                "/reports/sales",
                query_string={"customer": "3", "seller": "5"},
            )
            assert resp.status_code == 200

    def test_sales_export_csv(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("services.export_service.ExportService.export_to_csv", return_value=_export_io()), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/sales/export")
            assert resp.status_code == 200

    def test_sales_export_xlsx(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("services.export_service.ExportService.export_to_xlsx", return_value=_export_io()), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/sales/export?format=xlsx")
            assert resp.status_code == 200

    def test_sales_unauthenticated(self, reports_client):
        with _unauthenticated(reports_client):
            resp = reports_client.get("/reports/sales")
            assert resp.status_code in (302, 401)


class TestReportsPurchases:
    def test_purchases_returns_200(self, reports_client, mock_user):
        _configure_user(mock_user)
        resp = reports_client.get("/reports/purchases")
        assert resp.status_code == 200

    def test_purchases_with_start_end_date(self, reports_client, mock_user):
        _configure_user(mock_user)
        resp = reports_client.get(
            "/reports/purchases",
            query_string={"start_date": "2025-01-01", "end_date": "2025-06-30"},
        )
        assert resp.status_code == 200

    def test_purchases_seller_gets_403(self, reports_client, mock_user):
        mock_user.is_seller.return_value = True
        resp = reports_client.get("/reports/purchases")
        assert resp.status_code == 403

    def test_purchases_export_csv(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("services.export_service.ExportService.export_to_csv", return_value=_export_io()), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/purchases/export")
            assert resp.status_code == 200

    def test_purchases_export_seller_forbidden(self, reports_client, mock_user):
        mock_user.is_seller.return_value = True
        resp = reports_client.get("/reports/purchases/export")
        assert resp.status_code == 403


class TestReportsArReconciliation:
    def test_ar_reconciliation_returns_200(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("services.ar_reconciliation_service.ARReconciliationService.build_report", return_value={}), \
             patch("utils.branching.get_accessible_branches", return_value=[]):
            resp = reports_client.get("/reports/ar-reconciliation")
            assert resp.status_code == 200

    def test_ar_reconciliation_with_branch_id(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("services.ar_reconciliation_service.ARReconciliationService.build_report", return_value={}), \
             patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.user_can_access_branch", return_value=True):
            resp = reports_client.get("/reports/ar-reconciliation?branch_id=2")
            assert resp.status_code == 200

    def test_ar_reconciliation_branch_forbidden(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("utils.decorators.report_branch_scope_id", return_value=3):
            resp = reports_client.get("/reports/ar-reconciliation?branch_id=99")
            assert resp.status_code == 403


class TestReportsInventoryReconciliation:
    def test_inventory_reconciliation_returns_200(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary",
            return_value={"rows": []},
        ), patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.get_accessible_warehouse_ids", return_value=[]), \
             patch("models.Warehouse") as wh_model:
            wh_model.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = []
            resp = reports_client.get("/reports/inventory-reconciliation")
            assert resp.status_code == 200

    def test_inventory_reconciliation_date_params(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary",
            return_value={"rows": []},
        ), patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.get_accessible_warehouse_ids", return_value=[]), \
             patch("models.Warehouse") as wh_model:
            wh_model.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = []
            resp = reports_client.get(
                "/reports/inventory-reconciliation",
                query_string={"date_from": "2025-01-01", "date_to": "2025-06-30"},
            )
            assert resp.status_code == 200

    def test_inventory_reconciliation_export(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch(
            "services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary",
            return_value={"rows": []},
        ), patch("services.export_service.ExportService.export_to_xlsx", return_value=_export_io()), \
             patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.get_accessible_warehouse_ids", return_value=[]), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/inventory-reconciliation/export")
            assert resp.status_code == 200

    def test_inventory_reconciliation_branch_forbidden(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("utils.decorators.report_branch_scope_id", return_value=4):
            resp = reports_client.get("/reports/inventory-reconciliation?branch_id=8")
            assert resp.status_code == 403


class TestReportsReceivables:
    def test_receivables_returns_200(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.Customer") as customer_model:
            customer_model.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/receivables")
            assert resp.status_code == 200

    def test_receivables_with_customer(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.Customer") as customer_model:
            customer_model.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/receivables?customer=12")
            assert resp.status_code == 200

    def test_receivables_export_csv(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("services.export_service.ExportService.export_to_csv", return_value=_export_io()), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/receivables/export")
            assert resp.status_code == 200

    def test_receivables_export_xlsx(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("services.export_service.ExportService.export_to_xlsx", return_value=_export_io()), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/receivables/export?format=xlsx")
            assert resp.status_code == 200


class TestReportsInventory:
    def test_inventory_returns_200(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]):
            resp = reports_client.get("/reports/inventory")
            assert resp.status_code == 200

    def test_inventory_with_branch_id(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]), \
             patch("utils.branching.user_can_access_branch", return_value=True):
            resp = reports_client.get("/reports/inventory?branch_id=2")
            assert resp.status_code == 200

    def test_inventory_export_csv(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]), \
             patch("utils.branching.user_can_access_branch", return_value=True), \
             patch("services.export_service.ExportService.export_to_csv", return_value=_export_io()), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/inventory/export")
            assert resp.status_code == 200

    def test_inventory_branch_forbidden(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("utils.decorators.report_branch_scope_id", return_value=6):
            resp = reports_client.get("/reports/inventory?branch_id=20")
            assert resp.status_code == 403


class TestReportsApiModelFields:
    def test_empty_model_returns_empty_arrays(self, reports_client):
        resp = reports_client.get("/reports/api/model_fields")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["columns"] == []
        assert body["date_fields"] == []
        assert body["all_fields"] == []

    def test_empty_model_param_returns_empty_arrays(self, reports_client):
        resp = reports_client.get("/reports/api/model_fields?model=")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["columns"] == []
        assert body["date_fields"] == []
        assert body["all_fields"] == []

    def test_sale_model_returns_columns(self, reports_client):
        resp = reports_client.get("/reports/api/model_fields?model=sale")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "sale_number" in body["columns"]
        assert "sale_date" in body["date_fields"]
        assert body["all_fields"] == body["columns"]

    def test_sales_plural_model(self, reports_client):
        resp = reports_client.get("/reports/api/model_fields?model=sales")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "id" in body["columns"]

    def test_unknown_model_default_date_fields(self, reports_client):
        resp = reports_client.get("/reports/api/model_fields?model=unknown_table")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["columns"] == []
        assert "created_at" in body["date_fields"]


class TestReportsApiEntitySearch:
    def test_entity_search_supplier_default(self, reports_client):
        resp = reports_client.get("/reports/api/entity-search")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_entity_search_with_q(self, reports_client):
        resp = reports_client.get("/reports/api/entity-search?q=acme")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_entity_search_partner_type(self, reports_client):
        resp = reports_client.get("/reports/api/entity-search?type=partner&q=ali")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_entity_search_merchant_type(self, reports_client):
        resp = reports_client.get("/reports/api/entity-search?type=merchant&q=shop")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_entity_search_customer_type(self, reports_client):
        resp = reports_client.get("/reports/api/entity-search?type=customer&q=john")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestReportsEntityFragment:
    def test_supplier_fragment_success(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Supplier Co")
        purchase_query = MagicMock()
        purchase_query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = []
        payment_query = MagicMock()
        payment_query.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []
        payment_query.filter.return_value.filter.return_value.with_entities.return_value.scalar.return_value = 0
        payment_query.filter.return_value.filter.return_value.filter.return_value.all.return_value = []
        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("models.Purchase") as purchase_model, \
             patch("models.Payment") as payment_model:
            purchase_model.query = purchase_query
            payment_model.query = payment_query
            resp = reports_client.get("/reports/entity_report_fragment/supplier/9")
            assert resp.status_code == 200

    def test_customer_fragment_success(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Customer Co", customer_type="regular")
        sale_query = MagicMock()
        sale_query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = []
        receipt_query = MagicMock()
        receipt_query.filter_by.return_value.filter.return_value.all.return_value = []
        payment_query = MagicMock()
        payment_query.filter_by.return_value.filter.return_value.all.return_value = []
        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("models.Sale") as sale_model, \
             patch("models.Receipt") as receipt_model, \
             patch("models.Payment") as payment_model:
            sale_model.query = sale_query
            receipt_model.query = receipt_query
            payment_model.query = payment_query
            resp = reports_client.get("/reports/entity_report_fragment/customer/11")
            assert resp.status_code == 200

    def test_tenant_get_or_404_not_found_handled(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.tenant_get_or_404", side_effect=NotFound()), \
             patch("routes.reports.render_template", return_value="not-found-fragment") as render:
            resp = reports_client.get("/reports/entity_report_fragment/supplier/404")
            assert resp.status_code == 200
            assert render.called
            assert "error" in render.call_args[1]

    def test_supplier_branch_scope_403(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Scoped Supplier")
        scoped_query = MagicMock()
        scoped_query.filter_by.return_value.exists.return_value.scalar.return_value = False
        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("routes.reports.report_branch_scope_id", return_value=5), \
             patch("routes.reports._scoped_supplier_query", return_value=scoped_query), \
             patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(scalar=False)):
            resp = reports_client.get("/reports/entity_report_fragment/supplier/9")
            assert resp.status_code == 403

    def test_customer_branch_scope_403(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Scoped Customer")
        scoped_query = MagicMock()
        scoped_query.filter_by.return_value.exists.return_value.scalar.return_value = False
        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("routes.reports.report_branch_scope_id", return_value=5), \
             patch("routes.reports._scoped_customer_query", return_value=scoped_query), \
             patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(scalar=False)):
            resp = reports_client.get("/reports/entity_report_fragment/partner/11")
            assert resp.status_code == 403


class TestReportsTopSelling:
    def test_top_selling_returns_200(self, reports_client, mock_user):
        _configure_user(mock_user)
        resp = reports_client.get("/reports/top-selling")
        assert resp.status_code == 200

    def test_top_selling_date_params(self, reports_client, mock_user):
        _configure_user(mock_user)
        resp = reports_client.get(
            "/reports/top-selling",
            query_string={"date_from": "2025-01-01", "date_to": "2025-06-30"},
        )
        assert resp.status_code == 200

    def test_top_selling_limit_param(self, reports_client, mock_user):
        _configure_user(mock_user)
        resp = reports_client.get("/reports/top-selling?limit=5")
        assert resp.status_code == 200

    def test_top_selling_unauthenticated(self, reports_client):
        with _unauthenticated(reports_client):
            resp = reports_client.get("/reports/top-selling")
            assert resp.status_code in (302, 401)


class TestReportsUnauthenticated:
    def test_api_model_fields_unauthenticated(self, reports_client):
        with _unauthenticated(reports_client):
            resp = reports_client.get("/reports/api/model_fields?model=sale")
            assert resp.status_code in (302, 401)

    def test_entity_search_unauthenticated(self, reports_client):
        with _unauthenticated(reports_client):
            resp = reports_client.get("/reports/api/entity-search?q=test")
            assert resp.status_code in (302, 401)

    def test_inventory_export_unauthenticated(self, reports_client):
        with _unauthenticated(reports_client):
            resp = reports_client.get("/reports/inventory/export")
            assert resp.status_code in (302, 401)


class TestReportsTenantIsolation:
    def test_entity_fragment_invokes_tenant_get_or_404(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.tenant_get_or_404", side_effect=NotFound()) as tenant_get:
            reports_client.get("/reports/entity_report_fragment/supplier/999")
            tenant_get.assert_called_once()

    def test_entity_fragment_wrong_tenant_supplier(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.tenant_get_or_404", side_effect=NotFound("wrong tenant")), \
             patch("routes.reports.render_template", return_value="err") as render:
            resp = reports_client.get("/reports/entity_report_fragment/supplier/888")
            assert resp.status_code == 200
            assert "wrong tenant" in str(render.call_args[1].get("error", ""))


class TestReportsPartnersDeep:
    def _partner_row(self):
        row = MagicMock()
        row.product_name = "Widget"
        row.partner_name = "Partner A"
        row.percentage = Decimal("10")
        row.total_qty = Decimal("5")
        row.total_revenue = Decimal("500")
        row.partner_share_amount = Decimal("50")
        row.partner_id = 3
        return row

    def test_partners_with_commission_entries(self, reports_client, mock_user):
        _configure_user(mock_user)
        row = self._partner_row()
        call_count = {"n": 0}

        def query_side(*args, **kwargs):
            call_count["n"] += 1
            q = _chain_query_stub(scalar=True if call_count["n"] == 1 else 0, all=[row])
            return q

        product = MagicMock()
        product.id = 1
        product.name = "Widget"
        product.is_active = True
        product_partners = []
        partner = MagicMock()
        partner.customer_id = 2
        partner.percentage = Decimal("10")
        product.product_partners = [partner]

        partner_products_chain = MagicMock()
        partner_products_chain.join.return_value.filter.return_value.distinct.return_value.all.return_value = []

        with patch("routes.reports.db.session.query", side_effect=query_side), \
             patch("routes.reports.tenant_query", return_value=partner_products_chain):
            resp = reports_client.get("/reports/partners?date_from=2025-01-01&date_to=2025-12-31")
            assert resp.status_code == 200

    def test_partners_fallback_product_loop(self, reports_client, mock_user):
        _configure_user(mock_user)
        product = MagicMock()
        product.id = 1
        product.name = "Item"
        product.is_active = True
        partner = MagicMock()
        partner.customer_id = 2
        partner.percentage = Decimal("5")
        product.product_partners = [partner]

        sale_line = MagicMock()
        sale_line.line_total = Decimal("100")
        sale_line.quantity = Decimal("2")

        partner_products_chain = MagicMock()
        partner_products_chain.join.return_value.filter.return_value.distinct.return_value.all.return_value = [product]
        sales_chain = MagicMock()
        sales_chain.join.return_value.filter.return_value.all.return_value = [sale_line]

        def tenant_query_side(model):
            if getattr(model, "__name__", "") == "Product" or model.__name__ == "Product":
                return partner_products_chain
            return sales_chain

        with patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(scalar=False)), \
             patch("routes.reports.tenant_query", side_effect=tenant_query_side), \
             patch("routes.reports.Customer") as Customer:
            Customer.query.get.return_value = MagicMock(name="Merchant", customer_type="merchant")
            resp = reports_client.get("/reports/partners")
            assert resp.status_code == 200


class TestReportsSalesDeep:
    def test_sales_with_sale_rows_and_profit(self, reports_client, mock_user):
        _configure_user(mock_user)
        sale = MagicMock()
        sale.id = 1
        sale.amount_aed = Decimal("1000")
        sale.get_profit.return_value = Decimal("200")
        sale_query = _chain_query_stub(all=[sale])
        with patch("routes.reports.tenant_query", return_value=sale_query), \
             patch("routes.reports.get_confirmed_sale_paid_aed", return_value=Decimal("800")), \
             patch("routes.reports.Customer") as Customer, \
             patch("utils.tenanting.scoped_user_query", return_value=_chain_query_stub(all=[])):
            Customer.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/sales?date_from=2025-01-01")
            assert resp.status_code == 200

    def test_sales_seller_user_sees_own_only(self, reports_client, mock_user):
        _configure_user(mock_user)
        mock_user.is_seller.return_value = True
        sale_query = _chain_query_stub(all=[])
        with patch("routes.reports.tenant_query", return_value=sale_query), \
             patch("routes.reports.Customer") as Customer:
            Customer.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/sales")
            assert resp.status_code == 200


class TestReportsInventoryDeep:
    def test_inventory_with_warehouse_and_stock(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse = MagicMock()
        warehouse.id = 1
        warehouse.name = "Main"
        warehouse.is_main = True
        warehouse.tenant_id = 1
        warehouse.branch_id = 1
        product = MagicMock()
        product.id = 10
        product.name = "Stocked"
        product.cost_price = Decimal("10")
        product.min_stock_alert = Decimal("2")
        wh_chain = MagicMock()
        wh_inner = MagicMock()
        wh_inner.order_by.return_value.all.return_value = [warehouse]
        wh_chain.filter_by.return_value = wh_inner
        wh_inner.filter.return_value = wh_inner
        product_chain = MagicMock()
        product_chain.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [product]
        product_chain.filter_by.return_value.order_by.return_value.all.return_value = [product]

        def tenant_query_side(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]), \
             patch("routes.reports.tenant_query", side_effect=tenant_query_side), \
             patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(all=[(10, Decimal("5"))])):
            resp = reports_client.get(
                "/reports/inventory",
                query_string={
                    "category": "1", "include_zero": "1", "warehouse_id": "1",
                    "in_date_from": "2025-01-01", "out_date_to": "2025-06-30",
                },
            )
            assert resp.status_code == 200

    def test_inventory_warehouse_wrong_tenant_403(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse = MagicMock()
        warehouse.id = 99
        warehouse.tenant_id = 2
        warehouse.branch_id = 1
        wh_chain = MagicMock()
        wh_chain.filter.return_value.order_by.return_value.all.return_value = []
        with patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.get_accessible_warehouse_ids", return_value=[]), \
             patch("routes.reports.tenant_query", return_value=wh_chain), \
             patch("models.Warehouse") as Warehouse:
            Warehouse.query.filter_by.return_value.first.return_value = warehouse
            resp = reports_client.get("/reports/inventory?warehouse_id=99")
            assert resp.status_code == 403

    def test_inventory_non_admin_empty_warehouses(self, reports_client, mock_user):
        _configure_user(mock_user)
        mock_user.is_admin.return_value = False
        wh_chain = MagicMock()
        wh_chain.filter.return_value.order_by.return_value.all.return_value = []
        with patch("utils.branching.get_accessible_branches", return_value=[]), \
             patch("utils.branching.get_accessible_warehouse_ids", return_value=[]), \
             patch("routes.reports.tenant_query", return_value=wh_chain), \
             patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(all=[])):
            resp = reports_client.get("/reports/inventory")
            assert resp.status_code == 200


class TestReportsEntityFragmentDeep:
    def test_supplier_fragment_full_data(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Full Supplier")
        p_line = MagicMock()
        p_line.name = "Prod"
        p_line.qty = 3
        p_line.total = Decimal("300")
        p_line.last_date = None
        purchase = MagicMock()
        purchase.id = 1
        purchase.purchase_date = None
        purchase.total = Decimal("300")
        purchase.status = "confirmed"
        payment = MagicMock()
        payment.purchase_id = 1
        payment.amount_aed = Decimal("100")
        payment.payment_date = None
        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("routes.reports.report_branch_scope_id", return_value=None), \
             patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(all=[p_line])), \
             patch("models.Purchase") as Purchase, \
             patch("models.Payment") as Payment:
            Purchase.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [purchase]
            Payment.query.filter.return_value.filter.return_value.all.return_value = [payment]
            Payment.query.filter.return_value.filter.return_value.filter.return_value.all.return_value = []
            resp = reports_client.get("/reports/entity_report_fragment/supplier/5")
            assert resp.status_code == 200

    def test_customer_fragment_partner_type(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Partner Co", customer_type="partner")
        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("routes.reports.report_branch_scope_id", return_value=None), \
             patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(all=[])), \
             patch("models.Sale") as Sale, \
             patch("models.Receipt") as Receipt, \
             patch("models.Payment") as Payment:
            Sale.query.filter.return_value.order_by.return_value.all.return_value = []
            Receipt.query.filter.return_value.order_by.return_value.all.return_value = []
            Payment.query.filter.return_value.order_by.return_value.all.return_value = []
            resp = reports_client.get("/reports/entity_report_fragment/customer/7")
            assert resp.status_code == 200


class TestReportsApiModelFieldsAll:
    @pytest.mark.parametrize("model,expected_col", [
        ("purchase", "purchase_number"),
        ("customer", "name"),
        ("product", "sku"),
        ("expense", "amount"),
    ])
    def test_model_fields_variants(self, reports_client, model, expected_col):
        resp = reports_client.get(f"/reports/api/model_fields?model={model}")
        assert resp.status_code == 200
        assert expected_col in resp.get_json()["columns"]


class TestReportsReceivablesDeep:
    def test_receivables_with_aging_sale_rows(self, reports_client, mock_user):
        _configure_user(mock_user)
        sale = MagicMock()
        sale.amount_aed = Decimal("1000")
        sale.paid_amount_aed = Decimal("200")
        sale.sale_date = datetime.now(timezone.utc)
        sale_query = _chain_query_stub(all=[sale])
        with patch("routes.reports.tenant_query", return_value=sale_query), \
             patch("routes.reports.Customer") as Customer:
            Customer.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/receivables?customer=1")
            assert resp.status_code == 200


class TestReportsPurchasesDeep:
    def test_purchases_with_rows(self, reports_client, mock_user):
        _configure_user(mock_user)
        purchase = MagicMock()
        purchase.id = 1
        purchase.amount_aed = Decimal("500")
        purchase.get_profit = MagicMock(return_value=Decimal("0"))
        purchase_query = _chain_query_stub(all=[purchase])
        supplier_chain = MagicMock()
        supplier_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        with patch("routes.reports.tenant_query", return_value=purchase_query), \
             patch("routes.reports.get_confirmed_supplier_paid_aed", return_value=Decimal("200")), \
             patch("models.Supplier") as Supplier:
            Supplier.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/purchases?start_date=2025-01-01&end_date=2025-06-30")
            assert resp.status_code == 200


def _chain_query_stub(**terminals):
    q = MagicMock(name="query_chain")
    q.return_value = q
    for method in (
        "filter", "filter_by", "order_by", "join", "outerjoin", "group_by",
        "limit", "offset", "options", "select_from", "distinct", "having",
    ):
        getattr(q, method).return_value = q
    inner = q.filter.return_value
    inner.first.return_value = terminals.get("first")
    inner.scalar.return_value = terminals.get("scalar", 0)
    inner.all.return_value = terminals.get("all", [])
    inner.count.return_value = terminals.get("count", 0)
    inner.exists.return_value.scalar.return_value = terminals.get("exists", False)
    q.scalar.return_value = terminals.get("scalar", 0)
    q.all.return_value = terminals.get("all", [])
    return q


def _supplier_payment_chain(*, direct_all=None, unalloc_all=None, fifo_scalar=Decimal("0")):
    base = MagicMock(name="payment_base")
    direct = MagicMock(name="direct_payments")
    direct.all.return_value = direct_all if direct_all is not None else []
    unalloc = MagicMock(name="unalloc_payments")
    unalloc.all.return_value = unalloc_all if unalloc_all is not None else []
    sum_q = MagicMock(name="sum_q")
    sum_q.scalar.return_value = fifo_scalar
    state = {"n": 0}

    def filter_side(*args, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            return base
        if state["n"] == 2:
            return direct
        if state["n"] == 3:
            return unalloc
        return base

    base.filter.side_effect = filter_side
    base.with_entities.return_value = sum_q
    return base


class TestPartnersCommissionPath:
    def test_partners_has_entries_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        row = MagicMock()
        row.product_name = "Part"
        row.partner_name = "Partner"
        row.percentage = Decimal("15")
        row.total_qty = Decimal("4")
        row.total_revenue = Decimal("400")
        row.partner_share_amount = Decimal("60")
        row.partner_id = 8
        calls = {"n": 0}

        def query_factory(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return _chain_query_stub(scalar=True)
            return _chain_query_stub(all=[row])

        with patch("routes.reports.db.session.query", side_effect=query_factory), \
             patch("routes.reports.tenant_query", return_value=_chain_query_stub(all=[])):
            resp = reports_client.get("/reports/partners?date_from=2024-01-01&date_to=2024-12-31")
            assert resp.status_code == 200


class TestPartnersFallbackShares:
    def test_partners_product_partner_shares(self, reports_client, mock_user):
        _configure_user(mock_user)
        share = MagicMock()
        share.percentage = Decimal("10")
        share.partner_customer = MagicMock(id=4, name="PartnerCo")
        product = MagicMock()
        product.id = 1
        product.name = "SharedProd"
        product.partner_shares = [share]
        sale_line = MagicMock()
        sale_line.line_total = Decimal("200")
        sale_line.quantity = Decimal("2")
        pp_chain = MagicMock()
        pp_chain.join.return_value.filter.return_value.distinct.return_value.all.return_value = [product]
        sl_chain = MagicMock()
        sl_chain.join.return_value.filter.return_value.all.return_value = [sale_line]
        mp_chain = MagicMock()
        mp_chain.filter.return_value.all.return_value = []

        def tq(model):
            name = getattr(model, "__name__", "")
            if name == "Product":
                return pp_chain if not hasattr(tq, "pass2") else mp_chain
            if name == "SaleLine":
                return sl_chain
            return _chain_query_stub(all=[])

        tq.pass2 = False
        def tq_wrap(model):
            name = getattr(model, "__name__", "")
            if name == "Product":
                if not tq_wrap.seen:
                    tq_wrap.seen = True
                    return pp_chain
                return mp_chain
            if name == "SaleLine":
                return sl_chain
            return _chain_query_stub(all=[])
        tq_wrap.seen = False

        with patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(scalar=False)), \
             patch("routes.reports.tenant_query", side_effect=tq_wrap):
            resp = reports_client.get("/reports/partners")
            assert resp.status_code == 200


class TestPurchasesPaymentAllocation:
    def test_purchases_with_supplier_payments(self, reports_client, mock_user):
        _configure_user(mock_user)
        purchase = MagicMock()
        purchase.id = 5
        purchase.supplier_id = 3
        purchase.amount_aed = Decimal("1000")
        purchase.purchase_date = None
        purchase.get_profit = MagicMock(return_value=Decimal("0"))
        pmt = MagicMock()
        pmt.supplier_id = 3
        pmt.amount_aed = Decimal("400")
        pmt.purchase_id = None
        pmt.payment_date = None
        pq = _chain_query_stub(all=[purchase])
        pay_q = _chain_query_stub(all=[pmt])

        def tq(model):
            from models import Payment, Purchase
            if model is Payment:
                return pay_q
            return pq

        with patch("routes.reports.tenant_query", side_effect=tq), \
             patch("routes.reports.get_confirmed_supplier_paid_aed", return_value=Decimal("0")), \
             patch("models.Supplier") as Supplier:
            Supplier.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/purchases?supplier_id=3")
            assert resp.status_code == 200

    def test_purchases_summary_totals(self, reports_client, mock_user):
        _configure_user(mock_user)
        purchase = MagicMock()
        purchase.id = 2
        purchase.amount_aed = Decimal("800")
        purchase.get_profit = MagicMock(return_value=Decimal("50"))
        pq = _chain_query_stub(all=[purchase])
        with patch("routes.reports.tenant_query", return_value=pq), \
             patch("routes.reports.get_confirmed_supplier_paid_aed", return_value=Decimal("300")), \
             patch("models.Supplier") as Supplier:
            Supplier.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/purchases")
            assert resp.status_code == 200


class TestEntityFragmentPurchases:
    def test_supplier_fragment_with_purchase_lines(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Supplier X")
        purchase = MagicMock()
        purchase.id = 10
        purchase.purchase_date = None
        purchase.total = Decimal("500")
        purchase.status = "confirmed"
        payment_direct = MagicMock()
        payment_direct.purchase_id = 10
        payment_direct.amount_aed = Decimal("200")
        payment_direct.payment_date = None
        payment_unalloc = MagicMock()
        payment_unalloc.purchase_id = None
        payment_unalloc.amount_aed = Decimal("50")
        payment_unalloc.payment_date = None
        p_line = MagicMock()
        p_line.name = "Item"
        p_line.qty = 2
        p_line.total = Decimal("500")
        p_line.last_date = None
        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("routes.reports.report_branch_scope_id", return_value=None), \
             patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(all=[p_line])), \
             patch("models.Purchase") as Purchase, \
             patch("models.Payment") as Payment:
            Purchase.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [purchase]
            pay_base = MagicMock()
            pay_base.filter.return_value.all.side_effect = [
                [payment_direct],
                [payment_unalloc],
            ]
            Payment.query.filter.return_value = pay_base
            resp = reports_client.get("/reports/entity_report_fragment/supplier/12")
            assert resp.status_code == 200


class TestReceivablesAgingBuckets:
    def test_receivables_aging_30_60_90(self, reports_client, mock_user):
        _configure_user(mock_user)
        from datetime import datetime, timedelta, timezone
        sales = []
        for days in (10, 45, 75, 100, 150):
            s = MagicMock()
            s.amount_aed = Decimal("1000")
            s.paid_amount_aed = Decimal("100")
            s.sale_date = datetime.now(timezone.utc) - timedelta(days=days)
            sales.append(s)
        sq = _chain_query_stub(all=sales)
        with patch("routes.reports.tenant_query", return_value=sq), \
             patch("routes.reports.Customer") as Customer:
            Customer.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = reports_client.get("/reports/receivables")
            assert resp.status_code == 200


class TestInventoryExportDeep:
    def test_inventory_export_with_products(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse = MagicMock()
        warehouse.id = 2
        warehouse.name = "WH"
        warehouse.is_main = True
        wh_chain = MagicMock()
        wh_inner = MagicMock()
        wh_inner.order_by.return_value.all.return_value = [warehouse]
        wh_chain.filter_by.return_value = wh_inner
        product = MagicMock()
        product.id = 5
        product.name = "SKU"
        product.cost_price = Decimal("3")
        product.min_stock_alert = Decimal("1")
        product_chain = MagicMock()
        product_chain.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [product]

        def tq(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with patch("utils.branching.get_accessible_warehouse_ids", return_value=[2]), \
             patch("routes.reports.tenant_query", side_effect=tq), \
             patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(all=[(5, Decimal("10"))])), \
             patch("services.export_service.ExportService.export_to_csv", return_value=io.BytesIO(b"csv")), \
             patch("flask.send_file", return_value=make_response("ok", 200)):
            resp = reports_client.get("/reports/inventory/export?include_zero=1")
            assert resp.status_code == 200


class TestSalesExportWithRows:
    def test_sales_export_with_data(self, reports_client, mock_user):
        _configure_user(mock_user)
        sale = MagicMock()
        sale.id = 3
        sale.amount_aed = Decimal("200")
        sq = _chain_query_stub(all=[sale])
        with patch("routes.reports.tenant_query", return_value=sq), \
             patch("routes.reports.get_confirmed_sale_paid_aed", return_value=Decimal("200")), \
             patch("services.export_service.ExportService.export_to_csv", return_value=_export_io()), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/sales/export?format=csv&date_from=2025-01-01")
            assert resp.status_code == 200


class TestReportsModuleHelpers:
    def test_get_confirmed_sale_paid_aed(self):
        from routes.reports import get_confirmed_sale_paid_aed
        with patch("routes.reports.db.session.query", return_value=_chain_query_stub(scalar=Decimal("150"))):
            assert get_confirmed_sale_paid_aed(1, tenant_id=1, branch_id=2) == Decimal("150")

    def test_get_confirmed_sale_paid_no_tenant(self):
        from routes.reports import get_confirmed_sale_paid_aed
        with patch("routes.reports.db.session.query", return_value=_chain_query_stub(scalar=None)):
            assert get_confirmed_sale_paid_aed(5) == Decimal("0")

    def test_get_confirmed_supplier_paid_aed(self):
        from routes.reports import get_confirmed_supplier_paid_aed
        with patch("routes.reports.db.session.query", return_value=_chain_query_stub(scalar=Decimal("80"))):
            assert get_confirmed_supplier_paid_aed(3, purchase_id=10, tenant_id=1) == Decimal("80")

    def test_scoped_customer_query_no_branch(self):
        from routes.reports import _scoped_customer_query
        with patch("routes.reports.tenant_query", return_value=_chain_query_stub()) as tq, \
             patch("routes.reports.report_branch_scope_id", return_value=None):
            _scoped_customer_query()
            tq.assert_called_once()

    def test_scoped_customer_query_with_branch(self):
        from routes.reports import _scoped_customer_query
        base = _chain_query_stub()
        with patch("routes.reports.tenant_query", return_value=base), \
             patch("routes.reports.report_branch_scope_id", return_value=3):
            result = _scoped_customer_query()
            assert result is base.filter.return_value

    def test_scoped_supplier_query_with_branch(self):
        from routes.reports import _scoped_supplier_query
        base = _chain_query_stub()
        with patch("routes.reports.tenant_query", return_value=base), \
             patch("routes.reports.report_branch_scope_id", return_value=2):
            result = _scoped_supplier_query()
            assert result is base.filter.return_value

    def test_scoped_supplier_query_no_branch(self):
        from routes.reports import _scoped_supplier_query
        with patch("routes.reports.tenant_query", return_value=_chain_query_stub()), \
             patch("routes.reports.report_branch_scope_id", return_value=None):
            _scoped_supplier_query()


class TestPartnersMerchantsLoop:
    def test_merchants_revenue_share(self, reports_client, mock_user):
        _configure_user(mock_user)
        merchant = MagicMock()
        merchant.name = "MerchantCo"
        product = MagicMock()
        product.id = 2
        product.name = "MerchProd"
        product.merchant_customer_id = 9
        product.merchant_share = 20
        product.merchant_customer = merchant
        sale_line = MagicMock()
        sale_line.line_total = Decimal("500")
        sale_line.quantity = Decimal("5")
        empty_pp = MagicMock()
        empty_pp.join.return_value.filter.return_value.distinct.return_value.all.return_value = []
        merch_chain = MagicMock()
        merch_chain.filter.return_value.all.return_value = [product]
        sl_chain = MagicMock()
        sl_chain.join.return_value.filter.return_value.all.return_value = [sale_line]
        calls = {"product": 0}

        def tq(model):
            name = getattr(model, "__name__", "")
            if name == "Product":
                calls["product"] += 1
                return empty_pp if calls["product"] == 1 else merch_chain
            if name == "SaleLine":
                return sl_chain
            return _chain_query_stub(all=[])

        with patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(scalar=False)), \
             patch("routes.reports.tenant_query", side_effect=tq):
            resp = reports_client.get("/reports/partners?date_from=2025-01-01")
            assert resp.status_code == 200


class TestPartnersFullPipeline:
    def test_partners_commission_and_summaries(self, reports_client, mock_user):
        _configure_user(mock_user)
        row = MagicMock()
        row.product_name = "P"
        row.partner_name = "Partner"
        row.percentage = Decimal("10")
        row.total_qty = Decimal("2")
        row.total_revenue = Decimal("200")
        row.partner_share_amount = Decimal("20")
        row.partner_id = 4
        partner_cust = MagicMock()
        partner_cust.id = 4
        partner_cust.name = "Partner"
        partner_cust.customer_type = "partner"
        supplier = MagicMock()
        supplier.id = 1
        supplier.name = "SupA"
        supplier.tenant_id = 1
        query_calls = {"n": 0}

        def session_query(*args, **kwargs):
            query_calls["n"] += 1
            if query_calls["n"] == 1:
                return _chain_query_stub(scalar=True)
            if query_calls["n"] == 2:
                return _chain_query_stub(all=[row])
            return _chain_query_stub(scalar=Decimal("50"))

        with patch("routes.reports.db.session.query", side_effect=session_query), \
             patch("routes.reports.tenant_query", return_value=_chain_query_stub(all=[])), \
             patch("routes.reports._scoped_customer_query") as scq, \
             patch("routes.reports._scoped_supplier_query") as ssq:
            scq.return_value.filter_by.return_value.all.return_value = [partner_cust]
            ssq.return_value.all.return_value = [supplier]
            resp = reports_client.get("/reports/partners?date_from=2025-01-01&date_to=2025-12-31")
            assert resp.status_code == 200


class TestPurchasesFifoAllocation:
    def test_purchases_fifo_paid_allocation(self, reports_client, mock_user):
        _configure_user(mock_user)
        purchase = MagicMock()
        purchase.id = 1
        purchase.supplier_id = 7
        purchase.amount_aed = Decimal("600")
        purchase.purchase_date = None
        pmt = MagicMock()
        pmt.supplier_id = 7
        pmt.amount_aed = Decimal("400")
        pmt.purchase_id = None
        pmt.payment_date = None
        purchase_q = _chain_query_stub(all=[purchase])
        payment_q = _chain_query_stub(all=[pmt])
        sup_scoped = MagicMock()
        sup_scoped.filter.return_value.order_by.return_value.all.return_value = []

        def tq(model):
            from models import Payment
            if model is Payment:
                return payment_q
            return purchase_q

        with patch("routes.reports.tenant_query", side_effect=tq), \
             patch("routes.reports._scoped_supplier_query", return_value=sup_scoped):
            resp = reports_client.get("/reports/purchases")
            assert resp.status_code == 200
            assert purchase.paid_amount == Decimal("400")


class TestPartnersFallbackOnly:
    def test_product_partner_share_loop(self, reports_client, mock_user):
        _configure_user(mock_user)
        share = MagicMock()
        share.percentage = Decimal("15")
        share.partner_customer = MagicMock(id=8, name="SharePartner")
        product = MagicMock()
        product.id = 3
        product.name = "EarnProd"
        product.partner_shares = [share]
        sale_line = MagicMock()
        sale_line.line_total = Decimal("300")
        sale_line.quantity = Decimal("3")
        pp_chain = MagicMock()
        pp_chain.join.return_value.filter.return_value.distinct.return_value.all.return_value = [product]
        sl_chain = MagicMock()
        sl_chain.join.return_value.filter.return_value.all.return_value = [sale_line]
        empty_merch = MagicMock()
        empty_merch.filter.return_value.all.return_value = []
        pc = {"n": 0}

        def tq(model):
            name = getattr(model, "__name__", "")
            if name == "Product":
                pc["n"] += 1
                return pp_chain if pc["n"] == 1 else empty_merch
            if name == "SaleLine":
                return sl_chain
            return _chain_query_stub(all=[])

        with patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(scalar=False)), \
             patch("routes.reports.tenant_query", side_effect=tq), \
             patch("routes.reports._scoped_customer_query") as scq, \
             patch("routes.reports._scoped_supplier_query") as ssq:
            scq.return_value.filter_by.return_value.all.return_value = []
            ssq.return_value.all.return_value = []
            resp = reports_client.get("/reports/partners")
            assert resp.status_code == 200


class TestEntityFragmentCustomerDeep:
    def test_customer_partner_entity(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = MagicMock()
        entity.id = 15
        entity.name = "PartnerEnt"
        entity.customer_type = "partner"
        s_line = MagicMock()
        s_line.name = "SoldItem"
        s_line.qty = 2
        s_line.total = Decimal("100")
        s_line.last_date = None
        sp = MagicMock()
        sp.name = "Shared"
        sp.percentage = Decimal("10")
        sp.qty = 1
        sp.total_sales = Decimal("200")
        sp.last_date = None
        sale = MagicMock()
        sale.sale_number = "S1"
        sale.total = Decimal("100")
        sale.sale_date = None
        receipt = MagicMock()
        receipt.receipt_number = "R1"
        receipt.amount_aed = Decimal("50")
        receipt.receipt_date = None
        payment = MagicMock()
        payment.payment_number = "P1"
        payment.amount_aed = Decimal("20")
        payment.payment_date = None
        payment.payment_method = "cash"
        payment.notes = ""
        qc = {"n": 0}

        def session_query(*args, **kwargs):
            qc["n"] += 1
            if qc["n"] <= 3:
                return _chain_query_stub(scalar=Decimal("100"))
            if qc["n"] == 4:
                return _chain_query_stub(all=[s_line])
            if qc["n"] == 5:
                return _chain_query_stub(all=[sp])
            if qc["n"] == 6:
                return _chain_query_stub(all=[sale])
            if qc["n"] == 7:
                return _chain_query_stub(all=[receipt])
            return _chain_query_stub(all=[payment])

        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("routes.reports.report_branch_scope_id", return_value=None), \
             patch("routes.reports.db.session.query", side_effect=session_query):
            resp = reports_client.get("/reports/entity_report_fragment/customer/15")
            assert resp.status_code == 200

    def test_customer_merchant_entity(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = MagicMock()
        entity.id = 16
        entity.name = "MerchantEnt"
        entity.customer_type = "merchant"
        qc = {"n": 0}
        mp = MagicMock()
        mp.name = "MProd"
        mp.merchant_share = 25
        mp.qty = 4
        mp.total_sales = Decimal("400")
        mp.last_date = None

        def session_query(*args, **kwargs):
            qc["n"] += 1
            if qc["n"] <= 3:
                return _chain_query_stub(scalar=Decimal("0"))
            if qc["n"] == 4:
                return _chain_query_stub(all=[])
            if qc["n"] == 5:
                return _chain_query_stub(all=[mp])
            return _chain_query_stub(all=[])

        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("routes.reports.report_branch_scope_id", return_value=None), \
             patch("routes.reports.db.session.query", side_effect=session_query):
            resp = reports_client.get("/reports/entity_report_fragment/merchant/16")
            assert resp.status_code == 200

    def test_customer_negative_balance_label(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = MagicMock()
        entity.id = 17
        entity.name = "Debtor"
        entity.customer_type = "regular"
        scalars = iter([Decimal("10"), Decimal("500"), Decimal("0")])

        def session_query(*args, **kwargs):
            return _chain_query_stub(scalar=next(scalars, Decimal("0")))

        with patch("routes.reports.tenant_get_or_404", return_value=entity), \
             patch("routes.reports.report_branch_scope_id", return_value=None), \
             patch("routes.reports.db.session.query", side_effect=session_query):
            resp = reports_client.get("/reports/entity_report_fragment/customer/17")
            assert resp.status_code == 200


class TestPartnersHasEntriesPath:
    def test_commission_rows_populate_partners_data(self, reports_client, mock_user):
        _configure_user(mock_user)
        row = MagicMock()
        row.product_name = "Widget"
        row.partner_name = "Ptn"
        row.percentage = Decimal("12")
        row.total_qty = Decimal("4")
        row.total_revenue = Decimal("400")
        row.partner_share_amount = Decimal("48")
        row.partner_id = 9
        exists_q = MagicMock()
        exists_q.scalar.return_value = True
        rows_q = MagicMock()
        rows_q.join.return_value = rows_q
        rows_q.outerjoin.return_value = rows_q
        rows_q.filter.return_value = rows_q
        rows_q.group_by.return_value = rows_q
        rows_q.all.return_value = [row]
        financial_q = _chain_query_stub(scalar=Decimal("25"))
        queries = [exists_q, rows_q]

        def session_query(*args, **kwargs):
            if len(queries) > 0:
                return queries.pop(0)
            return financial_q

        partner_cust = MagicMock(id=9, name="Ptn", customer_type="partner")
        with patch("routes.reports.db.session.query", side_effect=session_query), \
             patch("routes.reports.tenant_query", return_value=_chain_query_stub(all=[])), \
             patch("routes.reports._scoped_customer_query") as scq, \
             patch("routes.reports._scoped_supplier_query") as ssq:
            scq.return_value.filter_by.return_value.all.return_value = [partner_cust]
            ssq.return_value.all.return_value = []
            resp = reports_client.get("/reports/partners?date_from=2025-01-01&date_to=2025-12-31")
            assert resp.status_code == 200


class TestReportsPartnersBranchScope:
    def test_partners_financials_with_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        partner_cust = MagicMock()
        partner_cust.id = 2
        partner_cust.name = "BranchPartner"
        partner_cust.customer_type = "partner"
        with patch("routes.reports.db.session.query", side_effect=lambda *a, **k: _chain_query_stub(scalar=False)), \
             patch("routes.reports.tenant_query", return_value=_chain_query_stub(all=[])), \
             patch("routes.reports._scoped_customer_query") as scq, \
             patch("routes.reports._scoped_supplier_query") as ssq, \
             patch("routes.reports.report_branch_scope_id", return_value=2):
            scq.return_value.filter_by.return_value.all.return_value = [partner_cust]
            ssq.return_value.all.return_value = []
            resp = reports_client.get("/reports/partners?date_from=2025-01-01")
            assert resp.status_code == 200


class TestReportsReceivablesExportDeep:
    def test_receivables_export_with_aging_rows(self, reports_client, mock_user):
        _configure_user(mock_user)
        from datetime import timedelta
        sale = MagicMock()
        sale.amount_aed = Decimal("500")
        sale.paid_amount_aed = Decimal("100")
        sale.sale_date = datetime.now(timezone.utc) - timedelta(days=45)
        sale.customer = MagicMock(name="C")
        sq = _chain_query_stub(all=[sale])
        with patch("routes.reports.tenant_query", return_value=sq), \
             patch("services.export_service.ExportService.export_to_csv", return_value=_export_io()), \
             patch("flask.send_file", return_value=_send_file_response()):
            resp = reports_client.get("/reports/receivables/export?format=csv")
            assert resp.status_code == 200


class TestTopSellingWithRows:
    def test_top_selling_products(self, reports_client, mock_user):
        _configure_user(mock_user)
        row = MagicMock()
        row.id = 1
        row.name = "Top"
        row.total_quantity = 10
        row.total_sales = Decimal("1000")
        with patch("routes.reports.db.session.query", return_value=_chain_query_stub(all=[row])):
            resp = reports_client.get("/reports/top-selling?limit=10&date_from=2025-01-01")
            assert resp.status_code == 200


class TestReportsPartnersFallbackLoop:
    def test_fallback_partner_shares_with_revenue(self, reports_client, mock_user):
        _configure_user(mock_user)
        share = MagicMock()
        share.percentage = Decimal("10")
        share.partner_customer = MagicMock(id=3, name="SharePartner")
        product = MagicMock()
        product.id = 1
        product.name = "ProdA"
        product.partner_shares = [share]
        line = MagicMock(line_total=Decimal("200"), quantity=Decimal("4"))
        sales_q = _chain_query_stub(all=[line])
        exists_q = MagicMock()
        exists_q.scalar.return_value = False
        partner_products_q = _chain_query_stub(all=[product])
        financial_q = _chain_query_stub(scalar=Decimal("0"))
        call_idx = {"n": 0}

        def session_query(*args, **kwargs):
            call_idx["n"] += 1
            if call_idx["n"] == 1:
                return exists_q
            return financial_q

        def tenant_query_side(model):
            name = getattr(model, "__name__", str(model))
            if name == "Product":
                return partner_products_q
            if name in ("SaleLine",):
                return sales_q
            return _chain_query_stub(all=[])

        partner_cust = MagicMock(id=3, name="SharePartner", customer_type="partner")
        with patch("routes.reports.db.session.query", side_effect=session_query), \
             patch("routes.reports.tenant_query", side_effect=tenant_query_side), \
             patch("routes.reports._scoped_customer_query") as scq, \
             patch("routes.reports._scoped_supplier_query") as ssq:
            scq.return_value.filter_by.return_value.all.return_value = [partner_cust]
            ssq.return_value.all.return_value = []
            resp = reports_client.get("/reports/partners?date_from=2025-01-01&date_to=2025-12-31")
            assert resp.status_code == 200

    def test_merchants_loop_with_revenue(self, reports_client, mock_user):
        _configure_user(mock_user)
        merchant = MagicMock(id=8, name="MerchantCo")
        product = MagicMock()
        product.id = 2
        product.name = "MerchProd"
        product.merchant_customer_id = 8
        product.merchant_customer = merchant
        product.merchant_share = 50
        line = MagicMock(line_total=Decimal("300"), quantity=Decimal("6"))
        sales_q = _chain_query_stub(all=[line])
        exists_q = MagicMock()
        exists_q.scalar.return_value = False
        merchant_products_q = _chain_query_stub(all=[product])
        empty_products_q = _chain_query_stub(all=[])
        financial_q = _chain_query_stub(scalar=Decimal("0"))
        call_idx = {"n": 0}

        def session_query(*args, **kwargs):
            call_idx["n"] += 1
            if call_idx["n"] == 1:
                return exists_q
            return financial_q

        def tenant_query_side(model):
            name = getattr(model, "__name__", str(model))
            if name == "Product":
                def product_query():
                    q = MagicMock()
                    q.join.return_value = empty_products_q
                    q.filter.return_value = merchant_products_q
                    q.distinct.return_value = empty_products_q
                    q.all.return_value = []
                    return q
                outer = MagicMock()
                outer.join.return_value = empty_products_q
                outer.filter.return_value = merchant_products_q
                outer.distinct.return_value = empty_products_q
                outer.all.side_effect = [[], [product]]
                return outer
            if name == "SaleLine":
                return sales_q
            return _chain_query_stub(all=[])

        with patch("routes.reports.db.session.query", side_effect=session_query), \
             patch("routes.reports.tenant_query", side_effect=tenant_query_side), \
             patch("routes.reports._scoped_customer_query", return_value=_chain_query_stub(all=[])), \
             patch("routes.reports._scoped_supplier_query", return_value=_chain_query_stub(all=[])):
            resp = reports_client.get("/reports/partners")
            assert resp.status_code == 200


class TestReportsSupplierFragmentDeep:
    def _supplier_entity(self):
        entity = MagicMock()
        entity.id = 12
        entity.name = "SupplierX"
        entity.customer_type = "supplier"
        return entity

    def test_supplier_direct_payment_allocation(self, reports_client, mock_user):
        _configure_user(mock_user)
        purchase = MagicMock()
        purchase.id = 1
        purchase.purchase_number = "P-100"
        purchase.purchase_date = datetime(2025, 3, 1, tzinfo=timezone.utc)
        purchase.status = "confirmed"
        purchase.amount_aed = Decimal("500")
        payment = MagicMock()
        payment.purchase_id = 1
        payment.amount_aed = Decimal("200")
        payment.payment_number = "PAY-1"
        payment.payment_date = datetime(2025, 3, 5, tzinfo=timezone.utc)
        payment.payment_method = "bank"
        payment.direction = "outgoing"
        payment.payment_confirmed = True
        unalloc = MagicMock()
        unalloc.amount_aed = Decimal("50")
        purchase_q = MagicMock()
        purchase_q.filter.return_value = purchase_q
        purchase_q.order_by.return_value = purchase_q
        purchase_q.all.return_value = [purchase]
        p_line = MagicMock(name="Widget", qty=Decimal("2"), total=Decimal("500"), last_date=purchase.purchase_date)
        with patch("routes.reports.tenant_get_or_404", return_value=self._supplier_entity()), \
             patch("routes.reports.report_branch_scope_id", return_value=None), \
             patch("routes.reports.db.session.query", return_value=_chain_query_stub(all=[p_line])), \
             patch("models.Purchase") as Purchase, \
             patch("models.Payment") as Payment:
            Purchase.query.filter_by.return_value = purchase_q
            Payment.query.filter.return_value = _supplier_payment_chain(
                direct_all=[payment],
                unalloc_all=[unalloc],
            )
            Payment.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [payment]
            resp = reports_client.get("/reports/entity_report_fragment/supplier/12")
            assert resp.status_code == 200

    def test_supplier_fifo_payment_allocation(self, reports_client, mock_user):
        _configure_user(mock_user)
        purchase = MagicMock()
        purchase.id = 2
        purchase.purchase_number = "P-200"
        purchase.purchase_date = datetime(2025, 4, 1, tzinfo=timezone.utc)
        purchase.status = "confirmed"
        purchase.amount_aed = Decimal("300")
        purchase_q = MagicMock()
        purchase_q.filter.return_value = purchase_q
        purchase_q.order_by.return_value = purchase_q
        purchase_q.all.return_value = [purchase]
        with patch("routes.reports.tenant_get_or_404", return_value=self._supplier_entity()), \
             patch("routes.reports.report_branch_scope_id", return_value=None), \
             patch("routes.reports.db.session.query", return_value=_chain_query_stub(all=[])), \
             patch("models.Purchase") as Purchase, \
             patch("models.Payment") as Payment:
            Purchase.query.filter_by.return_value = purchase_q
            Payment.query.filter.return_value = _supplier_payment_chain(
                direct_all=[],
                fifo_scalar=Decimal("150"),
            )
            Payment.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = []
            resp = reports_client.get("/reports/entity_report_fragment/supplier/12")
            assert resp.status_code == 200
