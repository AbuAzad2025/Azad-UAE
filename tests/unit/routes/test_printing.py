from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from flask import Response

from tests.unit.routes.conftest import unauthenticated_client


def _doc(branch_id=1, tenant_id=1, **extra):
    doc = MagicMock()
    doc.id = extra.get("id", 1)
    doc.tenant_id = tenant_id
    doc.branch_id = branch_id
    for k, v in extra.items():
        setattr(doc, k, v)
    return doc


def _model_chain(obj):
    q = MagicMock()
    q.filter_by.return_value = q
    q.filter.return_value = q
    q.first.return_value = obj
    q.first_or_404.return_value = obj
    return q


@pytest.fixture
def printing_client(app_factory, bypass_permission_auth):
    with (
        patch("routes.printing.PrintService.render_print", return_value="<html>print</html>") as rp,
        patch("routes.printing.PrintService.render_pdf", return_value=b"fake-pdf") as rpdf,
        patch("routes.printing.PrintService.audit_print") as audit,
        patch("routes.printing.PrintService.create_snapshot") as snap,
        patch("routes.printing.PrintService.bulk_print_documents", return_value="<html>bulk</html>") as bulk,
        patch("routes.printing.PrintService._get_model") as get_model,
        patch("routes.printing.PrintService.get_document") as get_doc,
        patch("routes.printing.PrintService.get_tenant_document") as get_tenant_doc,
        patch("routes.printing.PrintService.get_shipment_for_sale") as get_shipment,
        patch("routes.printing.PrintService.resolve_template", return_value="invoices/modern.html") as resolve,
        patch("routes.printing.PrintService.history_query") as hist_q,
        patch("routes.printing.PrintService.list_recent_history", return_value=[]) as list_hist,
        patch("routes.printing.branch_scope_id", return_value=None) as branch_scope,
        patch("routes.printing.render_template", return_value="error-page") as render_tpl,
        patch("extensions.db.session", MagicMock()) as sess,
        patch("routes.printing.InvoiceSettings.get_active") as get_settings,
        patch("routes.printing.send_file", return_value=Response(b"pdf", mimetype="application/pdf")) as send_file,
    ):
        settings = MagicMock()
        settings.active_template = "modern"
        get_settings.return_value = settings
        hist_q.return_value.paginate.return_value.items = []
        hist_q.return_value.paginate.return_value.page = 1
        # default doc for generic routes
        purchase_doc = _doc(branch_id=1, tenant_id=1, purchase_number="PO-001")
        get_doc.return_value = purchase_doc
        get_tenant_doc.return_value = purchase_doc
        get_model.return_value = MagicMock()
        get_model.return_value.query = _model_chain(purchase_doc)
        from routes.printing import printing_bp

        app = app_factory(printing_bp)
        client = app.test_client()
        client._mocks = {
            "render_print": rp,
            "render_pdf": rpdf,
            "audit_print": audit,
            "create_snapshot": snap,
            "bulk_print": bulk,
            "get_model": get_model,
            "get_document": get_doc,
            "get_tenant_document": get_tenant_doc,
            "get_shipment": get_shipment,
            "resolve_template": resolve,
            "branch_scope": branch_scope,
            "render_tpl": render_tpl,
            "session": sess,
            "get_settings": get_settings,
            "send_file": send_file,
            "settings": settings,
            "history_q": hist_q,
            "list_hist": list_hist,
        }
        yield client


class TestPrintingHelpers:
    def test_normalize_doc_type_hyphen(self):
        from routes.printing import _normalize_doc_type

        assert _normalize_doc_type("payroll-slip") == "payroll_slip"
        assert _normalize_doc_type("packing-slip") == "packing_slip"

    def test_check_branch_scope_match(self):
        from routes.printing import _check_branch_scope

        doc = _doc(branch_id=5)
        with patch("routes.printing.branch_scope_id", return_value=5):
            assert _check_branch_scope(doc) is False
        with patch("routes.printing.branch_scope_id", return_value=2):
            assert _check_branch_scope(doc) is True
        with patch("routes.printing.branch_scope_id", return_value=None):
            assert _check_branch_scope(doc) is False

    def test_get_filename_with_attr(self):
        from routes.printing import _get_filename

        entry = {"filename_attr": "purchase_number", "filename_prefix": "purchase"}
        doc = _doc(purchase_number="PO-123")
        assert _get_filename(entry, doc, "purchase", 1) == "purchase_PO-123.pdf"

    def test_get_filename_without_attr(self):
        from routes.printing import _get_filename

        entry = {"filename_attr": None, "filename_prefix": "cheque"}
        doc = _doc()
        assert _get_filename(entry, doc, "cheque", 99) == "cheque_99.pdf"

    def test_get_filename_attr_missing_value(self):
        from routes.printing import _get_filename

        entry = {"filename_attr": "purchase_number", "filename_prefix": "purchase"}
        doc = _doc(purchase_number=None)
        assert _get_filename(entry, doc, "purchase", 7) == "purchase_7.pdf"


class TestGenericPrint:
    def test_print_unknown_type_404(self, printing_client):
        resp = printing_client.get("/printing/unknown_doc/1")
        assert resp.status_code == 404

    def test_print_permission_denied_403(self, printing_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        resp = printing_client.get("/printing/purchase/1")
        assert resp.status_code == 403

    def test_print_document_not_found_404(self, printing_client):
        printing_client._mocks["get_document"].return_value = None
        resp = printing_client.get("/printing/purchase/99")
        assert resp.status_code == 404

    def test_print_branch_scope_403(self, printing_client):
        doc = _doc(branch_id=5, purchase_number="PO-X")
        printing_client._mocks["get_document"].return_value = doc
        printing_client._mocks["branch_scope"].return_value = 2
        resp = printing_client.get("/printing/purchase/1")
        assert resp.status_code == 403

    def test_print_purchase_success(self, printing_client):
        doc = _doc(branch_id=1, purchase_number="PO-001")
        printing_client._mocks["get_document"].return_value = doc
        printing_client._mocks["branch_scope"].return_value = None
        resp = printing_client.get("/printing/purchase/1")
        assert resp.status_code == 200
        printing_client._mocks["create_snapshot"].assert_called()
        printing_client._mocks["audit_print"].assert_called()
        printing_client._mocks["render_print"].assert_called()

    def test_print_sale_template_none_with_requested(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, sale_number="S-100")
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["branch_scope"].return_value = None
        # sale entry has template None, so resolve_template should be used when requested supplied
        resp = printing_client.get("/printing/sale/1?template=classic")
        assert resp.status_code == 200
        # render_print called with resolved template
        assert printing_client._mocks["render_print"].called

    def test_print_sale_template_none_without_requested_uses_settings(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, sale_number="S-101")
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["branch_scope"].return_value = None
        printing_client._mocks["get_settings"].return_value.active_template = "gulf"
        resp = printing_client.get("/printing/sale/1")
        assert resp.status_code == 200

    def test_print_sale_template_none_settings_none_fallback(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, sale_number="S-102")
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["get_settings"].return_value = None
        resp = printing_client.get("/printing/sale/1")
        assert resp.status_code == 200

    def test_print_sale_tenant_none_fallback(self, printing_client):
        # tid None => eff_tid from doc.tenant_id
        sale = _doc(branch_id=1, tenant_id=5, sale_number="S-200")
        printing_client._mocks["get_document"].return_value = sale
        with patch("routes.printing.get_active_tenant_id", return_value=None):
            resp = printing_client.get("/printing/sale/1")
        assert resp.status_code == 200

    def test_print_with_hyphenated_doc_type(self, printing_client):
        txn = _doc(branch_id=1, tenant_id=1)
        printing_client._mocks["get_document"].return_value = txn
        resp = printing_client.get("/printing/payroll-slip/10")
        assert resp.status_code == 200


class TestPdfPrint:
    def test_pdf_unknown_type_404(self, printing_client):
        resp = printing_client.get("/printing/unknown_doc/1/pdf")
        assert resp.status_code == 404

    def test_pdf_permission_denied_403(self, printing_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        resp = printing_client.get("/printing/purchase/1/pdf")
        assert resp.status_code == 403

    def test_pdf_not_found_404(self, printing_client):
        printing_client._mocks["get_document"].return_value = None
        resp = printing_client.get("/printing/purchase/99/pdf")
        assert resp.status_code == 404

    def test_pdf_branch_scope_403(self, printing_client):
        doc = _doc(branch_id=9, purchase_number="PO-PDF")
        printing_client._mocks["get_document"].return_value = doc
        printing_client._mocks["branch_scope"].return_value = 1
        resp = printing_client.get("/printing/purchase/1/pdf")
        assert resp.status_code == 403

    def test_pdf_sale_template_none_resolves(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, sale_number="S-300")
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["resolve_template"].return_value = "invoices/classic.html"
        resp = printing_client.get("/printing/sale/1/pdf?template=classic")
        assert resp.status_code == 200
        printing_client._mocks["render_pdf"].assert_called()
        printing_client._mocks["send_file"].assert_called()

    def test_pdf_purchase_success(self, printing_client):
        doc = _doc(branch_id=1, purchase_number="PO-PDF-1")
        printing_client._mocks["get_document"].return_value = doc
        printing_client._mocks["branch_scope"].return_value = None
        resp = printing_client.get("/printing/purchase/1/pdf")
        assert resp.status_code == 200
        printing_client._mocks["render_pdf"].assert_called()
        printing_client._mocks["send_file"].assert_called()

    def test_pdf_cheque_uses_fallback_filename(self, printing_client):
        cheque = _doc(branch_id=1, tenant_id=1, id=5)
        # cheque entry has filename_attr None => _get_filename fallback
        printing_client._mocks["get_document"].return_value = cheque
        resp = printing_client.get("/printing/cheque/5/pdf")
        assert resp.status_code == 200

    def test_pdf_expense_branch_scope_403(self, printing_client):
        expense = _doc(branch_id=8, expense_number="EX-PDF")
        printing_client._mocks["get_document"].return_value = expense
        printing_client._mocks["branch_scope"].return_value = 3
        resp = printing_client.get("/printing/expense/2/pdf")
        assert resp.status_code == 403


class TestPackingSlip:
    def test_packing_slip_success_without_shipment(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, id=20, sale_number="S-100")
        sale.customer = MagicMock()
        sale.customer.address = "Addr"
        sale.customer.name = "Cust"
        sale.customer.phone = "+971500000000"
        sale.lines = []
        sale.sale_date = datetime.now(UTC)
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["get_shipment"].return_value = None
        printing_client._mocks["branch_scope"].return_value = None
        resp = printing_client.get("/printing/packing-slip/20")
        assert resp.status_code == 200
        ctx = printing_client._mocks["render_print"].call_args[0][1]
        assert ctx["sale"] is sale

    def test_packing_slip_not_found_404(self, printing_client):
        printing_client._mocks["get_document"].return_value = None
        resp = printing_client.get("/printing/packing-slip/999")
        assert resp.status_code == 404

    def test_packing_slip_branch_scope_403(self, printing_client):
        sale = _doc(branch_id=6, sale_number="S-1")
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["branch_scope"].return_value = 1
        resp = printing_client.get("/printing/packing-slip/1")
        assert resp.status_code == 403

    def test_packing_slip_pdf_success(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, id=30, sale_number="S-200")
        sale.customer = None
        sale.lines = []
        sale.sale_date = datetime.now(UTC)
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["get_shipment"].return_value = None
        resp = printing_client.get("/printing/packing-slip/30/pdf")
        assert resp.status_code == 200
        printing_client._mocks["render_pdf"].assert_called()
        printing_client._mocks["send_file"].assert_called()

    def test_packing_slip_pdf_not_found_404(self, printing_client):
        printing_client._mocks["get_document"].return_value = None
        resp = printing_client.get("/printing/packing-slip/999/pdf")
        assert resp.status_code == 404

    def test_packing_slip_pdf_branch_scope_403(self, printing_client):
        sale = _doc(branch_id=6, sale_number="S-1")
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["branch_scope"].return_value = 1
        resp = printing_client.get("/printing/packing-slip/1/pdf")
        assert resp.status_code == 403

    def test_resolve_delivery_shipment_found(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, id=21, sale_number="S-101")
        sale.customer = None
        sale.lines = [MagicMock()]
        shipment = MagicMock()
        shipment.tracking_number = "TRK-1"
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["get_shipment"].return_value = shipment
        resp = printing_client.get("/printing/packing-slip/21")
        assert resp.status_code == 200
        ctx = printing_client._mocks["render_print"].call_args[0][1]
        assert ctx["delivery"] is shipment

    def test_resolve_delivery_exception_fallback(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, id=22, sale_number="S-102")
        sale.customer = None
        sale.lines = []
        sale.sale_date = datetime.now(UTC)
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["get_shipment"].side_effect = Exception("db error")
        resp = printing_client.get("/printing/packing-slip/22")
        assert resp.status_code == 200

    def test_packing_slip_with_customer_none(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, id=35, sale_number="S-500")
        sale.customer = None
        sale.lines = []
        sale.sale_date = datetime.now(UTC)
        printing_client._mocks["get_document"].return_value = sale
        printing_client._mocks["get_shipment"].return_value = None
        resp = printing_client.get("/printing/packing-slip/35")
        assert resp.status_code == 200
        ctx = printing_client._mocks["render_print"].call_args[0][1]
        assert ctx["delivery"].customer_name == ""


class TestBulkPrint:
    def test_bulk_print_sale_template_none(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1, sale_number="S-1")
        printing_client._mocks["get_tenant_document"].return_value = sale
        printing_client._mocks["resolve_template"].return_value = "invoices/modern.html"
        resp = printing_client.post(
            "/printing/bulk-print",
            json={"type": "sale", "ids": [1, 2]},
            content_type="application/json",
        )
        assert resp.status_code == 200
        printing_client._mocks["bulk_print"].assert_called_once()

    def test_bulk_print_filters_missing_docs(self, printing_client):
        printing_client._mocks["get_tenant_document"].return_value = None
        resp = printing_client.post(
            "/printing/bulk-print",
            json={"type": "purchase", "ids": [99]},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_bulk_print_unknown_type_400(self, printing_client):
        resp = printing_client.post(
            "/printing/bulk-print",
            json={"type": "unknown_doc", "ids": [1]},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Unknown document type" in resp.get_json()["message"]

    def test_bulk_print_hyphenated_type(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=1)
        printing_client._mocks["get_tenant_document"].return_value = sale
        resp = printing_client.post(
            "/printing/bulk-print",
            json={"type": "packing-slip", "ids": [1]},
            content_type="application/json",
        )
        # packing-slip normalizes to packing_slip which exists
        assert resp.status_code == 200

    def test_bulk_print_with_tid_none_fallback(self, printing_client):
        sale = _doc(branch_id=1, tenant_id=7, sale_number="S-TID")
        printing_client._mocks["get_tenant_document"].return_value = sale
        with patch("routes.printing.get_active_tenant_id", return_value=None):
            resp = printing_client.post(
                "/printing/bulk-print",
                json={"type": "purchase", "ids": [1]},
                content_type="application/json",
            )
        assert resp.status_code == 200


class TestPrintHistory:
    def test_history_renders(self, printing_client):
        with patch("routes.printing.PrintService.history_query") as hq:
            pag = MagicMock()
            pag.items = [MagicMock()]
            hq.return_value.paginate.return_value = pag
            with patch("routes.printing.render_template", return_value="history-page") as rt:
                resp = printing_client.get("/printing/history?page=1")
        assert resp.status_code == 200
        rt.assert_called_once()

    def test_history_with_pagination(self, printing_client):
        with patch("routes.printing.PrintService.history_query") as hq:
            hq.return_value.paginate.return_value = MagicMock(items=[])
            with patch("routes.printing.render_template", return_value="ok"):
                resp = printing_client.get("/printing/history?page=2")
        assert resp.status_code == 200

    def test_api_history_returns_list(self, printing_client):
        rec = MagicMock()
        rec.id = 1
        rec.document_type = "purchase"
        rec.document_id = 5
        rec.action = "print"
        rec.created_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        rec.user = MagicMock(full_name="Tester")
        printing_client._mocks["list_hist"].return_value = [rec]
        with patch("routes.printing.PrintService.list_recent_history", return_value=[rec]):
            resp = printing_client.get("/printing/api/print-history?limit=5")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"][0]["document_type"] == "purchase"

    def test_api_history_none_user(self, printing_client):
        rec = MagicMock()
        rec.id = 2
        rec.document_type = "sale"
        rec.document_id = 3
        rec.action = "pdf_download"
        rec.created_at = None
        rec.user = None
        with patch("routes.printing.PrintService.list_recent_history", return_value=[rec]):
            resp = printing_client.get("/printing/api/print-history")
        assert resp.status_code == 200
        assert resp.get_json()["data"][0]["user_name"] == "—"


class TestPreview:
    def test_preview_missing_params_400(self, printing_client):
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "purchase"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_preview_unsupported_type_400(self, printing_client):
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "unknown_xyz", "id": 1},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_preview_not_found_404(self, printing_client):
        printing_client._mocks["get_tenant_document"].return_value = None
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "purchase", "id": 99},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_preview_success(self, printing_client):
        doc = _doc(purchase_number="PO-9")
        printing_client._mocks["get_tenant_document"].return_value = doc
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "purchase", "id": 9},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "html" in resp.get_json()["data"]

    def test_preview_hyphenated_type(self, printing_client):
        txn = _doc(branch_id=1)
        printing_client._mocks["get_tenant_document"].return_value = txn
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "payroll-slip", "id": 10},
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestSettings:
    def test_settings_get_200(self, printing_client):
        with patch("routes.printing.render_template", return_value="settings-page") as rt:
            resp = printing_client.get("/printing/settings")
        assert resp.status_code == 200
        rt.assert_called_once()

    def test_settings_post_saves(self, printing_client):
        settings = printing_client._mocks["settings"]
        with patch("routes.printing.atomic_transaction"):
            resp = printing_client.post(
                "/printing/settings",
                data={
                    "paper_size": "A3",
                    "orientation": "landscape",
                    "active_template": "classic",
                    "header_color": "#111",
                    "accent_color": "#222",
                    "show_logo": "on",
                    "enable_qr_code": "on",
                    "enable_watermark": "on",
                    "show_terms": "on",
                },
            )
        assert resp.status_code in (302, 303)
        assert settings.paper_size == "A3"
        assert settings.show_logo is True
        assert settings.enable_watermark is True

    def test_settings_post_defaults(self, printing_client):
        settings = printing_client._mocks["settings"]
        with patch("routes.printing.atomic_transaction"):
            resp = printing_client.post("/printing/settings", data={})
        assert resp.status_code in (302, 303)
        assert settings.paper_size == "A4"


class TestAuth:
    def test_unauthenticated_redirect(self, printing_client):
        with unauthenticated_client(printing_client):
            resp = printing_client.get("/printing/purchase/1")
            assert resp.status_code in (302, 401)
