"""Coverage-99 boost for routes/customers.py.

Covers: branch-scoped query (44-57), in-scope service (64), scoped
balance (72), branch columns (113-116), export filters (136-155),
create fallbacks (221-231, 254-258), 403 paths (270, 295, 345, 414,
491, 525), edit fallback/exception (310-333), delete fallback
(373-391), print delegation (401-404), api_search empty (465),
balance fallback (494-495), sales loop (532-530).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def cust_client(app_factory, bypass_permission_auth):
    from routes.customers import customers_bp

    app = app_factory(customers_bp)
    return app.test_client()


def _customer():
    c = MagicMock()
    c.id = 5
    c.name = "Acme"
    c.name_ar = None
    c.customer_type = "retail"
    c.customer_classification = None
    c.phone = "0501"
    c.email = "a@b.c"
    c.preferred_currency = "AED"
    c.balance = 10
    c.created_at = None
    c.tenant_id = 1
    return c


class TestBranchScopeHelpers:
    def test_scoped_query_with_branch(self, cust_client):
        q = MagicMock()
        q.filter.return_value = q
        with (
            patch("routes.customers.tenant_query", return_value=q),
            patch("routes.customers.branch_scope_id", return_value=3),
        ):
            from routes.customers import _scoped_customer_query

            out = _scoped_customer_query()
        assert out is q

    def test_in_scope_service_call(self, cust_client):
        with (
            patch("routes.customers.branch_scope_id", return_value=3),
            patch(
                "services.customer_service.CustomerService.customer_id_in_branch_scope",
                return_value=True,
            ) as m,
        ):
            from routes.customers import _customer_in_scope

            assert _customer_in_scope(9) is True
            m.assert_called_once_with(9, 3)

    def test_scoped_balance(self, cust_client):
        with (
            patch("routes.customers.branch_scope_id", return_value=3),
            patch(
                "services.payment_service.PaymentService.get_customer_balance_scoped",
                return_value=Decimal("7"),
            ),
        ):
            from routes.customers import _get_customer_balance

            assert _get_customer_balance(9) == Decimal("7")


class TestIndexBranchColumns:
    def _get_index(self, client, show_columns):
        pagination = MagicMock()
        pagination.items = [_customer()]
        q = MagicMock()
        q.filter.return_value = q
        q.filter_by.return_value = q
        q.order_by.return_value.paginate.return_value = pagination
        with (
            patch("routes.customers._scoped_customer_query", return_value=q),
            patch("routes.customers.get_active_tenant_id", return_value=1),
            patch(
                "routes.customers.should_show_all_branch_columns",
                return_value=show_columns,
            ),
            patch(
                "services.customer_service.CustomerService.attach_branch_labels",
                return_value=None,
            ) as m,
            patch("routes.customers.render_template", return_value="ok"),
        ):
            resp = client.get("/customers/?search=x&type=retail")
        return resp, m

    def test_index_with_branch_columns(self, cust_client):
        resp, m = self._get_index(cust_client, True)
        assert resp.status_code == 200
        m.assert_called_once()

    def test_index_without_branch_columns(self, cust_client):
        resp, m = self._get_index(cust_client, False)
        assert resp.status_code == 200
        m.assert_not_called()


class TestExport:
    def _get(self, client, qs=""):
        c = _customer()
        q = MagicMock()
        q.filter.return_value = q
        q.filter_by.return_value = q
        q.order_by.return_value.all.return_value = [c]
        with (
            patch("routes.customers._scoped_customer_query", return_value=q),
            patch("routes.customers.get_active_tenant_id", return_value=1),
            patch("routes.customers.branch_scope_id", return_value=4),
            patch(
                "services.customer_service.CustomerService.branch_balance_map",
                return_value={5: Decimal("3")},
            ),
            patch("routes.customers.render_template", return_value="ok"),
        ):
            return client.get(f"/customers/export?format=csv{qs}")

    def test_export_csv_scoped(self, cust_client):
        assert self._get(cust_client, "&search=ac&type=retail").status_code == 200

    def test_export_xlsx(self, cust_client):
        c = _customer()
        q = MagicMock()
        q.filter.return_value = q
        q.filter_by.return_value = q
        q.order_by.return_value.all.return_value = [c]
        with (
            patch("routes.customers._scoped_customer_query", return_value=q),
            patch("routes.customers.get_active_tenant_id", return_value=None),
            patch("routes.customers.branch_scope_id", return_value=None),
            patch("routes.customers.render_template", return_value="ok"),
        ):
            resp = cust_client.get("/customers/export?format=xlsx")
        assert resp.status_code == 200


class TestCreateFallbacks:
    def test_create_currency_fallback(self, cust_client):
        with (
            patch("forms.customer.CustomerForm") as form_cls,
            patch("routes.customers.resolve_default_currency", side_effect=RuntimeError("no fx")),
            patch("routes.customers.get_system_default_currency", return_value="AED") as g,
            patch(
                "services.customer_service.CustomerService.create_customer",
                side_effect=RuntimeError("db down"),
            ),
            patch("routes.customers.render_template", return_value="form"),
        ):
            form = MagicMock()
            form.validate_on_submit.return_value = True
            form.name.data = "X"
            form.name_ar.data = ""
            form.customer_type.data = "retail"
            form.phone.data = ""
            form.email.data = ""
            form.address.data = ""
            form.tax_number.data = ""
            form.preferred_currency.data = ""
            form.is_active.data = True
            form.notes.data = ""
            form_cls.return_value = form
            resp = cust_client.post("/customers/create", data={"name": "X"})
        assert resp.status_code == 200
        g.assert_called_once()

    def test_create_limit_error(self, cust_client):
        from utils.tenant_limits import TenantLimitError

        with (
            patch("forms.customer.CustomerForm") as form_cls,
            patch("routes.customers.resolve_default_currency", return_value="AED"),
            patch(
                "utils.tenant_limits.check_customers_limit",
                side_effect=TenantLimitError("customers", 5, 5),
            ),
        ):
            form = MagicMock()
            form.validate_on_submit.return_value = True
            form_cls.return_value = form
            resp = cust_client.post("/customers/create", data={"name": "X"})
        assert resp.status_code in (302, 303)

    def test_create_generic_exception(self, cust_client):
        with (
            patch("forms.customer.CustomerForm") as form_cls,
            patch("routes.customers.resolve_default_currency", return_value="AED"),
            patch("utils.tenant_limits.check_customers_limit", return_value=None),
            patch(
                "services.customer_service.CustomerService.create_customer",
                side_effect=RuntimeError("db down"),
            ),
            patch("routes.customers.render_template", return_value="form") as rt,
        ):
            form = MagicMock()
            form.validate_on_submit.return_value = True
            form.name.data = "X"
            form.name_ar.data = ""
            form.customer_type.data = "retail"
            form.phone.data = ""
            form.email.data = ""
            form.address.data = ""
            form.tax_number.data = ""
            form.preferred_currency.data = ""
            form.is_active.data = True
            form.notes.data = ""
            form_cls.return_value = form
            resp = cust_client.post("/customers/create", data={"name": "X"})
        assert resp.status_code == 200
        assert rt.called


class TestForbiddenPaths:
    def _denied(self, client, url):
        with (
            patch("routes.customers.tenant_get_or_404", return_value=_customer()),
            patch("routes.customers._customer_in_scope", return_value=False),
            patch("routes.customers.render_template", return_value="denied"),
        ):
            return client.get(url)

    def test_view_403(self, cust_client):
        assert self._denied(cust_client, "/customers/5").status_code == 403

    def test_edit_403(self, cust_client):
        assert self._denied(cust_client, "/customers/5/edit").status_code == 403

    def test_delete_403(self, cust_client):
        with (
            patch("routes.customers.tenant_get_or_404", return_value=_customer()),
            patch("routes.customers._customer_in_scope", return_value=False),
            patch("routes.customers.render_template", return_value="denied"),
        ):
            assert cust_client.post("/customers/5/delete").status_code == 403

    def test_statement_403(self, cust_client):
        assert self._denied(cust_client, "/customers/5/statement").status_code == 403

    def test_balance_403(self, cust_client):
        with (
            patch("routes.customers.tenant_get_or_404", return_value=_customer()),
            patch("routes.customers._customer_in_scope", return_value=False),
        ):
            assert cust_client.get("/customers/5/balance").status_code == 403

    def test_sales_403(self, cust_client):
        assert self._denied(cust_client, "/customers/5/sales").status_code == 403


class TestEditFallbackAndException:
    def _post(self, client, currency_side_effect=None, service_side_effect=None):
        with (
            patch("routes.customers.tenant_get_or_404", return_value=_customer()),
            patch("routes.customers._customer_in_scope", return_value=True),
            patch("routes.customers.resolve_default_currency", side_effect=currency_side_effect),
            patch("routes.customers.get_system_default_currency", return_value="AED"),
            patch("routes.customers.render_template", return_value="form") as rt,
        ):
            if service_side_effect is not None:
                with patch(
                    "utils.field_validators.normalize_phone_optional",
                    side_effect=service_side_effect,
                ):
                    resp = client.post("/customers/5/edit", data={"name": "Y"})
            else:
                resp = client.post("/customers/5/edit", data={"name": "Y"})
        return resp, rt

    def test_edit_currency_fallback(self, cust_client):
        resp, _ = self._post(cust_client, currency_side_effect=RuntimeError("no fx"))
        assert resp.status_code in (200, 302, 303)

    def test_edit_exception(self, cust_client):
        resp, rt = self._post(cust_client, service_side_effect=RuntimeError("bad phone"))
        assert resp.status_code == 200
        assert rt.called


class TestDeleteFallback:
    def test_delete_exception_soft_delete(self, cust_client):
        from services.customer_service import CustomerService

        cust = _customer()
        with (
            patch("routes.customers.tenant_get_or_404", return_value=cust),
            patch("routes.customers._customer_in_scope", return_value=True),
            patch("routes.customers.get_active_tenant_id", return_value=1),
            patch.object(CustomerService, "relation_counts", side_effect=RuntimeError("db gone")),
            patch.object(CustomerService, "get_tenant_customer", return_value=cust),
            patch("routes.customers.db.session"),
        ):
            resp = cust_client.post("/customers/5/delete")
        assert resp.status_code in (302, 303)

    def test_delete_exception_no_customer(self, cust_client):
        from services.customer_service import CustomerService

        with (
            patch("routes.customers.tenant_get_or_404", return_value=_customer()),
            patch("routes.customers._customer_in_scope", return_value=True),
            patch("routes.customers.get_active_tenant_id", return_value=1),
            patch.object(CustomerService, "relation_counts", side_effect=RuntimeError("db gone")),
            patch.object(CustomerService, "get_tenant_customer", return_value=None),
            patch("routes.customers.db.session"),
            patch("routes.customers.render_template", return_value="ok"),
        ):
            resp = cust_client.post("/customers/5/delete")
        assert resp.status_code in (302, 303)

    def test_delete_fallback_inner_failure(self, cust_client):
        from services.customer_service import CustomerService

        with (
            patch("routes.customers.tenant_get_or_404", return_value=_customer()),
            patch("routes.customers._customer_in_scope", return_value=True),
            patch("routes.customers.get_active_tenant_id", return_value=1),
            patch.object(CustomerService, "relation_counts", side_effect=RuntimeError("db gone")),
            patch.object(CustomerService, "get_tenant_customer", side_effect=RuntimeError("gone")),
        ):
            resp = cust_client.post("/customers/5/delete")
        assert resp.status_code in (302, 303)


class TestPrintDelegation:
    def test_print_statement_delegates(self, cust_client):
        with patch("routes.printing.print_customer_statement", return_value="printed") as m:
            resp = cust_client.get("/customers/5/statement/print")
        assert resp.status_code == 200
        m.assert_called_once_with(5)


class TestApiSearchAndBalance:
    def test_api_search_empty_query(self, cust_client):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.limit.return_value.all.return_value = []
        with (
            patch("routes.customers._scoped_customer_query", return_value=q),
            patch("routes.customers._get_customer_balance", return_value=0),
        ):
            resp = cust_client.get("/customers/api/search")
        assert resp.status_code == 200

    def test_balance_currency_fallback(self, cust_client):
        sale = MagicMock()
        sale.id = 1
        sale.sale_number = "S1"
        sale.sale_date = MagicMock()
        sale.sale_date.strftime.return_value = "2024-01-01"
        sale.total_amount = 100
        sale.balance_due = 20
        sale.currency = None
        with (
            patch("routes.customers.tenant_get_or_404", return_value=_customer()),
            patch("routes.customers._customer_in_scope", return_value=True),
            patch("routes.customers.resolve_default_currency", side_effect=RuntimeError("x")),
            patch("routes.customers.get_system_default_currency", return_value="AED"),
            patch("routes.customers._get_customer_balance", return_value=Decimal("5")),
            patch("routes.customers._get_unpaid_sales", return_value=[sale]),
        ):
            resp = cust_client.get("/customers/5/balance")
        assert resp.status_code == 200

    def test_sales_with_positive_balance(self, cust_client):
        sale = MagicMock()
        sale.id = 2
        sale.sale_number = None
        sale.sale_date = MagicMock()
        sale.sale_date.strftime.return_value = "2024-02-01"
        sale.amount_aed = 50
        sale.paid_amount_aed = 10
        flat = MagicMock()
        flat.id = 3
        flat.sale_number = "S3"
        flat.sale_date = MagicMock()
        flat.sale_date.strftime.return_value = "2024-02-02"
        flat.amount_aed = 30
        flat.paid_amount_aed = 30
        with (
            patch("routes.customers.tenant_get_or_404", return_value=_customer()),
            patch("routes.customers._customer_in_scope", return_value=True),
            patch(
                "services.customer_service.CustomerService.confirmed_sales",
                return_value=[sale, flat],
            ),
        ):
            resp = cust_client.get("/customers/5/sales")
        assert resp.status_code == 200
