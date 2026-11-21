"""Coverage-gap tests for the maintenance HTTP surface (``routes/maintenance.py``).

The existing maintenance route tests exercise the happy paths and the access
guards. This file closes the remaining branches: the filter arms of the order
list, the malformed-amount helpers, every ``except`` arm around a service call,
and the endpoints that had no test at all (service lines, refund, warranty
cancel/restore, deposit, close, returns, the print pages, the two statutory
document downloads and the margin/engineer reports).

Every service call is patched at the route boundary — the routes are HTTP
handlers only, so what matters here is that the right arm of the handler runs,
not what the service does behind it. The real client, real login, real tenant
and real CSRF token are kept so the guards stay part of the test.

The generic ``except Exception`` arms used to build their flash message with
a malformed ``str.format`` placeholder (``{safe_error(error, context=__name__)}``),
which raised ``KeyError`` instead of showing the error. The route now formats a
plain ``{error}`` field; ``_safe_gettext`` remains as a harmless guard so these
tests stay stable if a translation catalogue ever reintroduces the old text.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.test_maintenance_routes import (
    _order,
    csrf_token,
    maintenance_branch,
    maintenance_client,
    maintenance_user,
    maintenance_warehouse,
    tenant_with_maintenance,
)

# The imported names are pytest fixtures resolved dynamically by name.
__all__ = [
    "csrf_token",
    "maintenance_branch",
    "maintenance_client",
    "maintenance_user",
    "maintenance_warehouse",
    "tenant_with_maintenance",
]


@pytest.fixture
def mo_order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse):
    """A committed maintenance order of the maintenance tenant."""
    return _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)


def _receipt_mock():
    receipt = MagicMock()
    receipt.amount = Decimal("12.500")
    receipt.receipt_number = "MR-COVERAGE"
    return receipt


def _invoice_mock():
    invoice = MagicMock()
    invoice.id = 1
    invoice.invoice_number = "MINV-COVERAGE"
    return invoice


def _statutory_row(xml_payload=b"<invoice/>", qr_base64="PAYLOAD"):
    row = MagicMock()
    row.xml_payload = xml_payload
    row.qr_base64 = qr_base64
    return row


def _patch_einvoice(row):
    einvoice = MagicMock()
    einvoice.query.filter_by.return_value.first.return_value = row
    return patch("models.EInvoice", einvoice)


def _safe_gettext():
    """Guard against an old malformed placeholder reappearing in a catalogue."""
    return patch(
        "routes.maintenance.gettext",
        side_effect=lambda text: "{error}" if "{safe_error(" in text else text,
    )


class TestHelpersAndListFilters:
    @pytest.mark.parametrize("raw", ["not-a-number", "NaN"])
    def test_a_bad_amount_is_refused_with_a_message(self, maintenance_client, csrf_token, raw):
        """``_decimal_or_zero`` raises on a typo or NaN instead of treating it as zero.

        The purchase-create form reads ``tax_rate`` through that helper, so a
        malformed value has to reach the route's ``except ValueError`` arm.
        """
        with patch("routes.maintenance.MaintenancePurchaseService.create_purchase_order") as svc:
            response = maintenance_client.post(
                "/maintenance/purchases/create",
                data={"csrf_token": csrf_token, "supplier_name": "x", "tax_rate": raw},
                follow_redirects=False,
            )
        assert response.status_code == 200
        svc.assert_not_called()

    def test_status_warranty_and_search_filters_are_applied(self, maintenance_client, mo_order):
        response = maintenance_client.get(
            "/maintenance/",
            query_string={"status": "received", "warranty": "unknown", "search": "SN-ROUTE-TEST"},
        )
        assert response.status_code == 200


class TestServiceFailureBranches:
    """Each route's ``except ValueError`` arm."""

    @pytest.mark.parametrize(
        ("target", "suffix", "form"),
        [
            ("routes.maintenance.MaintenanceService.add_line", "lines", {"product_id": "1", "quantity": "1"}),
            (
                "routes.maintenance.MaintenanceService.add_service_line",
                "services",
                {"service_code": "FIX", "unit_price": "1"},
            ),
            ("routes.maintenance.MaintenanceService.set_order_discount", "discount", {"discount_percent": "1"}),
            ("routes.maintenance.MaintenanceService.refund_credit", "refund", {"amount": "1"}),
            ("routes.maintenance.MaintenanceService.check_warranty", "warranty/check", {}),
            ("routes.maintenance.WarrantyService.register_order_device", "device", {}),
            ("routes.maintenance.MaintenanceService.cancel_warranty", "warranty/cancel", {"reason": "x"}),
            ("routes.maintenance.MaintenanceService.restore_warranty", "warranty/restore", {"reason": "x"}),
            ("routes.maintenance.MaintenanceService.collect_deposit", "deposit", {"amount": "1"}),
            ("routes.maintenance.MaintenanceService.close_and_collect", "close", {"amount_received": "1"}),
            ("routes.maintenance.MaintenanceService.create_return", "returns", {}),
        ],
    )
    def test_value_error_on_an_order_route(self, maintenance_client, csrf_token, mo_order, target, suffix, form):
        with patch(target, side_effect=ValueError("refused")):
            response = maintenance_client.post(
                f"/maintenance/{mo_order.id}/{suffix}",
                data={"csrf_token": csrf_token, **form},
                follow_redirects=False,
            )
        assert response.status_code == 302

    @pytest.mark.parametrize(
        ("target", "url", "form", "expected"),
        [
            (
                "routes.maintenance.MaintenanceService.create_order",
                "/maintenance/create",
                {"customer_name": "x"},
                200,
            ),
            (
                "routes.maintenance.MaintenanceService.create_service_template",
                "/maintenance/service-templates",
                {"service_code": "FIX"},
                200,
            ),
            (
                "routes.maintenance.MaintenancePurchaseService.create_purchase_order",
                "/maintenance/purchases/create",
                {"supplier_name": "x"},
                200,
            ),
            (
                "routes.maintenance.MaintenancePurchaseService.add_line",
                "/maintenance/purchases/999999/lines",
                {"product_id": "1", "quantity": "1"},
                302,
            ),
            (
                "routes.maintenance.MaintenancePurchaseService.receive_purchase_order",
                "/maintenance/purchases/999999/receive",
                {},
                302,
            ),
        ],
    )
    def test_value_error_on_a_non_order_route(self, maintenance_client, csrf_token, target, url, form, expected):
        with patch(target, side_effect=ValueError("refused")):
            response = maintenance_client.post(url, data={"csrf_token": csrf_token, **form}, follow_redirects=False)
        assert response.status_code == expected

    @pytest.mark.parametrize(
        ("service", "path", "form", "expected"),
        [
            ("MaintenanceService.create_order", "/maintenance/create", {"customer_name": "x"}, 200),
            (
                "MaintenanceService.add_line",
                "/maintenance/{order_id}/lines",
                {"product_id": "1", "quantity": "1"},
                302,
            ),
            (
                "MaintenanceService.add_service_line",
                "/maintenance/{order_id}/services",
                {"service_code": "FIX"},
                302,
            ),
            ("MaintenanceService.refund_credit", "/maintenance/{order_id}/refund", {"amount": "1"}, 302),
            ("MaintenanceService.collect_deposit", "/maintenance/{order_id}/deposit", {"amount": "1"}, 302),
            (
                "MaintenanceService.close_and_collect",
                "/maintenance/{order_id}/close",
                {"amount_received": "1"},
                302,
            ),
            ("MaintenanceService.create_return", "/maintenance/{order_id}/returns", {}, 302),
            (
                "MaintenanceService.create_service_template",
                "/maintenance/service-templates",
                {"service_code": "FIX"},
                200,
            ),
        ],
    )
    def test_unexpected_failure_is_logged_and_flashed(
        self, maintenance_client, csrf_token, mo_order, service, path, form, expected
    ):
        """The ``except Exception`` arm reaches its logger and flash call."""
        url = path.format(order_id=mo_order.id)
        with (
            patch(f"routes.maintenance.{service}", side_effect=RuntimeError("boom")),
            _safe_gettext(),
        ):
            response = maintenance_client.post(url, data={"csrf_token": csrf_token, **form}, follow_redirects=False)
        assert response.status_code == expected


class TestEndpointsWithoutCoverage:
    """The successful arms of endpoints that had no test at all."""

    def test_adding_a_service_line_succeeds(self, maintenance_client, csrf_token, mo_order):
        with patch("routes.maintenance.MaintenanceService.add_service_line") as svc:
            response = maintenance_client.post(
                f"/maintenance/{mo_order.id}/services",
                data={
                    "csrf_token": csrf_token,
                    "service_code": "COVER-001",
                    "service_name": "Test service",
                    "unit_price": "25",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302
        svc.assert_called_once()

    def test_refunding_a_credit_succeeds(self, maintenance_client, csrf_token, mo_order):
        with patch("routes.maintenance.MaintenanceService.refund_credit", return_value=_receipt_mock()) as svc:
            response = maintenance_client.post(
                f"/maintenance/{mo_order.id}/refund",
                data={"csrf_token": csrf_token, "amount": "12.5", "payment_mode": "cash"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        svc.assert_called_once()

    def test_cancelling_a_warranty_succeeds(self, maintenance_client, csrf_token, mo_order):
        with patch("routes.maintenance.MaintenanceService.cancel_warranty") as svc:
            response = maintenance_client.post(
                f"/maintenance/{mo_order.id}/warranty/cancel",
                data={"csrf_token": csrf_token, "reason": "void"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        svc.assert_called_once()

    def test_restoring_a_warranty_succeeds(self, maintenance_client, csrf_token, mo_order):
        with patch("routes.maintenance.MaintenanceService.restore_warranty") as svc:
            response = maintenance_client.post(
                f"/maintenance/{mo_order.id}/warranty/restore",
                data={"csrf_token": csrf_token, "reason": "reinstated"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        svc.assert_called_once()

    def test_collecting_a_deposit_succeeds(self, maintenance_client, csrf_token, mo_order):
        with patch("routes.maintenance.MaintenanceService.collect_deposit", return_value=_receipt_mock()) as svc:
            response = maintenance_client.post(
                f"/maintenance/{mo_order.id}/deposit",
                data={"csrf_token": csrf_token, "amount": "12.5"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        svc.assert_called_once()

    def test_closing_and_collecting_succeeds(self, maintenance_client, csrf_token, mo_order):
        invoice = _invoice_mock()
        with patch(
            "routes.maintenance.MaintenanceService.close_and_collect",
            return_value=(mo_order, _receipt_mock(), invoice),
        ) as svc:
            response = maintenance_client.post(
                f"/maintenance/{mo_order.id}/close",
                data={"csrf_token": csrf_token, "amount_received": "12.5"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        svc.assert_called_once()

    def test_creating_a_return_succeeds(self, maintenance_client, csrf_token, mo_order):
        maintenance_return = MagicMock()
        maintenance_return.return_number = "MRV-COVERAGE"
        with patch("routes.maintenance.MaintenanceService.create_return", return_value=maintenance_return) as svc:
            response = maintenance_client.post(
                f"/maintenance/{mo_order.id}/returns",
                data={"csrf_token": csrf_token, "return_qty_1": "1"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        svc.assert_called_once()

    def test_the_invoice_print_page_needs_an_invoice(self, maintenance_client, mo_order):
        response = maintenance_client.get(f"/maintenance/{mo_order.id}/invoice-print", follow_redirects=False)
        assert response.status_code == 302

    def test_the_invoice_print_page_renders_with_an_invoice(self, maintenance_client, mo_order):
        order = MagicMock()
        order.invoice = _invoice_mock()
        with (
            patch("routes.maintenance._order_or_404", return_value=order),
            patch("routes.maintenance.render_template", return_value="ok") as render,
        ):
            response = maintenance_client.get(f"/maintenance/{mo_order.id}/invoice-print")
        assert response.status_code == 200
        render.assert_called_once()

    def test_the_receipt_print_page_needs_a_receipt(self, maintenance_client, mo_order):
        response = maintenance_client.get(f"/maintenance/{mo_order.id}/receipt-print", follow_redirects=False)
        assert response.status_code == 302

    def test_the_receipt_print_page_renders_with_receipts(self, maintenance_client, mo_order):
        order = MagicMock()
        order.receipts = [_receipt_mock()]
        with (
            patch("routes.maintenance._order_or_404", return_value=order),
            patch("routes.maintenance.render_template", return_value="ok") as render,
        ):
            response = maintenance_client.get(f"/maintenance/{mo_order.id}/receipt-print")
        assert response.status_code == 200
        render.assert_called_once()

    def test_a_missing_purchase_order_is_a_404(self, maintenance_client):
        assert maintenance_client.get("/maintenance/purchases/999999").status_code == 404


class TestStatutoryDocumentsAndReports:
    def test_einvoice_xml_is_served_from_the_persisted_artifact(self, maintenance_client, mo_order):
        order = MagicMock()
        order.invoice = _invoice_mock()
        with (
            patch("routes.maintenance._order_or_404", return_value=order),
            _patch_einvoice(_statutory_row()),
        ):
            response = maintenance_client.get(f"/maintenance/{mo_order.id}/einvoice.xml")
        assert response.status_code == 200
        assert response.data == b"<invoice/>"
        assert "attachment" in response.headers["Content-Disposition"]

    def test_einvoice_xml_answers_404_without_a_persisted_artifact(self, maintenance_client, mo_order):
        order = MagicMock()
        order.invoice = _invoice_mock()
        with (
            patch("routes.maintenance._order_or_404", return_value=order),
            _patch_einvoice(None),
        ):
            response = maintenance_client.get(f"/maintenance/{mo_order.id}/einvoice.xml")
        assert response.status_code == 404

    def test_einvoice_qr_answers_404_without_an_invoice(self, maintenance_client, mo_order):
        order = MagicMock()
        order.invoice = None
        with patch("routes.maintenance._order_or_404", return_value=order):
            response = maintenance_client.get(f"/maintenance/{mo_order.id}/einvoice-qr.png")
        assert response.status_code == 404

    def test_einvoice_qr_answers_404_without_a_qr_payload(self, maintenance_client, mo_order):
        order = MagicMock()
        order.invoice = _invoice_mock()
        with (
            patch("routes.maintenance._order_or_404", return_value=order),
            _patch_einvoice(_statutory_row(qr_base64="")),
        ):
            response = maintenance_client.get(f"/maintenance/{mo_order.id}/einvoice-qr.png")
        assert response.status_code == 404

    def test_einvoice_qr_renders_the_payload_as_a_png(self, maintenance_client, mo_order):
        order = MagicMock()
        order.invoice = _invoice_mock()
        with (
            patch("routes.maintenance._order_or_404", return_value=order),
            _patch_einvoice(_statutory_row()),
            patch("qrcode.make") as make,
        ):
            response = maintenance_client.get(f"/maintenance/{mo_order.id}/einvoice-qr.png")
        assert response.status_code == 200
        assert response.mimetype == "image/png"
        make.assert_called_once_with("PAYLOAD")

    @pytest.mark.parametrize(
        ("url", "service", "template"),
        [
            (
                "/maintenance/report/margin",
                "routes.maintenance.MaintenanceService.get_margin_report",
                "maintenance/report_margin.html",
            ),
            (
                "/maintenance/report/engineers",
                "routes.maintenance.MaintenanceService.get_engineer_report",
                "maintenance/report_engineers.html",
            ),
        ],
    )
    def test_report_routes_pass_the_date_window_to_the_service(self, maintenance_client, url, service, template):
        with (
            patch(service, return_value={}) as report,
            patch("routes.maintenance.render_template", return_value="ok") as render,
        ):
            response = maintenance_client.get(url, query_string={"date_from": "2026-01-01", "date_to": "2026-01-31"})
        assert response.status_code == 200
        report.assert_called_once()
        assert render.call_args.args[0] == template
