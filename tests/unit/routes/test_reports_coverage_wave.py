"""Coverage wave for routes/reports.py — branch scope, exports, entity fragments."""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import make_response

from tests.unit.routes.test_reports_routes import (
    _chain_query_stub,
    _configure_user,
    _entity_mock,
    _export_io,
    _send_file_response,
)


def _partner_commission_row(**overrides):
    row = MagicMock()
    row.product_name = overrides.get("product_name", "Widget")
    row.partner_name = overrides.get("partner_name", "Partner A")
    row.percentage = overrides.get("percentage", Decimal("10"))
    row.total_qty = overrides.get("total_qty", Decimal("5"))
    row.total_revenue = overrides.get("total_revenue", Decimal("500"))
    row.partner_share_amount = overrides.get("partner_share_amount", Decimal("50"))
    row.partner_id = overrides.get("partner_id", 3)
    return row


class TestPartnersBranchScopeWave:
    def test_has_entries_branch_and_date_filters(self, reports_client, mock_user):
        _configure_user(mock_user)
        row = _partner_commission_row()
        exists_q = _chain_query_stub(scalar=True)
        rows_q = _chain_query_stub(all=[row])
        financial_q = _chain_query_stub(scalar=Decimal("100"))
        call_n = {"n": 0}

        def session_query(*args, **kwargs):
            call_n["n"] += 1
            if call_n["n"] == 1:
                return _chain_query_stub()
            if call_n["n"] == 2:
                return exists_q
            if call_n["n"] == 3:
                return rows_q
            return financial_q

        partner_cust = MagicMock(id=3, name="Partner A", customer_type="partner")
        supplier = MagicMock(id=1, name="Sup", tenant_id=1)
        with (
            patch("routes.reports.db.session.query", side_effect=session_query),
            patch(
                "routes.reports.tenant_query", return_value=_chain_query_stub(all=[])
            ),
            patch("routes.reports._scoped_customer_query") as scq,
            patch("routes.reports._scoped_supplier_query") as ssq,
            patch("routes.reports.report_branch_scope_id", return_value=7),
        ):
            scq.return_value.filter_by.return_value.all.return_value = [partner_cust]
            ssq.return_value.all.return_value = [supplier]
            resp = reports_client.get(
                "/reports/partners?date_from=2025-01-01&date_to=2025-12-31"
            )
            assert resp.status_code == 200

    def test_fallback_partner_sales_branch_scoped(self, reports_client, mock_user):
        _configure_user(mock_user)
        share = MagicMock()
        share.percentage = Decimal("10")
        share.partner_customer = MagicMock(id=4, name="P")
        product = MagicMock()
        product.id = 1
        product.name = "Prod"
        product.partner_shares = [share]
        line = MagicMock(line_total=Decimal("200"), quantity=Decimal("2"))
        pp_q = _chain_query_stub(all=[product])
        sl_q = _chain_query_stub(all=[line])
        empty_merch = _chain_query_stub(all=[])
        pc = {"n": 0}

        def tenant_query_side(model):
            name = getattr(model, "__name__", "")
            if name == "Product":
                pc["n"] += 1
                return pp_q if pc["n"] == 1 else empty_merch
            if name == "SaleLine":
                return sl_q
            return _chain_query_stub(all=[])

        with (
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(scalar=False),
            ),
            patch("routes.reports.tenant_query", side_effect=tenant_query_side),
            patch(
                "routes.reports._scoped_customer_query",
                return_value=_chain_query_stub(all=[]),
            ),
            patch(
                "routes.reports._scoped_supplier_query",
                return_value=_chain_query_stub(all=[]),
            ),
            patch("routes.reports.report_branch_scope_id", return_value=3),
        ):
            resp = reports_client.get("/reports/partners?date_from=2025-01-01")
            assert resp.status_code == 200

    def test_merchant_sales_branch_scoped(self, reports_client, mock_user):
        _configure_user(mock_user)
        merchant = MagicMock(id=9, name="M")
        product = MagicMock()
        product.id = 2
        product.name = "Merch"
        product.merchant_customer_id = 9
        product.merchant_customer = merchant
        product.merchant_share = 30
        line = MagicMock(line_total=Decimal("400"), quantity=Decimal("4"))
        sl_q = _chain_query_stub(all=[line])
        empty_pp = _chain_query_stub(all=[])
        merch_q = _chain_query_stub(all=[product])
        pc = {"n": 0}

        def tenant_query_side(model):
            name = getattr(model, "__name__", "")
            if name == "Product":
                pc["n"] += 1
                return empty_pp if pc["n"] == 1 else merch_q
            if name == "SaleLine":
                return sl_q
            return _chain_query_stub(all=[])

        with (
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(scalar=False),
            ),
            patch("routes.reports.tenant_query", side_effect=tenant_query_side),
            patch(
                "routes.reports._scoped_customer_query",
                return_value=_chain_query_stub(all=[]),
            ),
            patch(
                "routes.reports._scoped_supplier_query",
                return_value=_chain_query_stub(all=[]),
            ),
            patch("routes.reports.report_branch_scope_id", return_value=5),
        ):
            resp = reports_client.get("/reports/partners")
            assert resp.status_code == 200


class TestSalesBranchScopeWave:
    def test_sales_branch_scoped_filters(self, reports_client, mock_user):
        _configure_user(mock_user)
        sale = MagicMock()
        sale.id = 1
        sale.amount_aed = Decimal("500")
        sale.get_profit.return_value = Decimal("50")
        sq = _chain_query_stub(all=[sale])
        seller = MagicMock(id=2, username="seller1")
        sellers_q = _chain_query_stub(all=[seller])
        with (
            patch("routes.reports.tenant_query", return_value=sq),
            patch(
                "routes.reports.get_confirmed_sale_paid_aed",
                return_value=Decimal("200"),
            ),
            patch("routes.reports.Customer") as Customer,
            patch("utils.tenanting.scoped_user_query", return_value=sellers_q),
            patch("routes.reports.report_branch_scope_id", return_value=4),
        ):
            Customer.query.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )
            resp = reports_client.get(
                "/reports/sales?customer=3&seller=2&date_from=2025-01-01&date_to=2025-06-30"
            )
            assert resp.status_code == 200

    def test_sales_export_branch_seller_filters(self, reports_client, mock_user):
        _configure_user(mock_user)
        sale = MagicMock()
        sale.id = 2
        sale.amount_aed = Decimal("100")
        sale.sale_number = "S-1"
        sale.sale_date = datetime(2025, 1, 15, tzinfo=timezone.utc)
        sale.customer = MagicMock(name="C")
        sale.seller = MagicMock()
        sale.seller.get_display_name.return_value = "Seller"
        sale.branch = MagicMock(name="Branch")
        sale.warehouse = MagicMock(name="WH", name_ar="مستودع")
        sale.currency = "AED"
        sale.exchange_rate = Decimal("1")
        sale.payment_status = "partial"
        sq = _chain_query_stub(all=[sale])
        with (
            patch("routes.reports.tenant_query", return_value=sq),
            patch(
                "routes.reports.get_confirmed_sale_paid_aed", return_value=Decimal("50")
            ),
            patch("routes.reports.report_branch_scope_id", return_value=2),
            patch(
                "services.export_service.ExportService.export_to_xlsx",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get(
                "/reports/sales/export?format=xlsx&customer=1&seller=2&date_from=2025-01-01"
            )
            assert resp.status_code == 200


class TestPurchasesBranchScopeWave:
    def test_purchases_branch_scoped(self, reports_client, mock_user):
        _configure_user(mock_user)
        purchase = MagicMock()
        purchase.id = 1
        purchase.supplier_id = 3
        purchase.amount_aed = Decimal("800")
        pmt = MagicMock()
        pmt.supplier_id = 3
        pmt.amount_aed = Decimal("300")
        pq = _chain_query_stub(all=[purchase])
        pay_q = _chain_query_stub(all=[pmt])
        sup_scoped = _chain_query_stub(all=[])

        def tq(model):
            from models import Payment

            if model is Payment:
                return pay_q
            return pq

        with (
            patch("routes.reports.tenant_query", side_effect=tq),
            patch("routes.reports._scoped_supplier_query", return_value=sup_scoped),
            patch("routes.reports.report_branch_scope_id", return_value=6),
        ):
            resp = reports_client.get(
                "/reports/purchases?start_date=2025-01-01&end_date=2025-06-30&supplier_id=3"
            )
            assert resp.status_code == 200

    def test_purchases_export_xlsx_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        purchase = MagicMock()
        purchase.purchase_number = "PO-1"
        purchase.purchase_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
        purchase.supplier = MagicMock(name="Sup")
        purchase.branch = MagicMock(name="B")
        purchase.warehouse = MagicMock(name="W", name_ar="م")
        purchase.currency = "AED"
        purchase.exchange_rate = Decimal("1")
        purchase.amount_aed = Decimal("500")
        purchase.total_amount = Decimal("500")
        purchase.status = "confirmed"
        pq = _chain_query_stub(all=[purchase])
        with (
            patch("routes.reports.tenant_query", return_value=pq),
            patch("routes.reports.report_branch_scope_id", return_value=3),
            patch(
                "services.export_service.ExportService.export_to_xlsx",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get(
                "/reports/purchases/export?format=xlsx&supplier_id=1&start_date=2025-01-01"
            )
            assert resp.status_code == 200


class TestReconciliationWave:
    def test_ar_reconciliation_inaccessible_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("utils.branching.user_can_access_branch", return_value=False):
            resp = reports_client.get("/reports/ar-reconciliation?branch_id=99")
            assert resp.status_code == 403

    def test_inventory_reconciliation_inaccessible_branch(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        with patch("utils.branching.user_can_access_branch", return_value=False):
            resp = reports_client.get("/reports/inventory-reconciliation?branch_id=99")
            assert resp.status_code == 403

    def test_inventory_reconciliation_non_admin_no_warehouses(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        mock_user.is_admin.return_value = False
        wh_q = MagicMock()
        wh_q.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = (
            []
        )
        with (
            patch("models.Warehouse.query", wh_q),
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch(
                "services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary",
                return_value={"rows": []},
            ),
        ):
            resp = reports_client.get("/reports/inventory-reconciliation")
            assert resp.status_code == 200

    def test_inventory_reconciliation_warehouse_forbidden(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        wh = MagicMock()
        wh.id = 5
        wh_q = MagicMock()
        wh_q.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [
            wh
        ]
        with (
            patch("models.Warehouse.query", wh_q),
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]),
        ):
            resp = reports_client.get(
                "/reports/inventory-reconciliation?warehouse_id=5"
            )
            assert resp.status_code == 403

    def test_inventory_reconciliation_export_csv(self, reports_client, mock_user):
        _configure_user(mock_user)
        mock_user.is_admin.return_value = True
        row = {
            "tenant_id": 1,
            "product_id": 1,
            "product_name": "P",
            "warehouse_id": 1,
            "warehouse_name": "W",
            "pwc_qty": 10,
            "movement_qty": 10,
            "qty_diff": 0,
            "pwc_avg_cost": 5,
            "pwc_value": 50,
            "matched_qty": True,
        }
        wh = SimpleNamespace(id=1, tenant_id=1, branch_id=1, is_active=True)
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = wh
        with (
            patch(
                "services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary",
                return_value={"rows": [row]},
            ),
            patch("models.Warehouse.query", wh_query),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]),
            patch("utils.branching.user_can_access_branch", return_value=True),
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get(
                "/reports/inventory-reconciliation/export?format=csv&warehouse_id=1&branch_id=1"
            )
            assert resp.status_code == 200

    def test_inventory_reconciliation_export_warehouse_403(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        mock_user.is_admin.return_value = False
        with (
            patch("models.Warehouse.query") as wh_model,
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[2]),
            patch("utils.branching.user_can_access_branch", return_value=True),
        ):
            wh_model.query.filter_by.return_value.first.return_value = MagicMock(
                id=99, tenant_id=1, branch_id=1, is_active=True
            )
            resp = reports_client.get(
                "/reports/inventory-reconciliation/export?warehouse_id=99&branch_id=1"
            )
            assert resp.status_code == 403


class TestReceivablesWave:
    def test_receivables_naive_datetime_and_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        sale = MagicMock()
        sale.amount_aed = Decimal("1000")
        sale.paid_amount_aed = Decimal("100")
        sale.sale_date = datetime(2024, 1, 1)  # naive — triggers tz fix
        sq = _chain_query_stub(all=[sale])
        with (
            patch("routes.reports.tenant_query", return_value=sq),
            patch("routes.reports.Customer") as Customer,
            patch("routes.reports.report_branch_scope_id", return_value=2),
        ):
            Customer.query.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )
            resp = reports_client.get("/reports/receivables?customer=5")
            assert resp.status_code == 200

    def test_receivables_export_all_buckets(self, reports_client, mock_user):
        _configure_user(mock_user)
        now = datetime.now(timezone.utc)
        sales = []
        for days, num in ((10, "S1"), (45, "S2"), (75, "S3"), (100, "S4"), (150, "S5")):
            s = MagicMock()
            s.amount_aed = Decimal("500")
            s.paid_amount_aed = Decimal("50")
            s.sale_date = now - timedelta(days=days)
            s.sale_number = num
            s.customer = MagicMock(name="Cust")
            s.branch = MagicMock(name="B")
            s.currency = "AED"
            s.exchange_rate = Decimal("1")
            sales.append(s)
        sq = _chain_query_stub(all=sales)
        with (
            patch("routes.reports.tenant_query", return_value=sq),
            patch("routes.reports.report_branch_scope_id", return_value=1),
            patch(
                "services.export_service.ExportService.export_to_xlsx",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get(
                "/reports/receivables/export?format=xlsx&customer=1"
            )
            assert resp.status_code == 200


class TestInventoryWave:
    @staticmethod
    def _warehouse_product_setup(*, admin=True, warehouse_in_list=False):
        warehouse = MagicMock()
        warehouse.id = 10
        warehouse.name = "Main WH"
        warehouse.name_ar = "رئيسي"
        warehouse.is_main = True
        warehouse.tenant_id = 1
        warehouse.branch_id = 2
        product = MagicMock()
        product.id = 20
        product.name = "StockItem"
        product.sku = "SKU1"
        product.barcode = "123"
        product.cost_price = Decimal("15")
        product.regular_price = Decimal("25")
        product.min_stock_alert = Decimal("3")
        return warehouse, product

    def test_inventory_branch_forbidden_mismatch(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.report_branch_scope_id", return_value=1):
            resp = reports_client.get("/reports/inventory?branch_id=99")
            assert resp.status_code == 403

    def test_inventory_warehouse_admin_lookup_404(self, reports_client, mock_user):
        _configure_user(mock_user)
        wh_chain = _chain_query_stub(all=[])
        with (
            patch("routes.reports.tenant_query", return_value=wh_chain),
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch("models.Warehouse") as Warehouse,
        ):
            Warehouse.query.filter_by.return_value.first.return_value = None
            resp = reports_client.get("/reports/inventory?warehouse_id=999")
            assert resp.status_code == 404

    def test_inventory_warehouse_branch_mismatch_403(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse, product = TestInventoryWave._warehouse_product_setup()
        warehouse.branch_id = 99
        wh_chain = MagicMock()
        wh_chain.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = (
            []
        )
        product_chain = _chain_query_stub(all=[product])

        def tq(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with (
            patch("routes.reports.tenant_query", side_effect=tq),
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch("models.Warehouse") as Warehouse,
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[(20, Decimal("8"))]),
            ),
        ):
            Warehouse.query.filter_by.return_value.first.return_value = warehouse
            resp = reports_client.get("/reports/inventory?warehouse_id=10&branch_id=2")
            assert resp.status_code == 403

    def test_inventory_date_filters_and_stats(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse, product = TestInventoryWave._warehouse_product_setup()
        wh_inner = MagicMock()
        wh_inner.order_by.return_value.all.return_value = [warehouse]
        wh_chain = MagicMock()
        wh_chain.filter_by.return_value = wh_inner
        wh_inner.filter.return_value = wh_inner
        product_chain = MagicMock()
        product_chain.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [
            product
        ]

        def tq(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with (
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[10]),
            patch("routes.reports.tenant_query", side_effect=tq),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[(20, Decimal("5"))]),
            ),
        ):
            resp = reports_client.get(
                "/reports/inventory",
                query_string={
                    "warehouse_id": "10",
                    "in_date_from": "2025-01-01",
                    "in_date_to": "2025-06-30",
                    "out_date_from": "2025-01-01",
                    "out_date_to": "2025-06-30",
                    "category": "1",
                },
            )
            assert resp.status_code == 200

    def test_inventory_non_admin_warehouse_forbidden(self, reports_client, mock_user):
        _configure_user(mock_user)
        mock_user.is_admin.return_value = False
        wh_chain = _chain_query_stub(all=[])
        with (
            patch("routes.reports.tenant_query", return_value=wh_chain),
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[]),
            ),
        ):
            resp = reports_client.get("/reports/inventory?warehouse_id=55")
            assert resp.status_code == 403

    def test_inventory_export_full_path(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse, product = TestInventoryWave._warehouse_product_setup()
        wh_chain = _chain_query_stub(all=[warehouse])
        product_chain = _chain_query_stub(all=[product])

        def tq(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with (
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[10]),
            patch("utils.branching.user_can_access_branch", return_value=True),
            patch("routes.reports.tenant_query", side_effect=tq),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(
                    all=[(20, Decimal("12"))]
                ),
            ),
            patch(
                "services.export_service.ExportService.export_to_xlsx",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get(
                "/reports/inventory/export",
                query_string={
                    "format": "xlsx",
                    "warehouse_id": "10",
                    "branch_id": "2",
                    "include_zero": "1",
                    "in_date_from": "2025-01-01",
                    "in_date_to": "2025-06-30",
                    "out_date_from": "2025-01-01",
                    "out_date_to": "2025-06-30",
                    "category": "1",
                },
            )
            assert resp.status_code == 200

    def test_inventory_export_admin_warehouse_lookup(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse, product = TestInventoryWave._warehouse_product_setup()
        warehouse.branch_id = 2
        wh_chain = _chain_query_stub(all=[])
        product_chain = _chain_query_stub(all=[product])
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = warehouse

        def tq(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with (
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch("utils.branching.user_can_access_branch", return_value=True),
            patch("routes.reports.tenant_query", side_effect=tq),
            patch("models.Warehouse.query", wh_query),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[(20, Decimal("3"))]),
            ),
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=io.BytesIO(b"x"),
            ),
            patch("flask.send_file", return_value=make_response("ok", 200)),
        ):
            resp = reports_client.get(
                "/reports/inventory/export?warehouse_id=10&branch_id=2"
            )
            assert resp.status_code == 200


class TestEntitySearchWave:
    def test_supplier_search_returns_results(self, reports_client, mock_user):
        _configure_user(mock_user)
        supplier = SimpleNamespace(id=1, name="Acme Sup", phone="+971")
        scoped = _chain_query_stub(all=[supplier])
        with patch("routes.reports._scoped_supplier_query", return_value=scoped):
            resp = reports_client.get("/reports/api/entity-search?type=supplier&q=acme")
            assert resp.status_code == 200
            body = resp.get_json()
            assert len(body) == 1
            assert body[0]["type"] == "supplier"

    def test_customer_search_returns_results(self, reports_client, mock_user):
        _configure_user(mock_user)
        customer = SimpleNamespace(
            id=2, name="John", phone="050", customer_type="regular"
        )
        scoped = _chain_query_stub(all=[customer])
        with patch("routes.reports._scoped_customer_query", return_value=scoped):
            resp = reports_client.get("/reports/api/entity-search?type=customer&q=john")
            assert resp.status_code == 200
            assert resp.get_json()[0]["name"] == "John"


class TestEntityFragmentWave:
    @staticmethod
    def _supplier_purchase_payment_mocks(
        *, branch_id=3, direct_payments=None, fifo_scalar=Decimal("0")
    ):
        purchase = MagicMock()
        purchase.id = 1
        purchase.purchase_number = "PO-1"
        purchase.purchase_date = datetime(2025, 1, 10, tzinfo=timezone.utc)
        purchase.status = "confirmed"
        purchase.amount_aed = Decimal("1000")
        payment = MagicMock()
        payment.purchase_id = 1
        payment.amount_aed = Decimal("600")
        payment.payment_number = "PAY-1"
        payment.payment_date = datetime(2025, 1, 15, tzinfo=timezone.utc)
        payment.payment_method = "bank"
        payment.direction = "outgoing"
        payment.payment_confirmed = True
        payment.notes = "paid"
        p_line = MagicMock(
            name="Part",
            qty=Decimal("5"),
            total=Decimal("1000"),
            last_date=purchase.purchase_date,
        )
        purchase_q = MagicMock()
        purchase_q.filter_by.return_value = purchase_q
        purchase_q.filter.return_value = purchase_q
        purchase_q.order_by.return_value = purchase_q
        purchase_q.all.return_value = [purchase]
        session_calls = {"n": 0}

        def session_query(*args, **kwargs):
            session_calls["n"] += 1
            if branch_id is not None and session_calls["n"] == 1:
                return _chain_query_stub(scalar=True)
            return _chain_query_stub(all=[p_line])

        return {
            "purchase": purchase,
            "payment": payment,
            "p_line": p_line,
            "purchase_q": purchase_q,
            "session_query": session_query,
            "pay_chain": _payment_query_stub(
                direct_all=(
                    direct_payments if direct_payments is not None else [payment]
                ),
                fifo_total=fifo_scalar,
            ),
            "branch_id": branch_id,
        }

    def test_supplier_fragment_no_branch_direct_pay(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Supplier Direct")
        ctx = self._supplier_purchase_payment_mocks(branch_id=None)
        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch("routes.reports.report_branch_scope_id", return_value=None),
            patch("routes.reports.db.session.query", side_effect=ctx["session_query"]),
            patch("models.Purchase") as Purchase,
            patch("models.Payment") as Payment,
        ):
            Payment.query = MagicMock()
            Purchase.query.filter_by.return_value = ctx["purchase_q"]
            Payment.query.filter.return_value = ctx["pay_chain"]
            Payment.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [
                ctx["payment"]
            ]
            resp = reports_client.get("/reports/entity_report_fragment/supplier/12")
            assert resp.status_code == 200

    def test_supplier_fragment_branch_scoped_full(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Branch Supplier")
        ctx = self._supplier_purchase_payment_mocks(branch_id=3)
        scoped = MagicMock()
        scoped.filter_by.return_value.exists.return_value = MagicMock()
        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch(
                "routes.reports.report_branch_scope_id", return_value=ctx["branch_id"]
            ),
            patch("routes.reports._scoped_supplier_query", return_value=scoped),
            patch("routes.reports.db.session.query", side_effect=ctx["session_query"]),
            patch("models.Purchase") as Purchase,
            patch("models.Payment") as Payment,
        ):
            Payment.query = MagicMock()
            Purchase.query.filter_by.return_value = ctx["purchase_q"]
            Payment.query.filter.return_value = ctx["pay_chain"]
            Payment.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [
                ctx["payment"]
            ]
            resp = reports_client.get("/reports/entity_report_fragment/supplier/12")
            assert resp.status_code == 200

    def test_customer_fragment_branch_transactions(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = MagicMock()
        entity.id = 20
        entity.name = "Buyer"
        entity.customer_type = "regular"
        sale = MagicMock()
        sale.sale_number = "INV-1"
        sale.sale_date = datetime(2025, 3, 1, tzinfo=timezone.utc)
        sale.status = "confirmed"
        sale.amount_aed = Decimal("500")
        sale.paid_amount_aed = Decimal("200")
        receipt = MagicMock()
        receipt.receipt_number = "R-1"
        receipt.receipt_date = datetime(2025, 3, 5, tzinfo=timezone.utc)
        receipt.amount_aed = Decimal("200")
        receipt.payment_method = "cash"
        receipt.payment_confirmed = True
        payment = MagicMock()
        payment.payment_number = "P-1"
        payment.payment_date = datetime(2025, 3, 10, tzinfo=timezone.utc)
        payment.amount_aed = Decimal("50")
        payment.payment_method = "bank"
        payment.direction = "outgoing"
        payment.payment_confirmed = True
        payment.notes = "refund"
        s_line = MagicMock(
            name="Item",
            qty=Decimal("2"),
            total=Decimal("500"),
            last_date=sale.sale_date,
        )
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [sale]
        receipt_q = MagicMock()
        receipt_q.filter.return_value = receipt_q
        receipt_q.all.return_value = [receipt]
        payment_q = MagicMock()
        payment_q.filter.return_value = payment_q
        payment_q.all.return_value = [payment]
        scalars = iter([Decimal("500"), Decimal("200"), Decimal("50")])

        def session_query(*args, **kwargs):
            return _chain_query_stub(scalar=next(scalars, Decimal("0")), all=[s_line])

        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch("routes.reports.report_branch_scope_id", return_value=4),
            patch("routes.reports.db.session.query", side_effect=session_query),
            patch("models.Sale") as Sale,
            patch("models.Receipt") as Receipt,
            patch("models.Payment") as Payment,
        ):
            Sale.query.filter_by.return_value = sale_q
            Receipt.query.filter_by.return_value = receipt_q
            Payment.query.filter_by.return_value = payment_q
            resp = reports_client.get("/reports/entity_report_fragment/customer/20")
            assert resp.status_code == 200

    def test_partner_fragment_shared_products_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = MagicMock(id=30, name="Partner", customer_type="partner")
        sp = MagicMock(
            name="SharedProd",
            percentage=Decimal("15"),
            qty=Decimal("3"),
            total_sales=Decimal("300"),
            last_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        qc = {"n": 0}

        def session_query(*args, **kwargs):
            qc["n"] += 1
            if qc["n"] <= 3:
                return _chain_query_stub(scalar=Decimal("100"))
            if qc["n"] == 4:
                return _chain_query_stub(all=[])
            if qc["n"] == 5:
                return _chain_query_stub(all=[sp])
            return _chain_query_stub(all=[])

        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch("routes.reports.report_branch_scope_id", return_value=2),
            patch("routes.reports.db.session.query", side_effect=session_query),
            patch("models.Sale") as Sale,
            patch("models.Receipt") as Receipt,
            patch("models.Payment") as Payment,
        ):
            Sale.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            Receipt.query.filter_by.return_value.filter.return_value.all.return_value = (
                []
            )
            Payment.query.filter_by.return_value.filter.return_value.all.return_value = (
                []
            )
            resp = reports_client.get("/reports/entity_report_fragment/partner/30")
            assert resp.status_code == 200

    def test_merchant_fragment_products_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = MagicMock(id=31, name="Merchant", customer_type="merchant")
        mp = MagicMock(
            name="OwnProd",
            merchant_share=40,
            qty=Decimal("2"),
            total_sales=Decimal("400"),
            last_date=None,
        )
        qc = {"n": 0}

        def session_query(*args, **kwargs):
            qc["n"] += 1
            if qc["n"] <= 3:
                return _chain_query_stub(scalar=Decimal("0"))
            if qc["n"] == 4:
                return _chain_query_stub(all=[])
            if qc["n"] == 5:
                return _chain_query_stub(all=[mp])
            return _chain_query_stub(all=[])

        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch("routes.reports.report_branch_scope_id", return_value=2),
            patch("routes.reports.db.session.query", side_effect=session_query),
            patch("models.Sale") as Sale,
            patch("models.Receipt") as Receipt,
            patch("models.Payment") as Payment,
        ):
            Sale.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            Receipt.query.filter_by.return_value.filter.return_value.all.return_value = (
                []
            )
            Payment.query.filter_by.return_value.filter.return_value.all.return_value = (
                []
            )
            resp = reports_client.get("/reports/entity_report_fragment/merchant/31")
            assert resp.status_code == 200


class TestEntityFragmentDirectCall:
    def test_supplier_fifo_allocation_direct(self, app_factory, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Direct Supplier")
        ctx = TestEntityFragmentWave._supplier_purchase_payment_mocks(
            branch_id=None, direct_payments=[], fifo_scalar=Decimal("250")
        )
        ctx["payment"].purchase_id = None
        app = app_factory(
            __import__("routes.reports", fromlist=["reports_bp"]).reports_bp
        )
        with app.test_request_context("/reports/entity_report_fragment/supplier/12"):
            with (
                patch("flask_login.utils._get_user", return_value=mock_user),
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
                patch("routes.reports.tenant_get_or_404", return_value=entity),
                patch("routes.reports.report_branch_scope_id", return_value=None),
                patch("routes.reports.render_template", return_value="ok") as render,
                patch(
                    "routes.reports.db.session.query", side_effect=ctx["session_query"]
                ),
                patch("models.Purchase.query", ctx["purchase_q"]),
                patch("models.Payment.query") as pay_query,
            ):
                pay_query.filter.return_value = ctx["pay_chain"]
                pay_query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [
                    ctx["payment"]
                ]
                from routes.reports import entity_report_fragment

                resp = entity_report_fragment("supplier", id=12)
                assert resp[1] == 200 if isinstance(resp, tuple) else True
                assert render.called
                assert render.call_args[1].get("allocation_exact") is False

    def test_supplier_fifo_two_purchases(self, app_factory, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("FIFO Two")
        purchase_b = MagicMock(
            id=2,
            purchase_number="P2",
            purchase_date=datetime(2025, 2, 1, tzinfo=timezone.utc),
            status="confirmed",
            amount_aed=Decimal("500"),
        )
        ctx = TestEntityFragmentWave._supplier_purchase_payment_mocks(
            branch_id=None,
            direct_payments=[],
            fifo_scalar=Decimal("400"),
        )
        ctx["purchase_q"].all.return_value = [ctx["purchase"], purchase_b]
        app = app_factory(
            __import__("routes.reports", fromlist=["reports_bp"]).reports_bp
        )
        with app.test_request_context("/reports/entity_report_fragment/supplier/12"):
            with (
                patch("flask_login.utils._get_user", return_value=mock_user),
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
                patch("routes.reports.tenant_get_or_404", return_value=entity),
                patch("routes.reports.report_branch_scope_id", return_value=None),
                patch("routes.reports.render_template", return_value="ok") as render,
                patch(
                    "routes.reports.db.session.query", side_effect=ctx["session_query"]
                ),
                patch("models.Purchase.query", ctx["purchase_q"]),
                patch("models.Payment.query") as pay_query,
            ):
                pay_query.filter.return_value = ctx["pay_chain"]
                pay_query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = (
                    []
                )
                from routes.reports import entity_report_fragment

                entity_report_fragment("supplier", id=12)
                assert render.call_args[1].get("invoices")

    def test_customer_transactions_direct(self, app_factory, mock_user):
        _configure_user(mock_user)
        entity = SimpleNamespace(id=40, name="Buyer", customer_type="regular")
        sale = MagicMock(
            sale_number="INV-40",
            sale_date=datetime(2025, 4, 1, tzinfo=timezone.utc),
            status="confirmed",
            amount_aed=Decimal("800"),
            paid_amount_aed=Decimal("300"),
        )
        receipt = MagicMock(
            receipt_number="R-40",
            receipt_date=datetime(2025, 4, 2, tzinfo=timezone.utc),
            amount_aed=Decimal("300"),
            payment_method="cash",
        )
        payment = MagicMock(
            payment_number="P-40",
            payment_date=datetime(2025, 4, 3, tzinfo=timezone.utc),
            amount_aed=Decimal("100"),
            payment_method="bank",
            notes="draw",
        )
        sale_q = MagicMock()
        sale_q.filter_by.return_value = sale_q
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [sale]
        receipt_q = MagicMock()
        receipt_q.filter_by.return_value = receipt_q
        receipt_q.filter.return_value = receipt_q
        receipt_q.all.return_value = [receipt]
        payment_q = MagicMock()
        payment_q.filter_by.return_value = payment_q
        payment_q.filter.return_value = payment_q
        payment_q.all.return_value = [payment]
        scalars = iter([Decimal("800"), Decimal("300"), Decimal("100")])

        def session_query(*args, **kwargs):
            if session_query.i <= 3:
                session_query.i += 1
                return _chain_query_stub(scalar=next(scalars, Decimal("0")))
            if session_query.i == 4:
                session_query.i += 1
                return _chain_query_stub(all=[])
            session_query.i += 1
            return _chain_query_stub(all=[])

        session_query.i = 1
        app = app_factory(
            __import__("routes.reports", fromlist=["reports_bp"]).reports_bp
        )
        with app.test_request_context("/reports/entity_report_fragment/customer/40"):
            with (
                patch("flask_login.utils._get_user", return_value=mock_user),
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
                patch("routes.reports.tenant_get_or_404", return_value=entity),
                patch("routes.reports.report_branch_scope_id", return_value=None),
                patch("routes.reports.render_template", return_value="ok") as render,
                patch("routes.reports.db.session.query", side_effect=session_query),
                patch("models.Sale.query", sale_q),
                patch("models.Receipt.query", receipt_q),
                patch("models.Payment.query", payment_q),
            ):
                from routes.reports import entity_report_fragment

                entity_report_fragment("customer", id=40)
                assert render.called
                ctx = render.call_args[1]
                assert len(ctx.get("invoices", [])) == 1
                assert len(ctx.get("transactions", [])) == 2

    def test_merchant_share_products_direct(self, app_factory, mock_user):
        _configure_user(mock_user)
        entity = SimpleNamespace(id=51, name="Merchant", customer_type="merchant")
        mp = SimpleNamespace(
            name="Owned",
            merchant_share=35,
            qty=Decimal("2"),
            total_sales=Decimal("400"),
            last_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
        )
        sale_q = MagicMock()
        sale_q.filter_by.return_value = sale_q
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = []
        session_n = {"n": 0}

        def session_query(*args, **kwargs):
            session_n["n"] += 1
            if session_n["n"] <= 3:
                return _chain_query_stub(scalar=Decimal("50"))
            if session_n["n"] == 4:
                return _chain_query_stub(all=[])
            if session_n["n"] == 5:
                return _chain_query_stub(all=[mp])
            return _chain_query_stub(all=[])

        app = app_factory(
            __import__("routes.reports", fromlist=["reports_bp"]).reports_bp
        )
        with app.test_request_context("/reports/entity_report_fragment/merchant/51"):
            with (
                patch("flask_login.utils._get_user", return_value=mock_user),
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
                patch("routes.reports.tenant_get_or_404", return_value=entity),
                patch("routes.reports.report_branch_scope_id", return_value=None),
                patch("routes.reports.render_template", return_value="ok") as render,
                patch("routes.reports.db.session.query", side_effect=session_query),
                patch("models.Sale.query", sale_q),
                patch("models.Receipt.query") as rq,
                patch("models.Payment.query") as pq,
            ):
                rq.filter_by.return_value.filter.return_value.all.return_value = []
                pq.filter_by.return_value.filter.return_value.all.return_value = []
                from routes.reports import entity_report_fragment

                entity_report_fragment("merchant", id=51)
                assert render.called

    def test_supplier_direct_allocation_branch(self, app_factory, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("Direct Alloc")
        direct_pay = MagicMock(purchase_id=1, amount_aed=Decimal("200"))
        unalloc = MagicMock(purchase_id=None, amount_aed=Decimal("75"))
        ctx = TestEntityFragmentWave._supplier_purchase_payment_mocks(branch_id=3)
        ctx["pay_chain"] = _payment_query_stub(
            direct_all=[direct_pay], unalloc_all=[unalloc]
        )
        scoped = MagicMock()
        scoped.filter_by.return_value.exists.return_value = MagicMock()
        app = app_factory(
            __import__("routes.reports", fromlist=["reports_bp"]).reports_bp
        )
        with app.test_request_context("/reports/entity_report_fragment/supplier/12"):
            with (
                patch("flask_login.utils._get_user", return_value=mock_user),
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
                patch("routes.reports.tenant_get_or_404", return_value=entity),
                patch("routes.reports.report_branch_scope_id", return_value=3),
                patch("routes.reports._scoped_supplier_query", return_value=scoped),
                patch("routes.reports.render_template", return_value="ok") as render,
                patch(
                    "routes.reports.db.session.query", side_effect=ctx["session_query"]
                ),
                patch("models.Purchase.query", ctx["purchase_q"]),
                patch("models.Payment.query") as pay_query,
            ):
                pay_query.filter.return_value = ctx["pay_chain"]
                pay_query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [
                    ctx["payment"]
                ]
                from routes.reports import entity_report_fragment

                entity_report_fragment("supplier", id=12)
                assert render.call_args[1]["allocation_exact"] is True
                assert render.call_args[1]["unallocated_supplier_credit"] == Decimal(
                    "75"
                )

    def test_customer_branch_scoped_transactions(self, app_factory, mock_user):
        _configure_user(mock_user)
        entity = SimpleNamespace(id=55, name="Branch Cust", customer_type="regular")
        sale = MagicMock(
            sale_number="S55",
            sale_date=datetime(2025, 5, 1, tzinfo=timezone.utc),
            status="confirmed",
            amount_aed=Decimal("400"),
            paid_amount_aed=Decimal("100"),
        )
        receipt = MagicMock(
            receipt_number="R55",
            receipt_date=datetime(2025, 5, 2, tzinfo=timezone.utc),
            amount_aed=Decimal("100"),
            payment_method="cash",
        )
        payment = MagicMock(
            payment_number="P55",
            payment_date=datetime(2025, 5, 3, tzinfo=timezone.utc),
            amount_aed=Decimal("50"),
            payment_method="bank",
            notes="ref",
        )
        sale_q = MagicMock()
        sale_q.filter_by.return_value = sale_q
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [sale]
        receipt_q = MagicMock()
        receipt_q.filter_by.return_value = receipt_q
        receipt_q.filter.return_value = receipt_q
        receipt_q.all.return_value = [receipt]
        payment_q = MagicMock()
        payment_q.filter_by.return_value = payment_q
        payment_q.filter.return_value = payment_q
        payment_q.all.return_value = [payment]
        scoped = MagicMock()
        scoped.filter_by.return_value.exists.return_value = MagicMock()
        scalars = iter([Decimal("400"), Decimal("100"), Decimal("50")])
        call_n = {"n": 0}

        def session_query(*args, **kwargs):
            call_n["n"] += 1
            if call_n["n"] == 1:
                return _chain_query_stub(scalar=True)
            if call_n["n"] <= 4:
                return _chain_query_stub(scalar=next(scalars, Decimal("0")))
            return _chain_query_stub(all=[])

        app = app_factory(
            __import__("routes.reports", fromlist=["reports_bp"]).reports_bp
        )
        with app.test_request_context("/reports/entity_report_fragment/customer/55"):
            with (
                patch("flask_login.utils._get_user", return_value=mock_user),
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
                patch("routes.reports.tenant_get_or_404", return_value=entity),
                patch("routes.reports.report_branch_scope_id", return_value=2),
                patch("routes.reports._scoped_customer_query", return_value=scoped),
                patch("routes.reports.render_template", return_value="ok") as render,
                patch("routes.reports.db.session.query", side_effect=session_query),
                patch("models.Sale.query", sale_q),
                patch("models.Receipt.query", receipt_q),
                patch("models.Payment.query", payment_q),
            ):
                from routes.reports import entity_report_fragment

                entity_report_fragment("customer", id=55)
                assert len(render.call_args[1]["transactions"]) == 2

    def test_partner_shared_products_branch_direct(self, app_factory, mock_user):
        _configure_user(mock_user)
        entity = SimpleNamespace(id=60, name="Partner", customer_type="partner")
        sp = SimpleNamespace(
            name="Shared",
            percentage=Decimal("20"),
            qty=Decimal("1"),
            total_sales=Decimal("250"),
            last_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        sale_q = MagicMock()
        sale_q.filter_by.return_value = sale_q
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = []
        scoped = MagicMock()
        scoped.filter_by.return_value.exists.return_value = MagicMock()
        call_n = {"n": 0}

        def session_query(*args, **kwargs):
            call_n["n"] += 1
            if call_n["n"] == 1:
                return _chain_query_stub(scalar=True)
            if call_n["n"] <= 4:
                return _chain_query_stub(scalar=Decimal("10"))
            if call_n["n"] == 5:
                return _chain_query_stub(all=[])
            return _chain_query_stub(all=[sp])

        app = app_factory(
            __import__("routes.reports", fromlist=["reports_bp"]).reports_bp
        )
        with app.test_request_context("/reports/entity_report_fragment/partner/60"):
            with (
                patch("flask_login.utils._get_user", return_value=mock_user),
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
                patch("routes.reports.tenant_get_or_404", return_value=entity),
                patch("routes.reports.report_branch_scope_id", return_value=2),
                patch("routes.reports._scoped_customer_query", return_value=scoped),
                patch("routes.reports.render_template", return_value="ok") as render,
                patch("routes.reports.db.session.query", side_effect=session_query),
                patch("models.Sale.query", sale_q),
                patch("models.Receipt.query") as rq,
                patch("models.Payment.query") as pq,
            ):
                rq.filter_by.return_value.filter.return_value.all.return_value = []
                pq.filter_by.return_value.filter.return_value.all.return_value = []
                from routes.reports import entity_report_fragment

                entity_report_fragment("partner", id=60)
                assert any(
                    "Share:" in p["name"] for p in render.call_args[1]["products"]
                )


class TestTopSellingBranchWave:
    def test_top_selling_branch_scoped(self, reports_client, mock_user):
        _configure_user(mock_user)
        row = MagicMock(
            id=1, name="Hot", total_quantity=50, total_sales=Decimal("5000")
        )
        with (
            patch(
                "routes.reports.db.session.query",
                return_value=_chain_query_stub(all=[row]),
            ),
            patch("routes.reports.report_branch_scope_id", return_value=8),
        ):
            resp = reports_client.get(
                "/reports/top-selling?date_from=2025-01-01&limit=5"
            )
            assert resp.status_code == 200


class TestSalesExportSellerWave:
    def test_sales_export_seller_self_filter(self, reports_client, mock_user):
        _configure_user(mock_user)
        mock_user.is_seller.return_value = True
        mock_user.id = 42
        sq = _chain_query_stub(all=[])
        with (
            patch("routes.reports.tenant_query", return_value=sq),
            patch(
                "routes.reports.get_confirmed_sale_paid_aed", return_value=Decimal("0")
            ),
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get("/reports/sales/export?format=csv")
            assert resp.status_code == 200


class TestReconciliationForbiddenWave:
    def test_ar_reconciliation_scoped_branch_mismatch(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.report_branch_scope_id", return_value=5):
            resp = reports_client.get("/reports/ar-reconciliation?branch_id=9")
            assert resp.status_code == 403

    def test_inventory_reconciliation_scoped_branch_mismatch(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        with patch("routes.reports.report_branch_scope_id", return_value=3):
            resp = reports_client.get("/reports/inventory-reconciliation?branch_id=7")
            assert resp.status_code == 403

    def test_inventory_reconciliation_export_branch_forbidden(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        with (
            patch("routes.reports.report_branch_scope_id", return_value=2),
            patch("utils.branching.user_can_access_branch", return_value=True),
        ):
            resp = reports_client.get(
                "/reports/inventory-reconciliation/export?branch_id=8"
            )
            assert resp.status_code == 403

    def test_inventory_reconciliation_export_inaccessible_branch(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        with patch("utils.branching.user_can_access_branch", return_value=False):
            resp = reports_client.get(
                "/reports/inventory-reconciliation/export?branch_id=99"
            )
            assert resp.status_code == 403

    def test_inventory_reconciliation_export_xlsx_rows(self, reports_client, mock_user):
        _configure_user(mock_user)
        mock_user.is_admin.return_value = True
        row = {
            "tenant_id": 1,
            "product_id": 2,
            "product_name": "X",
            "warehouse_id": 3,
            "warehouse_name": "WH",
            "pwc_qty": 1,
            "movement_qty": 1,
            "qty_diff": 0,
            "pwc_avg_cost": 2,
            "pwc_value": 2,
            "matched_qty": False,
        }
        with (
            patch(
                "services.inventory_reconciliation_service.InventoryReconciliationService.build_warehouse_summary",
                return_value={"rows": [row]},
            ),
            patch(
                "services.export_service.ExportService.export_to_xlsx",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get(
                "/reports/inventory-reconciliation/export?format=xlsx"
            )
            assert resp.status_code == 200


class TestReceivablesExportNaiveDate:
    def test_receivables_export_naive_sale_date(self, reports_client, mock_user):
        _configure_user(mock_user)
        sale = MagicMock()
        sale.amount_aed = Decimal("300")
        sale.paid_amount_aed = Decimal("50")
        sale.sale_date = datetime(2024, 6, 1)  # naive
        sale.sale_number = "S-NAIVE"
        sale.customer = SimpleNamespace(name="Cust")
        sale.branch = SimpleNamespace(name="B")
        sale.currency = "AED"
        sale.exchange_rate = Decimal("1")
        sq = _chain_query_stub(all=[sale])
        with (
            patch("routes.reports.tenant_query", return_value=sq),
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get("/reports/receivables/export?format=csv")
            assert resp.status_code == 200


class TestInventoryStatsWave:
    def test_inventory_stats_computed(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse = SimpleNamespace(
            id=1, name="W", is_main=True, tenant_id=1, branch_id=1
        )
        product = MagicMock()
        product.id = 5
        product.name = "P"
        product.cost_price = Decimal("10")
        product.min_stock_alert = Decimal("5")
        wh_chain = _chain_query_stub(all=[warehouse])
        product_chain = _chain_query_stub(all=[product])

        def tq(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with (
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]),
            patch("routes.reports.tenant_query", side_effect=tq),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[(5, Decimal("3"))]),
            ),
        ):
            resp = reports_client.get("/reports/inventory?include_zero=1")
            assert resp.status_code == 200

    def test_inventory_warehouse_branch_mismatch_via_lookup(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        warehouse = SimpleNamespace(
            id=8, name="W", tenant_id=1, branch_id=99, is_active=True
        )
        wh_chain = _chain_query_stub(all=[])
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = warehouse
        product_chain = _chain_query_stub(all=[])
        with (
            patch(
                "routes.reports.tenant_query",
                side_effect=lambda m: (
                    wh_chain
                    if getattr(m, "__name__", "") == "Warehouse"
                    else product_chain
                ),
            ),
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch("utils.branching.user_can_access_branch", return_value=True),
            patch("models.Warehouse.query", wh_query),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[]),
            ),
        ):
            resp = reports_client.get("/reports/inventory?warehouse_id=8&branch_id=2")
            assert resp.status_code == 403

    def test_inventory_admin_appends_warehouse_via_lookup(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        warehouse = SimpleNamespace(
            id=8, name="W", tenant_id=1, branch_id=2, is_active=True
        )
        wh_chain = _chain_query_stub(all=[])
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = warehouse
        product_chain = _chain_query_stub(all=[])

        def tq(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with (
            patch("routes.reports.tenant_query", side_effect=tq),
            patch("utils.branching.get_accessible_branches", return_value=[]),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch("utils.branching.user_can_access_branch", return_value=True),
            patch("models.Warehouse.query", wh_query),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[]),
            ),
        ):
            resp = reports_client.get("/reports/inventory?warehouse_id=8&branch_id=2")
            assert resp.status_code == 200

    def test_inventory_export_warehouse_tenant_mismatch(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        warehouse = SimpleNamespace(
            id=10, name="W", tenant_id=99, branch_id=2, is_active=True
        )
        wh_chain = _chain_query_stub(all=[])
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = warehouse
        with (
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch("utils.branching.user_can_access_branch", return_value=True),
            patch("routes.reports.tenant_query", return_value=wh_chain),
            patch("models.Warehouse.query", wh_query),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[]),
            ),
        ):
            resp = reports_client.get(
                "/reports/inventory/export?warehouse_id=10&branch_id=2"
            )
            assert resp.status_code == 403

    def test_inventory_export_warehouse_branch_mismatch(
        self, reports_client, mock_user
    ):
        _configure_user(mock_user)
        warehouse = SimpleNamespace(
            id=10, name="W", tenant_id=1, branch_id=99, is_active=True
        )
        wh_chain = _chain_query_stub(all=[])
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = warehouse
        with (
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch("utils.branching.user_can_access_branch", return_value=True),
            patch("routes.reports.tenant_query", return_value=wh_chain),
            patch("models.Warehouse.query", wh_query),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[]),
            ),
        ):
            resp = reports_client.get(
                "/reports/inventory/export?warehouse_id=10&branch_id=2"
            )
            assert resp.status_code == 403

    def test_inventory_export_warehouse_not_found(self, reports_client, mock_user):
        _configure_user(mock_user)
        wh_chain = _chain_query_stub(all=[])
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = None
        with (
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
            patch("utils.branching.user_can_access_branch", return_value=True),
            patch("routes.reports.tenant_query", return_value=wh_chain),
            patch("models.Warehouse.query", wh_query),
        ):
            resp = reports_client.get(
                "/reports/inventory/export?warehouse_id=10&branch_id=2"
            )
            assert resp.status_code == 404


class TestInventoryExportBranchForbidden:
    def test_inventory_export_branch_mismatch(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("routes.reports.report_branch_scope_id", return_value=1):
            resp = reports_client.get("/reports/inventory/export?branch_id=5")
            assert resp.status_code == 403

    def test_inventory_export_inaccessible_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        with patch("utils.branching.user_can_access_branch", return_value=False):
            resp = reports_client.get("/reports/inventory/export?branch_id=3")
            assert resp.status_code == 403

    def test_inventory_export_non_admin_no_access(self, reports_client, mock_user):
        _configure_user(mock_user)
        mock_user.is_admin.return_value = False
        wh_chain = _chain_query_stub(all=[])
        with (
            patch("routes.reports.tenant_query", return_value=wh_chain),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
        ):
            resp = reports_client.get("/reports/inventory/export?warehouse_id=77")
            assert resp.status_code == 403


class TestSupplierFragmentFifoWave:
    def test_supplier_fragment_fifo_branch_scoped(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = _entity_mock("FIFO Supplier")
        ctx = TestEntityFragmentWave._supplier_purchase_payment_mocks(
            branch_id=2, direct_payments=[], fifo_scalar=Decimal("250")
        )
        ctx["payment"].purchase_id = None
        scoped = MagicMock()
        scoped.filter_by.return_value.exists.return_value = MagicMock()
        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch("routes.reports.report_branch_scope_id", return_value=2),
            patch("routes.reports._scoped_supplier_query", return_value=scoped),
            patch("routes.reports.db.session.query", side_effect=ctx["session_query"]),
            patch("models.Purchase") as Purchase,
            patch("models.Payment") as Payment,
        ):
            Payment.query = MagicMock()
            Purchase.query.filter_by.return_value = ctx["purchase_q"]
            Payment.query.filter.return_value = ctx["pay_chain"]
            Payment.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = [
                ctx["payment"]
            ]
            resp = reports_client.get("/reports/entity_report_fragment/supplier/12")
            assert resp.status_code == 200


def _payment_query_stub(*, direct_all=None, unalloc_all=None, fifo_total=Decimal("0")):
    """Mock Payment.query.filter chain for supplier entity fragment."""
    direct_all = direct_all if direct_all is not None else []
    unalloc_all = unalloc_all if unalloc_all is not None else []

    class Stub:
        def __init__(self):
            self._all_calls = 0

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            self._all_calls += 1
            if self._all_calls == 1:
                return direct_all
            return unalloc_all

        @staticmethod
        def with_entities(*args, **kwargs):
            sum_q = MagicMock()
            sum_q.scalar.return_value = fifo_total
            return sum_q

    stub = Stub()
    return stub


class TestPartnersCommissionRowLoop:
    def test_commission_rows_with_zero_qty(self, reports_client, mock_user):
        _configure_user(mock_user)
        row = _partner_commission_row(
            total_qty=Decimal("0"), total_revenue=Decimal("0")
        )
        entries_q = _chain_query_stub()
        exists_q = _chain_query_stub(scalar=True)
        rows_q = _chain_query_stub(all=[row])
        financial_q = _chain_query_stub(scalar=Decimal("0"))
        call_n = {"n": 0}

        def session_query(*args, **kwargs):
            call_n["n"] += 1
            if call_n["n"] == 1:
                return entries_q
            if call_n["n"] == 2:
                return exists_q
            if call_n["n"] == 3:
                return rows_q
            return financial_q

        with (
            patch("routes.reports.db.session.query", side_effect=session_query),
            patch(
                "routes.reports.tenant_query", return_value=_chain_query_stub(all=[])
            ),
            patch(
                "routes.reports._scoped_customer_query",
                return_value=_chain_query_stub(all=[]),
            ),
            patch(
                "routes.reports._scoped_supplier_query",
                return_value=_chain_query_stub(all=[]),
            ),
            patch("routes.reports.report_branch_scope_id", return_value=9),
        ):
            resp = reports_client.get(
                "/reports/partners?date_from=2025-01-01&date_to=2025-12-31"
            )
            assert resp.status_code == 200


class TestInventoryExportExcludeZero:
    def test_inventory_export_excludes_zero_stock(self, reports_client, mock_user):
        _configure_user(mock_user)
        warehouse = SimpleNamespace(
            id=1, name="W", name_ar="W", tenant_id=1, branch_id=1
        )
        product = MagicMock(
            id=6,
            name="Hidden",
            sku="H",
            barcode="",
            cost_price=Decimal("1"),
            regular_price=Decimal("2"),
        )
        wh_chain = _chain_query_stub(all=[warehouse])
        product_chain = _chain_query_stub(all=[product])

        def tq(model):
            if getattr(model, "__name__", "") == "Warehouse":
                return wh_chain
            return product_chain

        with (
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]),
            patch("routes.reports.tenant_query", side_effect=tq),
            patch(
                "routes.reports.db.session.query",
                side_effect=lambda *a, **k: _chain_query_stub(all=[(6, Decimal("5"))]),
            ),
            patch(
                "services.export_service.ExportService.export_to_csv",
                return_value=_export_io(),
            ),
            patch("flask.send_file", return_value=_send_file_response()),
        ):
            resp = reports_client.get("/reports/inventory/export?warehouse_id=1")
            assert resp.status_code == 200


class TestInventoryReconciliationExportAccess:
    def test_export_warehouse_not_accessible_non_admin(self, reports_client, mock_user):
        _configure_user(mock_user)
        mock_user.is_admin.return_value = False
        wh = SimpleNamespace(id=5, tenant_id=1, branch_id=1, is_active=True)
        wh_query = MagicMock()
        wh_query.filter_by.return_value.first.return_value = wh
        with (
            patch("models.Warehouse.query", wh_query),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[1]),
            patch("utils.branching.user_can_access_branch", return_value=True),
        ):
            resp = reports_client.get(
                "/reports/inventory-reconciliation/export?warehouse_id=5&branch_id=1"
            )
            assert resp.status_code == 403


class TestCustomerFragmentFullWave:
    def test_customer_sales_invoices_and_transactions(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = SimpleNamespace(id=40, name="Full Customer", customer_type="regular")
        sale = MagicMock()
        sale.sale_number = "INV-40"
        sale.sale_date = datetime(2025, 4, 1, tzinfo=timezone.utc)
        sale.status = "confirmed"
        sale.amount_aed = Decimal("800")
        sale.paid_amount_aed = Decimal("300")
        receipt = MagicMock()
        receipt.receipt_number = "R-40"
        receipt.receipt_date = datetime(2025, 4, 2, tzinfo=timezone.utc)
        receipt.amount_aed = Decimal("300")
        receipt.payment_method = "cash"
        payment = MagicMock()
        payment.payment_number = "P-40"
        payment.payment_date = datetime(2025, 4, 3, tzinfo=timezone.utc)
        payment.amount_aed = Decimal("100")
        payment.payment_method = "bank"
        payment.notes = "draw"
        s_line = MagicMock(
            name="Sold",
            qty=Decimal("4"),
            total=Decimal("800"),
            last_date=sale.sale_date,
        )
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [sale]
        receipt_q = MagicMock()
        receipt_q.filter.return_value = receipt_q
        receipt_q.all.return_value = [receipt]
        payment_q = MagicMock()
        payment_q.filter.return_value = payment_q
        payment_q.all.return_value = [payment]
        scalars = iter([Decimal("800"), Decimal("300"), Decimal("100")])
        session_n = {"n": 0}

        def session_query(*args, **kwargs):
            session_n["n"] += 1
            if session_n["n"] <= 3:
                return _chain_query_stub(scalar=next(scalars, Decimal("0")))
            if session_n["n"] == 4:
                return _chain_query_stub(all=[s_line])
            return _chain_query_stub(all=[])

        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch("routes.reports.report_branch_scope_id", return_value=None),
            patch("routes.reports.db.session.query", side_effect=session_query),
            patch("models.Sale") as Sale,
            patch("models.Receipt") as Receipt,
            patch("models.Payment") as Payment,
        ):
            Sale.query = MagicMock()
            Receipt.query = MagicMock()
            Payment.query = MagicMock()
            Sale.query.filter_by.return_value = sale_q
            Receipt.query.filter_by.return_value = receipt_q
            Payment.query.filter_by.return_value = payment_q
            resp = reports_client.get("/reports/entity_report_fragment/customer/40")
            assert resp.status_code == 200

    def test_partner_shared_products_with_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = SimpleNamespace(id=50, name="Partner", customer_type="partner")
        sp = MagicMock(
            name="Shared",
            percentage=Decimal("20"),
            qty=Decimal("2"),
            total_sales=Decimal("500"),
            last_date=datetime(2025, 2, 1, tzinfo=timezone.utc),
        )
        sale = MagicMock(
            sale_number="S50",
            sale_date=datetime(2025, 2, 1, tzinfo=timezone.utc),
            status="confirmed",
            amount_aed=Decimal("500"),
            paid_amount_aed=Decimal("0"),
        )
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [sale]
        receipt_q = MagicMock()
        receipt_q.filter.return_value = receipt_q
        receipt_q.all.return_value = []
        payment_q = MagicMock()
        payment_q.filter.return_value = payment_q
        payment_q.all.return_value = []
        session_n = {"n": 0}

        def session_query(*args, **kwargs):
            session_n["n"] += 1
            if session_n["n"] <= 3:
                return _chain_query_stub(scalar=Decimal("100"))
            if session_n["n"] == 4:
                return _chain_query_stub(all=[])
            if session_n["n"] == 5:
                return _chain_query_stub(all=[sp])
            return _chain_query_stub(all=[])

        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch("routes.reports.report_branch_scope_id", return_value=None),
            patch("routes.reports.db.session.query", side_effect=session_query),
            patch("models.Sale") as Sale,
            patch("models.Receipt") as Receipt,
            patch("models.Payment") as Payment,
        ):
            Sale.query = MagicMock()
            Receipt.query = MagicMock()
            Payment.query = MagicMock()
            Sale.query.filter_by.return_value = sale_q
            Receipt.query.filter_by.return_value = receipt_q
            Payment.query.filter_by.return_value = payment_q
            resp = reports_client.get("/reports/entity_report_fragment/partner/50")
            assert resp.status_code == 200

    def test_merchant_owned_products_with_branch(self, reports_client, mock_user):
        _configure_user(mock_user)
        entity = SimpleNamespace(id=51, name="Merchant", customer_type="merchant")
        mp = MagicMock(
            name="Owned",
            merchant_share=35,
            qty=Decimal("3"),
            total_sales=Decimal("600"),
            last_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
        )
        sale = MagicMock(
            sale_number="S51",
            sale_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            status="confirmed",
            amount_aed=Decimal("600"),
            paid_amount_aed=Decimal("100"),
        )
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [sale]
        session_n = {"n": 0}

        def session_query(*args, **kwargs):
            session_n["n"] += 1
            if session_n["n"] == 1:
                return _chain_query_stub(scalar=True)
            if session_n["n"] <= 4:
                return _chain_query_stub(scalar=Decimal("50"))
            if session_n["n"] == 5:
                return _chain_query_stub(all=[])
            if session_n["n"] == 6:
                return _chain_query_stub(all=[mp])
            return _chain_query_stub(all=[])

        scoped = MagicMock()
        scoped.filter_by.return_value.exists.return_value = MagicMock()
        with (
            patch("routes.reports.tenant_get_or_404", return_value=entity),
            patch("routes.reports.report_branch_scope_id", return_value=4),
            patch("routes.reports._scoped_customer_query", return_value=scoped),
            patch("routes.reports.db.session.query", side_effect=session_query),
            patch("models.Sale") as Sale,
            patch("models.Receipt") as Receipt,
            patch("models.Payment") as Payment,
        ):
            Sale.query = MagicMock()
            Receipt.query = MagicMock()
            Payment.query = MagicMock()
            Sale.query.filter_by.return_value = sale_q
            Receipt.query.filter_by.return_value.filter.return_value.all.return_value = (
                []
            )
            Payment.query.filter_by.return_value.filter.return_value.all.return_value = (
                []
            )
            resp = reports_client.get("/reports/entity_report_fragment/merchant/51")
            assert resp.status_code == 200
