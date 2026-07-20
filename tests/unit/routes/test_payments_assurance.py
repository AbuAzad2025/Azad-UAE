"""Supplementary assurance tests for routes/payments.py (>=99% coverage target)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.test_payments_routes import (
    _mock_payment,
    _mock_receipt,
    _payments_patches,
    _pm,
)


@pytest.fixture
def payments_client(app_factory, bypass_permission_auth):
    from routes.payments import payments_bp
    from routes.public import public_bp

    app = app_factory(payments_bp, public_bp)
    return app.test_client()


class TestPaymentHelperAssurance:
    def test_in_scope_branch_matches(self):
        with patch("utils.decorators.branch_scope_id", return_value=5):
            assert _pm()._in_scope_branch(5) is True

    def test_current_branch_id_with_default(self):
        with patch("utils.decorators.branch_scope_id", return_value=None):
            assert _pm()._current_branch_id(default=7) == 7
        with patch("utils.decorators.branch_scope_id", return_value=3):
            assert _pm()._current_branch_id(default=7) == 3

    def test_archived_item_branch_id_non_dict_data(self):
        assert _pm()._archived_item_branch_id(MagicMock(data="not-a-dict")) is None

    def test_ensure_customer_scope_returns_customer(self, mocker):
        customer = MagicMock(id=1)
        q = MagicMock()
        q.filter.return_value.first.return_value = customer
        mocker.patch("routes.payments._scoped_customers_query", return_value=q)
        assert _pm()._ensure_customer_scope(1) is customer

    def test_ensure_supplier_scope_returns_supplier(self, mocker):
        supplier = MagicMock(id=2)
        q = MagicMock()
        q.filter.return_value.first.return_value = supplier
        mocker.patch("routes.payments._scoped_suppliers_query", return_value=q)
        assert _pm()._ensure_supplier_scope(2) is supplier

    def test_scoped_customer_balance(self, mocker):
        mocker.patch("routes.payments._current_branch_id", return_value=4)
        mocker.patch(
            "routes.payments.PaymentService.get_customer_balance_scoped",
            return_value=Decimal("123.45"),
        )
        assert _pm()._scoped_customer_balance(10) == 123.45

    def test_scoped_customers_query_unscoped(self, mocker):
        base_q = MagicMock()
        active_q = MagicMock()
        base_q.filter.return_value = active_q
        mocker.patch("routes.payments.tenant_query", return_value=base_q)
        with patch("utils.decorators.branch_scope_id", return_value=None):
            result = _pm()._scoped_customers_query()
        assert result is active_q
        base_q.filter.assert_called_once()

    def test_scoped_suppliers_query_unscoped(self, mocker):
        base_q = MagicMock()
        active_q = MagicMock()
        base_q.filter.return_value = active_q
        mocker.patch("routes.payments.tenant_query", return_value=base_q)
        with patch("utils.decorators.branch_scope_id", return_value=None):
            result = _pm()._scoped_suppliers_query()
        assert result is active_q
        base_q.filter.assert_called_once()

    def test_receipt_item_status_pending_and_completed(self):
        assert _pm()._receipt_item_status({"payment_confirmed": False}) == "PENDING"
        assert _pm()._receipt_item_status({"payment_confirmed": True}) == "COMPLETED"

    def test_build_receipts_json_outgoing_totals(self, app_factory):
        from routes.payments import payments_bp, _build_receipts_json_response

        app = app_factory(payments_bp)
        items = [
            {
                "id": 1,
                "type": "payment",
                "number": "P1",
                "date": None,
                "amount": Decimal("80"),
                "currency": "AED",
                "payment_method": "cash",
                "direction": "outgoing",
                "payment_confirmed": False,
                "notes": None,
                "customer_name": None,
                "supplier_name": "Vendor X",
                "source_type": "bill_payment",
            },
            {
                "id": 2,
                "type": "receipt",
                "number": "R1",
                "date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "amount": Decimal("20"),
                "currency": "AED",
                "payment_method": "cash",
                "direction": "incoming",
                "payment_confirmed": True,
                "notes": "note",
                "customer_name": "Ali",
                "supplier_name": None,
                "source_type": "manual",
            },
        ]
        pag = MagicMock(page=2, pages=3)
        with app.test_request_context():
            data = _build_receipts_json_response(items, pag).get_json()
        assert data["totals"]["total_outgoing"] == 80.0
        assert data["totals"]["total_incoming"] == 20.0
        assert data["totals"]["grand_total"] == 100.0
        assert data["totals"]["net_total"] == -60.0
        assert data["payments"][0]["status"] == "PENDING"
        assert data["payments"][0]["entity_display"] == "Vendor X"
        assert data["payments"][0]["payment_date"] is None
        assert data["current_page"] == 2
        assert data["total_pages"] == 3


class TestVoucherSubmitAssurance:
    def test_create_voucher_preselects_customer_id(self, payments_client):
        cq = MagicMock()
        cq.order_by.return_value.all.return_value = []
        sq = MagicMock()
        sq.order_by.return_value.all.return_value = []
        with (
            patch("routes.payments._scoped_customers_query", return_value=cq),
            patch("routes.payments._scoped_suppliers_query", return_value=sq),
            patch("routes.payments.render_template", return_value="ok") as render,
        ):
            payments_client.get("/payments/voucher/create?customer_id=99&amount=10")
        _, kwargs = render.call_args
        assert kwargs["preselected_party_id"] == 99

    def test_voucher_incoming_supplier_out_of_scope(self, payments_client):
        with _payments_patches(supplier=None):
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "supplier",
                    "party_id": "2",
                    "amount": "50",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_voucher_outgoing_customer_out_of_scope(self, payments_client):
        with _payments_patches(customer=None):
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "outgoing",
                    "party_type": "customer",
                    "party_id": "1",
                    "amount": "50",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_voucher_incoming_supplier_cheque(self, payments_client, mocker):
        supplier = MagicMock(id=2, name="Sup", tenant_id=1)
        supplier.apply_payment = MagicMock()
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-IN-CHQ")
        mocker.patch("routes.payments.post_or_fail")
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_service.GLService.get_payment_debit_account",
            return_value="1101",
        )
        mocker.patch(
            "services.gl_service.GLService.get_payment_debit_concept",
            return_value="CASH",
        )
        payment_inst = MagicMock(id=61, amount=Decimal("60"), amount_aed=Decimal("60"))
        payment_cls = mocker.patch("routes.payments.Payment", return_value=payment_inst)
        with (
            _payments_patches(supplier=supplier),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "supplier",
                    "party_id": "2",
                    "amount": "60",
                    "payment_method": "cheque",
                    "cheque_number": "IN-CHQ-1",
                    "cheque_date": "2026-08-01",
                    "bank_name": "ADIB",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        _, kwargs = payment_cls.call_args
        assert kwargs["cheque_number"] == "IN-CHQ-1"

    def test_voucher_invalid_direction_fallback(self, payments_client):
        resp = payments_client.post(
            "/payments/voucher/submit",
            data={
                "direction": "sideways",
                "party_type": "customer",
                "party_id": "1",
                "amount": "10",
                "payment_method": "cash",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/payments/receipts" in resp.location or resp.location.endswith("/receipts")


class TestCreateFromSaleAndPaymentAssurance:
    def test_create_from_sale_branch_forbidden(self, payments_client):
        sale = MagicMock(
            branch_id=9,
            customer_id=1,
            balance_due=Decimal("100"),
            exchange_rate=1,
            currency="AED",
        )
        with (
            patch("routes.payments.tenant_get_or_404", return_value=sale),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            resp = payments_client.get("/payments/create_from_sale/5")
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_create_from_sale_foreign_currency_get(self, payments_client):
        sale = MagicMock(
            branch_id=1,
            customer_id=1,
            customer=MagicMock(),
            balance_due=Decimal("367"),
            exchange_rate=Decimal("3.67"),
            currency="USD",
        )
        with (
            patch("routes.payments.tenant_get_or_404", return_value=sale),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
        ):
            resp = payments_client.get("/payments/create_from_sale/5", follow_redirects=False)
        assert resp.status_code == 302
        assert "amount=100" in resp.location or "amount=100.0" in resp.location

    def test_create_from_sale_post_exception(self, payments_client, mocker):
        sale = MagicMock(
            branch_id=1,
            customer_id=1,
            customer=MagicMock(),
            balance_due=Decimal("100"),
            exchange_rate=1,
            currency="AED",
            id=5,
        )
        mocker.patch("routes.payments.tenant_get_or_404", return_value=sale)
        mocker.patch(
            "routes.payments.PaymentService.create_receipt",
            side_effect=RuntimeError("create fail"),
        )
        with patch("utils.decorators.branch_scope_id", return_value=None):
            resp = payments_client.post(
                "/payments/create_from_sale/5",
                data={
                    "amount": "50",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_payment_branch_forbidden(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=9,
            supplier_id=2,
            amount_aed=Decimal("500"),
            exchange_rate=1,
            currency="AED",
        )
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.db.session.query")
        with (
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            resp = payments_client.get("/payments/create_payment/8")
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_create_payment_foreign_currency_get(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            tenant_id=1,
            amount_aed=Decimal("367"),
            exchange_rate=Decimal("3.67"),
            currency="USD",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
        ):
            resp = payments_client.get("/payments/create_payment/8", follow_redirects=False)
        assert resp.status_code == 302
        assert "currency=USD" in resp.location

    def test_create_payment_missing_method_renders_form(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=1,
            currency="AED",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="form") as render,
        ):
            resp = payments_client.post("/payments/create_payment/8", data={"amount": "50"})
        assert resp.status_code == 200
        render.assert_called_once()

    def test_create_payment_currency_exception_fallback(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=1,
            currency="",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        mocker.patch(
            "routes.payments.resolve_default_currency",
            side_effect=RuntimeError("curr fail"),
        )
        mocker.patch("routes.payments.LoggingCore.log_error")
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="form") as render,
            patch("routes.payments.db.session") as session,
        ):
            session.rollback = MagicMock()
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "25",
                    "payment_method": "cash",
                    "currency": "AED",
                },
            )
        assert resp.status_code == 200
        render.assert_called_once()
        session.rollback.assert_called()


class TestReceiptViewPrintAssurance:
    def test_view_receipt_not_found(self, payments_client):
        with patch("routes.payments.tenant_get", return_value=None):
            resp = payments_client.get("/payments/receipts/404")
        assert resp.status_code == 404

    def test_print_receipt_redirects_to_payment(self, payments_client):
        payment = _mock_payment()
        with patch("routes.payments.tenant_get", side_effect=[None, payment]):
            resp = payments_client.get("/payments/receipts/99/print", follow_redirects=False)
        assert resp.status_code == 302

    def test_print_receipt_seller_forbidden(self, payments_client, bypass_permission_auth):
        receipt = _mock_receipt(user_id=99, branch_id=1)
        bypass_permission_auth.is_seller = MagicMock(return_value=True)
        bypass_permission_auth.is_owner = False
        bypass_permission_auth.id = 1
        with (
            patch("routes.payments.tenant_get", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_client.get("/payments/receipts/1/print", follow_redirects=False)
        assert resp.status_code == 302

    def test_print_receipt_sale_branch_ok(self, payments_client):
        receipt = _mock_receipt(branch_id=1, source_type="sale", source_id=10, user_id=42)
        sale = MagicMock(branch_id=1)
        settings = MagicMock(active_template="modern", enable_qr_code=False)
        with (
            patch("routes.payments.tenant_get", side_effect=[receipt, sale]),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.InvoiceSettings.get_active", return_value=settings),
            patch(
                "routes.payments.InvoiceSettings.company_print_context",
                return_value=(MagicMock(name_ar="Co"), settings, {}),
            ),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.payments.number_to_arabic_words", return_value="مائة"),
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("models.Branch") as branch_q,
            patch("routes.payments.render_template", return_value="ok") as render,
        ):
            branch_q.query.filter_by.return_value.first.return_value = MagicMock(name="Branch")
            resp = payments_client.get("/payments/receipts/1/print")
        assert resp.status_code == 200
        render.assert_called_once()

    def test_print_payment_branch_forbidden(self, payments_client):
        payment = _mock_payment(branch_id=9)
        with (
            _payments_patches(payment=payment, branch_scope=1),
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            resp = payments_client.get("/payments/payments/2/print")
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")


class TestArchiveRestoreDeleteAssurance:
    def test_archived_skips_out_of_scope(self, payments_client):
        in_scope = MagicMock(
            record_id=1,
            data={
                "receipt_number": "R1",
                "receipt_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "amount": "50",
                "currency": "AED",
                "amount_aed": "50",
                "customer_name": "X",
                "source_type": "manual",
                "branch_id": 1,
            },
            archived_at=datetime.now(timezone.utc),
        )
        out_scope = MagicMock(
            record_id=2,
            data={"branch_id": 99, "receipt_number": "R2", "amount": "10"},
            archived_at=datetime.now(timezone.utc),
        )
        q = MagicMock()
        q.filter.return_value = q
        q.all.side_effect = [[in_scope, out_scope], []]

        def render_side_effect(template, **ctx):
            assert len(ctx["archived_items"]) == 1
            assert ctx["archived_items"][0]["number"] == "R1"
            return "ok"

        with (
            patch("routes.payments.db.session.query", return_value=q),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", side_effect=render_side_effect),
        ):
            resp = payments_client.get("/payments/archived")
        assert resp.status_code == 200

    def test_restore_receipt_forbidden(self, payments_client):
        archived = MagicMock(data={"branch_id": 9})
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.first_or_404.return_value = archived
        with (
            patch("models.ArchivedRecord") as ar,
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            ar.query = q
            resp = payments_client.post("/payments/receipts/3/restore", follow_redirects=False)
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_restore_payment_forbidden(self, payments_client):
        archived = MagicMock(data={"branch_id": 9})
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.first_or_404.return_value = archived
        with (
            patch("models.ArchivedRecord") as ar,
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            ar.query = q
            resp = payments_client.post("/payments/payments/4/restore", follow_redirects=False)
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_archive_receipt_forbidden(self, payments_client):
        receipt = _mock_receipt(branch_id=9)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            resp = payments_client.post("/payments/receipts/1/archive", follow_redirects=False)
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_archive_payment_forbidden(self, payments_client):
        payment = _mock_payment(branch_id=9)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            resp = payments_client.post("/payments/payments/2/archive", follow_redirects=False)
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_delete_receipt_forbidden(self, payments_client):
        receipt = _mock_receipt(branch_id=9)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_delete_payment_forbidden(self, payments_client):
        payment = _mock_payment(branch_id=9)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            resp = payments_client.post("/payments/payments/2/delete", follow_redirects=False)
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_delete_receipt_hard_delete_with_cheque(self, payments_client, mocker):
        receipt = _mock_receipt(branch_id=1, source_type="manual", source_id=None, cheque_id=None)
        cheque = MagicMock()
        receipt.cheque = cheque
        mocker.patch("services.gl_service.GLService.reverse_entry")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.db.session") as session,
        ):
            session.delete = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        session.delete.assert_any_call(cheque)

    def test_delete_receipt_hard_delete_marks_sale_unpaid(self, payments_client, mocker):
        receipt = _mock_receipt(branch_id=1, source_type="sale", source_id=5, cheque_id=None)
        receipt.amount = Decimal("150")
        receipt.amount_aed = Decimal("150")
        sale = MagicMock(
            paid_amount=Decimal("150"),
            paid_amount_aed=Decimal("150"),
            amount_aed=Decimal("150"),
            balance_due=Decimal("0"),
        )
        mocker.patch("services.gl_service.GLService.reverse_entry")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("models.Sale") as sale_model,
            patch("routes.payments.db.session") as session,
        ):
            sale_model.query.filter_by.return_value.first.return_value = sale
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert sale.payment_status == "unpaid"

    def test_delete_payment_exception(self, payments_client, mocker):
        payment = _mock_payment(cheque_id=None, branch_id=1)
        mocker.patch(
            "services.gl_service.GLService.reverse_entry",
            side_effect=RuntimeError("gl fail"),
        )
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
        ):
            resp = payments_client.post("/payments/payments/2/delete", follow_redirects=False)
        assert resp.status_code == 302


class TestApiCustomerBalanceAssurance:
    def test_api_customer_balance_foreign_conversion(self, payments_client):
        customer = MagicMock(id=1)
        sale = MagicMock(
            id=10,
            sale_number="S-FX",
            sale_date=datetime(2026, 1, 1),
            total_amount=Decimal("367"),
            balance_due=Decimal("367"),
            exchange_rate=Decimal("3.67"),
            currency="USD",
        )
        with (
            _payments_patches(customer=customer),
            patch("routes.payments._scoped_customer_unpaid_sales", return_value=[sale]),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("routes.payments.resolve_default_currency", return_value="AED"),
        ):
            body = payments_client.get("/payments/api/customer-balance/1").get_json()
        row = body["unpaid_sales"][0]
        assert row["currency"] == "USD"
        assert row["balance_due_aed"] == 367.0
        assert abs(row["balance_due"] - 100.0) < 0.01


class TestReceiptsListAssurance:
    def test_receipts_no_branch_labels(self, payments_client):
        receipt = _mock_receipt()
        receipt.branch = None
        payment = _mock_payment()
        payment.branch = None
        with _payments_patches(receipts=[receipt], payments=[payment]):
            resp = payments_client.get("/payments/receipts")
        assert resp.status_code == 200

    def test_search_customers_with_query(self, payments_client):
        customer = SimpleNamespace(id=1, name="Ali", phone="050", email="a@t.com")
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.limit.return_value.all.return_value = [customer]
        with patch("routes.payments._scoped_customers_query", return_value=q):
            data = payments_client.get("/payments/search-entities?type=customers&q=Ali").get_json()
        assert data[0]["display"] == "Ali - 050"


class TestPaymentsGapCoverage:
    def test_receipts_pagination_iter_pages_ellipsis(self, payments_client):
        receipts = [
            _mock_receipt(
                id=i,
                receipt_number=f"R{i}",
                receipt_date=datetime(2026, 1, i if i < 29 else 28),
            )
            for i in range(1, 30)
        ]
        with _payments_patches(receipts=receipts, payments=[]):
            resp = payments_client.get("/payments/receipts?page=15")
        assert resp.status_code == 200

    def test_print_receipt_not_found_aborts(self, payments_client):
        with patch("routes.payments.tenant_get", return_value=None):
            resp = payments_client.get("/payments/receipts/404/print")
        assert resp.status_code == 404

    def test_print_receipt_out_of_scope_branch(self, payments_client):
        receipt = _mock_receipt(branch_id=9, user_id=42)
        with (
            patch("routes.payments.tenant_get", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="403") as render,
        ):
            resp = payments_client.get("/payments/receipts/1/print")
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_print_receipt_qr_and_currency_fallback(self, payments_client):
        receipt = _mock_receipt(branch_id=1, source_type="sale", source_id=10, user_id=42)
        receipt.user = MagicMock(
            get_display_name=MagicMock(return_value="User AR"),
            full_name="User",
            username="u1",
        )
        sale = MagicMock(branch_id=1)
        settings = MagicMock(active_template="modern", enable_qr_code=True)
        with (
            patch("routes.payments.tenant_get", side_effect=[receipt, sale]),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.InvoiceSettings.get_active", return_value=settings),
            patch(
                "routes.payments.InvoiceSettings.company_print_context",
                return_value=(MagicMock(name_ar="Co"), settings, {}),
            ),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.payments.number_to_arabic_words", return_value="مائة"),
            patch(
                "routes.payments.resolve_default_currency",
                side_effect=RuntimeError("fx"),
            ),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch(
                "routes.payments.generate_qr_data_url",
                return_value="data:image/png;base64,x",
            ) as qr,
            patch("models.Branch") as branch_cls,
            patch("routes.payments.render_template", return_value="ok") as render,
        ):
            branch_cls.query.filter_by.return_value.first.return_value = MagicMock(name="Branch")
            resp = payments_client.get("/payments/receipts/1/print")
        assert resp.status_code == 200
        qr.assert_called_once()
        render.assert_called()

    def test_create_voucher_incoming_supplier_refund(self, payments_client, mocker):
        supplier = MagicMock(id=3, name="Sup", tenant_id=1)
        supplier.apply_payment = MagicMock()
        payment_inst = MagicMock(
            id=10,
            payment_number="REC-1",
            branch_id=1,
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
        )
        payment_cls = MagicMock(return_value=payment_inst)
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="REC-1")
        mocker.patch("routes.payments.post_or_fail")
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_service.GLService.get_payment_debit_account",
            return_value="1101",
        )
        mocker.patch(
            "services.gl_service.GLService.get_payment_debit_concept",
            return_value="CASH",
        )
        with (
            _payments_patches(supplier=supplier),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("routes.payments.Payment", payment_cls),
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "supplier",
                    "party_id": "3",
                    "amount": "50",
                    "payment_method": "cash",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        payment_cls.assert_called_once()
        supplier.apply_payment.assert_called_once()

    def test_create_voucher_currency_exception_fallback(self, payments_client, mocker):
        customer = MagicMock(id=1, tenant_id=1)
        receipt = MagicMock(receipt_number="R-1", id=10)
        mocker.patch("services.logging_core.LoggingCore.log_error")
        with (
            _payments_patches(customer=customer),
            patch(
                "routes.payments.resolve_default_currency",
                side_effect=RuntimeError("tenant fx"),
            ),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("routes.payments.PaymentService.create_receipt", return_value=receipt),
        ):
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "customer",
                    "party_id": "1",
                    "amount": "25",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_receipt_sale_partial_status(self, payments_client, mocker):
        receipt = _mock_receipt(branch_id=1, source_type="sale", source_id=5, cheque_id=None)
        receipt.amount = Decimal("50")
        receipt.amount_aed = Decimal("50")
        sale = MagicMock(
            paid_amount=Decimal("100"),
            paid_amount_aed=Decimal("100"),
            amount_aed=Decimal("150"),
            balance_due=Decimal("50"),
        )
        mocker.patch("services.gl_service.GLService.reverse_entry")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("models.Sale") as sale_model,
            patch("routes.payments.db.session") as session,
        ):
            sale_model.query.filter_by.return_value.first.return_value = sale
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert sale.payment_status == "partial"

    def test_delete_payment_supplier_refund(self, payments_client, mocker):
        payment = _mock_payment(cheque_id=None, branch_id=1, payment_type="supplier")
        payment.supplier_id = 2
        supplier = MagicMock()
        mocker.patch("services.gl_service.GLService.reverse_entry")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("models.Supplier") as supplier_cls,
            patch("routes.payments.db.session") as session,
        ):
            supplier_cls.query.filter_by.return_value.first.return_value = supplier
            session.commit = MagicMock()
            resp = payments_client.post("/payments/payments/2/delete", follow_redirects=False)
        assert resp.status_code == 302
        supplier.apply_payment.assert_called_once()

    def test_archived_payments_skips_out_of_scope(self, payments_client):
        archived = MagicMock(
            record_id=7,
            data={
                "payment_number": "P-7",
                "payment_date": "2026-01-01T00:00:00",
                "amount": 10,
                "currency": "AED",
                "amount_aed": 10,
                "supplier_name": "S",
                "payment_type": "supplier",
                "branch_id": 99,
            },
            archived_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        q = MagicMock()
        q.filter.return_value = q
        q.all.side_effect = [[], [archived]]
        with (
            patch("routes.payments.db.session.query", return_value=q),
            patch("routes.payments._archived_item_branch_id", return_value=99),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="ok") as render,
        ):
            resp = payments_client.get("/payments/archived")
        assert resp.status_code == 200
        assert render.call_args.kwargs["archived_items"] == []

    def test_create_receipt_redirects_to_voucher(self, payments_client):
        resp = payments_client.get("/payments/receipts/create?customer_id=1", follow_redirects=False)
        assert resp.status_code == 302

    def test_api_customer_balance_currency_fallback(self, payments_client):
        customer = MagicMock(id=1)
        with (
            _payments_patches(customer=customer),
            patch("routes.payments._scoped_customer_unpaid_sales", return_value=[]),
            patch(
                "routes.payments.resolve_default_currency",
                side_effect=RuntimeError("fx"),
            ),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
        ):
            resp = payments_client.get("/payments/api/customer-balance/1")
        assert resp.status_code == 200


class TestReceiptsPaginationGap:
    def test_receipts_pagination_iter_pages_yields_ellipsis(self, payments_client):
        receipts = [_mock_receipt(id=i) for i in range(1, 101)]

        def render_side_effect(template, **ctx):
            pag = ctx.get("pagination")
            if pag:
                pages = list(pag.iter_pages())
                assert None in pages
            return "ok"

        with _payments_patches(receipts=receipts, count_receipts=100):
            with patch("routes.payments.render_template", side_effect=render_side_effect):
                resp = payments_client.get("/payments/receipts?per_page=10&page=5")
        assert resp.status_code == 200


class TestCreateFromSaleCurrencyFallback:
    def test_create_from_sale_log_error_inner_except(self, payments_client, mocker):
        sale = MagicMock(
            id=5,
            branch_id=1,
            balance_due=Decimal("100"),
            exchange_rate=1,
            currency="",
            customer=MagicMock(),
            tenant_id=1,
        )
        receipt = MagicMock(id=12)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=sale)
        mocker.patch("routes.payments.PaymentService.create_receipt", return_value=receipt)
        mocker.patch(
            "routes.payments.resolve_default_currency",
            side_effect=RuntimeError("curr fail"),
        )
        mocker.patch(
            "services.logging_core.LoggingCore.log_error",
            side_effect=RuntimeError("log fail"),
        )
        with payments_client.application.test_request_context(
            "/payments/create_from_sale/5",
            method="POST",
            data={"amount": "40", "payment_method": "cash"},
        ):
            with (
                patch("utils.decorators.branch_scope_id", return_value=None),
                patch("routes.payments.CurrencyService.get_all_rates", return_value={}),
            ):
                from routes.payments import create_from_sale

                resp = create_from_sale(5)
        assert resp.status_code == 302


class TestVoucherCurrencyInnerExcept:
    def test_voucher_submit_log_error_inner_except(self, payments_client, mocker):
        customer = MagicMock(id=1, tenant_id=1)
        receipt = MagicMock(receipt_number="R-1", id=10)
        mocker.patch(
            "services.logging_core.LoggingCore.log_error",
            side_effect=RuntimeError("log fail"),
        )
        with (
            _payments_patches(customer=customer),
            patch(
                "routes.payments.resolve_default_currency",
                side_effect=RuntimeError("tenant fx"),
            ),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("routes.payments.PaymentService.create_receipt", return_value=receipt),
        ):
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "customer",
                    "party_id": "1",
                    "amount": "25",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302


class TestArchivedPaymentsInScope:
    def test_archived_payments_in_scope_listed(self, payments_client):
        archived = MagicMock(
            record_id=7,
            data={
                "payment_number": "P-7",
                "payment_date": "2026-01-01T00:00:00",
                "amount": 10,
                "currency": "AED",
                "amount_aed": 10,
                "supplier_name": "S",
                "payment_type": "supplier",
                "branch_id": 1,
            },
            archived_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        q = MagicMock()
        q.filter.return_value = q
        q.all.side_effect = [[], [archived]]
        with (
            patch("routes.payments.db.session.query", return_value=q),
            patch("routes.payments._archived_item_branch_id", return_value=1),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="ok") as render,
        ):
            resp = payments_client.get("/payments/archived")
        assert resp.status_code == 200
        archived_items = render.call_args.kwargs["archived_items"]
        assert any(item.get("number") == "P-7" for item in archived_items)


class TestPaymentsFinalGaps:
    def test_create_from_sale_post_receipt_redirect(self, payments_client, mocker):
        sale = MagicMock(
            id=5,
            branch_id=1,
            customer_id=1,
            customer=MagicMock(),
            balance_due=Decimal("100"),
            exchange_rate=Decimal("1"),
            currency="AED",
            tenant_id=1,
        )
        receipt = MagicMock(id=11)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=sale)
        mocker.patch("routes.payments.PaymentService.create_receipt", return_value=receipt)
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.LoggingCore.log_audit"),
            patch("routes.payments.url_for", return_value="/payments/receipts/11"),
        ):
            resp = payments_client.post(
                "/payments/create_from_sale/5",
                data={"amount": "50", "payment_method": "cash", "currency": "AED"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert "/receipts/11" in resp.location

    def test_create_from_sale_currency_log_error_inner_except(self, payments_client, mocker):
        sale = MagicMock(
            id=5,
            branch_id=1,
            customer_id=1,
            customer=MagicMock(),
            balance_due=Decimal("100"),
            exchange_rate=Decimal("1"),
            currency="",
            tenant_id=1,
        )
        receipt = MagicMock(id=12)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=sale)
        mocker.patch("routes.payments.PaymentService.create_receipt", return_value=receipt)
        mocker.patch(
            "routes.payments.resolve_default_currency",
            side_effect=RuntimeError("curr fail"),
        )
        mocker.patch(
            "services.logging_core.LoggingCore.log_error",
            side_effect=RuntimeError("log fail"),
        )
        with payments_client.application.test_request_context(
            "/payments/create_from_sale/5",
            method="POST",
            data={"amount": "40", "payment_method": "cash"},
        ):
            with (
                patch("routes.payments.tenant_get_or_404", return_value=sale),
                patch("utils.decorators.branch_scope_id", return_value=None),
                patch("routes.payments.CurrencyService.get_all_rates", return_value={}),
            ):
                from routes.payments import create_from_sale

                resp = create_from_sale(5)
        assert resp.status_code == 302

    def test_create_payment_currency_log_error_inner_except(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=1,
            currency="",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        mocker.patch(
            "routes.payments.resolve_default_currency",
            side_effect=RuntimeError("curr fail"),
        )
        mocker.patch(
            "services.logging_core.LoggingCore.log_error",
            side_effect=RuntimeError("log fail"),
        )
        mocker.patch("routes.payments.get_system_default_currency", return_value="AED")
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="form"),
        ):
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "25",
                    "payment_method": "cash",
                    "currency": "AED",
                },
            )
        assert resp.status_code == 200

    def test_delete_payment_hard_delete_orphan_cheque(self, payments_client, mocker):
        cheque = MagicMock()
        payment = _mock_payment(cheque_id=None, branch_id=1)
        payment.cheque = cheque
        payment.supplier_id = None
        mocker.patch("services.gl_service.GLService.reverse_entry")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.db.session") as session,
        ):
            session.delete = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post("/payments/payments/2/delete", follow_redirects=False)
        assert resp.status_code == 302
        session.delete.assert_any_call(cheque)

    def test_delete_receipt_sale_marks_paid(self, payments_client, mocker):
        receipt = _mock_receipt(branch_id=1, source_type="sale", source_id=5, cheque_id=None)
        receipt.amount = Decimal("50")
        receipt.amount_aed = Decimal("50")
        sale = MagicMock(
            paid_amount=Decimal("150"),
            paid_amount_aed=Decimal("150"),
            amount_aed=Decimal("100"),
            balance_due=Decimal("0"),
        )
        mocker.patch("services.gl_service.GLService.reverse_entry")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("models.Sale") as sale_model,
            patch("routes.payments.db.session") as session,
        ):
            sale_model.query.filter_by.return_value.first.return_value = sale
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert sale.payment_status == "paid"
        assert sale.balance_due == 0
