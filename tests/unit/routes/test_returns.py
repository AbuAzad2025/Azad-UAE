from __future__ import annotations

from contextlib import ExitStack, contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


def _mock_return(**kwargs):
    pr = MagicMock()
    pr.id = kwargs.get("id", 1)
    pr.return_number = kwargs.get("return_number", "RET-001")
    pr.sale_id = kwargs.get("sale_id", 10)
    pr.refund_amount = kwargs.get("refund_amount", Decimal("50"))
    pr.amount_aed = kwargs.get("amount_aed", Decimal("50"))
    pr.tenant_id = kwargs.get("tenant_id", 1)
    return pr


def _mock_pagination(items, total=None):
    pag = MagicMock()
    pag.items = items
    pag.page = 1
    pag.per_page = 20
    pag.total = total if total is not None else len(items)
    pag.pages = 1
    return pag


@contextmanager
def _returns_patches(**kwargs):
    returns_q = kwargs.get("returns_q", _chain_query(all=[_mock_return()]))
    with ExitStack() as stack:
        stack.enter_context(patch("routes.returns.render_template", return_value="ok"))
        stack.enter_context(
            patch("services.return_service.get_active_tenant_id", return_value=kwargs.get("tenant_id", 1))
        )
        stack.enter_context(
            patch("services.return_service.is_platform_owner", return_value=kwargs.get("is_platform_owner", False))
        )
        stack.enter_context(patch("routes.returns.branch_scope_id", return_value=kwargs.get("branch_scope")))
        stack.enter_context(patch("routes.returns.should_show_all_branch_columns", return_value=False))
        stack.enter_context(patch("routes.returns.ProductReturn.query", returns_q))
        stack.enter_context(patch("routes.returns.LoggingCore.log_audit"))
        stack.enter_context(patch("extensions.limiter.limit", return_value=lambda f: f))
        yield


@pytest.fixture
def returns_client(app_factory, bypass_permission_auth):
    from routes.returns import returns_bp

    app = app_factory(returns_bp)
    return app.test_client()


class TestReturnsAuth:
    def test_index_requires_login(self, returns_client):
        with _returns_patches(), unauthenticated_client(returns_client):
            resp = returns_client.get("/returns/")
        assert resp.status_code == 401

    def test_search_sales_requires_login(self, returns_client):
        with _returns_patches(), unauthenticated_client(returns_client):
            resp = returns_client.get("/returns/api/search_sales?q=test")
        assert resp.status_code == 401

    def test_get_sale_lines_requires_login(self, returns_client):
        with _returns_patches(), unauthenticated_client(returns_client):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=1")
        assert resp.status_code == 401


class TestReturnsIndex:
    def test_index_renders(self, returns_client):
        with _returns_patches():
            resp = returns_client.get("/returns/")
        assert resp.status_code == 200

    def test_view_found(self, returns_client):
        pr = _mock_return()
        with _returns_patches(), patch("routes.returns._scoped_returns_query") as scoped:
            scoped.return_value.filter.return_value.first.return_value = pr
            resp = returns_client.get("/returns/view/1")
        assert resp.status_code == 200

    def test_view_not_found(self, returns_client):
        with _returns_patches(), patch("routes.returns._scoped_returns_query") as scoped:
            scoped.return_value.filter.return_value.first.return_value = None
            resp = returns_client.get("/returns/view/999")
        assert resp.status_code == 404


class TestReturnsApiCreate:
    def test_create_missing_body(self, returns_client):
        with _returns_patches():
            resp = returns_client.post("/returns/api/create", json=None)
        assert resp.status_code == 400

    def test_create_missing_sale_or_lines(self, returns_client):
        with _returns_patches():
            resp = returns_client.post("/returns/api/create", json={"sale_id": 1})
        assert resp.status_code == 400

    def test_create_success(self, returns_client):
        result = _mock_return(id=5, return_number="RET-005")
        with _returns_patches(), patch("utils.tenanting.tenant_get_or_404"), patch(
            "routes.returns.ReturnService.create_return", return_value=result
        ):
            resp = returns_client.post(
                "/returns/api/create",
                json={"sale_id": 10, "lines": [{"sale_line_id": 1, "quantity": 1}]},
            )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["data"]["return_number"] == "RET-005"

    def test_create_value_error(self, returns_client):
        with _returns_patches(), patch("utils.tenanting.tenant_get_or_404"), patch(
            "routes.returns.ReturnService.create_return", side_effect=ValueError("bad")
        ):
            resp = returns_client.post(
                "/returns/api/create",
                json={"sale_id": 10, "lines": [{"sale_line_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 400

    def test_create_server_error(self, returns_client):
        with _returns_patches(), patch("utils.tenanting.tenant_get_or_404"), patch(
            "routes.returns.ReturnService.create_return", side_effect=RuntimeError("db")
        ):
            resp = returns_client.post(
                "/returns/api/create",
                json={"sale_id": 10, "lines": [{"sale_line_id": 1, "quantity": 1}]},
            )
        assert resp.status_code == 500


class TestReturnsSearchSales:
    def test_search_sales_no_query_returns_empty(self, returns_client):
        with _returns_patches():
            resp = returns_client.get("/returns/api/search_sales")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"] == []

    def test_search_sales_empty_q_string(self, returns_client):
        with _returns_patches():
            resp = returns_client.get("/returns/api/search_sales?q=")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == []

    def test_search_sales_with_query_returns_paginated(self, returns_client):
        items = [
            {"id": 1, "text": "S-001 — Cust — 100 AED", "sale_number": "S-001"},
            {"id": 2, "text": "S-002 — Cust2 — 200 AED", "sale_number": "S-002"},
        ]
        pagination = _mock_pagination(items, total=2)
        with _returns_patches(), patch(
            "routes.returns.ReturnService.search_sales_for_return", return_value=(items, pagination)
        ) as mocked:
            resp = returns_client.get("/returns/api/search_sales?q=S-00&page=1")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        mocked.assert_called_once()
        # q, page, per_page, user
        assert mocked.call_args[0][0] == "S-00"

    def test_search_sales_strips_whitespace(self, returns_client):
        items = [{"id": 1, "text": "S-1"}]
        pagination = _mock_pagination(items)
        with _returns_patches(), patch(
            "routes.returns.ReturnService.search_sales_for_return", return_value=(items, pagination)
        ):
            resp = returns_client.get("/returns/api/search_sales?q=  test  ")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True

    def test_search_sales_with_whitespace_only_returns_empty(self, returns_client):
        with _returns_patches(), patch(
            "routes.returns.ReturnService.search_sales_for_return"
        ) as mocked:
            resp = returns_client.get("/returns/api/search_sales?q=   ")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == []
        mocked.assert_not_called()


class TestReturnsGetSaleLines:
    def _make_sale(self, lines_data):
        sale = MagicMock()
        sale.id = 100
        sale.tenant_id = 1
        sale.lines = []
        sale.returns = []
        for ld in lines_data:
            line = MagicMock()
            line.id = ld["id"]
            line.quantity = ld["quantity"]
            line.unit_price = ld.get("unit_price", Decimal("10"))
            line.variant_name = ld.get("variant_name", "")
            product = MagicMock()
            product.name = ld.get("product_name", "Product")
            line.product = product if ld.get("has_product", True) else None
            sale.lines.append(line)
        return sale

    def test_missing_sale_id_returns_400(self, returns_client):
        with _returns_patches():
            resp = returns_client.get("/returns/api/get_sale_lines")
        assert resp.status_code == 400
        assert "Missing sale_id" in resp.get_json()["message"]

    def test_sale_lines_success_with_available_qty(self, returns_client):
        sale = self._make_sale(
            [
                {"id": 1, "quantity": 5, "unit_price": Decimal("20"), "product_name": "Widget"},
                {"id": 2, "quantity": 3, "unit_price": Decimal("15"), "product_name": "Gadget"},
            ]
        )
        with _returns_patches(), patch("routes.returns.tenant_get_or_404", return_value=sale):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=100")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        lines = body["data"]["lines"]
        assert len(lines) == 2
        assert lines[0]["available_qty"] == 5
        assert lines[0]["product_name"] == "Widget"

    def test_sale_lines_filters_fully_returned(self, returns_client):
        # Sale line with 2 sold, but 2 already returned (approved) => available 0 filtered out
        sale = self._make_sale([{"id": 1, "quantity": 2, "unit_price": Decimal("10")}])
        ret_line = MagicMock()
        ret_line.quantity = 2
        ret_line.line_id = 1
        ret = MagicMock()
        ret.status = "approved"
        ret.lines = [ret_line]
        sale.returns = [ret]
        with _returns_patches(), patch("routes.returns.tenant_get_or_404", return_value=sale):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=100")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["lines"] == []

    def test_sale_lines_partial_return_reduces_available(self, returns_client):
        sale = self._make_sale([{"id": 10, "quantity": 10, "unit_price": Decimal("5")}])
        ret_line = MagicMock()
        ret_line.quantity = 4
        ret_line.line_id = 10
        ret = MagicMock()
        ret.status = "approved"
        ret.lines = [ret_line]
        sale.returns = [ret]
        with _returns_patches(), patch("routes.returns.tenant_get_or_404", return_value=sale):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=100")
        assert resp.status_code == 200
        lines = resp.get_json()["data"]["lines"]
        assert len(lines) == 1
        assert lines[0]["available_qty"] == 6

    def test_sale_lines_ignores_rejected_returns(self, returns_client):
        sale = self._make_sale([{"id": 5, "quantity": 3}])
        ret_line = MagicMock()
        ret_line.quantity = 3
        ret_line.line_id = 5
        ret = MagicMock()
        ret.status = "rejected"
        ret.lines = [ret_line]
        sale.returns = [ret]
        with _returns_patches(), patch("routes.returns.tenant_get_or_404", return_value=sale):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=100")
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]["lines"]) == 1
        assert resp.get_json()["data"]["lines"][0]["available_qty"] == 3

    def test_sale_lines_product_none_fallback(self, returns_client):
        sale = self._make_sale(
            [{"id": 7, "quantity": 1, "has_product": False, "variant_name": "Red"}]
        )
        # product is None => line.product fallback to "—"
        sale.lines[0].product = None
        with _returns_patches(), patch("routes.returns.tenant_get_or_404", return_value=sale):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=100")
        assert resp.status_code == 200
        lines = resp.get_json()["data"]["lines"]
        assert lines[0]["product_name"] == "—"
        assert lines[0]["variant"] == "Red"

    def test_sale_lines_variant_none(self, returns_client):
        sale = self._make_sale([{"id": 8, "quantity": 2, "variant_name": None}])
        sale.lines[0].variant_name = None
        with _returns_patches(), patch("routes.returns.tenant_get_or_404", return_value=sale):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=100")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["lines"][0]["variant"] == ""

    def test_sale_lines_unit_price_none(self, returns_client):
        sale = self._make_sale([{"id": 9, "quantity": 1}])
        sale.lines[0].unit_price = None
        with _returns_patches(), patch("routes.returns.tenant_get_or_404", return_value=sale):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=100")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["lines"][0]["unit_price"] == 0.0

    def test_sale_lines_quantity_none_treated_as_zero_and_filtered(self, returns_client):
        sale = self._make_sale([{"id": 11, "quantity": None}])
        sale.lines[0].quantity = None
        with _returns_patches(), patch("routes.returns.tenant_get_or_404", return_value=sale):
            resp = returns_client.get("/returns/api/get_sale_lines?sale_id=100")
        assert resp.status_code == 200
        # available = (0) - 0 = 0 => filtered out
        assert resp.get_json()["data"]["lines"] == []
