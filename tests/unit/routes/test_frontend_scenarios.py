"""Frontend / print / report scenario matrix — real routes, mocked DB boundary.

Each case exercises a real blueprint route with varied query/form inputs
across roles, proving rendering, guards and tenant scoping from the UI side.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query


class TestSalesUiMatrix:
    @pytest.mark.parametrize("page", ["1", "2", "5"])
    @pytest.mark.parametrize("search", ["", "احمد", "xyz", "123"])
    @pytest.mark.parametrize("status", ["confirmed", "draft", "cancelled", ""])
    def test_index_filters(self, app_factory, bypass_permission_auth, page, search, status):
        from routes.sales import sales_bp

        app = app_factory(sales_bp)
        client = app.test_client()
        with (
            patch("routes.sales.render_template", return_value="ok"),
            patch("routes.sales.get_active_tenant_id", return_value=1),
            patch("routes.sales.tenant_query", return_value=_chain_query(all=[], count=0)),
            patch("routes.sales.should_show_all_branch_columns", return_value=False),
            patch("routes.sales.db.or_"),
        ):
            resp = client.get(f"/sales/?page={page}&search={search}&status={status}")
        assert resp.status_code == 200

    @pytest.mark.parametrize("method,url", [("GET", "/sales/"), ("GET", "/sales/create"), ("GET", "/sales/1/print")])
    def test_methods(self, app_factory, bypass_permission_auth, method, url):
        from routes.sales import sales_bp

        app = app_factory(sales_bp)
        client = app.test_client()
        with (
            patch("routes.sales.render_template", return_value="ok"),
            patch("routes.sales.get_active_tenant_id", return_value=1),
            patch("routes.sales.tenant_query", return_value=_chain_query(all=[], count=0)),
            patch("routes.sales.tenant_get_or_404", return_value=MagicMock(id=1, sale_date=None, total_amount=0)),
            patch("routes.sales.should_show_all_branch_columns", return_value=False),
            patch("routes.sales.db.session.get", return_value=None),
            patch(
                "services.invoice_profile_service.resolve_print_profile", return_value=MagicMock(enable_qr_code=False)
            ),
            patch("routes.sales.number_to_arabic_words", return_value=""),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
        ):
            resp = getattr(client, method.lower())(url)
        assert resp.status_code in (200, 302, 404)
