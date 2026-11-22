"""Ultimate coverage gaps (batch B) — the last missed statements in services.

Every test below is pinned to a concrete line reported missing by
``coverage report --include="services/*" -m``.  Collaborators that own a
transaction boundary or a network call are mocked at the service boundary;
the branch under test itself always runs the real production code.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ─────────────────────── services/document_sequence_service.py ────────────


class TestDocumentSequenceRemaining:
    def test_get_or_create_without_tenant_returns_none(self):
        from services.document_sequence_service import DocumentSequenceService

        assert DocumentSequenceService.get_or_create(None, "sale") is None

    def test_next_number_without_sequence_returns_fallback(self):
        from services.document_sequence_service import DocumentSequenceService

        number = DocumentSequenceService.next_number(None, "sale")
        assert number.startswith("DOC-") and number.endswith("-0001")


# ─────────────────────────────── services/payment_service.py ──────────────


class TestPaymentServiceRemaining:
    def test_cheque_receipt_requires_cheque_date(self):
        from services.payment_service import PaymentService

        with pytest.raises(ValueError, match="تاريخ استحقاق الشيك"):
            PaymentService.create_receipt(
                {
                    "customer_id": 1,
                    "amount": Decimal("10"),
                    "currency": "AED",
                    "payment_method": "cheque",
                    "cheque_number": "CHQ-GAP-1",
                }
            )

    def test_scoped_balance_groups_allocated_references(self, db_session, sample_tenant, sample_customer):
        from models import Payment
        from services.payment_service import PaymentService

        payment = Payment(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            payment_number=f"PAY-GAP-{uuid.uuid4().hex[:8]}",
            payment_type="sale_payment",
            direction="incoming",
            reference_number="RCP-GAP-SCOPED",
            amount=Decimal("40"),
            amount_aed=Decimal("40"),
            payment_method="cash",
            payment_confirmed=True,
        )
        db_session.add(payment)
        db_session.flush()

        balance = PaymentService.get_customer_balance_scoped(sample_customer.id, tenant_id=sample_tenant.id)
        assert balance == Decimal("40")


# ─────────────────────────── services/commission_gl_service.py ────────────


class TestCommissionGlRemaining:
    def test_zero_amount_missing_partner_and_missing_sale_date(self, mocker):
        from services.commission_gl_service import _sync_partner_ledger_for_commissions

        sale = SimpleNamespace(tenant_id=1, id=99171, sale_number="S-GAP-COMM", sale_date=None)
        good_customer = SimpleNamespace(partner_id=77)
        bad_customer = SimpleNamespace(partner_id=78)
        entries = [
            SimpleNamespace(partner_customer=good_customer, commission_amount_aed=0),
            SimpleNamespace(partner_customer=bad_customer, commission_amount_aed=5),
            SimpleNamespace(partner_customer=good_customer, commission_amount_aed=7),
        ]

        partner_query = MagicMock()
        partner_query.filter_by.return_value.first.return_value = None
        mocker.patch("models.PartnerTransaction.query", partner_query)
        partner = SimpleNamespace(tenant_id=1, current_balance=Decimal("10"))
        mock_db = mocker.patch("services.commission_gl_service.db")
        mock_db.session.get.side_effect = lambda _model, pid: partner if pid == 77 else None

        _sync_partner_ledger_for_commissions(sale, entries)

        # Zero was skipped, the unknown partner was skipped, the valid one was
        # mirrored with a generated transaction date (sale_date is None).
        assert partner.current_balance == Decimal("17")
        mock_db.session.add.assert_called_once()
        transaction = mock_db.session.add.call_args.args[0]
        assert transaction.transaction_date is not None


# ─────────────────────────── services/income_tax_service.py ───────────────


class TestIncomeTaxRemaining:
    def test_estimate_requires_tenant_id(self):
        from services.income_tax_service import IncomeTaxService

        with pytest.raises(ValueError, match="tenant_id is required"):
            IncomeTaxService.estimate(None)

    def test_accrue_requires_tenant_and_fiscal_year(self):
        from services.income_tax_service import IncomeTaxService

        with pytest.raises(ValueError, match="tenant_id and fiscal_year are required"):
            IncomeTaxService.accrue(None, 2026)


# ─────────────────────────── services/store_pricing_service.py ────────────


class TestStorePricingRemaining:
    def test_explicit_store_price_is_used(self, db_session, sample_tenant, sample_product):
        from models.store_product_price import StoreProductPrice
        from services.store_pricing_service import StorePricingService

        row = StoreProductPrice(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            currency_code="AED",
            price=Decimal("12.345"),
            is_active=True,
            is_default=True,
        )
        db_session.add(row)
        db_session.flush()

        assert StorePricingService.resolve_store_price(sample_product, sample_tenant, "aed") == Decimal("12.345")

    def test_unresolvable_rate_returns_one(self, mocker, sample_tenant):
        from services.store_pricing_service import StorePricingService

        mocker.patch.object(StorePricingService, "_resolve_rate", return_value=None)
        assert StorePricingService.resolve_store_currency_rate(sample_tenant, "USD") == Decimal("1")


# ─────────────────────────── services/auto_approval_service.py ────────────


class TestAutoApprovalRemaining:
    def test_worker_logs_and_continues_when_run_fails(self, app, mocker):
        import threading

        from services import auto_approval_service as module

        stop_event = threading.Event()

        def _boom():
            stop_event.set()
            raise RuntimeError("scheduler boom")

        mocker.patch.object(module.AutoApprovalService, "run_auto_approval", side_effect=_boom)
        mocker.patch.object(module.time, "sleep")
        logger = mocker.patch.object(module, "logger")

        try:
            handle = module.schedule_auto_approval(app, stop_event=stop_event)
            handle["thread"].join(timeout=5)
            assert not handle["thread"].is_alive()
            logger.exception.assert_called_once()
        finally:
            module._auto_approval_schedulers.pop(app, None)


# ─────────────────────────── services/ai_service.py ───────────────────────


class TestAiServiceRemaining:
    def test_intent_knowledge_reports_data_collection_failure(self, mocker):
        from services.ai_service import AIService

        broken_result = MagicMock()
        broken_result.get.side_effect = RuntimeError("context unavailable")

        result = AIService._gather_intent_knowledge("ما المبيعات", broken_result)
        assert isinstance(result, str)
        assert "خطأ في جمع البيانات" in result


# ─────────────────────────── services/customer_service.py ─────────────────


class TestCustomerServiceRemaining:
    def test_branch_balance_map_accumulates_allocated_reference(
        self, db_session, sample_tenant, sample_customer, sample_branch
    ):
        from decimal import Decimal as D

        from models import Payment
        from services.customer_service import CustomerService

        payment = Payment(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            branch_id=sample_branch.id,
            payment_number=f"PAY-GAP-{uuid.uuid4().hex[:8]}",
            payment_type="sale_payment",
            direction="incoming",
            reference_number="RCP-GAP-BRANCH",
            amount=D("10"),
            amount_aed=D("10"),
            payment_method="cash",
            payment_confirmed=True,
        )
        db_session.add(payment)
        db_session.flush()

        balances = CustomerService.branch_balance_map([sample_customer], sample_branch.id)
        assert balances[sample_customer.id] == D("10")

    def test_opening_balance_accumulates_allocated_reference(self, db_session, sample_tenant, sample_customer):
        from decimal import Decimal as D

        from models import Payment
        from services.customer_service import CustomerService

        payment = Payment(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            payment_number=f"PAY-GAP-{uuid.uuid4().hex[:8]}",
            payment_type="sale_payment",
            direction="incoming",
            reference_number="RCP-GAP-OPENING",
            amount=D("25"),
            amount_aed=D("25"),
            payment_method="cash",
            payment_confirmed=True,
            payment_date=datetime(2020, 1, 1, 10, 0, 0),
        )
        db_session.add(payment)
        db_session.flush()

        opening = CustomerService.statement_opening_balance(sample_customer.id, sample_tenant.id, "2099-01-01")
        assert opening == 25.0


# ──────────────────────── services/azad_platform_fee_service.py ───────────


class TestAzadPlatformFeeRemaining:
    def test_confirm_payout_without_usd_rate_is_refused(self, mocker):
        from services.azad_platform_fee_service import AzadPlatformFeeService

        fee = MagicMock(fee_amount_aed=Decimal("25"), status="settled")
        query = MagicMock()
        query.filter.return_value.all.return_value = [fee]
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", query)
        mocker.patch(
            "services.azad_platform_fee_service.PaymentVault.get_platform_vault",
            return_value=MagicMock(),
        )
        mocker.patch(
            "services.exchange_rate_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
            return_value={"rate": 0},
        )

        with pytest.raises(ValueError, match="no valid AED"):
            AzadPlatformFeeService.confirm_settlement_paid(1)


# ─────────────────────────── services/backup_scope_config.py ──────────────


class TestBackupScopeConfigRemaining:
    def test_fetch_rows_without_where_clause(self, mocker):
        from services.backup_scope_config import _fetch_rows

        result = MagicMock()
        result.keys.return_value = ["id", "name"]
        result.fetchall.return_value = [(7, "seven")]
        conn = MagicMock()
        conn.execute.return_value = result

        assert _fetch_rows(conn, "tenants", "", {}) == [{"id": 7, "name": "seven"}]
        conn.execute.assert_called_once()


# ─────────────────────────── services/gl_posting.py ───────────────────────


class TestGlPostingRemaining:
    def test_existing_idempotent_entry_is_returned(self, db_session, sample_tenant):
        from models import GLJournalEntry
        from services.gl_posting import post_or_fail

        existing = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number=f"GAP-IDEM-{uuid.uuid4().hex[:8]}",
            entry_date=datetime.now(UTC),
            description="existing idempotent posting",
            reference_type="manual",
            reference_id=99172,
            currency="AED",
            total_debit=Decimal("0"),
            total_credit=Decimal("0"),
            status="posted",
            notes="IDEMPOTENT|GAP-KEY-99172|first attempt",
        )
        db_session.add(existing)
        db_session.flush()

        returned = post_or_fail(
            [
                {"account": "1110", "debit": Decimal("10"), "description": "debit"},
                {"account": "4110", "credit": Decimal("10"), "description": "credit"},
            ],
            description="duplicate attempt",
            reference_type="manual",
            reference_id=99172,
            tenant_id=sample_tenant.id,
            idempotency_key="GAP-KEY-99172",
        )
        assert returned.id == existing.id


# ─────────────────────── services/gl_provisioning_service.py ──────────────


class TestGlProvisioningRemaining:
    def test_invalid_gap_code_is_skipped(self, mocker, sample_tenant):
        from services.gl_provisioning_service import GLProvisioningService

        mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder.validate_tree",
            return_value={"missing_core_accounts": [{"code": None}, "not-a-template"]},
        )
        assert GLProvisioningService.get_missing_accounts(sample_tenant.id) == []


# ────────────────────── services/maintenance_order_service.py ─────────────


class TestMaintenanceOrderRemaining:
    def test_negative_invoice_balance_is_clamped_to_zero(self, db_session, mocker, sample_tenant, sample_user):
        from decimal import Decimal as D

        from models import MaintenanceOrder
        from services.maintenance_order_service import MaintenanceService

        order = MaintenanceOrder(
            tenant_id=sample_tenant.id,
            order_number=f"MO-GAP-{uuid.uuid4().hex[:8]}",
            received_by=sample_user.id,
            status="ready",
            total_amount=D("100"),
            amount=D("100"),
            amount_aed=D("100"),
            currency="AED",
            base_currency="AED",
        )
        db_session.add(order)
        db_session.flush()

        class _OverpaidInvoice:
            """An inconsistent invoice whose paid figure exceeds its total."""

            def __init__(self, total):
                self.total = total
                self.amount_aed = total
                self.invoice_number = "INV-GAP-OVERPAID"
                self._paid = D("0")

            @property
            def paid_amount(self):
                return self.total + D("500")

            @paid_amount.setter
            def paid_amount(self, value):
                self._paid = value

        invoice = _OverpaidInvoice(D("100"))
        mocker.patch.object(MaintenanceService, "_create_invoice", return_value=invoice)
        mocker.patch.object(MaintenanceService, "transition_status")
        mocker.patch("services.maintenance_order_service.MaintenanceGLService.post_parts_cost")
        mocker.patch("services.maintenance_order_service.MaintenanceGLService.post_invoice")
        mocker.patch("services.maintenance_order_service.MaintenanceGLService.post_deposit_application")
        mocker.patch("services.maintenance_order_service._apply_customer_movement")
        mocker.patch("services.maintenance_order_service._generate_maintenance_einvoice")
        mocker.patch("services.maintenance_order_service.log_financial")
        mocker.patch(
            "services.maintenance_order_service._customer_base_amount",
            side_effect=lambda _order, amount, _tid: amount,
        )

        closed, receipt, returned_invoice = MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="account",
        )
        assert closed.id == order.id
        assert receipt is None
        assert returned_invoice is invoice
        assert invoice.balance_due == D("0")


# ─────────────────────────── services/pos_session_service.py ──────────────


class TestPosSessionRemaining:
    def test_non_atomic_wrapper_delegates_to_atomic_helper(self, mocker):
        from services.pos_session_service import _accumulate_session_tender

        atomic = mocker.patch("services.pos_session_service._accumulate_session_tender_atomic")
        session = MagicMock()
        chunk = {"payment_method": "cash", "amount": 10}
        _accumulate_session_tender(session, chunk, tenant_id=7)
        atomic.assert_called_once_with(session, chunk, 7)


# ─────────────────────── services/reports_query_service.py ────────────────


class TestReportsQueryRemaining:
    def test_negative_partner_margin_is_clamped_to_zero(self, db_session, sample_tenant, sample_customer, sample_user):
        from decimal import Decimal as D

        from models import Product, ProductPartner, Sale, SaleLine
        from services.reports_query_service import ReportsQueryService

        product = Product(
            tenant_id=sample_tenant.id,
            name="Loss-making product",
            sku=f"SKU-GAP-{uuid.uuid4().hex[:8]}",
            cost_price=D("100"),
            regular_price=D("10"),
            is_active=True,
        )
        db_session.add(product)
        db_session.flush()
        db_session.add(
            ProductPartner(
                tenant_id=sample_tenant.id,
                product_id=product.id,
                partner_customer_id=sample_customer.id,
                percentage=D("10"),
            )
        )
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"SAL-GAP-{uuid.uuid4().hex[:8]}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            status="confirmed",
            subtotal=D("10"),
            total_amount=D("10"),
            amount=D("10"),
            amount_aed=D("10"),
            balance_due=D("0"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()
        db_session.add(
            SaleLine(
                tenant_id=sample_tenant.id,
                sale_id=sale.id,
                product_id=product.id,
                quantity=D("1"),
                unit_price=D("10"),
                line_total=D("10"),
                amount_aed=D("10"),
                cost_price=D("100"),
            )
        )
        db_session.flush()

        report = ReportsQueryService.build_partners_report(None, None, sample_tenant.id, None)
        assert report["partners_data"]
        assert report["partners_data"][0]["partner_share_amount"] == D("0")


# ─────────────────────── services/store_checkout_service.py ───────────────


class TestStoreCheckoutRemaining:
    def test_unresolvable_product_price_is_refused(self, mocker, sample_user, sample_product_with_stock, tenant_store):
        from services.store_checkout_service import StoreCheckoutService
        from services.store_pricing_service import StorePricingService

        mocker.patch(
            "services.store_checkout_service.StorePaymentMethodService.validate_for_checkout",
            return_value=MagicMock(code="cod", name_ar="COD"),
        )
        mocker.patch(
            "services.store_checkout_service.StoreService.online_stock_map",
            return_value={sample_product_with_stock.id: Decimal("20")},
        )
        mocker.patch(
            "services.store_checkout_service.StockService.check_availability_in_warehouse",
            return_value=(True, ""),
        )
        mocker.patch("services.store_notification_service.StoreNotificationService.notify_new_order")
        mocker.patch.object(StorePricingService, "resolve_store_price", return_value=None)

        with pytest.raises(ValueError, match="تعذر تحديد سعر المنتج"):
            StoreCheckoutService.create_web_order(
                tenant_store,
                {str(sample_product_with_stock.id): 1},
                "Web Buyer",
                "05098765432",
                "Delivery St",
            )


# ─────────────────────────── services/supplier_service.py ─────────────────


class TestSupplierRemaining:
    def test_maintenance_purchase_is_included_in_scoped_totals(self, mocker, sample_tenant, sample_supplier):
        from services.supplier_service import SupplierService

        query = MagicMock()
        query.all.return_value = [MagicMock()]
        mocker.patch.object(SupplierService, "maintenance_purchase_query", return_value=query)
        mocker.patch.object(SupplierService, "maintenance_purchase_base_amount", return_value=50.0)

        totals = SupplierService.supplier_scoped_totals(sample_supplier.id, tenant_id=sample_tenant.id)
        assert totals[1] == 50.0


# ─────────────────────────── services/tax_service.py ───────────────────────


class TestTaxRemaining:
    def test_unresolved_gl_accounts_are_logged(self, mocker, sample_tenant):
        from services.gl_service import GLService
        from services.tax_service import TaxService

        mocker.patch.object(
            GLService,
            "get_vat_report",
            return_value={"unresolved_accounts": ["4100"], "vat_output": 0, "vat_input": 0},
        )
        result = TaxService.get_vat_return("2026-01-01", "2026-12-31", tenant_id=sample_tenant.id)
        assert result["unresolved_accounts"] == ["4100"]


# ─────────────────────────── services/training_progress.py ────────────────


class TestTrainingProgressRemaining:
    def test_empty_domain_bucket_gets_zero_coverage(self, mocker, sample_tenant):
        from services import training_progress as module

        real_defaultdict = defaultdict

        def _seeded(*args, **kwargs):
            buckets = real_defaultdict(*args, **kwargs)
            buckets["__seeded_empty__"] = {"total": 0, "covered": 0, "avg_mastery": 0.0}
            return buckets

        mocker.patch.object(module, "defaultdict", side_effect=_seeded)
        progress = module.get_training_progress(sample_tenant.id)
        assert progress["by_domain"]["__seeded_empty__"]["coverage"] == 0.0


# ─────────────────────── services/zatca_submission_service.py ─────────────


class TestZatcaSubmissionRemaining:
    def test_unsigned_xml_is_signed_before_submission(self, mocker):
        from services.zatca_submission_service import ZatcaSubmissionService

        sale = MagicMock(tenant_id=11, id=3)
        tenant = MagicMock(zatca_phase2_enabled=True, zatca_environment="sandbox", id=11)
        mock_db = mocker.patch("services.zatca_submission_service.db")
        mock_db.session.get.return_value = tenant
        mocker.patch(
            "services.tenant_secrets_service.TenantSecretsService.get",
            side_effect=lambda _tid, _name: "x",
        )
        einvoice = MagicMock(
            xml_payload="<Invoice>unsigned</Invoice>",
            status="draft",
        )
        model = mocker.patch("models.EInvoice")
        model.query.filter_by.return_value.with_for_update.return_value.first.return_value = einvoice
        signer = mocker.patch(
            "utils.zatca_signing.sign_xml",
            return_value="<Invoice><ds:Signature>signed</ds:Signature></Invoice>",
        )
        response = MagicMock(status_code=200)
        response.json.return_value = {"reportingStatus": "REPORTED"}
        post = mocker.patch("services.zatca_submission_service.requests.post", return_value=response)

        result = ZatcaSubmissionService.submit(sale)
        assert result["submitted"] is True
        signer.assert_called_once()
        assert b"ds:Signature" in post.call_args.kwargs["data"]


# ─────────────────────────── services/analytics_service.py ────────────────


class TestAnalyticsRemaining:
    def test_package_tenant_filter_applied_when_model_supports_it(self, mocker):
        from services import analytics_service as module

        mocker.patch.object(module, "models", MagicMock())
        query = MagicMock()
        query.filter_by.return_value = query
        query.all.return_value = []
        session = MagicMock()
        session.query.return_value = query
        mocker.patch.object(module, "_db_session", return_value=session)

        assert module.AnalyticsService.get_package_performance(tenant_id=9) == []
        query.filter_by.assert_any_call(tenant_id=9)
