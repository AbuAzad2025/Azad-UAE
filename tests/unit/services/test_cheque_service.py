from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from models import Cheque, Payment, Receipt
from services.cheque_service import (
    calculate_amount_aed,
    process_cheque_bounce,
    process_cheque_cancel,
    process_cheque_clear,
    process_cheque_deposit,
    process_cheque_issue,
    process_cheque_receive,
    register_cheque_event_listeners,
    validate_cheque,
)


@pytest.fixture(autouse=True)
def _patch_gl_dependencies(mocker):
    mocker.patch("services.cheque_service.gl_ensure_core_accounts")
    mocker.patch("services.cheque_service.gl_post_or_fail", return_value=MagicMock(id=101))
    mocker.patch(
        "services.cheque_service.GLService.get_account_code_for_concept",
        return_value="1100",
    )
    mocker.patch("services.cheque_service.gl_get_customer_credit_account", return_value="1200")
    mocker.patch("services.cheque_service.gl_get_customer_credit_concept", return_value="AR")
    mocker.patch("services.cheque_service.gl_get_default_liquidity_account", return_value="1101")
    mocker.patch("utils.currency_utils.get_system_default_currency", return_value="AED")


def _minimal_cheque(**overrides):
    base = dict(
        cheque_number=f"CH-{uuid.uuid4().hex[:6]}",
        cheque_bank_number=f"BNK-{uuid.uuid4().hex[:4]}",
        bank_name="Test Bank",
        amount=Decimal("1000"),
        amount_aed=Decimal("1000"),
        currency="AED",
        exchange_rate=Decimal("1"),
        issue_date=date.today(),
        due_date=date.today(),
        cheque_type="incoming",
        status="pending",
    )
    base.update(overrides)
    return Cheque(**base)


class TestValidateCheque:
    def test_rejects_missing_number(self):
        ch = _minimal_cheque(cheque_number="")
        with pytest.raises(ValueError, match="رقم الشيك مطلوب"):
            validate_cheque(ch)

    def test_rejects_missing_bank_number(self):
        ch = _minimal_cheque(cheque_bank_number="")
        with pytest.raises(ValueError, match="رقم الشيك البنكي"):
            validate_cheque(ch)

    def test_rejects_missing_bank_name(self):
        ch = _minimal_cheque(bank_name="")
        with pytest.raises(ValueError, match="اسم البنك"):
            validate_cheque(ch)

    def test_rejects_non_positive_amount(self):
        ch = _minimal_cheque(amount=Decimal("0"))
        with pytest.raises(ValueError, match="المبلغ"):
            validate_cheque(ch)

    def test_rejects_missing_issue_date(self):
        ch = _minimal_cheque(issue_date=None)
        with pytest.raises(ValueError, match="تاريخ الإصدار"):
            validate_cheque(ch)

    def test_rejects_missing_due_date(self):
        ch = _minimal_cheque(due_date=None)
        with pytest.raises(ValueError, match="تاريخ الاستحقاق"):
            validate_cheque(ch)

    def test_rejects_invalid_type(self):
        ch = _minimal_cheque(cheque_type="invalid")
        with pytest.raises(ValueError, match="نوع الشيك"):
            validate_cheque(ch)

    def test_accepts_valid(self, incoming_cheque):
        validate_cheque(incoming_cheque)


class TestCalculateAmountAed:
    def test_base_currency(self, incoming_cheque):
        incoming_cheque.currency = "AED"
        incoming_cheque.amount = Decimal("500")
        calculate_amount_aed(incoming_cheque)
        assert incoming_cheque.amount_aed == Decimal("500")

    def test_foreign_with_rate(self, incoming_cheque):
        incoming_cheque.currency = "USD"
        incoming_cheque.amount = Decimal("100")
        incoming_cheque.exchange_rate = Decimal("3.67")
        calculate_amount_aed(incoming_cheque)
        assert incoming_cheque.amount_aed == Decimal("367.00")

    def test_foreign_without_rate(self, incoming_cheque):
        incoming_cheque.currency = "USD"
        incoming_cheque.amount = Decimal("200")
        incoming_cheque.exchange_rate = None
        calculate_amount_aed(incoming_cheque)
        assert incoming_cheque.amount_aed == Decimal("200")


class TestDeposit:
    def test_deposit_pending(self, incoming_cheque):
        process_cheque_deposit(incoming_cheque, deposit_date=date(2026, 1, 10))
        assert incoming_cheque.status == "deposited"
        assert incoming_cheque.deposit_date == date(2026, 1, 10)

    def test_deposit_under_collection(self, incoming_cheque):
        incoming_cheque.status = "under_collection"
        process_cheque_deposit(incoming_cheque)
        assert incoming_cheque.status == "deposited"

    def test_deposit_rejects_cleared(self, incoming_cheque):
        incoming_cheque.status = "cleared"
        with pytest.raises(ValueError, match="لا يمكن إيداع"):
            process_cheque_deposit(incoming_cheque)


class TestReceiveAndIssue:
    def test_receive_incoming(self, incoming_cheque):
        entry = process_cheque_receive(incoming_cheque)
        assert entry is not None

    def test_receive_outgoing_returns_none(self, outgoing_cheque):
        assert process_cheque_receive(outgoing_cheque) is None

    def test_issue_outgoing_supplier(self, mocker, db_session, sample_tenant, sample_supplier, outgoing_cheque):
        outgoing_cheque.supplier_id = sample_supplier.id
        db_session.flush()
        entry = process_cheque_issue(outgoing_cheque)
        assert entry is not None
        assert outgoing_cheque.gl_journal_entry_id == 101

    def test_issue_outgoing_customer(self, mocker, db_session, sample_customer, outgoing_cheque):
        outgoing_cheque.customer_id = sample_customer.id
        db_session.flush()
        assert process_cheque_issue(outgoing_cheque) is not None

    def test_issue_outgoing_expense_skips_gl(self, db_session, sample_expense, outgoing_cheque):
        outgoing_cheque.expense_id = sample_expense.id
        db_session.flush()
        assert process_cheque_issue(outgoing_cheque) is None

    def test_issue_incoming_returns_none(self, incoming_cheque):
        assert process_cheque_issue(incoming_cheque) is None


class TestClearCheque:
    def test_clear_deposited_aed(self, incoming_cheque):
        incoming_cheque.status = "deposited"
        process_cheque_clear(incoming_cheque, clearance_date=date(2026, 2, 1))
        assert incoming_cheque.status == "cleared"
        assert incoming_cheque.clearance_exchange_rate == Decimal("1.0")

    def test_clear_with_manual_rate(self, mocker, db_session, incoming_cheque):
        incoming_cheque.currency = "USD"
        incoming_cheque.amount = Decimal("100")
        incoming_cheque.amount_aed = Decimal("367")
        incoming_cheque.exchange_rate = Decimal("3.67")
        incoming_cheque.status = "deposited"
        db_session.flush()
        process_cheque_clear(incoming_cheque, clearance_exchange_rate=Decimal("3.70"))
        assert incoming_cheque.actual_amount_aed == Decimal("370.00")
        assert incoming_cheque.currency_gain_loss == Decimal("3.00")

    def test_clear_resolves_rate_on_failure(self, mocker, db_session, incoming_cheque):
        incoming_cheque.currency = "USD"
        incoming_cheque.amount = Decimal("50")
        incoming_cheque.amount_aed = Decimal("183.5")
        incoming_cheque.exchange_rate = Decimal("3.67")
        incoming_cheque.status = "pending"
        db_session.flush()
        mocker.patch(
            "services.cheque_service.gl_resolve_exchange_rate",
            side_effect=RuntimeError("no rate"),
        )
        process_cheque_clear(incoming_cheque)
        assert incoming_cheque.clearance_exchange_rate == Decimal("3.67")

    def test_clear_fx_gain_incoming(self, mocker, db_session, incoming_cheque):
        incoming_cheque.status = "deposited"
        incoming_cheque.currency = "USD"
        incoming_cheque.amount = Decimal("100")
        incoming_cheque.amount_aed = Decimal("360")
        incoming_cheque.exchange_rate = Decimal("3.6")
        db_session.flush()
        process_cheque_clear(incoming_cheque, clearance_exchange_rate=Decimal("3.70"))
        assert incoming_cheque.currency_gain_loss > Decimal("0")

    def test_clear_fx_loss_incoming(self, mocker, db_session, incoming_cheque):
        incoming_cheque.status = "deposited"
        incoming_cheque.currency = "USD"
        incoming_cheque.amount = Decimal("100")
        incoming_cheque.amount_aed = Decimal("370")
        incoming_cheque.exchange_rate = Decimal("3.7")
        db_session.flush()
        process_cheque_clear(incoming_cheque, clearance_exchange_rate=Decimal("3.60"))
        assert incoming_cheque.currency_gain_loss < Decimal("0")

    def test_clear_outgoing_with_fx(self, mocker, db_session, outgoing_cheque):
        outgoing_cheque.status = "deposited"
        outgoing_cheque.currency = "USD"
        outgoing_cheque.amount = Decimal("200")
        outgoing_cheque.amount_aed = Decimal("734")
        outgoing_cheque.exchange_rate = Decimal("3.67")
        db_session.flush()
        process_cheque_clear(outgoing_cheque, clearance_exchange_rate=Decimal("3.80"))
        assert outgoing_cheque.status == "cleared"

    def test_clear_confirms_payment(self, mocker, db_session, sample_tenant, outgoing_cheque, sample_user):
        outgoing_cheque.status = "deposited"
        payment = Payment(
            tenant_id=sample_tenant.id,
            payment_number=f"PAY-{uuid.uuid4().hex[:6]}",
            payment_type="supplier_payment",
            amount=Decimal("500"),
            amount_aed=Decimal("500"),
            payment_method="cheque",
            payment_confirmed=False,
            cheque_id=outgoing_cheque.id,
            user_id=sample_user.id,
        )
        db_session.add(payment)
        db_session.flush()
        process_cheque_clear(outgoing_cheque)
        assert payment.payment_confirmed is True

    def test_clear_confirms_receipt(
        self,
        mocker,
        db_session,
        sample_tenant,
        incoming_cheque,
        sample_customer,
        sample_user,
    ):
        incoming_cheque.status = "deposited"
        receipt = Receipt(
            tenant_id=sample_tenant.id,
            receipt_number=f"RCP-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
            payment_method="cheque",
            payment_confirmed=False,
            cheque_id=incoming_cheque.id,
            user_id=sample_user.id,
        )
        db_session.add(receipt)
        db_session.flush()
        process_cheque_clear(incoming_cheque)
        assert receipt.payment_confirmed is True

    def test_clear_rejects_wrong_status(self, incoming_cheque):
        incoming_cheque.status = "bounced"
        with pytest.raises(ValueError, match="لا يمكن تأكيد صرف"):
            process_cheque_clear(incoming_cheque)


class TestBounceCheque:
    def test_bounce_incoming(self, mocker, db_session, incoming_cheque):
        incoming_cheque.status = "deposited"
        process_cheque_bounce(incoming_cheque, reason="NSF")
        assert incoming_cheque.status == "bounced"
        assert incoming_cheque.bounce_reason == "NSF"

    def test_bounce_outgoing_supplier(self, mocker, db_session, sample_supplier, outgoing_cheque):
        outgoing_cheque.status = "pending"
        outgoing_cheque.supplier_id = sample_supplier.id
        db_session.flush()
        process_cheque_bounce(outgoing_cheque, reason="Insufficient funds")
        assert outgoing_cheque.status == "bounced"

    def test_bounce_outgoing_expense(self, db_session, sample_expense, outgoing_cheque):
        outgoing_cheque.status = "deposited"
        outgoing_cheque.expense_id = sample_expense.id
        db_session.flush()
        process_cheque_bounce(outgoing_cheque, reason="Returned")
        assert outgoing_cheque.status == "bounced"

    def test_bounce_with_fee(self, mocker, incoming_cheque):
        incoming_cheque.status = "deposited"
        post = mocker.patch("services.gl_posting.post_or_fail")
        process_cheque_bounce(incoming_cheque, reason="NSF", bounce_fee=Decimal("25"))
        post.assert_called_once()

    def test_bounce_fee_failure_logged(self, mocker, incoming_cheque):
        incoming_cheque.status = "deposited"
        mocker.patch("services.gl_posting.post_or_fail", side_effect=RuntimeError("gl"))
        process_cheque_bounce(incoming_cheque, reason="NSF", bounce_fee=Decimal("10"))

    def test_bounce_adjusts_customer(self, mocker, db_session, sample_customer, incoming_cheque):
        incoming_cheque.status = "deposited"
        incoming_cheque.customer_id = sample_customer.id
        db_session.flush()
        adjust = mocker.patch.object(sample_customer, "adjust_balance")
        process_cheque_bounce(incoming_cheque, reason="NSF")
        adjust.assert_called_once()

    def test_bounce_rejects_payment(self, db_session, sample_tenant, outgoing_cheque, sample_user):
        outgoing_cheque.status = "pending"
        payment = Payment(
            tenant_id=sample_tenant.id,
            payment_number=f"PAY-{uuid.uuid4().hex[:6]}",
            payment_type="supplier_payment",
            amount=Decimal("500"),
            amount_aed=Decimal("500"),
            payment_method="cheque",
            payment_confirmed=True,
            cheque_id=outgoing_cheque.id,
            user_id=sample_user.id,
        )
        db_session.add(payment)
        db_session.flush()
        process_cheque_bounce(outgoing_cheque, reason="Bounced")
        assert payment.payment_confirmed is False

    def test_bounce_rejects_receipt(self, db_session, sample_tenant, incoming_cheque, sample_customer, sample_user):
        incoming_cheque.status = "deposited"
        receipt = Receipt(
            tenant_id=sample_tenant.id,
            receipt_number=f"RCP-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
            payment_method="cheque",
            payment_confirmed=True,
            cheque_id=incoming_cheque.id,
            user_id=sample_user.id,
        )
        db_session.add(receipt)
        db_session.flush()
        process_cheque_bounce(incoming_cheque, reason="NSF")
        assert receipt.payment_confirmed is False

    def test_bounce_wrong_status(self, incoming_cheque):
        incoming_cheque.status = "cleared"
        with pytest.raises(ValueError, match="لا يمكن رفض"):
            process_cheque_bounce(incoming_cheque, reason="x")


class TestCancelCheque:
    def test_cancel_incoming(self, incoming_cheque):
        process_cheque_cancel(incoming_cheque, reason="Void", create_gl=True)
        assert incoming_cheque.status == "cancelled"
        assert "سبب الإلغاء" in (incoming_cheque.notes or "")

    def test_cancel_already_cancelled(self, incoming_cheque):
        incoming_cheque.status = "cancelled"
        process_cheque_cancel(incoming_cheque)
        assert incoming_cheque.status == "cancelled"

    def test_cancel_outgoing_supplier_restores_ap(self, mocker, db_session, sample_supplier, outgoing_cheque):
        outgoing_cheque.supplier_id = sample_supplier.id
        db_session.flush()
        apply = mocker.patch.object(sample_supplier, "apply_payment")
        process_cheque_cancel(outgoing_cheque, create_gl=True)
        apply.assert_called_once()

    def test_cancel_outgoing_expense(self, db_session, sample_expense, outgoing_cheque):
        outgoing_cheque.expense_id = sample_expense.id
        db_session.flush()
        process_cheque_cancel(outgoing_cheque, create_gl=True)

    def test_cancel_skips_gl(self, incoming_cheque, mocker):
        post = mocker.patch("services.cheque_service.gl_post_or_fail")
        process_cheque_cancel(incoming_cheque, create_gl=False)
        post.assert_not_called()

    def test_cancel_rejects_linked_payment(self, db_session, sample_tenant, outgoing_cheque, sample_user):
        payment = Payment(
            tenant_id=sample_tenant.id,
            payment_number=f"PAY-{uuid.uuid4().hex[:6]}",
            payment_type="supplier_payment",
            amount=Decimal("500"),
            amount_aed=Decimal("500"),
            payment_method="cheque",
            payment_confirmed=True,
            cheque_id=outgoing_cheque.id,
            user_id=sample_user.id,
        )
        db_session.add(payment)
        db_session.flush()
        process_cheque_cancel(outgoing_cheque)
        assert payment.payment_confirmed is False


class TestEventListeners:
    def test_register_and_overdue_warning(self, mocker, db_session, sample_tenant):
        register_cheque_event_listeners()
        warn = mocker.patch("services.cheque_service.logger.warning")
        ch = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number=f"EV-{uuid.uuid4().hex[:6]}",
            cheque_bank_number="BNK-EV",
            cheque_type="incoming",
            bank_name="Bank",
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            currency="AED",
            issue_date=date.today(),
            due_date=date.today() - timedelta(days=10),
            status="pending",
        )
        db_session.add(ch)
        db_session.flush()
        warn.assert_called()

    def test_status_change_log(self, mocker, db_session, incoming_cheque):
        register_cheque_event_listeners()
        info = mocker.patch("services.cheque_service.logger.info")
        incoming_cheque.status = "cleared"
        db_session.flush()
        info.assert_called()


class TestChequeEdgePaths:
    def test_issue_outgoing_without_party_uses_ap_fallback(self, outgoing_cheque):
        outgoing_cheque.supplier_id = None
        outgoing_cheque.customer_id = None
        outgoing_cheque.expense_id = None
        assert process_cheque_issue(outgoing_cheque) is not None

    def test_clear_outgoing_fx_gain_branch(self, mocker, db_session, outgoing_cheque):
        outgoing_cheque.status = "deposited"
        outgoing_cheque.currency = "USD"
        outgoing_cheque.amount = Decimal("100")
        outgoing_cheque.amount_aed = Decimal("360")
        outgoing_cheque.exchange_rate = Decimal("3.6")
        db_session.flush()
        process_cheque_clear(outgoing_cheque, clearance_exchange_rate=Decimal("3.50"))
        assert outgoing_cheque.status == "cleared"

    def test_bounce_outgoing_customer_credit(self, db_session, sample_customer, outgoing_cheque):
        outgoing_cheque.status = "pending"
        outgoing_cheque.customer_id = sample_customer.id
        outgoing_cheque.supplier_id = None
        db_session.flush()
        process_cheque_bounce(outgoing_cheque, reason="Returned")
        assert outgoing_cheque.status == "bounced"

    def test_bounce_customer_adjust_failure_logged(self, mocker, db_session, sample_customer, incoming_cheque):
        incoming_cheque.status = "deposited"
        incoming_cheque.customer_id = sample_customer.id
        db_session.flush()
        mocker.patch.object(sample_customer, "adjust_balance", side_effect=RuntimeError("cust"))
        err = mocker.patch("services.cheque_service.logger.error")
        process_cheque_bounce(incoming_cheque, reason="NSF")
        err.assert_called()

    def test_cancel_outgoing_customer_credit(self, db_session, sample_customer, outgoing_cheque):
        outgoing_cheque.customer_id = sample_customer.id
        outgoing_cheque.supplier_id = None
        db_session.flush()
        process_cheque_cancel(outgoing_cheque, create_gl=True)
        assert outgoing_cheque.status == "cancelled"

    def test_cancel_outgoing_without_party(self, outgoing_cheque):
        outgoing_cheque.supplier_id = None
        outgoing_cheque.customer_id = None
        outgoing_cheque.expense_id = None
        process_cheque_cancel(outgoing_cheque, create_gl=True)
        assert outgoing_cheque.status == "cancelled"

    def test_clear_with_tenant_scoped_payment(self, mocker, db_session, sample_tenant, outgoing_cheque, sample_user):
        outgoing_cheque.status = "deposited"
        payment = Payment(
            tenant_id=sample_tenant.id,
            payment_number=f"PAY-{uuid.uuid4().hex[:6]}",
            payment_type="supplier_payment",
            amount=Decimal("500"),
            amount_aed=Decimal("500"),
            payment_method="cheque",
            payment_confirmed=False,
            cheque_id=outgoing_cheque.id,
            user_id=sample_user.id,
        )
        db_session.add(payment)
        db_session.flush()
        process_cheque_clear(outgoing_cheque)
        assert payment.payment_confirmed is True

    def test_clear_resolves_rate_success(self, mocker, db_session, incoming_cheque):
        incoming_cheque.currency = "EUR"
        incoming_cheque.amount = Decimal("100")
        incoming_cheque.amount_aed = Decimal("400")
        incoming_cheque.exchange_rate = Decimal("4")
        incoming_cheque.status = "pending"
        db_session.flush()
        mocker.patch(
            "services.cheque_service.gl_resolve_exchange_rate",
            return_value={"rate": "4.10"},
        )
        process_cheque_clear(incoming_cheque)
        assert incoming_cheque.clearance_exchange_rate == Decimal("4.10")

    def test_clear_fatal_error_logged_and_reraised(self, mocker, incoming_cheque):
        incoming_cheque.status = "deposited"
        mocker.patch(
            "services.cheque_service._create_clearing_journal_entry",
            side_effect=RuntimeError("gl fail"),
        )
        exc = mocker.patch("services.cheque_service.logger.exception")
        with pytest.raises(RuntimeError, match="gl fail"):
            process_cheque_clear(incoming_cheque)
        exc.assert_called()

    def test_clear_confirms_receipt_with_tenant(
        self, db_session, sample_tenant, incoming_cheque, sample_customer, sample_user
    ):
        incoming_cheque.status = "deposited"
        receipt = Receipt(
            tenant_id=sample_tenant.id,
            receipt_number=f"RCP-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
            payment_method="cheque",
            payment_confirmed=False,
            cheque_id=incoming_cheque.id,
            user_id=sample_user.id,
        )
        db_session.add(receipt)
        db_session.flush()
        process_cheque_clear(incoming_cheque)
        assert receipt.payment_confirmed is True

    def test_bounce_outgoing_supplier_restores_ap(self, mocker, db_session, sample_supplier, outgoing_cheque):
        outgoing_cheque.status = "pending"
        outgoing_cheque.supplier_id = sample_supplier.id
        outgoing_cheque.expense_id = None
        db_session.flush()
        apply = mocker.patch.object(sample_supplier, "apply_payment")
        process_cheque_bounce(outgoing_cheque, reason="Returned")
        apply.assert_called_once()

    def test_cancel_expense_with_category_gl_code(self, db_session, sample_expense, outgoing_cheque):
        sample_expense.category.gl_account_code = "6200"
        outgoing_cheque.expense_id = sample_expense.id
        db_session.flush()
        process_cheque_cancel(outgoing_cheque, create_gl=True)
        assert outgoing_cheque.status == "cancelled"

    def test_cancel_rejects_receipt_loop(
        self, db_session, sample_tenant, incoming_cheque, sample_customer, sample_user
    ):
        receipt = Receipt(
            tenant_id=sample_tenant.id,
            receipt_number=f"RCP-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
            payment_method="cheque",
            payment_confirmed=True,
            cheque_id=incoming_cheque.id,
            user_id=sample_user.id,
        )
        db_session.add(receipt)
        db_session.flush()
        process_cheque_cancel(incoming_cheque)
        assert receipt.payment_confirmed is False

    def test_overdue_listener_datetime_due_date(self, mocker, db_session, sample_tenant):
        register_cheque_event_listeners()
        warn = mocker.patch("services.cheque_service.logger.warning")
        ch = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number=f"EV2-{uuid.uuid4().hex[:6]}",
            cheque_bank_number="BNK-EV2",
            cheque_type="incoming",
            bank_name="Bank",
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            currency="AED",
            issue_date=date.today(),
            due_date=datetime.now() - timedelta(days=10),
            status="pending",
        )
        db_session.add(ch)
        db_session.flush()
        warn.assert_called()

    def test_bounce_fatal_error_logged(self, mocker, incoming_cheque):
        incoming_cheque.status = "deposited"
        mocker.patch(
            "services.cheque_service._create_bounce_journal_entry",
            side_effect=RuntimeError("bounce boom"),
        )
        exc = mocker.patch("services.cheque_service.logger.exception")
        with pytest.raises(RuntimeError, match="bounce boom"):
            process_cheque_bounce(incoming_cheque, reason="NSF")
        exc.assert_called()

    def test_overdue_listener_error_logged(self, mocker):
        handlers = []

        def capture(model, evt):
            def decorator(fn):
                handlers.append(fn)
                return fn

            return decorator

        mocker.patch("sqlalchemy.event.listens_for", side_effect=capture)
        register_cheque_event_listeners()
        err = mocker.patch("services.cheque_service.logger.error")

        class _BadDue:
            def __sub__(self, other):
                raise RuntimeError("bad due")

        target = MagicMock(status="pending", cheque_number="EV3", due_date=_BadDue())
        handlers[0](None, None, target)
        err.assert_called()

    def test_status_listener_error_logged(self, mocker):
        handlers = []

        def capture(model, evt):
            def decorator(fn):
                handlers.append(fn)
                return fn

            return decorator

        mocker.patch("sqlalchemy.event.listens_for", side_effect=capture)
        register_cheque_event_listeners()
        err = mocker.patch("services.cheque_service.logger.error")
        mocker.patch(
            "services.cheque_service.logger.info",
            side_effect=RuntimeError("status log"),
        )
        target = MagicMock(status="cleared", cheque_number="EV4")
        handlers[-1](None, None, target)
        err.assert_called()
