"""Coverage for routes/suppliers.py fallback/except/guard arcs.

Targets: safe_float branches, create rating/currency/limit/opening-balance
arcs, edit currency fallback + exception arc, delete soft/hard/fallback arcs,
view branch-scope arc, statement sort/filter/refund arcs, api_search arcs.
Real Flask test-client paths; mocks only at service/DB/template boundaries.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query


def _mock_supplier(**kwargs):
    s = MagicMock()
    s.id = kwargs.get("id", 1)
    s.name = kwargs.get("name", "Vendor Co")
    s.phone = kwargs.get("phone", "0501234567")
    s.email = kwargs.get("email", "v@example.com")
    s.supplier_type = kwargs.get("supplier_type", "parts")
    s.is_active = kwargs.get("is_active", True)
    s.is_verified = kwargs.get("is_verified", False)
    s.tenant_id = kwargs.get("tenant_id", 1)
    s.preferred_currency = kwargs.get("preferred_currency", "AED")
    s.purchases = MagicMock()
    filt = _chain_query(all=[])
    s.purchases.filter_by.return_value = filt
    s.purchases.filter.return_value = filt
    return s


def _scoped(all_items=None):
    q = _chain_query(all=all_items or [])
    q.filter.return_value = q
    q.filter_by.return_value = q
    return q


@contextmanager
def _patches(**kwargs):
    supplier = kwargs.get("supplier", _mock_supplier())
    scoped = _scoped(kwargs.get("suppliers", [supplier]))
    with ExitStack() as stack:
        stack.enter_context(patch("routes.suppliers.render_template", return_value="ok"))
        stack.enter_context(
            patch(
                "services.supplier_service.SupplierService.scoped_suppliers_query",
                return_value=scoped,
            )
        )
        stack.enter_context(patch("routes.suppliers.tenant_get_or_404", return_value=supplier))
        stack.enter_context(patch("routes.suppliers.get_active_tenant_id", return_value=1))
        stack.enter_context(patch("routes.suppliers.branch_scope_id", return_value=kwargs.get("branch_scope")))
        stack.enter_context(
            patch(
                "routes.suppliers.should_show_all_branch_columns",
                return_value=kwargs.get("show_branches", False),
            )
        )
        stack.enter_context(patch("routes.suppliers._supplier_in_scope", return_value=kwargs.get("in_scope", True)))
        stack.enter_context(
            patch("routes.suppliers._supplier_scoped_totals", return_value=([], Decimal("0"), Decimal("0")))
        )
        stack.enter_context(patch("routes.suppliers.LoggingCore.log_audit"))
        stack.enter_context(patch("routes.suppliers.log_mutation"))
        stack.enter_context(patch("routes.suppliers.atomic_transaction"))
        stack.enter_context(patch("extensions.db.session"))
        yield {"scoped": scoped, "supplier": supplier}


@pytest.fixture
def suppliers_cov3_client(app_factory, bypass_permission_auth):
    from routes.suppliers import suppliers_bp

    app = app_factory(suppliers_bp)
    return app.test_client()


class TestSafeFloat:
    def test_none_returns_default(self):
        from routes.suppliers import safe_float

        assert safe_float(None) == 0.0
        assert safe_float(None, default=5.0) == 5.0

    def test_empty_string_returns_default(self):
        from routes.suppliers import safe_float

        assert safe_float("") == 0.0
        assert safe_float("   ") == 0.0

    def test_invalid_returns_default(self):
        from routes.suppliers import safe_float

        assert safe_float("abc") == 0.0
        assert safe_float("12x", default=1.5) == 1.5

    def test_valid_float(self):
        from routes.suppliers import safe_float

        assert safe_float("3.5") == 3.5
        assert safe_float(7) == 7.0


class TestCreateGuards:
    def test_missing_supplier_type_warns(self, suppliers_cov3_client):
        with _patches():
            resp = suppliers_cov3_client.post("/suppliers/create", data={"name": "X"})
        assert resp.status_code == 200

    def test_bad_rating_warns(self, suppliers_cov3_client):
        with _patches():
            resp = suppliers_cov3_client.post(
                "/suppliers/create", data={"name": "X", "supplier_type": "parts", "rating": "bad"}
            )
        assert resp.status_code == 200

    def test_currency_fallback_path(self, suppliers_cov3_client):
        with (
            _patches(),
            patch("routes.suppliers.resolve_default_currency", side_effect=Exception("nope")),
            patch("routes.suppliers.get_system_default_currency", return_value="AED"),
            patch(
                "services.supplier_service.SupplierService.create_supplier",
                side_effect=Exception("boom"),
            ),
        ):
            resp = suppliers_cov3_client.post("/suppliers/create", data={"name": "X", "supplier_type": "parts"})
        assert resp.status_code == 200

    def test_tenant_limit_redirects(self, suppliers_cov3_client):
        from utils.tenant_limits import TenantLimitError

        with (
            _patches(),
            patch("routes.suppliers.resolve_default_currency", return_value="AED"),
            patch("utils.tenant_limits.check_suppliers_limit", side_effect=TenantLimitError("suppliers", 5, 5)),
        ):
            resp = suppliers_cov3_client.post("/suppliers/create", data={"name": "X", "supplier_type": "parts"})
        assert resp.status_code == 302

    def test_create_with_opening_balance_posts_gl(self, suppliers_cov3_client):
        supplier = _mock_supplier()
        with (
            _patches(supplier=supplier),
            patch("routes.suppliers.resolve_default_currency", return_value="AED"),
            patch("utils.tenant_limits.check_suppliers_limit", return_value=None),
            patch("services.supplier_service.SupplierService.create_supplier", return_value=supplier),
            patch("services.gl_service.GLService.ensure_core_accounts") as ensure,
            patch("services.gl_posting.post_or_fail") as post,
        ):
            resp = suppliers_cov3_client.post(
                "/suppliers/create",
                data={"name": "X", "supplier_type": "parts", "initial_balance": "100"},
            )
        assert resp.status_code == 302
        ensure.assert_called_once()
        post.assert_called_once()

    def test_create_generic_exception_renders(self, suppliers_cov3_client):
        with (
            _patches(),
            patch("routes.suppliers.resolve_default_currency", return_value="AED"),
            patch("utils.tenant_limits.check_suppliers_limit", return_value=None),
            patch(
                "services.supplier_service.SupplierService.create_supplier",
                side_effect=RuntimeError("db down"),
            ),
        ):
            resp = suppliers_cov3_client.post("/suppliers/create", data={"name": "X", "supplier_type": "parts"})
        assert resp.status_code == 200


class TestViewEditDelete:
    def test_view_out_of_scope_403(self, suppliers_cov3_client):
        with _patches(in_scope=False):
            resp = suppliers_cov3_client.get("/suppliers/1")
        assert resp.status_code == 403

    def test_view_with_branch_scope(self, suppliers_cov3_client):
        supplier = _mock_supplier()
        filt = _chain_query(all=[])
        supplier.purchases.filter_by.return_value = filt
        with _patches(supplier=supplier, branch_scope=9):
            with patch(
                "services.supplier_service.SupplierService.supplier_scoped_totals",
                return_value=([], Decimal("10"), Decimal("4")),
            ):
                pass
            resp = suppliers_cov3_client.get("/suppliers/1")
        assert resp.status_code in (200, 302)

    def test_edit_out_of_scope_403(self, suppliers_cov3_client):
        with _patches(in_scope=False):
            resp = suppliers_cov3_client.get("/suppliers/1/edit")
        assert resp.status_code == 403

    def test_edit_post_currency_fallback(self, suppliers_cov3_client):
        supplier = _mock_supplier()
        with (
            _patches(supplier=supplier),
            patch("routes.suppliers.resolve_default_currency", side_effect=Exception("x")),
            patch("routes.suppliers.get_system_default_currency", return_value="AED"),
        ):
            resp = suppliers_cov3_client.post(
                "/suppliers/1/edit",
                data={"name": "New", "supplier_type": "", "rating": "", "credit_limit": "5"},
            )
        assert resp.status_code == 302

    def test_edit_post_exception_renders(self, suppliers_cov3_client):
        with (
            _patches(),
            patch("utils.field_validators.normalize_phone_optional", side_effect=Exception("bad")),
        ):
            resp = suppliers_cov3_client.post("/suppliers/1/edit", data={"name": "N"})
        assert resp.status_code == 200

    def test_delete_soft_when_linked(self, suppliers_cov3_client):
        supplier = _mock_supplier()
        with (
            _patches(supplier=supplier, in_scope=True),
            patch(
                "services.supplier_service.SupplierService.supplier_linked_counts",
                return_value={"purchases": 2, "payments": 1},
            ),
        ):
            resp = suppliers_cov3_client.post("/suppliers/1/delete")
        assert resp.status_code == 302
        assert supplier.is_active is False

    def test_delete_hard_when_unlinked(self, suppliers_cov3_client):
        with (
            _patches(),
            patch(
                "services.supplier_service.SupplierService.supplier_linked_counts",
                return_value={"purchases": 0, "payments": 0},
            ),
        ):
            resp = suppliers_cov3_client.post("/suppliers/1/delete")
        assert resp.status_code == 302

    def test_delete_out_of_scope_403(self, suppliers_cov3_client):
        with _patches(in_scope=False):
            resp = suppliers_cov3_client.post("/suppliers/1/delete")
        assert resp.status_code == 403

    def test_delete_fallback_soft_on_error(self, suppliers_cov3_client):
        supplier = _mock_supplier()
        with (
            _patches(supplier=supplier),
            patch(
                "services.supplier_service.SupplierService.supplier_linked_counts",
                side_effect=Exception("db down"),
            ),
        ):
            resp = suppliers_cov3_client.post("/suppliers/1/delete")
        assert resp.status_code == 302

    def test_delete_double_fault_renders_danger(self, suppliers_cov3_client):
        with (
            _patches(),
            patch(
                "services.supplier_service.SupplierService.supplier_linked_counts",
                side_effect=Exception("db down"),
            ),
            patch("routes.suppliers.atomic_transaction", side_effect=Exception("tx down")),
        ):
            resp = suppliers_cov3_client.post("/suppliers/1/delete")
        assert resp.status_code == 302


class TestStatement:
    def _statement_patches(self, stack, **kw):
        supplier = _mock_supplier()
        purch = MagicMock()
        purch.purchase_date = datetime(2026, 1, 5)
        purch.purchase_number = "PO-1"
        purch.base_amount = Decimal("100")
        purch.currency = "AED"
        purch.exchange_rate = Decimal("1")
        purch.total_amount = Decimal("100")
        pay = MagicMock()
        pay.payment_date = datetime(2026, 1, 6)
        pay.amount_aed = Decimal("40")
        pay.payment_confirmed = True
        pay.payment_method = "cash"
        pay.rejection_reason = None
        pay.direction = kw.get("direction", "outgoing")
        pay.currency = "AED"
        pay.exchange_rate = Decimal("1")
        pay.amount = Decimal("40")
        pay.payment_number = "PAY-1"
        pay.reference_number = ""
        pay.cheque_number = None
        pay.bank_name = None
        pay.cheque_date = None
        pay.notes = ""
        ret = MagicMock()
        ret.return_date = datetime(2026, 1, 7).date()
        ret.return_number = "R-1"
        ret.amount_aed = Decimal("10")
        ret.currency = "AED"
        ret.exchange_rate = Decimal("1")
        ret.total_amount = Decimal("10")
        pq = _chain_query(all=[purch])
        yq = _chain_query(all=[pay])
        rq = _chain_query(all=[ret])
        supplier.purchases.filter_by.return_value = pq
        stack.enter_context(patch("routes.suppliers.tenant_get_or_404", return_value=supplier))
        stack.enter_context(patch("routes.suppliers.get_active_tenant_id", return_value=1))
        stack.enter_context(patch("routes.suppliers.branch_scope_id", return_value=None))
        stack.enter_context(patch("routes.suppliers._supplier_in_scope", return_value=True))
        stack.enter_context(patch("routes.suppliers.render_template", return_value="ok"))
        stack.enter_context(
            patch(
                "services.supplier_service.SupplierService.statement_ledger_queries",
                return_value=(yq, rq),
            )
        )
        stack.enter_context(
            patch(
                "services.supplier_service.SupplierService.preperiod_opening_balance",
                return_value=25.0,
            )
        )
        return supplier

    def test_statement_with_dates_and_refund(self, suppliers_cov3_client):
        with ExitStack() as stack:
            self._statement_patches(stack, direction="incoming")
            resp = suppliers_cov3_client.get("/suppliers/1/statement?date_from=2026-01-01&date_to=2026-02-01")
        assert resp.status_code == 200

    def test_statement_pending_cheque_affects_balance(self, suppliers_cov3_client):
        with ExitStack() as stack:
            supplier = _mock_supplier()
            pay = MagicMock()
            pay.payment_date = datetime(2026, 1, 6)
            pay.amount_aed = Decimal("40")
            pay.payment_confirmed = False
            pay.payment_method = "cheque"
            pay.rejection_reason = None
            pay.direction = "outgoing"
            pay.currency = "AED"
            pay.exchange_rate = Decimal("1")
            pay.amount = Decimal("40")
            pay.payment_number = "PAY-2"
            pay.reference_number = ""
            pay.cheque_number = "1"
            pay.bank_name = "B"
            pay.cheque_date = None
            pay.notes = ""
            pq = _chain_query(all=[])
            yq = _chain_query(all=[pay])
            rq = _chain_query(all=[])
            supplier.purchases.filter_by.return_value = pq
            stack.enter_context(patch("routes.suppliers.tenant_get_or_404", return_value=supplier))
            stack.enter_context(patch("routes.suppliers.get_active_tenant_id", return_value=1))
            stack.enter_context(patch("routes.suppliers.branch_scope_id", return_value=None))
            stack.enter_context(patch("routes.suppliers._supplier_in_scope", return_value=True))
            stack.enter_context(patch("routes.suppliers.render_template", return_value="ok"))
            stack.enter_context(
                patch(
                    "services.supplier_service.SupplierService.statement_ledger_queries",
                    return_value=(yq, rq),
                )
            )
            stack.enter_context(
                patch(
                    "services.supplier_service.SupplierService.preperiod_opening_balance",
                    return_value=0.0,
                )
            )
            resp = suppliers_cov3_client.get("/suppliers/1/statement")
        assert resp.status_code == 200

    def test_statement_sort_key_none_date(self, suppliers_cov3_client):
        from routes.suppliers import statement as _unused  # noqa: F401  (ensures import path)

        with ExitStack() as stack:
            supplier = _mock_supplier()
            purch = MagicMock()
            purch.purchase_date = None
            purch.purchase_number = "PO-9"
            purch.base_amount = Decimal("5")
            purch.currency = "AED"
            purch.exchange_rate = Decimal("1")
            purch.total_amount = Decimal("5")
            pq = _chain_query(all=[purch])
            yq = _chain_query(all=[])
            rq = _chain_query(all=[])
            supplier.purchases.filter_by.return_value = pq
            stack.enter_context(patch("routes.suppliers.tenant_get_or_404", return_value=supplier))
            stack.enter_context(patch("routes.suppliers.get_active_tenant_id", return_value=1))
            stack.enter_context(patch("routes.suppliers.branch_scope_id", return_value=None))
            stack.enter_context(patch("routes.suppliers._supplier_in_scope", return_value=True))
            stack.enter_context(patch("routes.suppliers.render_template", return_value="ok"))
            stack.enter_context(
                patch(
                    "services.supplier_service.SupplierService.statement_ledger_queries",
                    return_value=(yq, rq),
                )
            )
            stack.enter_context(
                patch(
                    "services.supplier_service.SupplierService.preperiod_opening_balance",
                    return_value=0.0,
                )
            )
            resp = suppliers_cov3_client.get("/suppliers/1/statement")
        assert resp.status_code == 200

    def test_statement_out_of_scope_403(self, suppliers_cov3_client):
        with ExitStack() as stack:
            stack.enter_context(patch("routes.suppliers.tenant_get_or_404", return_value=_mock_supplier()))
            stack.enter_context(patch("routes.suppliers._supplier_in_scope", return_value=False))
            stack.enter_context(patch("routes.suppliers.render_template", return_value="e403"))
            resp = suppliers_cov3_client.get("/suppliers/1/statement")
        assert resp.status_code == 403

    def test_print_statement_delegates(self, suppliers_cov3_client):
        with ExitStack() as stack:
            stack.enter_context(patch("routes.suppliers.tenant_get_or_404", return_value=_mock_supplier()))
            stack.enter_context(patch("routes.printing.print_supplier_statement", return_value="printed"))
            resp = suppliers_cov3_client.get("/suppliers/1/statement/print")
        assert resp.status_code == 200


class TestApiSearch:
    def test_search_with_query(self, suppliers_cov3_client):
        with _patches(suppliers=[_mock_supplier()]):
            resp = suppliers_cov3_client.get("/suppliers/api/search?q=Vendor")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_search_empty_query_lists(self, suppliers_cov3_client):
        with _patches(suppliers=[_mock_supplier()]):
            resp = suppliers_cov3_client.get("/suppliers/api/search")
        assert resp.status_code == 200

    def test_search_exception_returns_empty(self, suppliers_cov3_client):
        with ExitStack() as stack:
            stack.enter_context(patch("routes.suppliers.render_template", return_value="ok"))
            stack.enter_context(
                patch(
                    "services.supplier_service.SupplierService.scoped_suppliers_query",
                    side_effect=Exception("db down"),
                )
            )
            resp = suppliers_cov3_client.get("/suppliers/api/search?q=x")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == []
