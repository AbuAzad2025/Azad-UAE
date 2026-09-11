"""Coverage for routes/reports.py remaining arcs.

Targets: before_request guard, seller 403s, xlsx/csv export arcs,
branch-mismatch 403s, warehouse 403/404 arcs, api_model_fields branches,
entity fragment arcs + exception arc, receivables/ap-aging arcs.
Real test-client paths; service/DB boundaries mocked only.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


def _chain():
    from tests.unit.routes.conftest import _stub_query

    return _stub_query()


@pytest.fixture
def reports_cov3_client(app_factory, bypass_reports_auth):
    from routes.reports import reports_bp

    app = app_factory(reports_bp)
    with (
        patch("routes.reports.render_template", return_value="ok"),
        patch("services.reports_query_service.db.session.query", return_value=_chain()),
        patch("services.reports_query_service.tenant_query", return_value=_chain()),
    ):
        yield app.test_client()


def _sale(sid=1, days_ago=5, amount="100", paid="20"):
    s = MagicMock()
    s.id = sid
    s.sale_number = f"S-{sid}"
    s.sale_date = datetime.now(UTC).replace(tzinfo=None) - __import__("datetime").timedelta(days=days_ago)
    s.amount_aed = Decimal(amount)
    s.paid_amount_aed = Decimal(paid)
    s.customer = MagicMock(name="C")
    s.customer.name = "C"
    s.branch = MagicMock(name="B")
    s.branch.name = "B"
    s.currency = "AED"
    s.exchange_rate = Decimal("1")
    s.payment_status = "partial"
    s.seller = MagicMock()
    s.seller.get_display_name.return_value = "Seller"
    s.warehouse = None
    return s


class TestGuardsAndExports:
    def test_before_request_allows_index_for_owner(self, reports_cov3_client):
        resp = reports_cov3_client.get("/reports/")
        assert resp.status_code == 200

    def test_purchases_seller_403(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = True
        with patch("routes.reports.render_template", return_value="denied"):
            resp = reports_cov3_client.get("/reports/purchases")
        assert resp.status_code == 403

    def test_purchases_export_seller_403(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = True
        with patch("routes.reports.render_template", return_value="denied"):
            resp = reports_cov3_client.get("/reports/purchases/export")
        assert resp.status_code == 403

    def test_sales_export_xlsx(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = False
        # call via real send_file path with xlsx mock returning BytesIO
        with (
            patch(
                "services.reports_query_service.ReportsQueryService.fetch_sales_report",
                return_value=[],
            ),
            patch(
                "services.reports_query_service.ReportsQueryService.get_confirmed_sale_paid_map",
                return_value={},
            ),
            patch(
                "services.export_service.ExportService.export_to_xlsx",
                return_value=io.BytesIO(b"xlsx-bytes"),
            ),
        ):
            resp = reports_cov3_client.get("/reports/sales/export?format=xlsx")
        assert resp.status_code == 200

    def test_purchases_export_csv(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = False
        with (
            patch(
                "services.reports_query_service.ReportsQueryService.fetch_purchases_report",
                return_value=[],
            ),
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=io.BytesIO(b"csv-bytes"),
            ),
        ):
            resp = reports_cov3_client.get("/reports/purchases/export?format=csv")
        assert resp.status_code == 200

    def test_ap_aging_export_rejects_csv(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = False
        resp = reports_cov3_client.get("/reports/ap-aging/export?format=csv")
        assert resp.status_code == 400

    def test_ap_aging_export_pdf(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = False
        with (
            patch(
                "services.reports_query_service.ReportsQueryService.build_ap_aging_report",
                return_value={"as_of": "2026-01-01"},
            ),
            patch("services.print_service.PrintService.render_pdf", return_value=b"%PDF"),
        ):
            resp = reports_cov3_client.get("/reports/ap-aging/export?format=pdf")
        assert resp.status_code == 200

    def test_api_ap_aging_seller_403(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = True
        resp = reports_cov3_client.get("/reports/api/ap-aging")
        assert resp.status_code == 403

    def test_api_ap_aging_ok(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_seller.return_value = False
        with patch(
            "services.reports_query_service.ReportsQueryService.build_ap_aging_report",
            return_value={"rows": []},
        ):
            resp = reports_cov3_client.get("/reports/api/ap-aging")
        assert resp.status_code == 200


class TestBranchMismatch:
    def test_ar_mismatch_403(self, reports_cov3_client):
        with (
            patch("routes.reports.report_branch_scope_id", return_value=1),
            patch("routes.reports.render_template", return_value="denied"),
        ):
            resp = reports_cov3_client.get("/reports/ar-reconciliation?branch_id=2")
        assert resp.status_code == 403

    def test_inventory_mismatch_403(self, reports_cov3_client):
        with (
            patch("routes.reports.report_branch_scope_id", return_value=1),
            patch("routes.reports.render_template", return_value="denied"),
        ):
            resp = reports_cov3_client.get("/reports/inventory?branch_id=2")
        assert resp.status_code == 403

    def test_inventory_export_mismatch_403(self, reports_cov3_client):
        with (
            patch("routes.reports.report_branch_scope_id", return_value=1),
            patch("routes.reports.render_template", return_value="denied"),
        ):
            resp = reports_cov3_client.get("/reports/inventory/export?branch_id=2")
        assert resp.status_code == 403

    def test_inventory_bad_warehouse_admin_fallback_404(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_admin.return_value = True
        with (
            patch("routes.reports.report_branch_scope_id", return_value=None),
            patch(
                "services.reports_query_service.ReportsQueryService.fetch_inventory_warehouses",
                return_value=[],
            ),
            patch(
                "services.reports_query_service.ReportsQueryService.find_active_warehouse",
                return_value=None,
            ),
            patch("routes.reports.render_template", return_value="nf"),
        ):
            resp = reports_cov3_client.get("/reports/inventory?warehouse_id=999")
        assert resp.status_code == 404

    def test_treasury_style_inventory_warehouse_tenant_mismatch_403(self, reports_cov3_client, bypass_reports_auth):
        bypass_reports_auth.is_admin.return_value = True
        wh = MagicMock(id=7, tenant_id=999, branch_id=None)
        with (
            patch("routes.reports.report_branch_scope_id", return_value=None),
            patch(
                "services.reports_query_service.ReportsQueryService.fetch_inventory_warehouses",
                return_value=[],
            ),
            patch(
                "services.reports_query_service.ReportsQueryService.find_active_warehouse",
                return_value=wh,
            ),
            patch("routes.reports.render_template", return_value="denied"),
        ):
            resp = reports_cov3_client.get("/reports/inventory?warehouse_id=7")
        assert resp.status_code == 403


class TestModelFieldsAndFragments:
    @pytest.mark.parametrize("model", ["sale", "purchase", "customer", "product", "expense", "weird", ""])
    def test_api_model_fields_models(self, reports_cov3_client, model):
        resp = reports_cov3_client.get(f"/reports/api/model_fields?model={model}")
        assert resp.status_code == 200
        assert "columns" in resp.get_json()["data"]

    def test_entity_search(self, reports_cov3_client):
        with patch(
            "services.reports_query_service.ReportsQueryService.search_entities",
            return_value=[{"id": 1}],
        ):
            resp = reports_cov3_client.get("/reports/api/entity-search?q=a&type=supplier")
        assert resp.status_code == 200

    def test_supplier_fragment(self, reports_cov3_client):
        ent = MagicMock(id=3)
        with (
            patch("routes.reports.tenant_get_or_404", return_value=ent),
            patch("routes.reports.report_branch_scope_id", return_value=None),
            patch(
                "services.reports_query_service.ReportsQueryService.build_supplier_fragment_data",
                return_value={"balance": 5},
            ),
            patch("routes.reports.render_template", return_value="ok"),
        ):
            resp = reports_cov3_client.get("/reports/entity_report_fragment/supplier/3")
        assert resp.status_code == 200

    def test_customer_fragment_vip(self, reports_cov3_client):
        ent = MagicMock(id=4, customer_type="vip")
        with (
            patch("routes.reports.tenant_get_or_404", return_value=ent),
            patch("routes.reports.report_branch_scope_id", return_value=None),
            patch(
                "services.reports_query_service.ReportsQueryService.build_customer_fragment_data",
                return_value={"balance": 1},
            ),
            patch("routes.reports.render_template", return_value="ok"),
        ):
            resp = reports_cov3_client.get("/reports/entity_report_fragment/customer/4")
        assert resp.status_code == 200

    def test_fragment_exception_renders_error(self, reports_cov3_client):
        with (
            patch("routes.reports.tenant_get_or_404", side_effect=Exception("gone")),
            patch("routes.reports.render_template", return_value="err"),
        ):
            resp = reports_cov3_client.get("/reports/entity_report_fragment/supplier/9")
        assert resp.status_code == 200

    def test_top_selling(self, reports_cov3_client):
        with (
            patch(
                "services.reports_query_service.ReportsQueryService.fetch_top_selling_products",
                return_value=[],
            ),
            patch("routes.reports.render_template", return_value="ok"),
        ):
            resp = reports_cov3_client.get("/reports/top-selling?limit=5")
        assert resp.status_code == 200

    def test_receivables_export_xlsx(self, reports_cov3_client):
        with (
            patch(
                "services.reports_query_service.ReportsQueryService.fetch_receivables_sales",
                return_value=[_sale()],
            ),
            patch(
                "services.export_service.ExportService.export_to_xlsx",
                return_value=io.BytesIO(b"x"),
            ),
        ):
            resp = reports_cov3_client.get("/reports/receivables/export?format=xlsx")
        assert resp.status_code == 200

    def test_inventory_reconciliation_export_csv(self, reports_cov3_client):
        with (
            patch("routes.reports.report_branch_scope_id", return_value=None),
            patch(
                "services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary",
                return_value={"rows": []},
            ),
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=io.BytesIO(b"c"),
            ),
        ):
            resp = reports_cov3_client.get("/reports/inventory-reconciliation/export?format=csv")
        assert resp.status_code == 200
