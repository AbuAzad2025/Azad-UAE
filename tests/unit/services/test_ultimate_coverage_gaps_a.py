"""Final statement/branch gaps for five services files.

Covers the active-tenant lookup arcs of AiActionsQueryService, the successful
non-dry-run and warnings/upload arcs of backup_scoped_restore, the missing
cheque_service scoping/journal/bounce/cancel arcs, the remaining POS checkout
branches, and the manual-refund/promo/scoped-query arcs of ReturnService.
Collaborators that own DB writes are stubbed at the service boundary; no
production code or other test file is touched.
"""

from __future__ import annotations

import json
import tarfile
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.ai_actions_query_service import AiActionsQueryService


# ───────────────────────────── ai_actions_query_service ─────────────────────────────
class TestAiActionsActiveTenantArcs:
    @pytest.mark.parametrize(
        "method,model_path",
        [
            ("all_active_sales", "models.sale.Sale"),
            ("all_active_expenses", "models.expense.Expense"),
            ("all_active_purchases", "models.purchase.Purchase"),
            ("all_active_cheques", "models.cheque.Cheque"),
        ],
    )
    def test_active_tenant_filter_applied_when_no_tid(self, mocker, method, model_path):
        chain = MagicMock()
        chain.filter_by.return_value = chain
        chain.all.return_value = ["row"]
        model = mocker.patch(model_path)
        model.query.filter_by.return_value = chain
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=7)

        assert getattr(AiActionsQueryService, method)() == ["row"]
        model.query.filter_by.assert_called_once_with(is_active=True)
        chain.filter_by.assert_called_once_with(tenant_id=7)


# ───────────────────────────── backup_scoped_restore ─────────────────────────────
class TestBackupScopedRestoreTail:
    @staticmethod
    def _bundle(tmp_path, *, with_uploads):
        from services.backup_scope_config import SCOPE_TENANT

        manifest = {
            "backup_scope": SCOPE_TENANT,
            "tenant_id": 7,
            "row_counts_per_table": {"tenants": 1, "products": 1},
        }
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "tenants.jsonl").write_text(json.dumps({"id": 7}), encoding="utf-8")
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        archive = tmp_path / "bundle.tar.gz"
        uploads = None
        if with_uploads:
            uploads = tmp_path / "uploads.tar.gz"
            with tarfile.open(uploads, "w:gz") as utar:
                payload = b"file"
                info = tarfile.TarInfo(name="tenant_7/logo.png")
                info.size = len(payload)
                utar.addfile(info, BytesIO(payload))
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(manifest_path, arcname="manifest.json")
            tar.add(data_dir, arcname="data")
            if uploads is not None:
                tar.add(uploads, arcname="uploads.tar.gz")
        return str(archive)

    @staticmethod
    def _restore_class(mocker, tmp_path, archive, verify):
        from services.backup_scope_config import SCOPE_TENANT

        cls = MagicMock()
        cls._urls_same_database.return_value = False
        cls._BASEDIR = str(tmp_path / "uploads_root")
        cls.verify_backup.return_value = {
            "valid": True,
            "manifest": {"backup_scope": SCOPE_TENANT, "tenant_id": 7, "row_counts_per_table": {}},
        }
        cls._backup_path.return_value = archive
        mocker.patch("services.backup_scoped_engine.ensure_target_schema", return_value=(True, None))
        mocker.patch(
            "services.backup_scoped_restore.import_scoped_tables",
            return_value={"ok": True, "inserted": {}, "errors": []},
        )
        mocker.patch("services.backup_scoped_restore.verify_scoped_restore", return_value=verify)
        return cls

    def test_success_without_uploads_and_without_warnings(self, mocker, tmp_path):
        from services.backup_scoped_restore import RESTORE_CONFIRM, restore_scoped_backup

        archive = self._bundle(tmp_path, with_uploads=False)
        cls = self._restore_class(mocker, tmp_path, archive, {"ok": True, "errors": [], "warnings": []})
        outcome = restore_scoped_backup(
            cls,
            "bundle.tar.gz",
            "postgresql://localhost/newdb",
            confirmation=RESTORE_CONFIRM,
        )
        assert outcome["ok"] is True
        assert outcome["scope"] == "tenant"

    def test_success_with_warnings_and_upload_extraction(self, mocker, tmp_path):
        from services.backup_scoped_restore import RESTORE_CONFIRM, restore_scoped_backup

        archive = self._bundle(tmp_path, with_uploads=True)
        cls = self._restore_class(mocker, tmp_path, archive, {"ok": True, "errors": [], "warnings": ["minor"]})
        dest = tmp_path / "dest"
        dest.mkdir()
        outcome = restore_scoped_backup(
            cls,
            "bundle.tar.gz",
            "postgresql://localhost/newdb",
            confirmation=RESTORE_CONFIRM,
            restore_uploads=True,
            uploads_dest_root=str(dest),
        )
        assert outcome["ok"] is True
        assert any("uploads" in warning for warning in outcome["warnings"])
        assert (dest / "tenant_7" / "logo.png").exists()


# ───────────────────────────── cheque_service ─────────────────────────────
def _cheque(**overrides):
    cheque = MagicMock()
    defaults = {
        "id": 1,
        "tenant_id": 1,
        "branch_id": 2,
        "cheque_type": "incoming",
        "cheque_type_ar": "وارد",
        "status": "deposited",
        "amount": Decimal("100"),
        "amount_aed": Decimal("100"),
        "actual_amount_aed": Decimal("100"),
        "currency": "AED",
        "exchange_rate": Decimal("1"),
        "currency_gain_loss": Decimal("0"),
        "cheque_bank_number": "BNK-1",
        "customer_id": None,
        "customer": None,
        "supplier_id": None,
        "expense_id": None,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(cheque, key, value)
    return cheque


def _query_with_first(result):
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = result
    return query


class TestChequeServiceGaps:
    def test_scoped_queries_without_tenant(self, db_session):
        from services.cheque_service import ChequeService

        assert ChequeService.scoped_customers_query(tenant_id=None, branch_id=None) is not None
        assert ChequeService.scoped_suppliers_query(tenant_id=None, branch_id=None) is not None

    def test_clearing_entry_unknown_type_skips_posting(self, mocker):
        from services.cheque_service import _create_clearing_journal_entry

        mocker.patch("services.cheque_service.gl_get_default_liquidity_account", return_value="1110")
        post = mocker.patch("services.cheque_service._post_gl")
        _create_clearing_journal_entry(_cheque(cheque_type="other", currency_gain_loss=Decimal("1")))
        post.assert_not_called()

    def test_clear_without_tenant_scope(self, mocker):
        from services.cheque_service import process_cheque_clear

        mocker.patch("utils.currency_utils.resolve_tenant_base_currency", return_value="AED")
        mocker.patch("utils.currency_utils.convert_and_quantize_aed", return_value=Decimal("100"))
        mocker.patch("services.cheque_service._create_clearing_journal_entry")
        payment = mocker.patch("models.payment.Payment")
        receipt = mocker.patch("models.receipt.Receipt")
        payment.query.filter_by.return_value.first.return_value = None
        receipt.query.filter_by.return_value.first.return_value = None

        cheque = _cheque(tenant_id=None, status="pending")
        process_cheque_clear(cheque)
        assert cheque.status == "cleared"

    def test_bounce_entry_unknown_type_skips_posting(self, mocker):
        from services.cheque_service import _create_bounce_journal_entry

        post = mocker.patch("services.cheque_service._post_gl")
        _create_bounce_journal_entry(_cheque(cheque_type="other"))
        post.assert_not_called()

    def test_bounce_entry_expense_category_account(self, mocker):
        from services.cheque_service import _create_bounce_journal_entry

        post = mocker.patch("services.cheque_service._post_gl")
        gl = mocker.patch("services.cheque_service.GLService")
        gl.get_account_code_for_concept.return_value = "2110"
        db = mocker.patch("services.cheque_service.db")
        db.session.get.return_value = MagicMock(category=MagicMock(gl_account_code="6100"))

        cheque = _cheque(cheque_type="outgoing", expense_id=7, supplier_id=None, customer_id=None)
        _create_bounce_journal_entry(cheque)
        lines = post.call_args.kwargs["lines"]
        assert lines[-1]["account"] == "6100"

    def test_bounce_incoming_pending_is_rejected(self):
        from services.cheque_service import process_cheque_bounce

        with pytest.raises(Exception):
            process_cheque_bounce(_cheque(cheque_type="incoming", status="pending"), "reason")

    def test_bounce_fee_without_tenant_and_missing_supplier(self, mocker):
        from services.cheque_service import process_cheque_bounce

        mocker.patch("services.cheque_service.db")
        mocker.patch("services.cheque_service._create_bounce_journal_entry")
        gl = mocker.patch("services.cheque_service.GLService")
        gl.get_account_code_for_concept.return_value = "6600"
        mocker.patch("services.cheque_service.gl_get_default_liquidity_account", return_value="1110")
        post_or_fail = mocker.patch("services.gl_posting.post_or_fail")

        journal = mocker.patch("models.GLJournalEntry")
        journal.query.filter.return_value = _query_with_first(None)
        payment = mocker.patch("models.payment.Payment")
        receipt = mocker.patch("models.receipt.Receipt")
        payment.query.filter_by.return_value.first.return_value = MagicMock()
        receipt.query.filter_by.return_value.first.return_value = None
        supplier = mocker.patch("models.supplier.Supplier")
        supplier.query.filter_by.return_value.first.return_value = None

        cheque = _cheque(tenant_id=None, cheque_type="outgoing", supplier_id=9, status="deposited")
        process_cheque_bounce(cheque, "reason", bounce_fee=Decimal("5"))
        post_or_fail.assert_called_once()

    def test_bounce_fee_already_posted_is_skipped(self, mocker):
        from services.cheque_service import process_cheque_bounce

        mocker.patch("services.cheque_service.db")
        mocker.patch("services.cheque_service._create_bounce_journal_entry")
        gl = mocker.patch("services.cheque_service.GLService")
        gl.get_account_code_for_concept.return_value = "6600"
        mocker.patch("services.cheque_service.gl_get_default_liquidity_account", return_value="1110")
        post_or_fail = mocker.patch("services.gl_posting.post_or_fail")

        journal = mocker.patch("models.GLJournalEntry")
        journal.query.filter.return_value = _query_with_first(MagicMock())
        payment = mocker.patch("models.payment.Payment")
        receipt = mocker.patch("models.receipt.Receipt")
        payment.query.filter_by.return_value.first.return_value = None
        receipt.query.filter_by.return_value.first.return_value = None

        process_cheque_bounce(_cheque(tenant_id=1, status="deposited"), "reason", bounce_fee=Decimal("5"))
        post_or_fail.assert_not_called()

    def test_cancel_entry_unknown_type_skips_posting(self, mocker):
        from services.cheque_service import _create_cancel_journal_entry

        post = mocker.patch("services.cheque_service._post_gl")
        _create_cancel_journal_entry(_cheque(cheque_type="other"))
        post.assert_not_called()

    def test_cancel_incoming_with_subledger_reverses_customer(self, mocker):
        from services.cheque_service import process_cheque_cancel

        mocker.patch("services.cheque_service._create_cancel_journal_entry")
        payment = mocker.patch("models.Payment")
        receipt = mocker.patch("models.receipt.Receipt")
        payments = payment.query.filter_by.return_value
        payments.filter.return_value = payments
        payments.all.return_value = [MagicMock()]
        receipts = receipt.query.filter_by.return_value
        receipts.filter.return_value = receipts
        receipts.all.return_value = []

        cheque = _cheque(tenant_id=1, cheque_type="incoming", customer_id=5, customer=MagicMock(), status="pending")
        process_cheque_cancel(cheque, "reason")
        cheque.customer.adjust_balance.assert_called_once()

    def test_cancel_outgoing_without_tenant_and_missing_supplier(self, mocker):
        from services.cheque_service import process_cheque_cancel

        mocker.patch("services.cheque_service._create_cancel_journal_entry")
        payment = mocker.patch("models.Payment")
        receipt = mocker.patch("models.receipt.Receipt")
        payments = payment.query.filter_by.return_value
        payments.filter.return_value = payments
        payments.all.return_value = [MagicMock()]
        receipts = receipt.query.filter_by.return_value
        receipts.filter.return_value = receipts
        receipts.all.return_value = []
        supplier = mocker.patch("models.supplier.Supplier")
        supplier.query.filter_by.return_value.first.return_value = None

        cheque = _cheque(tenant_id=None, cheque_type="outgoing", supplier_id=9, status="pending")
        process_cheque_cancel(cheque, "reason")


# ───────────────────────────── pos_checkout_service ─────────────────────────────
def _pos_env(mocker, *, order_type=None, promotion_error=None):
    customer = MagicMock()
    customer.id = 7
    customer.name = "Walkin"
    customer.customer_type = "individual"

    product = MagicMock()
    product.id = 50
    product.name = "Widget"
    product.name_ar = "منتج"
    product.is_active = True
    product.has_serial_number = False
    product.category_id = None

    sale = MagicMock()
    sale.id = 900
    sale.sale_number = "POS-900"
    sale.total_amount = Decimal("10")
    sale.amount_aed = Decimal("10")
    sale.tenant_id = 1
    sale.payment_status = "paid"

    mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=customer)
    mocker.patch("services.pos_checkout_service.db")
    mocker.patch("services.pos_checkout_service._safe_for_update", return_value=product)
    mocker.patch("utils.pos_checkout_helpers.PricingService.get_price", return_value=Decimal("10"))
    mocker.patch("services.pos_checkout_service.SaleService.create_sale", return_value=sale)
    mocker.patch(
        "services.pos_checkout_service.PosWriteService.create_kds_order",
        return_value=SimpleNamespace(id=9),
    )
    ot = mocker.patch("services.pos_checkout_service.PosOrderType")
    ot.get_by_code.return_value = order_type
    ot.default_for_tenant.return_value = None
    promo = mocker.patch("services.pos_checkout_service.PromotionService.evaluate_cart")
    if promotion_error is not None:
        promo.side_effect = promotion_error

    def to_aed(amount, currency, rate, **kwargs):
        return Decimal(str(amount))

    mocker.patch("services.pos_checkout_service.convert_and_quantize_aed", side_effect=to_aed)
    mocker.patch("utils.pos_checkout_helpers.convert_and_quantize_aed", side_effect=to_aed)
    mocker.patch("services.pos_checkout_service._accumulate_session_tender_atomic")
    mocker.patch("services.pos_checkout_service.LoggingCore.log_audit")
    mocker.patch("services.pos_checkout_service.log_mutation")
    tenant_query = mocker.patch("utils.tenanting.tenant_query")
    tenant_query.return_value.filter_by.return_value.first.return_value = None
    mocker.patch(
        "services.pos_checkout_service.PosOverrideService.require_permission_or_override",
        return_value=123,
    )
    mocker.patch("services.pos_checkout_service.get_active_branch_id", return_value=1)
    mocker.patch("services.pos_checkout_service.context_aware_default_currency", return_value="AED")

    user = MagicMock()
    user.id = 1
    user.is_owner = False
    user.has_permission = lambda code: True
    session = MagicMock()
    session.id = 11
    session.tenant_id = 1
    session.status = "open"
    session.total_sales = Decimal("0")
    session.total_cash_sales = Decimal("0")
    session.total_change_given = Decimal("0")
    shift = SimpleNamespace(id=12, total_change_given=Decimal("0"))
    return {
        "user": user,
        "session": session,
        "shift": shift,
        "tenant_id": 1,
        "branch_id": 2,
        "promotions_enabled": False,
        "multi_tender_allowed": True,
    }


def _pos_checkout(**kwargs):
    from services.pos_checkout_service import PosCheckoutService

    return PosCheckoutService.checkout(**kwargs)


def _pos_payload(lines=None, **overrides):
    payload = {
        "walkin": True,
        "currency": "AED",
        "lines": lines if lines is not None else [{"product_id": 50, "quantity": 1}],
    }
    payload.update(overrides)
    return payload


class TestPosCheckoutRemainingArcs:
    def test_standard_price_when_unit_price_absent(self, mocker):
        env = _pos_env(mocker)
        response, _ = _pos_checkout(payload=_pos_payload(), **env)
        assert response["success"] is True

    def test_price_override_with_permission_is_audited(self, mocker):
        env = _pos_env(mocker)
        lines = [{"product_id": 50, "quantity": 1, "unit_price": "99999"}]
        response, _ = _pos_checkout(payload=_pos_payload(lines=lines), **env)
        assert response["success"] is True

    def test_promotion_failure_is_swallowed(self, mocker):
        env = _pos_env(mocker, promotion_error=RuntimeError("promo down"))
        env["promotions_enabled"] = True
        response, _ = _pos_checkout(payload=_pos_payload(), **env)
        assert response["promotion_discount"] == 0.0

    def test_paid_amount_parse_and_method_branches(self, mocker):
        env = _pos_env(mocker)
        from services.pos_checkout_service import PosCheckoutError

        response, _ = _pos_checkout(payload=_pos_payload(paid_amount="not-money"), **env)
        assert response["success"] is True
        with pytest.raises(PosCheckoutError):
            _pos_checkout(payload=_pos_payload(paid_amount=20, payment_method=""), **env)
        response, _ = _pos_checkout(payload=_pos_payload(paid_amount=20, payment_method="card"), **env)
        assert response["success"] is True

    def test_split_tender_error_and_success(self, mocker):
        env = _pos_env(mocker)
        from services.pos_checkout_service import PosCheckoutError

        with pytest.raises(PosCheckoutError):
            _pos_checkout(payload=_pos_payload(payments=[{"bad": 1}]), **env)
        response, _ = _pos_checkout(
            payload=_pos_payload(payments=[{"amount": 5, "payment_method": "card"}]),
            **env,
        )
        assert response["success"] is True

    def test_qa_marker_invalid_table_and_known_order_type(self, mocker):
        order_type = SimpleNamespace(code="dine_in", kds_enabled=False)
        env = _pos_env(mocker, order_type=order_type)
        response, _ = _pos_checkout(
            payload=_pos_payload(
                qa_marker=True,
                notes="n",
                table_id="not-an-int",
                order_type="dine_in",
                payment_method="card",
                paid_amount=5,
            ),
            **env,
        )
        assert response["order_type"] == "dine_in"

    def test_cash_change_with_shift(self, mocker):
        env = _pos_env(mocker)
        response, _ = _pos_checkout(payload=_pos_payload(payment_method="cash", paid_amount=50), **env)
        assert response["change_due"] == 40.0

    def test_cash_change_without_shift(self, mocker):
        env = _pos_env(mocker)
        env["shift"] = None
        response, _ = _pos_checkout(payload=_pos_payload(payment_method="cash", paid_amount=50), **env)
        assert response["change_due"] == 40.0

    def test_split_tender_without_change(self, mocker):
        env = _pos_env(mocker)
        env["shift"] = None
        response, _ = _pos_checkout(
            payload=_pos_payload(payments=[{"amount": 5, "payment_method": "card"}]),
            **env,
        )
        assert response["change_due"] == 0.0

    def test_session_none_branch(self, mocker):
        env = _pos_env(mocker)
        env["session"] = None
        with pytest.raises(AttributeError):
            _pos_checkout(payload=_pos_payload(), **env)


# ───────────────────────────── return_service ─────────────────────────────
def _return_setup(
    mocker,
    *,
    line_total="100",
    cost="40",
    product_cost="30",
    tax_rate="5",
    promo=None,
    customer=True,
    recalc=True,
    commission="0",
    vat=True,
):
    sale = SimpleNamespace(
        id=100,
        tenant_id=1,
        branch_id=2,
        warehouse_id=3,
        status="confirmed",
        customer_id=5 if customer else None,
        customer=MagicMock() if customer else None,
        currency="AED",
        exchange_rate=Decimal("1"),
        sale_number="S-100",
        subtotal=Decimal("100"),
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        tax_rate=Decimal(tax_rate),
        seller_id=10,
        prices_include_vat=False,
    )
    if recalc:
        sale.recalculate_payment_status = MagicMock()
    if promo is not None:
        sale.promotion_discount_amount = Decimal(promo)

    line = SimpleNamespace(
        id=200,
        sale_id=sale.id,
        tenant_id=1,
        product_id=50,
        quantity=Decimal("1"),
        line_total=Decimal(line_total),
        cost_price=Decimal(cost),
        tax_category="standard",
    )
    product = SimpleNamespace(id=50, name="Widget", has_serial_number=False, cost_price=Decimal(product_cost))
    line.product = product

    session = mocker.patch("services.return_service.db.session")
    session.get.side_effect = lambda model, pk: {sale.id: sale, line.id: line}.get(pk)
    sum_chain = session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value
    sum_chain.scalar.return_value = Decimal("0")
    mocker.patch("services.return_service.generate_number", return_value="R-1")
    mocker.patch("services.return_service.should_post_vat_gl", return_value=vat)
    mocker.patch("services.return_service.current_app.config.get", return_value=False)
    mocker.patch("services.return_service.GLService.get_account_code_for_concept", return_value="4100")
    mocker.patch("services.return_service.GLService.get_customer_credit_account", return_value="1130")
    mocker.patch("services.return_service.GLService.get_customer_credit_concept", return_value="AR")
    mocker.patch("services.return_service.GLService.ensure_core_accounts")
    post = mocker.patch("services.return_service.post_or_fail")
    mocker.patch("services.return_service.StockService.create_movement")
    mocker.patch(
        "services.return_service.ReturnService._commission_reversal_total",
        return_value=Decimal(commission),
    )
    mocker.patch("utils.currency_utils.convert_and_quantize_aed", return_value=Decimal("100"))
    mocker.patch("services.einvoice_service.EInvoiceService.generate_for_return")
    cost_history = mocker.patch("models.ProductCostHistory")
    cost_history.query.filter_by.return_value.order_by.return_value.first.return_value = None
    return post


def _create_return(mocker, manual_refund_amount=None):
    from services.return_service import ReturnService

    return ReturnService.create_return(
        100,
        [{"sale_line_id": 200, "quantity": 1, "condition": "good"}],
        user=None,
        manual_refund_amount=manual_refund_amount,
    )


class TestReturnServiceRemainingArcs:
    def test_automatic_path_posts_revenue_and_cost(self, mocker):
        _return_setup(mocker)
        assert _create_return(mocker) is not None

    def test_manual_refund_with_nonzero_blended_rate(self, mocker):
        _return_setup(mocker)
        result = _create_return(mocker, "50")
        assert result.refund_amount == Decimal("50.000")

    def test_manual_refund_with_zero_blended_rate(self, mocker):
        _return_setup(mocker, tax_rate="0")
        result = _create_return(mocker, "50")
        assert result.refund_amount == Decimal("50.000")

    def test_zero_refund_zero_cost_no_customer_no_recalculate(self, mocker):
        _return_setup(mocker, cost="0", product_cost="0", customer=False, recalc=False)
        result = _create_return(mocker, "0")
        assert result.refund_amount == Decimal("0.000")

    def test_promotional_discount_reversal_is_posted(self, mocker):
        post = _return_setup(mocker, promo="20")
        _create_return(mocker)
        assert any(
            line["concept_code"] == "CAMPAIGN_DISCOUNT_REVERSAL"
            for call in post.call_args_list
            for line in call.kwargs.get("lines", [])
        )

    def test_partner_commission_reversal_is_posted(self, mocker):
        post = _return_setup(mocker, commission="10")
        _create_return(mocker)
        assert any(
            line["concept_code"] == "PARTNER_CURRENT_ACCOUNT"
            for call in post.call_args_list
            for line in call.kwargs.get("lines", [])
        )

    def test_einvoice_failure_is_reraised(self, mocker):
        _return_setup(mocker)
        mocker.patch(
            "services.einvoice_service.EInvoiceService.generate_for_return",
            side_effect=RuntimeError("einvoice down"),
        )
        with pytest.raises(RuntimeError, match="einvoice down"):
            _create_return(mocker)

    def test_scoped_query_platform_owner_without_tenant(self, mocker):
        from services.return_service import ReturnService

        mocker.patch("services.return_service.get_active_tenant_id", return_value=None)
        mocker.patch("services.return_service.is_platform_owner", return_value=True)
        user = MagicMock()
        user.is_seller = None
        assert ReturnService.get_scoped_returns_query(user) is not None

    def test_scoped_query_non_owner_without_tenant(self, mocker):
        from services.return_service import ReturnService

        mocker.patch("services.return_service.get_active_tenant_id", return_value=None)
        mocker.patch("services.return_service.is_platform_owner", return_value=False)
        user = MagicMock()
        user.is_seller = None
        assert ReturnService.get_scoped_returns_query(user) is not None

    def test_scoped_query_seller_and_branch(self, mocker):
        from services.return_service import ReturnService

        mocker.patch("services.return_service.get_active_tenant_id", return_value=1)
        mocker.patch("services.return_service.is_platform_owner", return_value=False)
        user = MagicMock()
        user.id = 10
        user.is_seller = MagicMock(return_value=True)
        assert ReturnService.get_scoped_returns_query(user, scoped_branch_id=99) is not None

    def test_search_sales_for_both_query_shapes(self, mocker):
        from services.return_service import ReturnService

        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        customer = MagicMock()
        customer.name = "Ali"
        chain.paginate.return_value.items = [
            MagicMock(id=5, sale_number="S-5", customer=customer, total_amount=Decimal("10"), currency="AED")
        ]
        mocker.patch("utils.tenanting.tenant_query", return_value=chain)

        for query in ("123", "S-5"):
            items, pagination = ReturnService.search_sales_for_return(query, 1, 10, MagicMock())
            assert items[0]["sale_number"] == "S-5"
            assert pagination is chain.paginate.return_value
