"""Coverage-99 boost for routes/purchases.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def pur_client(app_factory, bypass_permission_auth):
    from routes.purchases import purchases_bp

    app = app_factory(purchases_bp)
    return app.test_client()


def _purchase():
    p = MagicMock()
    p.id = 5
    p.tenant_id = 1
    p.branch_id = None
    p.purchase_number = "PU5"
    p.supplier_id = 9
    p.amount_aed = 100
    p.get_paid_amount.return_value = 0
    return p


class TestSafeFloat:
    def test_branches(self, pur_client):
        from routes.purchases import safe_float

        assert safe_float(None) == 0.0
        assert safe_float("") == 0.0
        assert safe_float("  ") == 0.0
        assert safe_float("1.5") == 1.5
        assert safe_float("bad") == 0.0
        assert safe_float(None, default=2.0) == 2.0


class TestCreate:
    def test_no_warehouse(self, pur_client):
        resp = pur_client.post("/purchases/create", data={})
        assert resp.status_code in (200, 302, 303)

    def test_with_lines_and_currency_fallback(self, pur_client):
        from services.purchase_service import PurchaseService

        purchase = MagicMock(id=21)
        with (
            patch("routes.purchases.ensure_warehouse_access", return_value=None),
            patch("routes.purchases.resolve_default_currency", side_effect=RuntimeError("x")),
            patch("routes.purchases.get_system_default_currency", return_value="AED"),
            patch.object(PurchaseService, "create_purchase", return_value=purchase),
            patch("routes.purchases.db.session"),
        ):
            resp = pur_client.post(
                "/purchases/create",
                data={
                    "warehouse_id": "3",
                    "line_count": "2",
                    "lines[0][product_id]": "10",
                    "lines[0][quantity]": "2",
                    "lines[0][unit_cost]": "5",
                    "lines[0][discount_percent]": "bad",
                    "lines[0][serials]": "S1\nS2\n",
                    "lines[1][product_id]": "",
                    "lines[1][quantity]": "0",
                },
            )
        assert resp.status_code in (200, 302, 303)

    def test_create_value_error(self, pur_client):
        from services.purchase_service import PurchaseService

        with (
            patch("routes.purchases.ensure_warehouse_access", return_value=None),
            patch("routes.purchases.resolve_default_currency", return_value="AED"),
            patch.object(PurchaseService, "create_purchase", side_effect=ValueError("bad lines")),
            patch("routes.purchases.render_template", return_value="form"),
        ):
            resp = pur_client.post("/purchases/create", data={"warehouse_id": "3", "line_count": "0"})
        assert resp.status_code == 200

    def test_create_generic_error(self, pur_client):
        from services.purchase_service import PurchaseService

        with (
            patch("routes.purchases.ensure_warehouse_access", return_value=None),
            patch("routes.purchases.resolve_default_currency", return_value="AED"),
            patch.object(PurchaseService, "create_purchase", side_effect=RuntimeError("boom")),
            patch("routes.purchases.render_template", return_value="form"),
        ):
            resp = pur_client.post("/purchases/create", data={"warehouse_id": "3", "line_count": "0"})
        assert resp.status_code == 200

    def test_create_get_currency_fallback(self, pur_client):
        with (
            patch("routes.purchases.resolve_default_currency", side_effect=RuntimeError("x")),
            patch("routes.purchases.get_system_default_currency", return_value="AED"),
            patch("services.currency_service.CurrencyService.get_all_rates", return_value={}),
            patch("routes.purchases.get_accessible_warehouses", return_value=[]),
            patch("utils.tax_settings.get_prices_include_vat", return_value=False),
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.get_active_branch_id", return_value=None),
            patch("routes.purchases.render_template", return_value="form"),
        ):
            assert pur_client.get("/purchases/create").status_code == 200


class TestViewPrintEdit:
    def test_view_branch_mismatch(self, pur_client):
        p = _purchase()
        p.branch_id = 8
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=9),
            patch("routes.purchases.render_template", return_value="denied"),
        ):
            assert pur_client.get("/purchases/5").status_code == 403

    def test_print_qr_branches(self, pur_client):
        from models.invoice_settings import InvoiceSettings

        p = _purchase()
        settings = MagicMock(enable_qr_code=True)
        ver = MagicMock(public_token="tok")
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch.object(InvoiceSettings, "company_print_context", return_value=(None, settings, None)),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch(
                "services.document_verification_service.DocumentVerificationService.get_or_create_verification",
                return_value=ver,
            ),
            patch("routes.purchases.url_for", return_value="/verify/tok"),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/5/print").status_code == 200
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch.object(InvoiceSettings, "company_print_context", return_value=(None, settings, None)),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch(
                "services.document_verification_service.DocumentVerificationService.get_or_create_verification",
                return_value=None,
            ),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/5/print").status_code == 200

    def test_edit_paid_and_mismatch(self, pur_client):
        paid = _purchase()
        paid.get_paid_amount.return_value = 50
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=paid),
            patch("utils.decorators.branch_scope_id", return_value=None),
        ):
            assert pur_client.post("/purchases/5/edit", data={}).status_code in (200, 302)
        other = _purchase()
        other.branch_id = 8
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=other),
            patch("utils.decorators.branch_scope_id", return_value=9),
            patch("routes.purchases.render_template", return_value="denied"),
        ):
            assert pur_client.get("/purchases/5/edit").status_code == 403

    def test_edit_post_and_error(self, pur_client):
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=_purchase()),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.purchases.db.session"),
        ):
            assert pur_client.post("/purchases/5/edit", data={"notes": "n"}).status_code in (
                200,
                302,
            )
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=_purchase()),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.purchases.db.session.commit", side_effect=RuntimeError("x")),
            patch("routes.purchases.render_template", return_value="form"),
        ):
            assert pur_client.post("/purchases/5/edit", data={"notes": "n"}).status_code == 200


class TestDelete:
    def _purchase_with(self, paid=0, cheques=0, stock=False, supplier=None):
        from services.purchase_service import PurchaseService

        p = _purchase()
        p.get_paid_amount.return_value = paid
        return p, PurchaseService, cheques, stock, supplier

    def test_delete_with_links(self, pur_client):
        from services.purchase_service import PurchaseService

        p = _purchase()
        p.get_paid_amount.return_value = 10
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch.object(PurchaseService, "count_linked_cheques", return_value=1),
            patch.object(PurchaseService, "has_stock_movements", return_value=False),
            patch("services.archive_service.ArchiveService.archive_record", return_value=None),
            patch("routes.purchases.db.session"),
        ):
            assert pur_client.post("/purchases/5/delete").status_code in (200, 302)

    def test_delete_with_stock(self, pur_client):
        from services.purchase_service import PurchaseService

        p = _purchase()
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch.object(PurchaseService, "count_linked_cheques", return_value=0),
            patch.object(PurchaseService, "has_stock_movements", return_value=True),
            patch("services.archive_service.ArchiveService.archive_record", return_value=None),
            patch("routes.purchases.db.session"),
        ):
            assert pur_client.post("/purchases/5/delete").status_code in (200, 302)

    def test_delete_full_with_supplier(self, pur_client):
        from services.purchase_service import PurchaseService

        p = _purchase()
        supplier = MagicMock()
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch.object(PurchaseService, "count_linked_cheques", return_value=0),
            patch.object(PurchaseService, "has_stock_movements", return_value=False),
            patch.object(PurchaseService, "get_tenant_supplier", return_value=supplier),
            patch.object(PurchaseService, "delete_purchase", return_value=None),
            patch("services.gl_service.GLService.reverse_entry", return_value=None),
            patch("routes.purchases.db.session"),
        ):
            assert pur_client.post("/purchases/5/delete").status_code in (200, 302)

    def test_delete_full_no_supplier(self, pur_client):
        from services.purchase_service import PurchaseService

        p = _purchase()
        p.supplier_id = None
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch.object(PurchaseService, "count_linked_cheques", return_value=0),
            patch.object(PurchaseService, "has_stock_movements", return_value=False),
            patch.object(PurchaseService, "delete_purchase", return_value=None),
            patch("services.gl_service.GLService.reverse_entry", return_value=None),
            patch("routes.purchases.db.session"),
        ):
            assert pur_client.post("/purchases/5/delete").status_code in (200, 302)


class TestRequisitions:
    def test_list(self, pur_client):
        from services.purchase_service import PurchaseService

        with (
            patch.object(PurchaseService, "list_requisitions", return_value=[]),
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/requisitions").status_code == 200

    def test_create_ok_and_error(self, pur_client):
        from services.procurement_service import ProcurementService
        from services.purchase_service import PurchaseService

        with (
            patch.object(ProcurementService, "create_requisition", return_value=MagicMock()),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            resp = pur_client.post(
                "/purchases/requisitions/create",
                data={"line_0_product_id": "1", "line_0_quantity": "2"},
            )
            assert resp.status_code in (200, 302)
        with (
            patch.object(ProcurementService, "create_requisition", side_effect=ValueError("bad")),
            patch.object(PurchaseService, "list_active_products", return_value=[]),
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.post("/purchases/requisitions/create", data={}).status_code == 200

    def test_submit_approve_reject(self, pur_client):
        from services.procurement_service import ProcurementService

        pr = MagicMock()
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=pr),
            patch.object(ProcurementService, "submit_requisition", return_value=None),
        ):
            assert pur_client.post("/purchases/requisitions/1/submit").status_code in (200, 302)
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=pr),
            patch.object(ProcurementService, "submit_requisition", side_effect=ValueError("bad")),
        ):
            assert pur_client.post("/purchases/requisitions/1/submit").status_code in (200, 302)
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=pr),
            patch.object(ProcurementService, "approve_requisition", return_value=None),
        ):
            assert pur_client.post("/purchases/requisitions/1/approve").status_code in (200, 302)
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=pr),
            patch.object(ProcurementService, "approve_requisition", side_effect=ValueError("bad")),
        ):
            assert pur_client.post("/purchases/requisitions/1/approve").status_code in (200, 302)
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=pr),
            patch.object(ProcurementService, "reject_requisition", return_value=None),
        ):
            assert pur_client.post("/purchases/requisitions/1/reject", data={"reason": "r"}).status_code in (200, 302)
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=pr),
            patch.object(ProcurementService, "reject_requisition", side_effect=ValueError("bad")),
        ):
            assert pur_client.post("/purchases/requisitions/1/reject").status_code in (200, 302)


class TestGrn:
    def test_list(self, pur_client):
        from services.purchase_service import PurchaseService

        with (
            patch.object(PurchaseService, "list_goods_receipts", return_value=[]),
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/grn").status_code == 200

    def test_create_ok_and_error(self, pur_client):
        from services.procurement_service import ProcurementService
        from services.purchase_service import PurchaseService

        with patch.object(ProcurementService, "create_grn", return_value=MagicMock()):
            assert pur_client.post(
                "/purchases/grn/create",
                data={"po_id": "3", "line_0_po_line_id": "1", "line_0_received_quantity": "2"},
            ).status_code in (200, 302)
        with (
            patch.object(ProcurementService, "create_grn", side_effect=KeyError("k")),
            patch.object(PurchaseService, "list_receivable_purchase_orders", return_value=[]),
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.post("/purchases/grn/create", data={"po_id": "3"}).status_code == 200

    def test_confirm_ok_and_error(self, pur_client):
        from services.procurement_service import ProcurementService

        grn = MagicMock()
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=grn),
            patch.object(ProcurementService, "confirm_grn", return_value=None),
        ):
            assert pur_client.post("/purchases/grn/1/confirm").status_code in (200, 302)
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=grn),
            patch.object(ProcurementService, "confirm_grn", side_effect=ValueError("bad")),
        ):
            assert pur_client.post("/purchases/grn/1/confirm").status_code in (200, 302)


class TestMatch:
    def test_ok_and_error(self, pur_client):
        from services.procurement_service import ProcurementService

        with (
            patch.object(ProcurementService, "three_way_match", return_value={"ok": True}),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/match/4?invoice_amount=100").status_code == 200
        with (
            patch.object(ProcurementService, "three_way_match", side_effect=ValueError("mismatch")),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/match/4").status_code == 200


class TestRemainingArcs:
    def test_print_qr_disabled(self, pur_client):
        from models.invoice_settings import InvoiceSettings

        p = _purchase()
        settings = MagicMock(enable_qr_code=False)
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch.object(InvoiceSettings, "company_print_context", return_value=(None, settings, None)),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/5/print").status_code == 200

    def test_delete_supplier_none(self, pur_client):
        from services.purchase_service import PurchaseService

        p = _purchase()
        with (
            patch("routes.purchases.tenant_get_or_404", return_value=p),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch.object(PurchaseService, "count_linked_cheques", return_value=0),
            patch.object(PurchaseService, "has_stock_movements", return_value=False),
            patch.object(PurchaseService, "get_tenant_supplier", return_value=None),
            patch.object(PurchaseService, "delete_purchase", return_value=None),
            patch("services.gl_service.GLService.reverse_entry", return_value=None),
            patch("routes.purchases.db.session"),
        ):
            assert pur_client.post("/purchases/5/delete").status_code in (200, 302)

    def test_requisition_get(self, pur_client):
        from services.purchase_service import PurchaseService

        with (
            patch.object(PurchaseService, "list_active_products", return_value=[]),
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/requisitions/create").status_code == 200

    def test_grn_get(self, pur_client):
        from services.purchase_service import PurchaseService

        with (
            patch.object(PurchaseService, "list_receivable_purchase_orders", return_value=[]),
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.render_template", return_value="ok"),
        ):
            assert pur_client.get("/purchases/grn/create").status_code == 200
