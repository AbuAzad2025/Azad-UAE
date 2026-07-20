from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import (
    _chain_query,
    unauthenticated_client,
)


def _pm():
    import routes.payments as payments_module

    return payments_module


def _mock_receipt(**kwargs):
    r = MagicMock()
    r.id = kwargs.get("id", 1)
    r.receipt_number = kwargs.get("receipt_number", "REC-001")
    r.receipt_date = kwargs.get("receipt_date", datetime.now(timezone.utc))
    r.amount = kwargs.get("amount", Decimal("100"))
    r.currency = kwargs.get("currency", "AED")
    r.amount_aed = kwargs.get("amount_aed", Decimal("100"))
    r.direction = kwargs.get("direction", "incoming")
    r.customer = kwargs.get("customer", MagicMock(name="Customer A"))
    r.customer.name = kwargs.get("customer_name", "Customer A")
    r.supplier_name = None
    r.payment_method = kwargs.get("payment_method", "cash")
    r.payment_confirmed = kwargs.get("payment_confirmed", True)
    r.source_type = kwargs.get("source_type", "manual")
    r.source_id = kwargs.get("source_id")
    r.notes = kwargs.get("notes", "")
    r.branch_id = kwargs.get("branch_id", 1)
    r.branch = kwargs.get("branch", MagicMock(name="Main", code="BR1"))
    r.user_id = kwargs.get("user_id", 42)
    r.tenant_id = kwargs.get("tenant_id", 1)
    r.cheque_id = kwargs.get("cheque_id")
    r.cheque = kwargs.get("cheque")
    return r


def _mock_payment(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", 2)
    p.payment_number = kwargs.get("payment_number", "PAY-001")
    p.payment_date = kwargs.get("payment_date", datetime.now(timezone.utc))
    p.amount = kwargs.get("amount", Decimal("200"))
    p.currency = "AED"
    p.amount_aed = Decimal("200")
    p.direction = kwargs.get("direction", "outgoing")
    p.supplier_name = kwargs.get("supplier_name", "Supplier B")
    p.payment_method = "bank_transfer"
    p.payment_confirmed = True
    p.payment_type = "bill_payment"
    p.notes = ""
    p.branch_id = kwargs.get("branch_id", 1)
    p.branch = MagicMock(name="Main", code="BR1")
    p.user_id = 42
    p.tenant_id = 1
    p.supplier_id = kwargs.get("supplier_id")
    p.cheque_id = kwargs.get("cheque_id")
    p.cheque = kwargs.get("cheque")
    p.user = MagicMock(full_name="Tester", username="tester")
    p.user.get_display_name = MagicMock(return_value="Tester")
    return p


def _tenant_query_chain(receipts=None, payments=None, count_receipts=0, count_payments=0):
    receipts = receipts or []
    payments = payments or []
    rq = MagicMock()
    rq.count.return_value = count_receipts or len(receipts)
    rq.order_by.return_value.limit.return_value.all.return_value = receipts
    rq.filter.return_value = rq
    rq.join.return_value = rq
    pq = MagicMock()
    pq.count.return_value = count_payments or len(payments)
    pq.order_by.return_value.limit.return_value.all.return_value = payments
    pq.filter.return_value = pq

    def tenant_query_side(model):
        name = getattr(model, "__name__", str(model))
        if name == "Receipt":
            return rq
        if name == "Payment":
            return pq
        if name == "Customer":
            cq = MagicMock()
            cq.filter.return_value = cq
            cq.order_by.return_value.limit.return_value.all.return_value = []
            return cq
        if name == "Supplier":
            sq = MagicMock()
            sq.filter.return_value = sq
            sq.order_by.return_value.limit.return_value.all.return_value = []
            return sq
        if name == "Sale":
            return _chain_query(all=[])
        return _chain_query(all=[])

    return tenant_query_side, rq, pq


@contextmanager
def _payments_patches(**cfg):
    tq_side, rq, pq = _tenant_query_chain(
        receipts=cfg.get("receipts"),
        payments=cfg.get("payments"),
    )
    customer = cfg.get("customer")
    supplier = cfg.get("supplier")
    scoped_customers = MagicMock()
    scoped_customers.filter.return_value.first.return_value = customer
    scoped_suppliers = MagicMock()
    scoped_suppliers.filter.return_value.first.return_value = supplier

    with (
        patch("routes.payments.tenant_query", side_effect=tq_side),
        patch(
            "routes.payments.tenant_get_or_404",
            side_effect=cfg.get("get_or_404", lambda m, i: cfg.get("receipt") or cfg.get("payment")),
        ),
        patch(
            "routes.payments.tenant_get",
            side_effect=cfg.get("tenant_get", lambda m, i, or_404=True: cfg.get("receipt")),
        ),
        patch("routes.payments._scoped_customers_query", return_value=scoped_customers),
        patch("routes.payments._scoped_suppliers_query", return_value=scoped_suppliers),
        patch("routes.payments.render_template", return_value="ok") as render,
        patch("utils.decorators.branch_scope_id", return_value=cfg.get("branch_scope")),
        patch("routes.payments.should_show_all_branch_columns", return_value=False),
        patch("routes.payments.LoggingCore.log_audit") as audit,
        patch("routes.payments.PaymentService.create_receipt") as create_receipt,
        patch(
            "routes.payments.PaymentService.get_customer_balance_scoped",
            return_value=Decimal("500"),
        ),
        patch("routes.payments.resolve_default_currency", return_value="AED"),
        patch("routes.payments.get_system_default_currency", return_value="AED"),
        patch("routes.payments.db.session") as session,
    ):
        yield {
            "render": render,
            "audit": audit,
            "create_receipt": create_receipt,
            "session": session,
            "rq": rq,
            "pq": pq,
        }


@pytest.fixture
def payments_client(app_factory, bypass_permission_auth):
    from routes.payments import payments_bp
    from routes.public import public_bp

    app = app_factory(payments_bp, public_bp)
    return app.test_client()


class TestPaymentHelpers:
    def test_in_scope_branch_none_scope(self):
        with patch("utils.decorators.branch_scope_id", return_value=None):
            assert _pm()._in_scope_branch(99) is True

    def test_in_scope_branch_mismatch(self):
        with patch("utils.decorators.branch_scope_id", return_value=2):
            assert _pm()._in_scope_branch(5) is False

    def test_archived_item_branch_id(self):
        rec = MagicMock(data={"branch_id": 3})
        assert _pm()._archived_item_branch_id(rec) == 3
        assert _pm()._archived_item_branch_id(MagicMock(data=None)) is None

    def test_build_receipts_json_response(self, app_factory):
        from routes.payments import payments_bp, _build_receipts_json_response

        app = app_factory(payments_bp)
        items = [
            {
                "id": 1,
                "type": "receipt",
                "number": "R1",
                "date": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "amount": Decimal("100"),
                "currency": "AED",
                "payment_method": "cash",
                "direction": "incoming",
                "payment_confirmed": True,
                "notes": "",
                "customer_name": "A",
                "supplier_name": None,
                "source_type": "manual",
            }
        ]
        pag = MagicMock(page=1, pages=1)
        with app.test_request_context():
            resp = _build_receipts_json_response(items, pag)
            data = resp.get_json()
        assert data["totals"]["total_incoming"] == 100.0
        assert data["payments"][0]["status"] == "COMPLETED"

    def test_resolve_transaction_rate(self, mocker):
        mocker.patch(
            "routes.payments.ExchangeRateService.resolve_exchange_rate_for_transaction",
            return_value={"rate": "3.67"},
        )
        mocker.patch("utils.currency_utils.resolve_tenant_base_currency", return_value="AED")
        mocker.patch("routes.payments.get_active_tenant_id", return_value=1)
        mocker.patch("routes.payments.current_user", MagicMock())
        rate = _pm()._resolve_transaction_rate("USD", 3.67)
        assert rate == Decimal("3.67")


class TestPaymentsAuth:
    def test_index_redirects(self, payments_client):
        resp = payments_client.get("/payments/")
        assert resp.status_code == 302

    def test_receipts_unauthenticated(self, payments_client):
        with unauthenticated_client(payments_client):
            resp = payments_client.get("/payments/receipts")
        assert resp.status_code == 401


class TestReceiptsList:
    def test_receipts_html(self, payments_client, bypass_permission_auth):
        receipt = _mock_receipt()
        with _payments_patches(receipts=[receipt], payments=[_mock_payment()]):
            resp = payments_client.get("/payments/receipts")
        assert resp.status_code == 200

    def test_receipts_json_format(self, payments_client):
        receipt = _mock_receipt(direction="incoming", amount=Decimal("150"))
        payment = _mock_payment(direction="outgoing", amount=Decimal("50"))
        with _payments_patches(receipts=[receipt], payments=[payment]):
            resp = payments_client.get("/payments/receipts?format=json&direction=incoming")
        body = resp.get_json()
        assert "payments" in body
        assert body["totals"]["net_total"] == body["totals"]["total_incoming"] - body["totals"]["total_outgoing"]

    def test_receipts_direction_outgoing_filter(self, payments_client):
        with _payments_patches():
            resp = payments_client.get("/payments/receipts?direction=outgoing&search=sup")
        assert resp.status_code == 200

    def test_receipts_seller_filter(self, payments_client, bypass_permission_auth):
        bypass_permission_auth.is_seller = MagicMock(return_value=True)
        with _payments_patches():
            resp = payments_client.get("/payments/receipts")
        assert resp.status_code == 200


class TestSearchEntities:
    def test_search_customers(self, payments_client):
        customer = SimpleNamespace(id=1, name="Ali", phone="050", email="a@t.com")
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.limit.return_value.all.return_value = [customer]
        with patch("routes.payments._scoped_customers_query", return_value=q):
            resp = payments_client.get("/payments/search-entities?type=customer&q=Ali")
        data = resp.get_json()
        assert data[0]["name"] == "Ali"

    def test_search_suppliers(self, payments_client):
        supplier = SimpleNamespace(id=2, name="Sup", phone="", email="")
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.limit.return_value.all.return_value = [supplier]
        with patch("routes.payments._scoped_suppliers_query", return_value=q):
            resp = payments_client.get("/payments/search-entities?type=supplier")
        assert resp.get_json()[0]["name"] == "Sup"

    def test_search_unknown_type(self, payments_client):
        resp = payments_client.get("/payments/search-entities?type=other")
        assert resp.get_json() == []


class TestViewAndPrint:
    def test_view_payment_branch_forbidden(self, payments_client):
        payment = _mock_payment(branch_id=9)
        with (
            _payments_patches(payment=payment, branch_scope=1),
            patch("routes.payments.tenant_get_or_404", return_value=payment),
        ):
            resp = payments_client.get("/payments/payments/2")
        assert resp.status_code == 403

    def test_view_payment_ok(self, payments_client):
        payment = _mock_payment(branch_id=1)
        with (
            _payments_patches(payment=payment, branch_scope=1),
            patch("routes.payments.tenant_get_or_404", return_value=payment),
        ):
            resp = payments_client.get("/payments/payments/2")
        assert resp.status_code == 200

    def test_print_payment_with_qr(self, payments_client):
        payment = _mock_payment(branch_id=1)
        payment.amount = Decimal("100")
        payment.currency = "AED"
        payment.payment_date = datetime.now(timezone.utc)
        settings = MagicMock(enable_qr_code=True, active_template="modern")
        tenant = MagicMock(name_ar="Co")
        with (
            _payments_patches(payment=payment, branch_scope=None),
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch(
                "routes.payments.InvoiceSettings.company_print_context",
                return_value=(tenant, settings, {"name_ar": "Co"}),
            ),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.payments.number_to_arabic_words", return_value="مائة"),
            patch(
                "routes.payments.generate_qr_data_url",
                return_value="data:image/png;base64,x",
            ),
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("routes.payments.render_template", return_value="ok") as render,
            patch("models.Branch") as branch_q,
        ):
            branch_q.query.filter_by.return_value.first.return_value = MagicMock(name="Branch")
            resp = payments_client.get("/payments/payments/2/print")
        assert resp.status_code == 200
        render.assert_called_once()


class TestVoucherFlows:
    def test_create_voucher_get(self, payments_client):
        cq = MagicMock()
        cq.order_by.return_value.all.return_value = [MagicMock(id=1, name="C", customer_type="retail")]
        sq = MagicMock()
        sq.order_by.return_value.all.return_value = [MagicMock(id=2, name="S")]
        with (
            patch("routes.payments._scoped_customers_query", return_value=cq),
            patch("routes.payments._scoped_suppliers_query", return_value=sq),
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_client.get("/payments/voucher/create?direction=outgoing&party_id=1&amount=50")
        assert resp.status_code == 200

    def test_voucher_submit_missing_fields(self, payments_client):
        resp = payments_client.post("/payments/voucher/submit", data={"direction": "incoming"})
        assert resp.status_code == 302

    def test_voucher_incoming_customer(self, payments_client):
        customer = MagicMock(id=1, tenant_id=1)
        receipt = MagicMock(receipt_number="REC-99", id=10)
        with (
            _payments_patches(customer=customer),
            patch("routes.payments.PaymentService.create_receipt", return_value=receipt),
        ):
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "customer",
                    "party_id": "1",
                    "amount": "100",
                    "payment_method": "cash",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_voucher_customer_out_of_scope(self, payments_client):
        with _payments_patches(customer=None):
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "customer",
                    "party_id": "1",
                    "amount": "100",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_voucher_incoming_supplier_refund(self, payments_client, mocker):
        supplier = MagicMock(id=2, name="Sup", tenant_id=1)
        supplier.apply_payment = MagicMock()
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-RF")
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
            patch("models.Payment", MagicMock),
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
                    "amount": "75",
                    "payment_method": "cash",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_voucher_outgoing_supplier_cash(self, payments_client, mocker):
        supplier = MagicMock(id=2, name="Sup", tenant_id=1)
        supplier.apply_payment = MagicMock()
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-OUT")
        mocker.patch("routes.payments.post_or_fail")
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_account",
            return_value="1101",
        )
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_concept",
            return_value="CASH",
        )
        with (
            _payments_patches(supplier=supplier),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("models.Payment", MagicMock),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "outgoing",
                    "party_type": "supplier",
                    "party_id": "2",
                    "amount": "120",
                    "payment_method": "cash",
                    "currency": "AED",
                    "date": "2026-06-01",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302


class TestReceiptCrud:
    def test_create_receipt_redirects(self, payments_client):
        resp = payments_client.get("/payments/receipts/create?amount=10")
        assert resp.status_code == 302

    def test_view_receipt_redirects_to_payment(self, payments_client):
        payment = _mock_payment()
        with patch("routes.payments.tenant_get", side_effect=[None, payment]):
            resp = payments_client.get("/payments/receipts/99", follow_redirects=False)
        assert resp.status_code == 302

    def test_view_receipt_seller_forbidden(self, payments_client, bypass_permission_auth):
        receipt = _mock_receipt(user_id=99, branch_id=1)
        bypass_permission_auth.is_seller = MagicMock(return_value=True)
        bypass_permission_auth.is_owner = False
        bypass_permission_auth.id = 1
        with (
            patch("routes.payments.tenant_get", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_client.get("/payments/receipts/1", follow_redirects=False)
        assert resp.status_code == 302

    def test_archive_receipt(self, payments_client):
        receipt = _mock_receipt(branch_id=1)
        archive = MagicMock()
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService", return_value=archive),
        ):
            resp = payments_client.post("/payments/receipts/1/archive", follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_receipt_hard_delete(self, payments_client, mocker):
        receipt = _mock_receipt(branch_id=1, cheque_id=None, source_type="manual", source_id=None)
        mocker.patch("services.gl_service.GLService.reverse_entry")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.db.session") as session,
        ):
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_receipt_with_links_archives(self, payments_client):
        receipt = _mock_receipt(branch_id=1, source_type="sale", source_id=5, cheque_id=3)
        receipt.cheque = MagicMock()
        archive = MagicMock()
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService", return_value=archive),
            patch("models.Sale") as sale_model,
            patch("routes.payments.db.session") as session,
        ):
            sale = MagicMock(
                paid_amount=Decimal("100"),
                paid_amount_aed=Decimal("100"),
                amount_aed=Decimal("200"),
                balance_due=Decimal("100"),
            )
            sale_model.query.filter_by.return_value.first.return_value = sale
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302


class TestPaymentCrud:
    def test_archive_payment(self, payments_client):
        payment = _mock_payment(branch_id=1)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService") as arch_cls,
            patch("routes.payments.db.session") as session,
        ):
            arch_cls.return_value.archive_record = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post("/payments/payments/2/archive", follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_payment_with_cheque_archives(self, payments_client):
        payment = _mock_payment(cheque_id=5)
        payment.cheque = MagicMock()
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService") as arch_cls,
            patch("routes.payments.db.session") as session,
        ):
            arch_cls.return_value.archive_record = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post("/payments/payments/2/delete", follow_redirects=False)
        assert resp.status_code == 302


class TestArchivedAndRestore:
    def test_archived_receipts_list(self, payments_client):
        archived = MagicMock(
            record_id=1,
            data={
                "receipt_number": "R-OLD",
                "receipt_date": "2026-01-01T00:00:00",
                "amount": "50",
                "currency": "AED",
                "amount_aed": "50",
                "customer_name": "X",
                "source_type": "manual",
            },
            archived_at=datetime.now(timezone.utc),
        )
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [archived]
        with (
            patch("routes.payments.db.session.query", return_value=q),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_client.get("/payments/archived")
        assert resp.status_code == 200

    def test_restore_receipt(self, payments_client):
        archived = MagicMock(data={"branch_id": 1})
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.first_or_404.return_value = archived
        with (
            patch("models.ArchivedRecord") as ar,
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.db.session") as session,
        ):
            ar.query = q
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/3/restore", follow_redirects=False)
        assert resp.status_code == 302


class TestApiCustomerBalance:
    def test_customer_balance_forbidden(self, payments_client):
        with _payments_patches(customer=None):
            resp = payments_client.get("/payments/api/customer-balance/1")
        assert resp.status_code == 403

    def test_customer_balance_json(self, payments_client):
        customer = MagicMock(id=1)
        sale = MagicMock(
            id=10,
            sale_number="S1",
            sale_date=datetime(2026, 1, 1),
            total_amount=Decimal("200"),
            balance_due=Decimal("50"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        with (
            _payments_patches(customer=customer),
            patch("routes.payments._scoped_customer_unpaid_sales", return_value=[sale]),
        ):
            resp = payments_client.get("/payments/api/customer-balance/1")
        body = resp.get_json()
        assert body["balance"] == 500.0
        assert len(body["unpaid_sales"]) == 1


class TestCreateFromSaleAndPurchase:
    def test_create_from_sale_get_redirect(self, payments_client):
        sale = MagicMock(
            branch_id=1,
            customer_id=1,
            customer=MagicMock(),
            balance_due=Decimal("100"),
            exchange_rate=1,
            currency="AED",
        )
        with (
            patch("routes.payments.tenant_get_or_404", return_value=sale),
            patch("utils.decorators.branch_scope_id", return_value=None),
        ):
            resp = payments_client.get("/payments/create_from_sale/5", follow_redirects=False)
        assert resp.status_code == 302

    def test_create_payment_get_redirect(self, payments_client, mocker):
        purchase = MagicMock(
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=1,
            currency="AED",
            id=8,
        )
        mocker.patch("routes.payments.db.session.query")
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        with patch("utils.decorators.branch_scope_id", return_value=None):
            resp = payments_client.get("/payments/create_payment/8", follow_redirects=False)
        assert resp.status_code == 302

    def test_create_payment_post_invalid_amount(self, payments_client, mocker):
        purchase = MagicMock(
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=1,
            currency="AED",
            id=8,
        )
        mocker.patch("routes.payments.db.session.query")
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        with patch("utils.decorators.branch_scope_id", return_value=None):
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "0",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302


class TestPaymentsExtendedCoverage:
    def test_receipt_branch_without_code(self, payments_client):
        receipt = _mock_receipt()
        receipt.branch = MagicMock(name="BranchOnly", code=None)
        with _payments_patches(receipts=[receipt]):
            resp = payments_client.get("/payments/receipts")
        assert resp.status_code == 200

    def test_view_receipt_ok(self, payments_client):
        receipt = _mock_receipt(branch_id=1, user_id=42)
        with (
            patch("routes.payments.tenant_get", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_client.get("/payments/receipts/1")
        assert resp.status_code == 200

    def test_print_receipt_template_fallback(self, payments_client):
        receipt = _mock_receipt(branch_id=1, user_id=42)
        receipt.amount = Decimal("50")
        receipt.currency = "AED"
        settings = MagicMock(active_template="missing", enable_qr_code=False)
        with (
            patch("routes.payments.tenant_get", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.InvoiceSettings.get_active", return_value=settings),
            patch(
                "routes.payments.InvoiceSettings.company_print_context",
                return_value=(MagicMock(name_ar="Co"), settings, {}),
            ),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.payments.number_to_arabic_words", return_value="خمسون"),
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("models.Branch") as branch_q,
            patch(
                "routes.payments.render_template",
                side_effect=[RuntimeError("tpl"), "ok"],
            ) as render,
            patch(
                "services.logging_core.LoggingCore.log_error",
                side_effect=RuntimeError("log fail"),
            ),
        ):
            branch_q.query.filter_by.return_value.first.return_value = None
            resp = payments_client.get("/payments/receipts/1/print")
        assert resp.status_code == 200
        assert render.call_count == 2

    def test_archived_includes_payment(self, payments_client):
        archived_payment = MagicMock(
            record_id=9,
            data={
                "payment_number": "P-OLD",
                "payment_date": "2026-01-02T00:00:00",
                "amount": "80",
                "currency": "AED",
                "amount_aed": "80",
                "supplier_name": "Sup",
                "payment_type": "bill",
            },
            archived_at=datetime.now(timezone.utc),
        )
        q = MagicMock()
        q.filter.return_value = q
        q.all.side_effect = [[], [archived_payment]]
        with (
            patch("routes.payments.db.session.query", return_value=q),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_client.get("/payments/archived")
        assert resp.status_code == 200

    def test_restore_payment(self, payments_client):
        archived = MagicMock(data={"branch_id": 1})
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.first_or_404.return_value = archived
        with (
            patch("models.ArchivedRecord") as ar,
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.db.session") as session,
        ):
            ar.query = q
            session.commit = MagicMock()
            resp = payments_client.post("/payments/payments/4/restore", follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_payment_hard_delete(self, payments_client, mocker):
        payment = _mock_payment(cheque_id=None, supplier_id=3, branch_id=1)
        payment.tenant_id = 1
        payment.amount_aed = Decimal("100")
        supplier = MagicMock()
        supplier.apply_payment = MagicMock()
        mocker.patch("services.gl_service.GLService.reverse_entry")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("models.Supplier") as sup_model,
            patch("routes.payments.db.session") as session,
        ):
            sup_model.query.filter_by.return_value.first.return_value = supplier
            session.commit = MagicMock()
            resp = payments_client.post("/payments/payments/2/delete", follow_redirects=False)
        assert resp.status_code == 302

    def test_create_from_sale_post_success(self, payments_client, mocker):
        sale = MagicMock(
            branch_id=1,
            customer_id=1,
            customer=MagicMock(),
            balance_due=Decimal("100"),
            exchange_rate=Decimal("1"),
            currency="AED",
            id=5,
            tenant_id=1,
        )
        receipt = MagicMock(id=11)
        create_receipt = mocker.patch("routes.payments.PaymentService.create_receipt", return_value=receipt)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=sale),
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
        create_receipt.assert_called_once()

    def test_voucher_outgoing_customer_cash(self, payments_client, mocker):
        customer = MagicMock(id=1, name="Cust", tenant_id=1)
        customer.apply_receipt = MagicMock()
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-CUST")
        mocker.patch("routes.payments.post_or_fail")
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_account",
            return_value="1101",
        )
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_concept",
            return_value="CASH",
        )
        mocker.patch(
            "services.gl_service.GLService.get_customer_credit_account",
            return_value="1130",
        )
        mocker.patch(
            "services.gl_service.GLService.get_customer_credit_concept",
            return_value="AR",
        )
        with (
            _payments_patches(customer=customer),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("models.Payment", MagicMock),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "outgoing",
                    "party_type": "customer",
                    "party_id": "1",
                    "amount": "90",
                    "payment_method": "cash",
                    "currency": "AED",
                    "date": "2026-06-01",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_api_customer_balance_foreign_sale(self, payments_client):
        customer = MagicMock(id=1)
        sale = MagicMock(
            id=10,
            sale_number="S-FX",
            sale_date=datetime(2026, 1, 1),
            total_amount=Decimal("200"),
            balance_due=Decimal("100"),
            exchange_rate=Decimal("3.67"),
            currency="USD",
        )
        with (
            _payments_patches(customer=customer),
            patch("routes.payments._scoped_customer_unpaid_sales", return_value=[sale]),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
        ):
            resp = payments_client.get("/payments/api/customer-balance/1")
        body = resp.get_json()
        assert body["unpaid_sales"][0]["currency"] == "USD"

    def test_scoped_suppliers_search_with_query(self, payments_client):
        supplier = SimpleNamespace(id=3, name="Vendor", phone="05", email="v@t.com")
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.limit.return_value.all.return_value = [supplier]
        with patch("routes.payments._scoped_suppliers_query", return_value=q):
            resp = payments_client.get("/payments/search-entities?type=suppliers&q=Ven")
        assert resp.get_json()[0]["name"] == "Vendor"

    def test_receipts_accept_json_header(self, payments_client):
        receipt = _mock_receipt()
        with _payments_patches(receipts=[receipt]):
            resp = payments_client.get("/payments/receipts", headers={"Accept": "application/json"})
        assert resp.status_code == 200
        assert "payments" in resp.get_json()


class TestPaymentsDeepCoverage:
    def test_scoped_customer_unpaid_sales_branch_filter(self, mocker):
        mocker.patch("routes.payments._current_branch_id", return_value=3)
        sale = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = [sale]
        mocker.patch("routes.payments.tenant_query", return_value=q)
        result = _pm()._scoped_customer_unpaid_sales(1)
        assert result == [sale]

    def test_ensure_customer_scope_returns_none(self, mocker):
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        mocker.patch("routes.payments._scoped_customers_query", return_value=q)
        assert _pm()._ensure_customer_scope(99) is None

    def test_voucher_submit_exception_redirects(self, payments_client, mocker):
        mocker.patch("routes.payments._ensure_customer_scope", side_effect=RuntimeError("boom"))
        resp = payments_client.post(
            "/payments/voucher/submit",
            data={
                "direction": "incoming",
                "party_type": "customer",
                "party_id": "1",
                "amount": "10",
                "payment_method": "cash",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_ensure_supplier_scope_returns_none(self, mocker):
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        mocker.patch("routes.payments._scoped_suppliers_query", return_value=q)
        assert _pm()._ensure_supplier_scope(88) is None

    def test_scoped_customers_query_branch_scoped(self, mocker):
        base_q = MagicMock()
        scoped_q = MagicMock()
        base_q.filter.return_value = scoped_q
        scoped_q.filter.return_value = scoped_q
        mocker.patch("routes.payments.tenant_query", return_value=base_q)
        with patch("utils.decorators.branch_scope_id", return_value=2):
            result = _pm()._scoped_customers_query()
        assert result is scoped_q
        assert base_q.filter.call_count >= 1

    def test_scoped_suppliers_query_branch_scoped(self, mocker):
        base_q = MagicMock()
        scoped_q = MagicMock()
        base_q.filter.return_value = scoped_q
        scoped_q.filter.return_value = scoped_q
        mocker.patch("routes.payments.tenant_query", return_value=base_q)
        with patch("utils.decorators.branch_scope_id", return_value=3):
            result = _pm()._scoped_suppliers_query()
        assert result is scoped_q

    def test_receipts_branch_scope_filter(self, payments_client):
        with _payments_patches(branch_scope=2):
            resp = payments_client.get("/payments/receipts")
        assert resp.status_code == 200

    def test_receipts_pagination_iter_pages(self, payments_client):
        receipts = [_mock_receipt(id=i) for i in range(25)]

        def render_side_effect(template, **ctx):
            pag = ctx.get("pagination")
            if pag:
                list(pag.iter_pages())
            return "ok"

        with _payments_patches(receipts=receipts, count_receipts=25):
            with patch("routes.payments.render_template", side_effect=render_side_effect):
                resp = payments_client.get("/payments/receipts?per_page=10&page=2")
        assert resp.status_code == 200

    def test_archive_payment_failure(self, payments_client):
        payment = _mock_payment(branch_id=1)
        archive = MagicMock()
        archive.archive_record.side_effect = RuntimeError("archive fail")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService", return_value=archive),
            patch("routes.payments.db.session") as session,
        ):
            session.commit = MagicMock()
            session.rollback = MagicMock()
            resp = payments_client.post("/payments/payments/2/archive", follow_redirects=False)
        assert resp.status_code == 302
        session.rollback.assert_called()

    def test_restore_payment_exception(self, payments_client):
        archived = MagicMock(data={"branch_id": 1})
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.first_or_404.return_value = archived
        with (
            patch("models.ArchivedRecord") as ar,
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.db.session") as session,
        ):
            ar.query = q
            session.delete = MagicMock(side_effect=RuntimeError("delete fail"))
            session.rollback = MagicMock()
            resp = payments_client.post("/payments/payments/4/restore", follow_redirects=False)
        assert resp.status_code == 302
        session.rollback.assert_called()

    def test_create_from_sale_currency_exception_fallback(self, payments_client, mocker):
        sale = MagicMock(
            branch_id=1,
            customer_id=1,
            customer=MagicMock(),
            balance_due=Decimal("100"),
            exchange_rate=Decimal("1"),
            currency="",
            id=5,
            tenant_id=1,
        )
        receipt = MagicMock(id=12)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=sale)
        mocker.patch("routes.payments.PaymentService.create_receipt", return_value=receipt)
        mocker.patch(
            "routes.payments.resolve_default_currency",
            side_effect=RuntimeError("curr fail"),
        )
        mocker.patch("routes.payments.LoggingCore.log_error")
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.CurrencyService.get_all_rates", return_value={}),
        ):
            resp = payments_client.post(
                "/payments/create_from_sale/5",
                data={
                    "amount": "40",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_voucher_submit_currency_fallback(self, payments_client, mocker):
        customer = MagicMock(id=1, tenant_id=1)
        receipt = MagicMock(receipt_number="REC-FX", id=20)
        mocker.patch(
            "routes.payments.resolve_default_currency",
            side_effect=RuntimeError("curr fail"),
        )
        mocker.patch("routes.payments.LoggingCore.log_error")
        with (
            _payments_patches(customer=customer),
            patch("routes.payments.PaymentService.create_receipt", return_value=receipt),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
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

    def test_voucher_outgoing_supplier_out_of_scope(self, payments_client):
        with _payments_patches(supplier=None):
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "outgoing",
                    "party_type": "supplier",
                    "party_id": "2",
                    "amount": "50",
                    "payment_method": "cash",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_archive_receipt_exception(self, payments_client):
        receipt = _mock_receipt(branch_id=1)
        archive = MagicMock()
        archive.archive_record.side_effect = RuntimeError("archive fail")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService", return_value=archive),
            patch("routes.payments.db.session") as session,
        ):
            session.rollback = MagicMock()
            resp = payments_client.post("/payments/receipts/1/archive", follow_redirects=False)
        assert resp.status_code == 302
        session.rollback.assert_called()

    def test_restore_receipt_exception(self, payments_client):
        archived = MagicMock(data={"branch_id": 1})
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.first_or_404.return_value = archived
        with (
            patch("models.ArchivedRecord") as ar,
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.db.session") as session,
        ):
            ar.query = q
            session.delete = MagicMock(side_effect=RuntimeError("del fail"))
            session.rollback = MagicMock()
            resp = payments_client.post("/payments/receipts/3/restore", follow_redirects=False)
        assert resp.status_code == 302
        session.rollback.assert_called()

    def test_delete_receipt_updates_sale_paid_status(self, payments_client):
        receipt = _mock_receipt(branch_id=1, source_type="sale", source_id=5, cheque_id=None)
        receipt.amount = Decimal("50")
        receipt.amount_aed = Decimal("50")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService") as arch_cls,
            patch("models.Sale") as sale_model,
            patch("routes.payments.db.session") as session,
        ):
            sale = MagicMock(
                paid_amount=Decimal("100"),
                paid_amount_aed=Decimal("100"),
                amount_aed=Decimal("200"),
                balance_due=Decimal("100"),
            )
            sale_model.query.filter_by.return_value.first.return_value = sale
            arch_cls.return_value.archive_record = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert sale.payment_status == "partial"

    def test_delete_receipt_marks_sale_paid(self, payments_client):
        receipt = _mock_receipt(branch_id=1, source_type="sale", source_id=6, cheque_id=None)
        receipt.amount = Decimal("50")
        receipt.amount_aed = Decimal("50")
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService") as arch_cls,
            patch("models.Sale") as sale_model,
            patch("routes.payments.db.session") as session,
        ):
            sale = MagicMock(
                paid_amount=Decimal("100"),
                paid_amount_aed=Decimal("100"),
                amount_aed=Decimal("50"),
                balance_due=Decimal("0"),
            )
            sale_model.query.filter_by.return_value.first.return_value = sale
            arch_cls.return_value.archive_record = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert sale.payment_status == "paid"
        assert sale.balance_due == 0

    def test_create_payment_card_and_ewallet(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-CARD")
        mocker.patch("routes.payments.post_or_fail")
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_account",
            return_value="1120",
        )
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_concept",
            return_value="BANK",
        )
        payment_inst = MagicMock(
            id=72,
            amount=Decimal("30"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("30"),
            branch_id=1,
            supplier_name="S",
            payment_number="PAY-CARD",
            notes="",
            cheque_id=None,
        )
        mocker.patch("models.Payment", return_value=payment_inst)
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("routes.payments.url_for", return_value="/purchases/8"),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "30",
                    "payment_method": "card",
                    "reference_number_card": "AUTH-99",
                    "card_last4": "4242",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert "4242" in (payment_inst.notes or "")

    def test_create_payment_ewallet(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-EW")
        mocker.patch("routes.payments.post_or_fail")
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_account",
            return_value="1120",
        )
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_concept",
            return_value="BANK",
        )
        payment_inst = MagicMock(
            id=73,
            amount=Decimal("20"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("20"),
            branch_id=1,
            supplier_name="S",
            payment_number="PAY-EW",
            cheque_id=None,
        )
        mocker.patch("models.Payment", return_value=payment_inst)
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("routes.payments.url_for", return_value="/purchases/8"),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "20",
                    "payment_method": "e_wallet",
                    "reference_number_ewallet": "EW-REF-1",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert payment_inst.reference_number == "EW-REF-1"

    def test_create_payment_post_exception_renders_form(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", side_effect=RuntimeError("num fail"))
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("routes.payments.render_template", return_value="form") as render,
            patch("routes.payments.db.session") as session,
        ):
            session.rollback = MagicMock()
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "50",
                    "payment_method": "cash",
                    "currency": "AED",
                },
            )
        assert resp.status_code == 200
        render.assert_called_once()

    def test_api_customer_balance_currency_fallback(self, payments_client, mocker):
        customer = MagicMock(id=1)
        mocker.patch("routes.payments.resolve_default_currency", side_effect=RuntimeError("curr"))
        with (
            _payments_patches(customer=customer),
            patch("routes.payments._scoped_customer_unpaid_sales", return_value=[]),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
        ):
            resp = payments_client.get("/payments/api/customer-balance/1")
        assert resp.status_code == 200
        assert resp.get_json()["currency"] == "AED"

    def test_print_payment_currency_fallback(self, payments_client):
        payment = _mock_payment(branch_id=1)
        payment.amount = Decimal("50")
        payment.currency = "AED"
        payment.payment_date = datetime.now(timezone.utc)
        settings = MagicMock(enable_qr_code=False, active_template="modern")
        tenant = MagicMock(name_ar="Co")
        with (
            _payments_patches(payment=payment, branch_scope=None),
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch(
                "routes.payments.InvoiceSettings.company_print_context",
                return_value=(tenant, settings, {"name_ar": "Co"}),
            ),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.payments.number_to_arabic_words", return_value="خمسون"),
            patch(
                "routes.payments.resolve_default_currency",
                side_effect=RuntimeError("curr"),
            ),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("routes.payments.render_template", return_value="ok"),
            patch("models.Branch") as branch_q,
        ):
            branch_q.query.filter_by.return_value.first.return_value = MagicMock(name="Branch")
            resp = payments_client.get("/payments/payments/2/print")
        assert resp.status_code == 200

    def test_voucher_outgoing_supplier_cheque(self, payments_client, mocker):
        supplier = MagicMock(id=2, name="Sup", tenant_id=1)
        supplier.apply_payment = MagicMock()
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-CHQ")
        mocker.patch("services.cheque_service.process_cheque_issue")
        payment_inst = MagicMock(
            id=55,
            amount=Decimal("200"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("200"),
            branch_id=1,
        )
        mocker.patch("models.Payment", return_value=payment_inst)
        with (
            _payments_patches(supplier=supplier),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("models.Cheque", MagicMock),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "outgoing",
                    "party_type": "supplier",
                    "party_id": "2",
                    "amount": "200",
                    "payment_method": "cheque",
                    "cheque_number": "CHQ-9",
                    "cheque_date": "2026-07-01",
                    "bank_name": "ENBD",
                    "currency": "AED",
                    "date": "2026-06-15",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_payment_post_bank_transfer(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-PUR")
        mocker.patch("routes.payments.post_or_fail")
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_account",
            return_value="1120",
        )
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_concept",
            return_value="BANK",
        )
        payment_inst = MagicMock(
            id=70,
            amount=Decimal("100"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("100"),
            branch_id=1,
            supplier_name="S",
            payment_number="PAY-PUR",
        )
        mocker.patch("models.Payment", return_value=payment_inst)
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("routes.payments.url_for", return_value="/purchases/8"),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "100",
                    "payment_method": "bank_transfer",
                    "bank_name_transfer": "ADCB",
                    "reference_number_transfer": "TRX-1",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_receipt_exception(self, payments_client, mocker):
        receipt = _mock_receipt(branch_id=1, source_type="manual", source_id=None, cheque_id=None)
        mocker.patch(
            "services.gl_service.GLService.reverse_entry",
            side_effect=RuntimeError("gl fail"),
        )
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
        ):
            resp = payments_client.post("/payments/receipts/1/delete", follow_redirects=False)
        assert resp.status_code == 302

    def test_create_from_sale_missing_payment_method(self, payments_client, mocker):
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
        mocker.patch("routes.payments.CurrencyService.get_all_rates", return_value={})
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="ok") as render,
        ):
            resp = payments_client.post("/payments/create_from_sale/5", data={"amount": "50"})
        assert resp.status_code == 200
        render.assert_called_once()

    def test_voucher_outgoing_customer_cheque(self, payments_client, mocker):
        customer = MagicMock(id=1, name="Cust", tenant_id=1)
        customer.apply_receipt = MagicMock()
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-CCHQ")
        mocker.patch("services.cheque_service.process_cheque_issue")
        payment_inst = MagicMock(
            id=56,
            amount=Decimal("80"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("80"),
            branch_id=1,
        )
        mocker.patch("models.Payment", return_value=payment_inst)
        with (
            _payments_patches(customer=customer),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("models.Cheque", MagicMock),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            session.commit = MagicMock()
            resp = payments_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "outgoing",
                    "party_type": "customer",
                    "party_id": "1",
                    "amount": "80",
                    "payment_method": "cheque",
                    "cheque_number": "CHQ-C1",
                    "cheque_date": "2026-07-02",
                    "bank_name": "FAB",
                    "currency": "AED",
                    "date": "2026-06-20",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_payment_exceeds_balance(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("100"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        with patch("utils.decorators.branch_scope_id", return_value=None):
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "200",
                    "payment_method": "cash",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_receipt_item_status_pending(self):
        assert _pm()._receipt_item_status({"payment_confirmed": False}) == "PENDING"

    def test_view_receipt_sale_branch_scope(self, payments_client):
        receipt = _mock_receipt(branch_id=2, source_type="sale", source_id=10, user_id=42)
        sale = MagicMock(branch_id=99)
        with (
            patch("routes.payments.tenant_get", side_effect=[receipt, sale]),
            patch("utils.decorators.branch_scope_id", return_value=1),
            patch("routes.payments.render_template", return_value="ok") as render,
        ):
            resp = payments_client.get("/payments/receipts/1")
        assert resp.status_code == 403
        render.assert_called_with("errors/403.html")

    def test_create_payment_cheque_path(self, payments_client, mocker):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="S",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        mock_query = MagicMock()
        mock_query.filter.return_value.scalar.return_value = Decimal("0")
        mocker.patch("routes.payments.db.session.query", return_value=mock_query)
        mocker.patch("routes.payments.tenant_get_or_404", return_value=purchase)
        mocker.patch("routes.payments.tenant_get", return_value=MagicMock())
        mocker.patch("routes.payments._resolve_transaction_rate", return_value=Decimal("1"))
        mocker.patch("utils.helpers.generate_number", return_value="PAY-CHQ-P")
        mocker.patch("routes.payments.post_or_fail")
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_account",
            return_value="1120",
        )
        mocker.patch(
            "services.gl_service.GLService.get_payment_credit_concept",
            return_value="BANK",
        )
        payment_inst = MagicMock(
            id=71,
            amount=Decimal("50"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("50"),
            branch_id=1,
            supplier_name="S",
            payment_number="PAY-CHQ-P",
            cheque_id=None,
        )
        mocker.patch("models.Payment", return_value=payment_inst)
        with (
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch(
                "routes.payments.atomic_transaction",
                return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()),
            ),
            patch("routes.payments.url_for", return_value="/purchases/8"),
            patch("models.Cheque", MagicMock),
            patch("routes.payments.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            resp = payments_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "50",
                    "payment_method": "cheque",
                    "cheque_number": "CHQ-P1",
                    "cheque_date": "2026-08-01",
                    "bank_name": "ENBD",
                    "currency": "AED",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
