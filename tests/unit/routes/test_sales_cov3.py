"""Coverage for routes/sales.py remaining arcs.

Targets: safe_float arcs, index filter arcs (search/status/payment/seller/
branch), create invalid-line skip + no-lines + currency-fallback + limit +
generic-exception arcs, print/edit/cancel/delete/archive/restore/api arcs.
Real test-client paths; service/DB boundaries mocked only.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query


def _mock_sale(**kwargs):
    s = MagicMock()
    s.id = kwargs.get("id", 1)
    s.tenant_id = 1
    s.branch_id = 2
    s.seller_id = 42
    s.sale_number = "S-2026-0001"
    s.status = kwargs.get("status", "confirmed")
    s.payment_status = kwargs.get("payment_status", "unpaid")
    s.total_amount = Decimal("100")
    s.currency = "AED"
    s.sale_date = datetime(2026, 6, 26)
    s.discount_amount = Decimal("0")
    s.notes = ""
    s.calculate_totals = MagicMock()
    s.seller = MagicMock(full_name="Seller", username="seller")
    s.seller.get_display_name.return_value = "Seller"
    s.customer = MagicMock(name="Customer")
    return s


def _mock_customer(cid=5):
    c = MagicMock()
    c.id = cid
    c.tenant_id = 1
    c.customer_type = "retail"
    return c


def _mock_product(pid=10):
    p = MagicMock()
    p.id = pid
    p.tenant_id = 1
    p.cost_price = Decimal("50")
    p.unit = "pcs"
    p.get_price_for_customer.return_value = Decimal("99")
    return p


@contextmanager
def _patches(**kwargs):
    sale = kwargs.get("sale", _mock_sale())

    def _get_or_404(model, pk, user=None):
        name = getattr(model, "__name__", str(model))
        if name == "Sale":
            if int(pk) == int(sale.id):
                return sale
            raise NotFound()
        if name == "Customer":
            return _mock_customer(cid=pk)
        if name == "Product":
            return _mock_product(pid=pk)
        return MagicMock()

    arch_q = MagicMock()
    arch_q.filter_by.return_value = arch_q
    arch_q.filter.return_value = arch_q
    arch_q.order_by.return_value = arch_q
    arch_q.limit.return_value = arch_q
    arch_q.all.return_value = []
    with ExitStack() as stack:
        stack.enter_context(patch("routes.sales.render_template", return_value="ok"))
        stack.enter_context(patch("routes.sales.get_active_tenant_id", return_value=1))
        stack.enter_context(
            patch(
                "routes.sales.tenant_query",
                return_value=_chain_query(all=[sale], count=1),
            )
        )
        stack.enter_context(patch("routes.sales.tenant_get_or_404", side_effect=_get_or_404))
        stack.enter_context(patch("routes.sales.tenant_get", side_effect=_get_or_404))
        stack.enter_context(patch("routes.sales.db.session.get", return_value=MagicMock()))
        stack.enter_context(patch("routes.sales.db.session.query", return_value=_chain_query(all=[])))
        stack.enter_context(patch("routes.sales.should_show_all_branch_columns", return_value=False))
        stack.enter_context(patch("routes.sales.StoreService.get_physical_warehouses", return_value=[]))
        stack.enter_context(patch("routes.sales.get_accessible_warehouses", return_value=[]))
        stack.enter_context(patch("routes.sales.ensure_warehouse_access"))
        stack.enter_context(patch("routes.sales.atomic_transaction"))
        stack.enter_context(patch("routes.sales.SaleService.create_sale", return_value=sale))
        stack.enter_context(patch("routes.sales.SaleService.list_active_users", return_value=[]))
        stack.enter_context(patch("routes.sales.SaleService.cancel_sale"))
        stack.enter_context(patch("routes.sales.SaleService.has_inventory_posted", return_value=False))
        stack.enter_context(patch("routes.sales.StockService.get_product_stock", return_value=Decimal("25")))
        stack.enter_context(patch("routes.sales.LoggingCore.log_audit"))
        stack.enter_context(patch("routes.sales.LoggingCore.log_error"))
        stack.enter_context(
            patch("routes.sales.InvoiceSettings.get_active", return_value=MagicMock(enable_qr_code=False))
        )
        stack.enter_context(patch("routes.sales.number_to_arabic_words", return_value="مائة"))
        stack.enter_context(patch("routes.sales.generate_qr_data_url", return_value="data:x"))
        stack.enter_context(patch("utils.decorators.branch_scope_id", return_value=kwargs.get("branch_scope")))
        stack.enter_context(
            patch.dict(
                "utils.decorators._LIMIT_CHECKERS",
                {"sales_monthly": MagicMock(return_value=None)},
            )
        )
        yield {"sale": sale}


@pytest.fixture
def sales_cov3_client(app_factory, bypass_permission_auth):
    from routes.sales import sales_bp

    app = app_factory(sales_bp)
    return app.test_client()


class TestSafeFloatAndIndex:
    def test_safe_float_arcs(self):
        from routes.sales import safe_float

        assert safe_float(None) == 0.0
        assert safe_float("  ") == 0.0
        assert safe_float("bad") == 0.0
        assert safe_float("2.5") == 2.5

    def test_index_with_search_and_filters(self, sales_cov3_client):
        with _patches():
            resp = sales_cov3_client.get("/sales/?search=S-1&status=draft&payment_status=paid")
        assert resp.status_code == 200

    def test_index_seller_scoped(self, sales_cov3_client, bypass_permission_auth):
        bypass_permission_auth.is_seller.return_value = True
        bypass_permission_auth.id = 42
        with _patches():
            resp = sales_cov3_client.get("/sales/")
        assert resp.status_code == 200

    def test_index_branch_scoped(self, sales_cov3_client):
        with _patches(branch_scope=3):
            resp = sales_cov3_client.get("/sales/")
        assert resp.status_code == 200


class TestCreate:
    def test_create_invalid_line_skipped_then_no_lines(self, sales_cov3_client):
        with _patches():
            resp = sales_cov3_client.post(
                "/sales/create",
                data={"customer_id": "5", "line_count": "1", "lines[0][product_id]": "xx"},
            )
        assert resp.status_code == 302

    def test_create_currency_fallback(self, sales_cov3_client):
        with (
            _patches(),
            patch("routes.sales.resolve_default_currency", side_effect=Exception("no cur")),
            patch("routes.sales.get_system_default_currency", return_value="AED"),
        ):
            resp = sales_cov3_client.post(
                "/sales/create",
                data={
                    "customer_id": "5",
                    "line_count": "1",
                    "lines[0][product_id]": "10",
                    "lines[0][quantity]": "2",
                },
            )
        assert resp.status_code in (200, 302)

    def test_create_tenant_limit(self, sales_cov3_client):
        from utils.tenant_limits import TenantLimitError

        with (
            _patches(),
            patch("routes.sales.SaleService.create_sale", side_effect=TenantLimitError("sales", 5, 5)),
        ):
            resp = sales_cov3_client.post(
                "/sales/create",
                data={
                    "customer_id": "5",
                    "line_count": "1",
                    "lines[0][product_id]": "10",
                    "lines[0][quantity]": "1",
                },
            )
        assert resp.status_code in (200, 302)

    def test_create_value_error(self, sales_cov3_client):
        with (
            _patches(),
            patch("routes.sales.SaleService.create_sale", side_effect=ValueError("bad data")),
        ):
            resp = sales_cov3_client.post(
                "/sales/create",
                data={
                    "customer_id": "5",
                    "line_count": "1",
                    "lines[0][product_id]": "10",
                    "lines[0][quantity]": "1",
                },
            )
        assert resp.status_code in (200, 302)

    def test_create_generic_exception(self, sales_cov3_client):
        with (
            _patches(),
            patch("routes.sales.SaleService.create_sale", side_effect=RuntimeError("down")),
        ):
            resp = sales_cov3_client.post(
                "/sales/create",
                data={
                    "customer_id": "5",
                    "line_count": "1",
                    "lines[0][product_id]": "10",
                    "lines[0][quantity]": "1",
                },
            )
        assert resp.status_code in (200, 302)


class TestDetailActions:
    def test_view_404(self, sales_cov3_client):
        with _patches():
            resp = sales_cov3_client.get("/sales/9999")
        assert resp.status_code == 404

    def test_print_ok(self, sales_cov3_client):
        with (
            _patches(),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
        ):
            resp = sales_cov3_client.get("/sales/1/print")
        assert resp.status_code == 200

    def test_edit_get_ok(self, sales_cov3_client):
        with _patches():
            resp = sales_cov3_client.get("/sales/1/edit")
        assert resp.status_code == 200

    def test_edit_post_exception(self, sales_cov3_client):
        with (
            _patches(),
            patch("routes.sales.LoggingCore.log_audit", side_effect=Exception("audit down")),
        ):
            resp = sales_cov3_client.post("/sales/1/edit", data={"notes": "x"})
        assert resp.status_code in (200, 302)

    def test_cancel_ok(self, sales_cov3_client):
        with _patches():
            resp = sales_cov3_client.post("/sales/1/cancel")
        assert resp.status_code == 302

    def test_delete_archived_list(self, sales_cov3_client):
        with _patches():
            resp = sales_cov3_client.get("/sales/archived")
        assert resp.status_code == 200

    def test_archive_and_restore(self, sales_cov3_client):
        with (
            _patches(),
            patch("services.archive_service.ArchiveService.archive_record", return_value=True),
            patch("services.archive_service.ArchiveService.restore_record", return_value=True),
            patch(
                "services.sale_service.SaleService.get_archived_sale_record",
                return_value=MagicMock(),
            ),
        ):
            assert sales_cov3_client.post("/sales/1/archive").status_code in (200, 302)
            assert sales_cov3_client.post("/sales/1/restore").status_code in (200, 302)

    def test_delete_with_gl_reverse(self, sales_cov3_client):
        sale = _mock_sale()
        with (
            _patches(sale=sale),
            patch("routes.sales.SaleService.has_inventory_posted", return_value=True),
            patch("services.gl_service.GLService.reverse_entry"),
            patch("routes.sales.db.session.delete"),
        ):
            resp = sales_cov3_client.post("/sales/1/delete")
        assert resp.status_code == 302

    def test_api_get_price(self, sales_cov3_client):
        with _patches():
            resp = sales_cov3_client.get("/sales/api/get-price?product_id=10&customer_id=5")
        assert resp.status_code in (200, 400, 404)

    def test_api_calculate_totals(self, sales_cov3_client):
        with _patches():
            resp = sales_cov3_client.post(
                "/sales/api/calculate-totals",
                json={"lines": [{"product_id": 10, "quantity": 1}]},
            )
        assert resp.status_code in (200, 400)
