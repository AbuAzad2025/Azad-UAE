"""Coverage-99 boost for routes/printing.py.

Covers: print_customer_statement (357-472), print_supplier_statement
(494-629), print_advanced_ledger (645-671).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def print_client(app_factory, bypass_permission_auth):
    from routes.printing import printing_bp

    app = app_factory(printing_bp)
    return app.test_client()


def _sale():
    s = MagicMock()
    s.sale_date = datetime(2024, 1, 5)
    s.sale_number = "S1"
    s.amount_aed = 100
    return s


def _payment(direction="incoming", confirmed=True, method="cash"):
    p = MagicMock()
    p.payment_date = datetime(2024, 1, 6)
    p.payment_number = "P1"
    p.reference_number = None
    p.amount_aed = 40
    p.direction = direction
    p.payment_confirmed = confirmed
    p.payment_method = method
    p.rejection_reason = None
    return p


def _receipt():
    r = MagicMock()
    r.receipt_date = None
    r.receipt_number = "R1"
    r.amount_aed = 10
    return r


def _return():
    r = MagicMock()
    r.return_date = datetime(2024, 1, 7)
    r.return_number = "RT1"
    r.amount_aed = 5
    return r


class TestCustomerStatement:
    def _get(self, client, qs=""):
        customer = MagicMock(tenant_id=1)
        with (
            patch("utils.tenanting.tenant_get_or_404", return_value=customer),
            patch("routes.customers._customer_in_scope", return_value=True),
            patch(
                "services.customer_service.CustomerService.statement_opening_balance",
                return_value=20.0,
            ),
            patch(
                "services.customer_service.CustomerService.statement_records",
                return_value={
                    "sales": [_sale()],
                    "payments": [_payment("incoming"), _payment("outgoing")],
                    "receipts": [_receipt()],
                    "returns": [_return()],
                },
            ),
            patch("routes.printing.get_active_tenant_id", return_value=1),
            patch("routes.printing.branch_scope_id", return_value=None),
            patch("models.invoice_settings.InvoiceSettings.company_print_context", return_value=(None, None, None)),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.printing.PrintService.create_snapshot", return_value=None),
            patch("routes.printing.PrintService.audit_print", return_value=None),
            patch("routes.printing.PrintService.render_print", return_value="ok"),
        ):
            return client.get(f"/printing/customer-statement/5{qs}")

    def test_full_with_dates(self, print_client):
        assert self._get(print_client, "?date_from=2024-01-01&date_to=2024-01-31").status_code == 200

    def test_full_no_dates(self, print_client):
        assert self._get(print_client).status_code == 200

    def test_out_of_scope(self, print_client):
        with (
            patch("utils.tenanting.tenant_get_or_404", return_value=MagicMock()),
            patch("routes.customers._customer_in_scope", return_value=False),
            patch("routes.printing.render_template", return_value="denied"),
        ):
            resp = print_client.get("/printing/customer-statement/5")
        assert resp.status_code == 403


class TestSupplierStatement:
    def _get(self, client, qs="", payments=None):
        supplier = MagicMock(tenant_id=1)

        def _chain(items):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value.all.return_value = items
            return q

        purchase = MagicMock()
        purchase.purchase_date = datetime(2024, 2, 1)
        purchase.purchase_number = "PU1"
        purchase.amount_aed = 200
        pr = MagicMock()
        pr.return_date = datetime(2024, 2, 3)
        pr.return_number = "PR1"
        pr.amount_aed = 15
        if payments is None:
            payments = [
                _payment("incoming", True, "cash"),
                _payment("outgoing", False, "cheque"),
                _payment("outgoing", False, "cash"),
            ]
            payments[2].rejection_reason = "x"
        with (
            patch("utils.tenanting.tenant_get_or_404", return_value=supplier),
            patch("routes.suppliers._supplier_in_scope", return_value=True),
            patch(
                "services.supplier_service.SupplierService.print_statement_queries",
                return_value=(_chain([purchase]), _chain(payments), _chain([pr])),
            ),
            patch(
                "services.supplier_service.SupplierService.preperiod_opening_balance",
                return_value=7.0,
            ),
            patch("routes.printing.get_active_tenant_id", return_value=1),
            patch("routes.printing.branch_scope_id", return_value=None),
            patch("models.invoice_settings.InvoiceSettings.company_print_context", return_value=(None, None, None)),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.printing.PrintService.create_snapshot", return_value=None),
            patch("routes.printing.PrintService.audit_print", return_value=None),
            patch("routes.printing.PrintService.render_print", return_value="ok"),
        ):
            return client.get(f"/printing/supplier-statement/6{qs}")

    def test_full_with_dates(self, print_client):
        assert self._get(print_client, "?date_from=2024-01-01&date_to=2024-02-28").status_code == 200

    def test_full_no_dates(self, print_client):
        assert self._get(print_client).status_code == 200

    def test_sort_key_variants(self, print_client):
        from datetime import UTC, date

        aware = _payment("outgoing", True, "cash")
        aware.payment_date = datetime(2024, 1, 6, tzinfo=UTC)
        naive = _payment("outgoing", True, "cash")
        none_date = _payment("outgoing", True, "cash")
        none_date.payment_date = None
        plain_date = _payment("outgoing", True, "cash")
        plain_date.payment_date = date(2024, 1, 8)
        assert self._get(print_client, payments=[aware, naive, none_date, plain_date]).status_code == 200

    def test_out_of_scope(self, print_client):
        with (
            patch("utils.tenanting.tenant_get_or_404", return_value=MagicMock()),
            patch("routes.suppliers._supplier_in_scope", return_value=False),
            patch("routes.printing.render_template", return_value="denied"),
        ):
            resp = print_client.get("/printing/supplier-statement/6")
        assert resp.status_code == 403


class TestAdvancedLedger:
    def test_trial_balance_mixed(self, print_client):
        from models import GLAccount

        a1 = MagicMock(spec=GLAccount)
        a1.get_balance.return_value = 100
        a2 = MagicMock(spec=GLAccount)
        a2.get_balance.return_value = -40
        a3 = MagicMock(spec=GLAccount)
        a3.get_balance.return_value = 0
        with (
            patch("routes.printing.get_active_tenant_id", return_value=1),
            patch("models.GLAccount.query") as mq,
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("models.invoice_settings.InvoiceSettings.get_active", return_value=MagicMock()),
            patch("routes.printing.PrintService.render_print", return_value="ok"),
        ):
            mq.filter_by.return_value.limit.return_value.all.return_value = [a1, a2, a3]
            resp = print_client.get("/printing/advanced-ledger/professional-printing")
        assert resp.status_code == 200
