from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event

# Supplier Ageing Bucket Partitions


class TestSupplierAgeingBuckets:
    """Edge-case timestamps at bucket boundaries: 0-30, 31-60, 61-90, 90+ days."""

    @staticmethod
    def _bucket(due_date, today=None):
        """Compute aging bucket for an invoice based on due_date vs today."""
        today = today or date.today()
        overdue = (today - due_date).days
        if overdue <= 0:
            return "current"
        if overdue <= 30:
            return "0_30"
        if overdue <= 60:
            return "31_60"
        if overdue <= 90:
            return "61_90"
        return "90_plus"

    # --- Boundaries at exactly 0, 30, 60, 90 days overdue ---

    def test_bucket_current(self):
        d = date.today()
        assert self._bucket(d) == "current"

    def test_bucket_exactly_0_days_overdue(self):
        d = date.today()
        assert self._bucket(d) == "current"

    def test_bucket_1_day_overdue_0_30(self):
        d = date.fromordinal(date.today().toordinal() - 1)
        assert self._bucket(d) == "0_30"

    def test_bucket_30_days_overdue_boundary(self):
        d = date.fromordinal(date.today().toordinal() - 30)
        assert self._bucket(d) == "0_30"

    def test_bucket_31_days_overdue_boundary(self):
        d = date.fromordinal(date.today().toordinal() - 31)
        assert self._bucket(d) == "31_60"

    def test_bucket_60_days_overdue_boundary(self):
        d = date.fromordinal(date.today().toordinal() - 60)
        assert self._bucket(d) == "31_60"

    def test_bucket_61_days_overdue_boundary(self):
        d = date.fromordinal(date.today().toordinal() - 61)
        assert self._bucket(d) == "61_90"

    def test_bucket_90_days_overdue_boundary(self):
        d = date.fromordinal(date.today().toordinal() - 90)
        assert self._bucket(d) == "61_90"

    def test_bucket_91_days_overdue_boundary(self):
        d = date.fromordinal(date.today().toordinal() - 91)
        assert self._bucket(d) == "90_plus"

    def test_bucket_365_days_overdue(self):
        d = date.fromordinal(date.today().toordinal() - 365)
        assert self._bucket(d) == "90_plus"


# Cheque Clearance GL Routing


class TestChequeClearanceGL:
    """Verify debit/credit routing on check clearance (incoming and outgoing)."""

    @staticmethod
    def _patch_db_queries(mocker):
        mocker.patch("services.cheque_service.gl_ensure_core_accounts")
        from models.payment import Payment
        from models.receipt import Receipt

        mocker.patch.object(
            Payment,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch.object(
            Receipt,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mocker.MagicMock(),
        )

    def test_clear_incoming_creates_gl_lines(self, mocker, app):
        """Verify check clearing creates GL lines under a valid app context."""
        self._patch_db_queries(mocker)
        mock_gl = mocker.patch("services.cheque_service.gl_post_or_fail")
        mock_liquidity = mocker.patch(
            "services.cheque_service.gl_get_default_liquidity_account",
            return_value="1120",
        )
        mocker.patch(
            "services.cheque_service.GLService.get_account_code_for_concept",
            return_value="1150",
        )

        cheque = MagicMock()
        cheque.id = 1
        cheque.cheque_type = "incoming"
        cheque.cheque_bank_number = "CHK001"
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.amount = Decimal("1000")
        cheque.amount_aed = Decimal("1000")
        cheque.actual_amount_aed = Decimal("1010")
        cheque.currency_gain_loss = Decimal("10")
        cheque.currency = "AED"
        cheque.clearance_exchange_rate = Decimal("1.0")
        cheque.status = "deposited"
        cheque.customer_id = 1
        cheque.customer = MagicMock()
        cheque.supplier_id = None
        cheque.expense_id = None

        from services.cheque_service import process_cheque_clear

        with app.app_context():
            process_cheque_clear(cheque)

        assert mock_gl.called
        args, kwargs = mock_gl.call_args
        lines = kwargs.get("lines", args[0] if args else [])
        concepts = {line["concept_code"] for line in lines if line.get("concept_code")}
        assert "CHEQUES_UNDER_COLLECTION" in concepts
        assert mock_liquidity.called

    def test_clear_outgoing_creates_gl_lines(self, mocker, app):
        self._patch_db_queries(mocker)
        mocker.patch("services.cheque_service.gl_post_or_fail")
        mocker.patch(
            "services.cheque_service.gl_get_default_liquidity_account",
            return_value="1120",
        )
        mocker.patch(
            "services.cheque_service.GLService.get_account_code_for_concept",
            return_value="2130",
        )

        cheque = MagicMock()
        cheque.cheque_type = "outgoing"
        cheque.cheque_bank_number = "CHK002"
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.amount = Decimal("2000")
        cheque.amount_aed = Decimal("2000")
        cheque.actual_amount_aed = Decimal("2000")
        cheque.currency_gain_loss = Decimal("0")
        cheque.currency = "AED"
        cheque.clearance_exchange_rate = Decimal("1.0")
        cheque.status = "deposited"
        cheque.customer_id = None
        cheque.supplier_id = 1
        cheque.expense_id = None

        from services.cheque_service import process_cheque_clear

        with app.app_context():
            process_cheque_clear(cheque)

        assert cheque.status == "cleared"

    def test_clear_rejects_invalid_status(self, mocker):
        cheque = MagicMock()
        cheque.status = "cancelled"
        cheque.status_ar = "ملغي"

        from services.cheque_service import process_cheque_clear

        with pytest.raises(ValueError, match="لا يمكن تأكيد صرف شيك"):
            process_cheque_clear(cheque)

    def test_clear_missing_liquidity_account(self, mocker, app):
        self._patch_db_queries(mocker)
        mocker.patch(
            "services.cheque_service.gl_get_default_liquidity_account",
            return_value=None,
        )
        mocker.patch("services.cheque_service.gl_post_or_fail")

        cheque = MagicMock()
        cheque.cheque_type = "incoming"
        cheque.cheque_bank_number = "CHK003"
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.amount = Decimal("500")
        cheque.amount_aed = Decimal("500")
        cheque.actual_amount_aed = Decimal("500")
        cheque.currency_gain_loss = Decimal("0")
        cheque.currency = "AED"
        cheque.clearance_exchange_rate = Decimal("1.0")
        cheque.status = "deposited"

        from services.cheque_service import process_cheque_clear

        with app.app_context():
            process_cheque_clear(cheque)
        assert cheque.status == "cleared"


# Cheque Bounce GL Routing


class TestChequeBounceGL:
    """Verify bounce reverses entries, applies fees, locks state."""

    @staticmethod
    def _patch_bounce_deps(mocker):
        mocker.patch("services.cheque_service.gl_ensure_core_accounts")
        from models.expense import Expense
        from models.payment import Payment
        from models.receipt import Receipt
        from models.supplier import Supplier

        mocker.patch.object(
            Expense,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch.object(
            Payment,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch.object(
            Receipt,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch.object(
            Supplier,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mocker.MagicMock(),
        )

    def test_bounce_incoming_reverses_gl(self, mocker, app):
        self._patch_bounce_deps(mocker)
        mock_gl = mocker.patch("services.cheque_service.gl_post_or_fail")
        mocker.patch(
            "services.cheque_service.gl_get_customer_credit_account",
            return_value="1100",
        )
        mocker.patch("services.cheque_service.gl_get_customer_credit_concept", return_value="AR")
        mocker.patch(
            "services.cheque_service.GLService.get_account_code_for_concept",
            return_value="1150",
        )

        cheque = MagicMock()
        cheque.cheque_type = "incoming"
        cheque.cheque_bank_number = "CHK010"
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.amount_aed = Decimal("1500")
        cheque.amount = Decimal("1500")
        cheque.customer_id = 1
        cheque.customer = MagicMock()
        cheque.supplier_id = None
        cheque.expense_id = None
        cheque.status = "deposited"

        from services.cheque_service import process_cheque_bounce

        with app.app_context():
            process_cheque_bounce(cheque, "insufficient funds")

        assert cheque.status == "bounced"
        assert cheque.bounce_reason == "insufficient funds"
        assert mock_gl.called

    def test_bounce_outgoing_reverses_gl(self, mocker, app):
        self._patch_bounce_deps(mocker)
        mocker.patch("services.cheque_service.gl_post_or_fail")
        mocker.patch(
            "services.cheque_service.GLService.get_account_code_for_concept",
            return_value="2130",
        )

        cheque = MagicMock()
        cheque.cheque_type = "outgoing"
        cheque.cheque_bank_number = "CHK011"
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.amount = Decimal("2000")
        cheque.amount_aed = Decimal("2000")
        cheque.customer_id = None
        cheque.supplier_id = 1
        cheque.supplier = MagicMock()
        cheque.expense_id = None
        cheque.status = "deposited"

        from services.cheque_service import process_cheque_bounce

        with app.app_context():
            process_cheque_bounce(cheque, "account closed")

        assert cheque.status == "bounced"

    def test_bounce_with_fee_posts_extra_entry(self, mocker, app):
        self._patch_bounce_deps(mocker)
        mock_gl = mocker.patch("services.cheque_service.gl_post_or_fail")
        mock_post = mocker.patch("services.gl_posting.post_or_fail")
        mocker.patch(
            "services.cheque_service.gl_get_customer_credit_account",
            return_value="1100",
        )
        mocker.patch("services.cheque_service.gl_get_customer_credit_concept", return_value="AR")
        mocker.patch(
            "services.cheque_service.gl_get_default_liquidity_account",
            return_value="1120",
        )
        mocker.patch(
            "services.cheque_service.GLService.get_account_code_for_concept",
            return_value="1150",
        )
        # No prior bounce-fee GL row → post_or_fail must run for the fee.
        gl_q = MagicMock()
        gl_q.filter.return_value = gl_q
        gl_q.first.return_value = None
        mocker.patch("models.GLJournalEntry.query", gl_q)

        cheque = MagicMock()
        cheque.cheque_type = "incoming"
        cheque.cheque_bank_number = "CHK012"
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.amount_aed = Decimal("1000")
        cheque.amount = Decimal("1000")
        cheque.customer_id = 1
        cheque.customer = MagicMock()
        cheque.supplier_id = None
        cheque.expense_id = None
        cheque.status = "deposited"

        from services.cheque_service import process_cheque_bounce

        with app.app_context():
            process_cheque_bounce(cheque, "refer to drawer", bounce_fee=Decimal("50"))

        assert mock_gl.called
        assert mock_post.called

    def test_bounce_rejects_invalid_status(self):
        cheque = MagicMock()
        cheque.status = "cleared"
        cheque.status_ar = "مصروف"

        from services.cheque_service import process_cheque_bounce

        with pytest.raises(ValueError, match="لا يمكن رفض شيك"):
            process_cheque_bounce(cheque, "reason")

    def test_bounce_locks_state(self, mocker, app):
        self._patch_bounce_deps(mocker)
        mocker.patch("services.cheque_service.gl_post_or_fail")
        mocker.patch(
            "services.cheque_service.gl_get_customer_credit_account",
            return_value="1100",
        )
        mocker.patch("services.cheque_service.gl_get_customer_credit_concept", return_value="AR")
        mocker.patch(
            "services.cheque_service.GLService.get_account_code_for_concept",
            return_value="1150",
        )

        cheque = MagicMock()
        cheque.cheque_type = "incoming"
        cheque.cheque_bank_number = "CHK013"
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.amount_aed = Decimal("1000")
        cheque.amount = Decimal("1000")
        cheque.customer_id = 1
        cheque.customer = MagicMock()
        cheque.supplier_id = None
        cheque.expense_id = None
        cheque.status = "deposited"

        from services.cheque_service import process_cheque_bounce

        with app.app_context():
            process_cheque_bounce(cheque, "bounced")

        assert cheque.status == "bounced"
        assert cheque.clearance_date is not None


# Cheque State Transition Guards


class TestChequeStateTransitions:
    """Verify proper state machine: clear from deposited/pending, bounce from deposited/pending."""

    def test_clear_from_pending(self, mocker, app):
        mocker.patch("services.cheque_service.gl_ensure_core_accounts")
        from models.payment import Payment
        from models.receipt import Receipt

        mocker.patch.object(
            Payment,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch.object(
            Receipt,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mocker.MagicMock(),
        )
        mocker.patch("services.cheque_service.gl_post_or_fail")
        mocker.patch(
            "services.cheque_service.gl_get_default_liquidity_account",
            return_value="1120",
        )
        mocker.patch(
            "services.cheque_service.GLService.get_account_code_for_concept",
            return_value="1150",
        )

        cheque = MagicMock()
        cheque.cheque_type = "incoming"
        cheque.cheque_bank_number = "CHK020"
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.amount = Decimal("1000")
        cheque.amount_aed = Decimal("1000")
        cheque.actual_amount_aed = Decimal("1000")
        cheque.currency_gain_loss = Decimal("0")
        cheque.currency = "AED"
        cheque.clearance_exchange_rate = Decimal("1.0")
        cheque.status = "pending"

        from services.cheque_service import process_cheque_clear

        with app.app_context():
            process_cheque_clear(cheque)
        assert cheque.status == "cleared"

    def test_bounce_invalid_status_raises(self):
        cheque = MagicMock()
        cheque.status = "cleared"
        cheque.status_ar = "مصروف"

        from services.cheque_service import process_cheque_bounce

        with pytest.raises(ValueError, match="لا يمكن رفض شيك"):
            process_cheque_bounce(cheque, "nope")


class TestChequeEventListeners:
    def test_overdue_warning_and_status_log(self, mocker):
        """The overdue warning and the status-change log both fire, and neither raises.

        Registration used to be read back out of
        ``sqlalchemy.event.registry._key_to_collection`` with a two-tuple key, and
        SQLAlchemy 2.x keys that registry by ``(id(target), identifier, id(fn))``.
        The lookup therefore never matched, ``before`` came back empty, and the
        test skipped - while the listeners it was checking were registered the
        whole time. Rather than reach into that private registry again (and get
        the key shape wrong a third time), this captures the listeners as they
        register and calls them directly. That also lets the test assert the
        handler survives a broken due_date instead of only the happy paths.
        """
        import importlib

        import services.cheque_service as cs

        importlib.reload(cs)
        warn = mocker.patch.object(cs.logger, "warning")
        info = mocker.patch.object(cs.logger, "info", side_effect=[None, RuntimeError("log failure")])
        err = mocker.patch.object(cs.logger, "error")

        registered: dict[str, list] = {}

        real_listens_for = event.listens_for

        def spy(target, identifier, *args, **kwargs):
            def decorate(fn):
                registered.setdefault(identifier, []).append(fn)
                return real_listens_for(target, identifier, *args, **kwargs)(fn)

            return decorate

        mocker.patch.object(event, "listens_for", side_effect=spy)
        cs.register_cheque_event_listeners()

        assert "before_insert" in registered, f"no before_insert listener registered: {sorted(registered)}"
        assert "after_update" in registered, f"no after_update listener registered: {sorted(registered)}"

        overdue = MagicMock(
            cheque_number="CH-1",
            status="pending",
            due_date=date.today() - timedelta(days=30),
        )
        for fn in registered["before_insert"]:
            fn(None, None, overdue)
        assert warn.called, "an overdue cheque produced no warning"

        for fn in registered["after_update"]:
            fn(None, None, MagicMock(cheque_number="CH-2", status="cleared"))
        assert info.called, "a cleared cheque produced no status log"

        # A handler that raises on bad data rolls back the write that triggered it,
        # so both failure shapes have to be logged instead: the logger itself
        # failing, and a malformed due_date.
        for fn in registered["after_update"]:
            fn(None, None, MagicMock(cheque_number="CH-2b", status="cleared"))
        broken = MagicMock(cheque_number="CH-3", status="pending", due_date=object())
        for fn in registered["before_insert"]:
            fn(None, None, broken)
        assert err.call_count >= 2, f"expected both failure shapes logged, got {err.call_count}"
