"""Final coverage gaps (batch C) — remaining missed statements in services.

Each test targets a concrete missed statement confirmed by the combined CI
coverage data.  Collaborators are mocked at the service boundary; the
conversion / aggregation math itself stays real.  No production code is
touched and no ``# noqa`` / ``# type: ignore`` is used.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.gl_account_resolver import GLMappingError

# ═══════════════════════ services/celery_tasks.py ═════════════════════════


class TestCeleryTasksRemaining:
    def test_send_invoice_email_with_explicit_tenant(self, app, db_session, sample_tenant, sample_sale, mocker):
        """Line 211 — the explicit tenant predicate on the sale lookup."""
        mocker.patch("app.create_app", return_value=app)
        # TestConfig leaves MAIL_USERNAME unset, so Flask-Mail is never
        # init_app'd; stub Message so the constructor needs no extension.
        mocker.patch("flask_mail.Message", MagicMock())
        send = mocker.patch("extensions.mail.send")
        result = __import__("services.celery_tasks", fromlist=["send_invoice_email"]).send_invoice_email(
            sample_sale.id, sample_tenant.id
        )
        assert result == {"success": True}
        send.assert_called_once()

    def test_abandoned_cart_second_reminder_failure_is_logged(self, app, mocker):
        """Lines 377-378 — the second-reminder exception handler."""
        from models.shop_abandoned_cart import ShopAbandonedCart

        cart = MagicMock(id=1, tenant_id=1, reminder_count=1, reminder_sent_at=datetime.now(UTC))
        tenant_query = MagicMock()
        tenant_query.filter.return_value.distinct.return_value.all.return_value = [(1,)]
        cart_query = MagicMock()
        cart_query.filter.return_value.all.side_effect = [[], [cart]]
        mocker.patch.object(ShopAbandonedCart, "query", cart_query)
        fake_db = MagicMock()
        fake_db.session.query.return_value = tenant_query
        mocker.patch("extensions.db", fake_db)
        get_store = mocker.patch(
            "services.store_service.StoreService.get_tenant_store",
            side_effect=RuntimeError("store unavailable"),
        )
        mocker.patch("services.celery_tasks.atomic_transaction", side_effect=lambda _name: contextlib.nullcontext())
        from services import celery_tasks

        assert celery_tasks.send_abandoned_cart_reminders() is None
        cart_query.filter.assert_called()
        get_store.assert_called_once()

    def test_revaluate_open_fx_items_task(self, app, mocker):
        """Line 393 — the task returns the revaluation summary."""
        mocker.patch("app.create_app", return_value=app)
        mocker.patch(
            "services.fx_revaluation_service.revaluate_open_items",
            return_value={"ar_count": 0, "ap_count": 0},
        )
        from services.celery_tasks import revaluate_open_fx_items

        assert revaluate_open_fx_items(1) == {"ar_count": 0, "ap_count": 0}

    def test_sync_carrier_tracking_query_failure(self, app, mocker):
        """Lines 417-418 — the shipment query failure path."""
        from models.shipment import Shipment

        query = MagicMock()
        query.filter.return_value.all.side_effect = RuntimeError("db down")
        mocker.patch.object(Shipment, "query", query)
        from services.celery_tasks import sync_carrier_tracking

        assert sync_carrier_tracking() == {"synced": 0, "error": "query failed"}

    def test_sync_carrier_tracking_success_and_sync_failure(self, app, mocker):
        """Lines 422-427, 429 — counted success and swallowed sync exception."""
        from models.shipment import Shipment

        query = MagicMock()
        query.filter.return_value.all.return_value = [
            MagicMock(id=1, tenant_id=1),
            MagicMock(id=2, tenant_id=1),
        ]
        mocker.patch.object(Shipment, "query", query)
        mocker.patch(
            "services.carrier_tracking_service.CarrierTrackingService.sync_shipment",
            side_effect=[{"success": True}, RuntimeError("carrier down")],
        )
        mocker.patch("services.celery_tasks.atomic_transaction", side_effect=lambda _name: contextlib.nullcontext())
        from services.celery_tasks import sync_carrier_tracking

        assert sync_carrier_tracking() == {"synced": 1, "total": 2}


# ═══════════════════════ services/purchase_service.py ═════════════════════


class TestPurchaseServiceRemaining:
    def test_import_levy_skips_non_positive_lines(self):
        """Line 90 — invalid quantity/cost lines are ignored by the helper."""
        from services.purchase_service import compute_import_levy_defaults

        duty, excise = compute_import_levy_defaults(
            [(0, "20", 0, "tobacco"), (1, "-5", 0, "tobacco")],
            country="AE",
            customs_duty=None,
            excise_amount=None,
        )
        assert duty == Decimal("0.000")
        assert excise == Decimal("0.000")

    def test_create_purchase_import_defaults_and_excise_gl(self, app, mocker):
        """Lines 263-280 and 486 — import levy defaulting + excise GL line."""
        from services.purchase_service import PurchaseService

        app.config["ENABLE_LANDED_COST_CAPITALIZATION"] = False
        user = MagicMock()
        user.id = 1
        user.tenant_id = 1
        user.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = "Widget"
        product.has_serial_number = False
        product.warranty_days = 0
        warehouse = MagicMock(id=1, branch_id=1, tenant_id=1)

        mocker.patch("services.purchase_service.ensure_warehouse_access", return_value=warehouse)
        mocker.patch("services.purchase_service.get_active_tenant_id", return_value=1)
        mocker.patch("services.purchase_service.validate_currency_code", return_value="AED")
        mocker.patch("services.purchase_service.generate_number", return_value="P-IMP-1")
        mocker.patch("utils.tax_settings.vat_country", return_value="AE")
        mocker.patch("utils.tax_settings.should_post_vat_gl", return_value=False)
        mocker.patch("services.purchase_service.should_post_vat_gl", return_value=False)
        mocker.patch(
            "services.purchase_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
            return_value={"rate": 1.0},
        )
        session = mocker.patch("services.purchase_service.db.session")
        session.query.return_value.filter.return_value.all.return_value = []
        mocker.patch("services.purchase_service.db.session.get", return_value=product)
        mocker.patch("services.purchase_service.PurchaseLine")
        mocker.patch("services.purchase_service.Product")
        mocker.patch("services.purchase_service.StockService.create_movement")
        mocker.patch("services.budget_enforcement.check_budget_for_account", return_value=None)
        mocker.patch(
            "services.purchase_service.GLService.get_account_code_for_concept",
            return_value="1140",
        )
        posted = mocker.patch("services.purchase_service.post_or_fail")

        purchase = PurchaseService.create_purchase(
            user,
            {"supplier_name": "Overseas Supplier"},
            [{"product_id": 1, "quantity": 2, "unit_cost": 20}],
            warehouse_id=1,
            currency="AED",
            is_import=True,
            excise_amount=Decimal("10"),
        )
        assert purchase is not None
        assert Decimal(str(purchase.excise_amount)) == Decimal("10.000")
        concept_codes = [row.get("concept_code") for row in posted.call_args.args[0]]
        assert "EXCISE_DUTY" in concept_codes

    def test_cancel_purchase_with_confirmed_return_is_refused(self, mocker):
        """Line 572 — a purchase that already has a return cannot be cancelled."""
        from models import PurchaseReturn
        from services.purchase_service import PurchaseService

        mocker.patch.object(
            PurchaseReturn,
            "query",
            MagicMock(filter_by=MagicMock(return_value=MagicMock(first=MagicMock(return_value=MagicMock())))),
        )
        purchase = MagicMock(status="confirmed", id=9, tenant_id=1)
        with pytest.raises(ValueError, match="مرتجعات"):
            PurchaseService.cancel_purchase(purchase)


# ═══════════════════════ services/einvoice_service.py ═════════════════════


class TestEInvoiceServiceRemaining:
    def _document(self):
        return {
            "xml_payload": "<Invoice>cov-c</Invoice>",
            "format": "zatca_phase2_invoice_xml",
            "invoice_hash": "a" * 64,
            "invoice_counter_value": 7,
            "qr_base64": "",
        }

    def test_save_maintenance_phase2_insert_then_update(self, db_session, sample_tenant, mocker):
        """Lines 142, 145-147 — phase-2 counter field and the row-update branch."""
        from services.einvoice_service import EInvoiceService

        existing = MagicMock()
        mocker.patch.object(EInvoiceService, "_upsert_maintenance_row", side_effect=[None, existing])
        mocker.patch("extensions.db", MagicMock())
        mocker.patch("models.EInvoice")
        first = EInvoiceService._save_maintenance(sample_tenant.id, sample_tenant, self._document(), 5001)
        assert first is not None
        document = self._document()
        document["invoice_counter_value"] = 11
        second = EInvoiceService._save_maintenance(sample_tenant.id, sample_tenant, document, 5001)
        assert second is existing
        assert second.invoice_counter_value == 11

    def test_generate_maintenance_invoice_without_persisted_id(self):
        """Lines 283-284 — a transient invoice has nothing to attach to."""
        from services.einvoice_service import EInvoiceService

        assert EInvoiceService.generate_for_maintenance_invoice(MagicMock(id="not-an-int")) is None

    def test_generate_maintenance_invoice_tenant_fallback_and_no_order(self, db_session, sample_tenant, mocker):
        """Lines 288-290, 293, 297 — tenant fallback, missing tenant/order."""
        from services.einvoice_service import EInvoiceService

        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=sample_tenant.id)
        invoice = MagicMock(id=6001, tenant_id=None, order=None)
        assert EInvoiceService.generate_for_maintenance_invoice(invoice) is None
        invoice = MagicMock(id=6002, tenant_id=999999)
        assert EInvoiceService.generate_for_maintenance_invoice(invoice) is None

    def test_generate_maintenance_invoice_without_document(self, db_session, sample_tenant, mocker):
        """Lines 341-346 — a jurisdiction without a profile produces no artifact."""
        from services.einvoice_service import EInvoiceService

        order = SimpleNamespace(
            lines=[],
            services_lines=[],
            customer=MagicMock(),
        )
        invoice = MagicMock(
            id=6003,
            tenant_id=sample_tenant.id,
            order=order,
            invoice_number="MNT-1",
            invoice_date=datetime.now(UTC),
            currency="AED",
            exchange_rate=Decimal("1"),
            tax_rate=Decimal("5"),
            subtotal=Decimal("100"),
            taxable_amount=Decimal("100"),
            tax_amount=Decimal("5"),
            total_amount=Decimal("105"),
        )
        mocker.patch.object(EInvoiceService, "_build_document", return_value=None)
        assert EInvoiceService.generate_for_maintenance_invoice(invoice) is None


# ═══════════════════════ services/partner_service.py ═══════════════════════


class TestPartnerServiceRemaining:
    def test_return_revenue_reduction_skips_zero_quantities(self):
        """Line 150 — a zero sold/returned quantity is ignored."""
        from services.partner_service import PartnerService

        row = (1, 0, Decimal("10"), 2, Decimal("5"), Decimal("4"), 1, False, 5, Decimal("100"), Decimal("5"))
        mocker_rows = [row]
        original = PartnerService._approved_return_rows
        PartnerService._approved_return_rows = staticmethod(lambda *a, **k: mocker_rows)
        try:
            assert PartnerService._return_revenue_reduction(1, None, None, "company", None) == Decimal("0")
        finally:
            PartnerService._approved_return_rows = staticmethod(original)

    def test_return_revenue_reduction_vat_inclusive_warehouse(self):
        """Line 156 — VAT is stripped from a warehouse-scoped inclusive gross."""
        from services.partner_service import PartnerService

        row = (1, Decimal("2"), Decimal("210"), 2, Decimal("5"), Decimal("4"), 1, True, 5, Decimal("100"), Decimal("5"))
        original = PartnerService._approved_return_rows
        PartnerService._approved_return_rows = staticmethod(lambda *a, **k: [row])
        try:
            reduction = PartnerService._return_revenue_reduction(1, None, None, "warehouse", 9)
        finally:
            PartnerService._approved_return_rows = staticmethod(original)
        assert reduction == Decimal("200.000")

    def test_warehouse_branch_id_no_warehouse(self):
        """Line 372 — no warehouse id means no branch override."""
        from services.partner_service import PartnerService

        assert PartnerService._warehouse_branch_id(1, None) is None

    def test_warehouse_branch_id_lookup_failure(self, mocker):
        """Lines 379-380 — a failed warehouse lookup is swallowed."""
        from services.partner_service import PartnerService

        mocker.patch("services.partner_service.db.session.get", side_effect=RuntimeError("db down"))
        assert PartnerService._warehouse_branch_id(1, 42) is None

    def test_partner_statement_backdated_transaction_opens_the_balance(self, mocker):
        """Lines 923-925 — a transaction before the range becomes the opening balance."""
        from datetime import date

        from models import PartnerTransaction
        from services.partner_service import PartnerService

        partner = SimpleNamespace(id=7, tenant_id=1, current_balance=Decimal("0"))
        mocker.patch("services.partner_service.db.session.get", return_value=partner)
        early = MagicMock(transaction_date=date(2026, 1, 1), amount_base=Decimal("100"))
        late = MagicMock(transaction_date=date(2026, 3, 1), amount_base=Decimal("50"))
        query = MagicMock()
        query.filter.return_value.order_by.return_value.all.return_value = [early, late]
        mocker.patch.object(PartnerTransaction, "query", query)
        result = PartnerService.get_partner_statement(7, date(2026, 2, 1), date(2026, 3, 31))
        assert result["opening_balance"] == 100.0
        assert result["closing_balance"] == 150.0

    def test_unified_statement_skips_zero_sold_quantity_reversal(self, mocker):
        """Line 1073 — a return with zero sold quantity is ignored."""
        from models import Customer, PartnerProfitDistribution
        from services.partner_service import PartnerService

        partner = SimpleNamespace(id=7, tenant_id=1, current_balance=Decimal("0"))
        mocker.patch("services.partner_service.db.session.get", return_value=partner)
        dists_query = MagicMock()
        dists_query.filter_by.return_value.order_by.return_value.all.return_value = []
        mocker.patch.object(PartnerProfitDistribution, "query", dists_query)
        customer_query = MagicMock()
        customer_query.filter_by.return_value.all.return_value = [
            SimpleNamespace(id=11, name=" buyer ", customer_type="regular")
        ]
        mocker.patch.object(Customer, "query", customer_query)
        commission_q = MagicMock()
        commission_q.filter.return_value.scalar.return_value = Decimal("10")
        reversed_q = MagicMock()
        reversed_q.join.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
            (1, 2, 0, Decimal("10"))
        ]
        mocker.patch(
            "services.partner_service.db.session.query",
            side_effect=[commission_q, reversed_q],
        )
        result = PartnerService.get_unified_statement(7)
        assert result["partner"] is partner


# ══════════════════ services/store_payment_method_service.py ══════════════


class TestStorePaymentMethodServiceRemaining:
    def test_set_platform_disabled(self, db_session, sample_tenant):
        """Lines 151-157 — the platform owner hard lock."""
        from models import StorePaymentMethod
        from services.store_payment_method_service import StorePaymentMethodService

        method = StorePaymentMethod(
            tenant_id=sample_tenant.id,
            code="cod",
            name_ar="نقد",
            name_en="Cash",
            is_enabled=True,
        )
        db_session.add(method)
        db_session.flush()
        result = StorePaymentMethodService.set_platform_disabled(method.id, True, tenant_id=sample_tenant.id)
        assert result.platform_disabled is True

    def test_set_platform_disabled_rejects_unknown_method(self, db_session, sample_tenant):
        """Line 154 — a method owned by nobody cannot be locked."""
        from services.store_payment_method_service import StorePaymentMethodService

        with pytest.raises(ValueError):
            StorePaymentMethodService.set_platform_disabled(999999, True, tenant_id=sample_tenant.id)

    def test_toggle_enabled_blocked_by_platform_lock(self, db_session, sample_tenant):
        """Line 166 — a platform-disabled method cannot be re-enabled."""
        from models import StorePaymentMethod
        from services.store_payment_method_service import StorePaymentMethodService

        method = StorePaymentMethod(
            tenant_id=sample_tenant.id,
            code="card",
            name_ar="بطاقة",
            name_en="Card",
            is_enabled=False,
            platform_disabled=True,
        )
        db_session.add(method)
        db_session.flush()
        with pytest.raises(ValueError):
            StorePaymentMethodService.toggle_enabled(method.id, True, tenant_id=sample_tenant.id)


# ═════════════════ services/ar_reconciliation_service.py ═══════════════════


class TestARReconciliationRemaining:
    def test_receivable_account_requires_tenant(self):
        """Line 21 — no tenant means no concept resolution."""
        from services.ar_reconciliation_service import _get_receivable_concept_account

        with pytest.raises(ValueError, match="tenant_id is required"):
            _get_receivable_concept_account()

    def test_optional_accounts_mapping_error_and_missing_tenant(self, mocker):
        """Lines 31, 34, 35, 45, 46, 47 — optional-account fallbacks."""
        from services.ar_reconciliation_service import _get_merchant_account, _get_partner_account

        err = GLMappingError(1, "PARTNER_CURRENT_ACCOUNT", None, "no mapping")
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            side_effect=err,
        )
        assert _get_partner_account(tenant_id=1) is None
        assert _get_merchant_account(tenant_id=1) is None
        with pytest.raises(ValueError, match="tenant_id is required"):
            _get_partner_account()
        with pytest.raises(ValueError, match="tenant_id is required"):
            _get_merchant_account()

    def test_build_report_without_tenant_scope(self, mocker):
        """Branch 184->186 — the report tolerates a missing tenant predicate."""
        from services.ar_reconciliation_service import ARReconciliationService

        mocker.patch(
            "services.ar_reconciliation_service._ar_subledger_accounts",
            return_value=(("1130", "label", ("regular",)),),
        )
        mocker.patch("services.ar_reconciliation_service._get_receivable_concept_account", return_value="1130")
        mocker.patch("services.ar_reconciliation_service._get_partner_account", return_value=None)
        mocker.patch("services.ar_reconciliation_service._get_merchant_account", return_value=None)
        mocker.patch.object(ARReconciliationService, "_gl_balance", return_value=Decimal("0"))
        mocker.patch.object(ARReconciliationService, "_ops_unpaid", return_value=Decimal("0"))
        report = ARReconciliationService.build_report()
        assert report["all_matched"] is True


# ══════════════════ services/fx_revaluation_service.py ═════════════════════


class TestFXRevaluationRemaining:
    def test_compat_atomic_transaction(self, db_session):
        """Lines 40-41 — the backward-compatible savepoint wrapper."""
        from services.fx_revaluation_service import atomic_transaction

        with atomic_transaction("cov-c"):
            pass

    def test_revaluation_resolves_tenant_from_context(self, mocker):
        """Line 151 — a non-owner caller inherits the active tenant."""
        from services import fx_revaluation_service

        mocker.patch.object(fx_revaluation_service, "is_platform_owner", return_value=False)
        mocker.patch.object(fx_revaluation_service, "get_active_tenant_id", return_value=1)
        mocker.patch.object(fx_revaluation_service, "resolve_tenant_base_currency", return_value="AED")
        mocker.patch.object(fx_revaluation_service, "_posted_period_entries", return_value=[99])
        summary = fx_revaluation_service.revaluate_open_items()
        assert summary["skipped_existing_period"] is True

    def test_reverse_sale_revaluation_without_tenant(self, mocker):
        """Line 430 — the unscoped query branch for a sale settlement."""
        from services import fx_revaluation_service

        mocker.patch.object(fx_revaluation_service, "tenant_query", create=True)
        mocker.patch("services.fx_revaluation_service.GLJournalEntry", create=True)
        from models.gl import GLJournalEntry

        query = MagicMock()
        query.filter.return_value.all.return_value = []
        mocker.patch.object(GLJournalEntry, "query", query)
        assert fx_revaluation_service.reverse_sale_revaluation(12, tenant_id=None) == []

    def test_reverse_purchase_revaluation_without_tenant(self, mocker):
        """Line 493 — the unscoped query branch for a purchase settlement."""
        from models.gl import GLJournalEntry
        from services import fx_revaluation_service

        query = MagicMock()
        query.filter.return_value.all.return_value = []
        mocker.patch.object(GLJournalEntry, "query", query)
        assert fx_revaluation_service.reverse_purchase_revaluation(13, tenant_id=None) == []

    def test_reverse_purchase_revaluation_reverses_entries(self, db_session, mocker):
        """Lines 504-507 — each posted entry produces a reversal id."""
        from models.gl import GLJournalEntry
        from services import fx_revaluation_service

        reversed_entry = MagicMock(id=77)
        entry = MagicMock()
        entry.reverse_entry.return_value = reversed_entry
        query = MagicMock()
        query.filter.return_value.all.return_value = [entry]
        mocker.patch.object(GLJournalEntry, "query", query)
        tenant_query = MagicMock()
        tenant_query.return_value.filter.return_value.filter.return_value.all.return_value = [entry]
        mocker.patch.object(fx_revaluation_service, "tenant_query", tenant_query)
        assert fx_revaluation_service.reverse_purchase_revaluation(14, tenant_id=1) == [77]


# ═════════════════════════ services/return_service.py ═══════════════════════


class TestReturnServiceRemaining:
    def test_commission_reversal_bad_quantity(self):
        """Lines 65-66 — a non-numeric quantity yields no reversal."""
        from services.return_service import ReturnService

        line = MagicMock()
        type(line).quantity = property(lambda self: (_ for _ in ()).throw(RuntimeError("bad qty")))
        assert ReturnService._commission_reversal_total(line, 1, 1) == Decimal("0")

    def test_commission_reversal_caps_ratio_at_one(self, mocker):
        """Line 71 — returning more than sold is capped at 100%."""
        from services.return_service import ReturnService

        commission_query = MagicMock()
        commission_query.filter_by.return_value.all.return_value = [MagicMock(commission_amount_aed=Decimal("10"))]
        mocker.patch("services.return_service.PartnerCommissionEntry.query", commission_query)
        line = MagicMock(quantity=Decimal("1"), id=5)
        assert ReturnService._commission_reversal_total(line, 3, 1) == Decimal("10.000")

    def test_create_return_posts_commission_reversal(self, app, mocker):
        """Lines 663-664 — the partner-commission GL leg of a return."""
        from services.return_service import ReturnService

        sale = MagicMock(
            id=100,
            tenant_id=1,
            branch_id=2,
            warehouse_id=3,
            status="confirmed",
            customer_id=5,
            customer=MagicMock(),
            currency="AED",
            exchange_rate=Decimal("1"),
            sale_number="S-C-1",
            subtotal=Decimal("100"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("5"),
            seller_id=10,
            prices_include_vat=False,
        )
        sale.recalculate_payment_status = MagicMock()
        product = MagicMock(id=50, name="Widget", has_serial_number=False, cost_price=Decimal("30"))
        line = MagicMock(
            id=200,
            sale_id=100,
            tenant_id=1,
            product_id=50,
            product=product,
            quantity=Decimal("2"),
            line_total=Decimal("100"),
            cost_price=Decimal("40"),
        )
        session = mocker.patch("services.return_service.db.session")
        session.get.side_effect = lambda model, pk: {sale.id: sale, line.id: line}.get(pk)
        session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal(
            "0"
        )
        mocker.patch("services.return_service.generate_number", return_value="R-C-1")
        mocker.patch("services.return_service.get_active_tenant_id", return_value=1)
        mocker.patch("services.return_service.is_platform_owner", return_value=False)
        mocker.patch("services.return_service.branch_scope_id_for", return_value=None)
        mocker.patch("services.return_service.should_post_vat_gl", return_value=True)
        mocker.patch("services.return_service.StockService.create_movement")
        mocker.patch("services.return_service.current_app.config.get", return_value=False)
        mocker.patch(
            "services.return_service.GLService.get_account_code_for_concept",
            return_value="4100",
        )
        mocker.patch("services.return_service.GLService.get_customer_credit_account", return_value="1130")
        mocker.patch("services.return_service.GLService.get_customer_credit_concept", return_value="AR")
        ensure_core = mocker.patch("services.return_service.GLService.ensure_core_accounts")
        posted = mocker.patch("services.return_service.post_or_fail")
        commission_query = MagicMock()
        commission_query.filter_by.return_value.all.return_value = [MagicMock(commission_amount_aed=Decimal("5"))]
        mocker.patch("services.return_service.PartnerCommissionEntry.query", commission_query)
        user = MagicMock(is_authenticated=True, id=10, tenant_id=1)
        user.is_seller = MagicMock(return_value=False)

        with app.app_context():
            result = ReturnService.create_return(
                sale.id, [{"sale_line_id": line.id, "quantity": 1, "condition": "good"}], user=user
            )
        assert result is not None
        assert ensure_core.called
        concept_sets = [row.get("concept_code") for call in posted.call_args_list for row in call.kwargs["lines"]]
        assert "PARTNER_CURRENT_ACCOUNT" in concept_sets


# ════════════════════ services/pos_checkout_service.py ═════════════════════


def _patch_pos_boundary(mocker, *, merged, product, session_obj, shift_obj, table, sale):
    """Patch every collaborator of ``PosCheckoutService.checkout``."""
    mocker.patch(
        "services.pos_checkout_service.get_pos_walkin_customer",
        return_value=SimpleNamespace(id=7, customer_type="retail", name="Walk-in"),
    )
    mocker.patch("services.pos_checkout_service.merge_checkout_lines", return_value=merged)
    mocker.patch("services.pos_checkout_service._safe_for_update", return_value=product)
    mocker.patch("services.pos_checkout_service._pos_standard_price", return_value=Decimal("10"))
    mocker.patch("services.pos_checkout_service.PromotionService.evaluate_cart", return_value=None)
    mocker.patch("services.pos_checkout_service.SaleService.create_sale", return_value=sale)
    mocker.patch(
        "services.pos_checkout_service.PosOverrideService.require_permission_or_override",
        return_value=None,
    )
    mocker.patch("services.pos_checkout_service.PosOrderType.get_by_code", return_value=None)
    mocker.patch("services.pos_checkout_service.PosOrderType.default_for_tenant", return_value=None)
    table_query = MagicMock()
    table_query.filter_by.return_value.first.return_value = table
    mocker.patch("utils.tenanting.tenant_query", return_value=table_query)
    mocker.patch("services.pos_checkout_service.db.session")
    mocker.patch("services.pos_checkout_service._compute_change_due", return_value=Decimal("0"))
    mocker.patch("services.pos_checkout_service.log_mutation")
    mocker.patch("services.pos_checkout_service.LoggingCore.log_audit")


def _pos_user():
    user = MagicMock()
    user.id = 10
    user.is_owner = True
    user.has_permission.return_value = True
    return user


def _pos_session(status="open"):
    return MagicMock(
        id=1,
        tenant_id=1,
        status=status,
        total_sales=Decimal("0"),
        total_cash_sales=Decimal("0"),
        total_change_given=Decimal("0"),
    )


def _pos_sale():
    return MagicMock(
        id=900,
        tenant_id=1,
        sale_number="POS-C-1",
        total_amount=Decimal("10"),
        payment_status="paid",
        table_id=None,
    )


class TestPosCheckoutRemaining:
    def test_empty_merged_cart_uses_empty_lock_set(self, mocker):
        """Line 124 — an empty merge result produces an empty lock dictionary."""
        from services.pos_checkout_service import PosCheckoutService

        _patch_pos_boundary(
            mocker,
            merged=[],
            product=MagicMock(id=1, is_active=True, has_serial_number=False, name="P"),
            session_obj=_pos_session(),
            shift_obj=None,
            table=None,
            sale=_pos_sale(),
        )
        response, _ = PosCheckoutService.checkout(
            payload={"lines": [{"product_id": 1, "quantity": 1}]},
            user=_pos_user(),
            session=_pos_session(),
            shift=None,
            tenant_id=1,
            branch_id=None,
            promotions_enabled=False,
            multi_tender_allowed=False,
        )
        assert response["success"] is True

    def test_serial_numbers_are_normalised(self, mocker):
        """Line 143 — cleaned serials are written back onto the merged row."""
        from services.pos_checkout_service import PosCheckoutService

        product = MagicMock(id=1, is_active=True, has_serial_number=True, name="Serialised")
        merged = [
            {
                "product_id": 1,
                "quantity": 1,
                "unit_price": "10",
                "discount_percent": 0,
                "serials": ["  S1  "],
            }
        ]
        _patch_pos_boundary(
            mocker,
            merged=merged,
            product=product,
            session_obj=_pos_session(),
            shift_obj=None,
            table=None,
            sale=_pos_sale(),
        )
        PosCheckoutService.checkout(
            payload={"lines": merged},
            user=_pos_user(),
            session=_pos_session(),
            shift=None,
            tenant_id=1,
            branch_id=None,
            promotions_enabled=False,
            multi_tender_allowed=False,
        )
        assert merged[0]["serials"] == ["S1"]

    def test_closed_session_is_refused(self, mocker):
        """Line 274 — a closed POS session blocks checkout."""
        from services.pos_checkout_service import PosCheckoutError, PosCheckoutService

        _patch_pos_boundary(
            mocker,
            merged=[{"product_id": 1, "quantity": 1, "unit_price": "10", "discount_percent": 0}],
            product=MagicMock(id=1, is_active=True, has_serial_number=False, name="P"),
            session_obj=_pos_session("closed"),
            shift_obj=None,
            table=None,
            sale=_pos_sale(),
        )
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload={"lines": [{"product_id": 1, "quantity": 1}]},
                user=_pos_user(),
                session=_pos_session("closed"),
                shift=None,
                tenant_id=1,
                branch_id=None,
                promotions_enabled=False,
                multi_tender_allowed=False,
            )

    def test_closed_shift_is_refused(self, mocker):
        """Line 279 — a closed shift blocks checkout."""
        from services.pos_checkout_service import PosCheckoutError, PosCheckoutService

        _patch_pos_boundary(
            mocker,
            merged=[{"product_id": 1, "quantity": 1, "unit_price": "10", "discount_percent": 0}],
            product=MagicMock(id=1, is_active=True, has_serial_number=False, name="P"),
            session_obj=_pos_session(),
            shift_obj=MagicMock(status="closed"),
            table=None,
            sale=_pos_sale(),
        )
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload={"lines": [{"product_id": 1, "quantity": 1}]},
                user=_pos_user(),
                session=_pos_session(),
                shift=MagicMock(status="closed"),
                tenant_id=1,
                branch_id=None,
                promotions_enabled=False,
                multi_tender_allowed=False,
            )

    def test_active_table_is_linked_to_the_sale(self, mocker):
        """Line 313 — the optional table id is attached to the sale."""
        from services.pos_checkout_service import PosCheckoutService

        sale = _pos_sale()
        _patch_pos_boundary(
            mocker,
            merged=[{"product_id": 1, "quantity": 1, "unit_price": "10", "discount_percent": 0}],
            product=MagicMock(id=1, is_active=True, has_serial_number=False, name="P"),
            session_obj=_pos_session(),
            shift_obj=None,
            table=MagicMock(id=99),
            sale=sale,
        )
        PosCheckoutService.checkout(
            payload={"lines": [{"product_id": 1, "quantity": 1}], "table_id": 5},
            user=_pos_user(),
            session=_pos_session(),
            shift=None,
            tenant_id=1,
            branch_id=None,
            promotions_enabled=False,
            multi_tender_allowed=False,
        )
        assert sale.table_id == 99


# ═══════════════════════════ services/gl_service.py ════════════════════════


class TestGLServiceRemaining:
    def test_report_account_requires_a_concept(self, mocker):
        """Line 319 — a blank concept never resolves to an account."""
        from services.gl_service import GLService

        assert GLService._resolve_report_account("", 1) is None

    def test_account_code_for_concept_requires_tenant(self, mocker):
        """Line 1477 — no tenant means the concept cannot be resolved."""
        from services.gl_service import GLService

        mocker.patch("services.gl_service.gl_helpers.resolve_tenant_id", return_value=None)
        with pytest.raises(GLMappingError):
            GLService.get_account_code_for_concept("AR")

    def test_account_balances_empty_ids(self):
        """Line 1647 — no account ids means no balances."""
        from services.gl_service import GLService

        assert GLService._account_balances(1, []) == {}

    def test_labelled_balances_disambiguates_duplicate_names(self):
        """Line 1694 — duplicate account names get their code appended."""
        from services.gl_service import GLService

        first = SimpleNamespace(id=1, name="Cash", code="1100")
        second = SimpleNamespace(id=2, name="Cash", code="1110")
        balances = {1: (Decimal("1"), Decimal("0")), 2: (Decimal("2"), Decimal("0"))}
        result = GLService._labelled_balances([first, second], balances, 1)
        assert result == {"Cash": 1.0, "Cash (1110)": 2.0}

    def test_close_fiscal_year_is_idempotent(self, mocker):
        """Line 2089 — a prior closing entry refuses a second close."""
        from models.gl import GLJournalEntry
        from services.gl_service import FiscalYearService

        mocker.patch.object(
            GLJournalEntry,
            "query",
            MagicMock(filter_by=MagicMock(return_value=MagicMock(first=MagicMock(return_value=MagicMock())))),
        )
        with pytest.raises(ValueError, match="مُقفلة بالفعل"):
            FiscalYearService.close_fiscal_year(1, 2026)


# ══════════════════════ services/stock_sync_service.py ═════════════════════


class TestStockSyncRemaining:
    def _tenant_query(self, mocker, *, existing=None):
        q = MagicMock()
        q.filter_by.return_value.first.return_value = existing
        mocker.patch("services.stock_sync_service.tenant_query", return_value=q)

    def test_payload_tenant_matches_api_key_tenant(self, mocker):
        """Line 153 — the payload tenant is accepted when it matches the key."""
        from services.stock_sync_service import StockSyncService

        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=7)
        batch = MagicMock(id=5, status="completed")
        self._tenant_query(mocker, existing=batch)
        result = StockSyncService.process_sync_payload({"idempotency_key": "cov-c-match", "tenant_id": 7})
        assert result["cached"] is True

    def test_payload_tenant_mismatch_is_refused(self, mocker):
        """Line 152 — a payload naming another tenant is rejected."""
        from services.stock_sync_service import StockSyncService

        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=7)
        with pytest.raises(ValueError, match="does not match"):
            StockSyncService.process_sync_payload({"idempotency_key": "cov-c-mismatch", "tenant_id": 8})

    def test_invalid_unit_cost_is_rejected(self, mocker):
        """Lines 246-247 — an unparsable unit cost aborts the batch."""
        from services.stock_sync_service import StockSyncService

        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        self._tenant_query(mocker, existing=None)
        product = MagicMock(id=1)
        warehouse = MagicMock(id=2)
        mocker.patch(
            "services.stock_sync_service._prefetch_lookups",
            return_value=({"SKU-1": product}, {"WH1": warehouse}, warehouse),
        )
        mocker.patch("services.stock_sync_service.StockService.create_movement")
        mocker.patch("services.stock_sync_service.atomic_transaction", side_effect=lambda _n: contextlib.nullcontext())
        with pytest.raises(ValueError, match="invalid unit_cost"):
            StockSyncService.process_sync_payload(
                {
                    "idempotency_key": "cov-c-cost",
                    "tenant_id": 7,
                    "movements": [
                        {
                            "sku": "SKU-1",
                            "quantity": 1,
                            "movement_type": "adjustment",
                            "unit_cost": "not-a-number",
                        }
                    ],
                }
            )


# ══════════════════════ services/error_audit_service.py ════════════════════


class TestErrorAuditServiceRemaining:
    def test_non_string_value_is_not_a_secret(self):
        """Line 519 — only strings are scanned for secret patterns."""
        from services.error_audit_service import ErrorAuditService

        assert ErrorAuditService._contains_secret_value(12345) is False

    def test_sensitive_headers_are_redacted(self):
        """Lines 548-549 — authorization/cookie headers never reach the log."""
        from services.error_audit_service import ErrorAuditService

        cleaned = ErrorAuditService._sanitize_dict({"Authorization": "Bearer abc", "Set-Cookie": "sid=1"})
        assert cleaned == {"Authorization": "***REDACTED***", "Set-Cookie": "***REDACTED***"}

    def test_secret_pattern_in_value_is_redacted(self):
        """Lines 572-573 — a bearer token inside a value is redacted."""
        from services.error_audit_service import ErrorAuditService

        cleaned = ErrorAuditService._sanitize_dict({"note": "Bearer " + "a" * 30})
        assert cleaned["note"] == "***REDACTED***"


# ══════════════════════ services/ai_training_service.py ═════════════════════


class TestAITrainingServiceRemaining:
    def test_count_memories_counts_total_active_and_corrected(self, db_session, sample_tenant):
        """Lines 51-55 — the dashboard statistics loop."""
        from models.ai import AiMemory
        from services.ai_training_service import count_memories

        db_session.add(
            AiMemory(tenant_id=sample_tenant.id, key="cov-c-1", value="v1", category="general", is_active=True)
        )
        db_session.add(
            AiMemory(tenant_id=sample_tenant.id, key="cov-c-2", value="v2", category="corrected", is_active=True)
        )
        db_session.add(
            AiMemory(tenant_id=sample_tenant.id, key="cov-c-3", value="v3", category="general", is_active=False)
        )
        db_session.flush()
        stats = count_memories(sample_tenant.id)
        assert stats == {"total": 3, "active": 2, "corrected": 1}


# ════════════════════ services/exchange_rate_service.py ═════════════════════


class TestExchangeRateServiceRemaining:
    def test_active_tenant_lookup_failure_falls_back(self, mocker):
        """Lines 275-276 — a broken tenant lookup does not break display rates."""
        from services.exchange_rate_service import ExchangeRateService

        ExchangeRateService._display_cache.clear()
        mocker.patch("utils.tenanting.get_active_tenant_id", side_effect=RuntimeError("no context"))
        mocker.patch.object(ExchangeRateService, "_fetch_primary", return_value=None)
        mocker.patch.object(ExchangeRateService, "_fetch_frankfurter", return_value=None)
        mocker.patch.object(ExchangeRateService, "_fetch_fallbacks", return_value=None)
        result = ExchangeRateService.get_online_rates_for_display("USD", ("AED",))
        assert result["provider"] == "fallback_static"

    def test_resolve_rate_defaults_to_tenant_base_currency(self, mocker, sample_tenant):
        """Lines 391-393 — a blank target currency uses the tenant's base."""
        from services.exchange_rate_service import ExchangeRateService

        mocker.patch("utils.currency_utils.resolve_tenant_base_currency", return_value="AED")
        mocker.patch.object(ExchangeRateService, "_get_admin_rate", return_value=Decimal("3.67"))
        result = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", None, tenant_id=sample_tenant.id)
        assert Decimal(str(result["rate"])) == Decimal("3.67")
