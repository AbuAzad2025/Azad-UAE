from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Response

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


def _doc_mock(branch_id=1, tenant_id=1, **extra):
    doc = MagicMock()
    doc.id = extra.get("id", 1)
    doc.tenant_id = tenant_id
    doc.branch_id = branch_id
    for key, val in extra.items():
        setattr(doc, key, val)
    return doc


def _model_query_chain(obj):
    q = MagicMock()
    q.filter_by.return_value = q
    q.filter.return_value = q
    q.first_or_404.return_value = obj
    q.first.return_value = obj
    return q


def _register_entry(printing_client, doc_type, model_cls, entry):
    """Inject a mock registry entry so the generic route can find it."""
    pass


@pytest.fixture
def printing_client(app_factory, bypass_permission_auth):
    with (
        patch(
            "routes.printing.PrintService.render_print",
            return_value="<html>print</html>",
        ) as render_print,
        patch(
            "routes.printing.PrintService.render_pdf", return_value=b"fake-pdf"
        ) as render_pdf,
        patch("routes.printing.PrintService.audit_print") as audit_print,
        patch("routes.printing.PrintService.create_snapshot") as create_snapshot,
        patch(
            "routes.printing.PrintService.bulk_print_documents",
            return_value="<html>bulk</html>",
        ) as bulk_print,
        patch("routes.printing.PrintService._get_model") as get_model,
        patch("routes.printing.branch_scope_id", return_value=None) as branch_scope,
        patch("routes.printing.render_template", return_value="403-page") as render_tpl,
        patch("routes.printing.db.session", MagicMock()) as session,
        patch("routes.printing.InvoiceSettings.get_active") as get_settings,
        patch("routes.printing.PrintHistory") as history_model,
        patch(
            "routes.printing.send_file",
            return_value=Response(b"pdf", mimetype="application/pdf"),
        ) as send_file,
    ):
        settings = MagicMock()
        get_settings.return_value = settings
        history_model.query = _chain_query()
        from routes.printing import printing_bp

        app = app_factory(printing_bp)
        client = app.test_client()
        client._printing_mocks = {
            "render_print": render_print,
            "render_pdf": render_pdf,
            "audit_print": audit_print,
            "create_snapshot": create_snapshot,
            "bulk_print": bulk_print,
            "get_model": get_model,
            "branch_scope": branch_scope,
            "render_tpl": render_tpl,
            "session": session,
            "get_settings": get_settings,
            "history_model": history_model,
            "send_file": send_file,
            "settings": settings,
        }
        yield client


class TestGenericPrint:
    @staticmethod
    def setup_mocks(printing_client, doc_type="purchase", doc=None):
        if doc is None:
            doc = _doc_mock(purchase_number="PO-001")
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(doc)
        mocks["get_model"].return_value = model_cls
        return doc, model_cls

    def test_print_unknown_type_returns_404(self, printing_client):
        resp = printing_client.get("/printing/unknown_doc/1")
        assert resp.status_code == 404

    def test_print_document_returns_200(self, printing_client):
        doc, _ = self.setup_mocks(printing_client, "purchase")
        mocks = printing_client._printing_mocks
        resp = printing_client.get("/printing/purchase/1")
        assert resp.status_code == 200
        mocks["create_snapshot"].assert_called_once()
        mocks["audit_print"].assert_called_once()
        mocks["render_print"].assert_called_once()

    def test_print_document_pdf_download(self, printing_client):
        doc, _ = self.setup_mocks(printing_client, "purchase")
        mocks = printing_client._printing_mocks
        resp = printing_client.get("/printing/purchase/1/pdf")
        assert resp.status_code == 200
        mocks["render_pdf"].assert_called_once()
        mocks["send_file"].assert_called_once()
        mocks["create_snapshot"].assert_called_once()
        mocks["audit_print"].assert_called_once()

    def test_pdf_unknown_type_returns_404(self, printing_client):
        resp = printing_client.get("/printing/unknown_doc/1/pdf")
        assert resp.status_code == 404


class TestPrintExpense:
    @staticmethod
    def setup_mocks(printing_client, doc_type="expense", doc=None):
        if doc is None:
            doc = _doc_mock(expense_number="EX-001")
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(doc)
        mocks["get_model"].return_value = model_cls

    def test_print_expense_returns_200(self, printing_client):
        self.setup_mocks(printing_client, "expense")
        mocks = printing_client._printing_mocks
        resp = printing_client.get("/printing/expense/2")
        assert resp.status_code == 200
        mocks["render_print"].assert_called_once()

    def test_expense_pdf_download(self, printing_client):
        self.setup_mocks(printing_client, "expense")
        mocks = printing_client._printing_mocks
        resp = printing_client.get("/printing/expense/2/pdf")
        assert resp.status_code == 200
        mocks["render_pdf"].assert_called_once()
        mocks["send_file"].assert_called_once()


class TestPrintPayroll:
    def test_salary_slip_returns_200(self, printing_client):
        txn = _doc_mock(id=10, branch_id=1)
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(txn)
        mocks["get_model"].return_value = model_cls
        resp = printing_client.get("/printing/payroll-slip/10")
        assert resp.status_code == 200
        mocks["render_print"].assert_called_once()

    def test_payroll_slip_pdf_download(self, printing_client):
        txn = _doc_mock(id=11, branch_id=1)
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(txn)
        mocks["get_model"].return_value = model_cls
        resp = printing_client.get("/printing/payroll-slip/11/pdf")
        assert resp.status_code == 200
        mocks["render_pdf"].assert_called_once()
        mocks["send_file"].assert_called_once()


class TestPrintCheque:
    def test_print_cheque_returns_200(self, printing_client):
        cheque = _doc_mock(id=5, branch_id=1)
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(cheque)
        mocks["get_model"].return_value = model_cls
        resp = printing_client.get("/printing/cheque/5")
        assert resp.status_code == 200
        mocks["render_print"].assert_called_once()


class TestPackingSlip:
    def test_packing_slip_without_shipment(self, printing_client):
        sale = _doc_mock(id=20, sale_number="S-100", branch_id=1)
        customer = MagicMock()
        customer.address = "Addr"
        customer.name = "Cust"
        customer.phone = "+971500000000"
        sale.customer = customer
        sale.lines = []
        sale.sale_date = datetime.now(timezone.utc)
        mocks = printing_client._printing_mocks
        sale_q = MagicMock()
        sale_q.filter_by.return_value = sale_q
        sale_q.filter.return_value = sale_q
        sale_q.first_or_404.return_value = sale
        ship_q = MagicMock()
        ship_q.filter_by.return_value.first.return_value = None
        with patch("models.Sale") as sale_cls, patch("models.Shipment") as ship_model:
            sale_cls.query = sale_q
            ship_model.query = ship_q
            resp = printing_client.get("/printing/packing-slip/20")
        assert resp.status_code == 200
        ctx = mocks["render_print"].call_args[0][1]
        assert ctx["sale"] is sale
        assert ctx["delivery"].customer_name == "Cust"

    def test_packing_slip_with_shipment(self, printing_client):
        sale = _doc_mock(id=21, sale_number="S-101", branch_id=1)
        sale.customer = None
        sale.lines = [MagicMock()]
        shipment = MagicMock()
        shipment.tracking_number = "TRK-1"
        mocks = printing_client._printing_mocks
        sale_q = MagicMock()
        sale_q.filter_by.return_value = sale_q
        sale_q.filter.return_value = sale_q
        sale_q.first_or_404.return_value = sale
        ship_q = MagicMock()
        ship_q.filter_by.return_value.first.return_value = shipment
        with patch("models.Sale") as sale_cls, patch("models.Shipment") as ship_model:
            sale_cls.query = sale_q
            ship_model.query = ship_q
            resp = printing_client.get("/printing/packing-slip/21")
        assert resp.status_code == 200
        ctx = mocks["render_print"].call_args[0][1]
        assert ctx["delivery"] is shipment


class TestBulkPrint:
    def test_bulk_print_sale_documents(self, printing_client):
        sale = _doc_mock(id=1, branch_id=1)
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query.filter_by.return_value.first.return_value = sale
        mocks["get_model"].return_value = model_cls
        resp = printing_client.post(
            "/printing/bulk-print",
            json={"type": "sale", "ids": [1, 2]},
            content_type="application/json",
        )
        assert resp.status_code == 200
        mocks["bulk_print"].assert_called_once()

    def test_bulk_print_unknown_type_returns_400(self, printing_client):
        resp = printing_client.post(
            "/printing/bulk-print",
            json={"type": "unknown_doc", "ids": [1]},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Unknown document type" in resp.get_json()["error"]


class TestPrintHistory:
    def test_print_history_returns_200(self, printing_client):
        record = MagicMock()
        record.id = 1
        printing_client._printing_mocks["history_model"].query = _chain_query(
            all=[record]
        )
        with patch(
            "routes.printing.render_template", return_value="history-page"
        ) as render:
            resp = printing_client.get("/printing/history")
        assert resp.status_code == 200
        render.assert_called_once()
        assert "printing/history.html" in render.call_args[0][0]

    def test_print_history_pagination(self, printing_client):
        printing_client._printing_mocks["history_model"].query = _chain_query(all=[])
        with patch("routes.printing.render_template", return_value="history-page"):
            resp = printing_client.get("/printing/history?page=2")
        assert resp.status_code == 200


class TestPrintApiPreview:
    def test_preview_missing_params_returns_400(self, printing_client):
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "purchase"},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Missing type or id" in resp.get_json()["error"]

    def test_preview_unsupported_type_returns_400(self, printing_client):
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "unknown_type_xyz", "id": 1},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Unsupported type" in resp.get_json()["error"]

    def test_preview_document_not_found_returns_404(self, printing_client):
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query.filter_by.return_value.first.return_value = None
        mocks["get_model"].return_value = model_cls
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "purchase", "id": 99},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_preview_purchase_success(self, printing_client):
        purchase = _doc_mock(purchase_number="PO-9")
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query.filter_by.return_value.first.return_value = purchase
        mocks["get_model"].return_value = model_cls
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "purchase", "id": 9},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "html" in resp.get_json()

    def test_preview_expense_success(self, printing_client):
        expense = _doc_mock(expense_number="EX-PREV")
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query.filter_by.return_value.first.return_value = expense
        mocks["get_model"].return_value = model_cls
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "expense", "id": 2},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "html" in resp.get_json()

    def test_preview_cheque_success(self, printing_client):
        cheque = _doc_mock(id=7)
        mocks = printing_client._printing_mocks
        model_cls = MagicMock()
        model_cls.query.filter_by.return_value.first.return_value = cheque
        mocks["get_model"].return_value = model_cls
        resp = printing_client.post(
            "/printing/api/preview",
            json={"type": "cheque", "id": 7},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "html" in resp.get_json()


class TestPrintApiHistory:
    def test_api_print_history_returns_json(self, printing_client):
        record = MagicMock()
        record.id = 1
        record.document_type = "purchase"
        record.document_id = 5
        record.action = "print"
        record.created_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        record.user = MagicMock(full_name="Tester")
        hist_q = MagicMock()
        hist_q.filter_by.return_value = hist_q
        hist_q.order_by.return_value.limit.return_value.all.return_value = [record]
        printing_client._printing_mocks["history_model"].query = hist_q
        resp = printing_client.get("/printing/api/print-history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["document_type"] == "purchase"
        assert data[0]["user_name"] == "Tester"

    def test_api_print_history_with_limit(self, printing_client):
        hist_q = MagicMock()
        hist_q.filter_by.return_value = hist_q
        hist_q.order_by.return_value.limit.return_value.all.return_value = []
        printing_client._printing_mocks["history_model"].query = hist_q
        resp = printing_client.get("/printing/api/print-history?limit=5")
        assert resp.status_code == 200
        hist_q.order_by.return_value.limit.assert_called_with(5)


class TestPrintSettings:
    def test_settings_get_returns_200(self, printing_client):
        with patch(
            "routes.printing.render_template", return_value="settings-page"
        ) as render:
            resp = printing_client.get("/printing/settings")
        assert resp.status_code == 200
        render.assert_called_once()
        assert "printing/settings.html" in render.call_args[0][0]

    def test_settings_post_saves_and_redirects(self, printing_client):
        settings = printing_client._printing_mocks["settings"]
        resp = printing_client.post(
            "/printing/settings",
            data={
                "paper_size": "A4",
                "orientation": "landscape",
                "active_template": "modern",
                "header_color": "#111111",
                "accent_color": "#222222",
                "show_logo": "on",
                "enable_qr_code": "on",
            },
        )
        assert resp.status_code in (302, 303)
        assert settings.paper_size == "A4"
        assert settings.orientation == "landscape"
        printing_client._printing_mocks["session"].commit.assert_called_once()


class TestPrintingBranchScope:
    def test_purchase_branch_scope_403(self, printing_client):
        purchase = _doc_mock(branch_id=5, purchase_number="PO-X")
        mocks = printing_client._printing_mocks
        mocks["branch_scope"].return_value = 2
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(purchase)
        mocks["get_model"].return_value = model_cls
        resp = printing_client.get("/printing/purchase/1")
        assert resp.status_code == 403
        mocks["render_print"].assert_not_called()

    def test_expense_branch_scope_403(self, printing_client):
        expense = _doc_mock(branch_id=8, expense_number="EX-X")
        mocks = printing_client._printing_mocks
        mocks["branch_scope"].return_value = 3
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(expense)
        mocks["get_model"].return_value = model_cls
        resp = printing_client.get("/printing/expense/1")
        assert resp.status_code == 403

    def test_packing_slip_branch_scope_403(self, printing_client):
        sale = _doc_mock(id=1, branch_id=6, sale_number="S-1")
        sale.customer = None
        sale.lines = []
        mocks = printing_client._printing_mocks
        mocks["branch_scope"].return_value = 1
        sale_q = MagicMock()
        sale_q.filter_by.return_value = sale_q
        sale_q.filter.return_value = sale_q
        sale_q.first_or_404.return_value = sale
        ship_q = MagicMock()
        ship_q.filter_by.return_value.first.return_value = None
        with patch("models.Sale") as sale_cls, patch("models.Shipment") as ship_model:
            sale_cls.query = sale_q
            ship_model.query = ship_q
            resp = printing_client.get("/printing/packing-slip/1")
        assert resp.status_code == 403


class TestPrintingAuth:
    def test_unauthenticated_print_purchase(self, printing_client):
        with unauthenticated_client(printing_client):
            resp = printing_client.get("/printing/purchase/1")
            assert resp.status_code in (302, 401)


class TestPrintingCoverageGaps:
    def test_purchase_pdf_branch_scope_403(self, printing_client):
        purchase = _doc_mock(branch_id=5, purchase_number="PO-PDF")
        mocks = printing_client._printing_mocks
        mocks["branch_scope"].return_value = 2
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(purchase)
        mocks["get_model"].return_value = model_cls
        resp = printing_client.get("/printing/purchase/1/pdf")
        assert resp.status_code == 403

    def test_expense_pdf_branch_scope_403(self, printing_client):
        expense = _doc_mock(branch_id=8, expense_number="EX-PDF")
        mocks = printing_client._printing_mocks
        mocks["branch_scope"].return_value = 3
        model_cls = MagicMock()
        model_cls.query = _model_query_chain(expense)
        mocks["get_model"].return_value = model_cls
        resp = printing_client.get("/printing/expense/2/pdf")
        assert resp.status_code == 403

    def test_packing_slip_shipment_import_error(self, printing_client):
        sale = _doc_mock(id=22, sale_number="S-102", branch_id=1)
        sale.customer = None
        sale.lines = []
        sale.sale_date = datetime.now(timezone.utc)
        sale_q = MagicMock()
        sale_q.filter_by.return_value = sale_q
        sale_q.filter.return_value = sale_q
        sale_q.first_or_404.return_value = sale
        with patch("models.Sale") as sale_cls:
            sale_cls.query = sale_q
            import builtins

            real_import = builtins.__import__

            def _import_shim(
                name, globals_dict=None, locals_dict=None, fromlist=(), level=0
            ):
                if name == "models" and fromlist and "Shipment" in fromlist:
                    raise ImportError("Shipment unavailable")
                return real_import(name, globals_dict, locals_dict, fromlist, level)

            with patch("builtins.__import__", side_effect=_import_shim):
                resp = printing_client.get("/printing/packing-slip/22")
        assert resp.status_code == 200

    def test_bulk_print_unknown_template_type_returns_400(self, printing_client):
        resp = printing_client.post(
            "/printing/bulk-print",
            json={"type": "unknown_type_xyz", "ids": [1]},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Unknown document type" in resp.get_json()["error"]
