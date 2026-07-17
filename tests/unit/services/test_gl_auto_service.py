from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from models import Customer
from services import gl_auto_service


class TestValidateDecimalPrecision:
    def test_none_is_valid(self):
        assert gl_auto_service.validate_decimal_precision(None) is True

    def test_valid_decimal_within_limits(self):
        assert gl_auto_service.validate_decimal_precision("10.123") is True

    def test_too_many_decimal_places(self):
        assert (
            gl_auto_service.validate_decimal_precision("1.1234", decimal_places=3)
            is False
        )

    def test_too_many_digits(self):
        assert (
            gl_auto_service.validate_decimal_precision(
                "1234567890123456", max_digits=15
            )
            is False
        )

    def test_invalid_value_returns_false(self):
        assert gl_auto_service.validate_decimal_precision("not-a-number") is False


class TestEnsureBalanceConsistency:
    def test_customer_balance_consistent(self):
        connection = MagicMock()
        sale_row = MagicMock(amount_aed=Decimal("100"), paid_amount_aed=Decimal("40"))
        customer_row = MagicMock(balance=Decimal("60"))
        connection.execute.return_value.fetchall.return_value = [sale_row]
        connection.execute.return_value.first.return_value = customer_row

        result = gl_auto_service.ensure_balance_consistency(connection, Customer, 7)

        assert result["stored"] == Decimal("60")
        assert result["calculated"] == Decimal("60")
        assert result["consistent"] is True

    def test_customer_balance_inconsistent(self):
        connection = MagicMock()
        sale_row = MagicMock(amount_aed=Decimal("100"), paid_amount_aed=Decimal("0"))
        customer_row = MagicMock(balance=Decimal("50"))
        connection.execute.return_value.fetchall.return_value = [sale_row]
        connection.execute.return_value.first.return_value = customer_row

        result = gl_auto_service.ensure_balance_consistency(connection, Customer, 7)

        assert result["consistent"] is False

    def test_missing_customer_returns_zero_stored(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        connection.execute.return_value.first.return_value = None

        result = gl_auto_service.ensure_balance_consistency(connection, Customer, 99)

        assert result["stored"] == Decimal("0")
        assert result["calculated"] == Decimal("0")
        assert result["consistent"] is True

    def test_exception_returns_none_fields(self):
        connection = MagicMock()
        connection.execute.side_effect = RuntimeError("db down")

        result = gl_auto_service.ensure_balance_consistency(connection, Customer, 1)

        assert result == {"stored": None, "calculated": None, "consistent": None}


class TestValidateJournalEntryBalance:
    def test_balanced_entry_passes(self):
        target = MagicMock(
            entry_number="JE-1", total_debit=Decimal("100"), total_credit=Decimal("100")
        )
        gl_auto_service.validate_journal_entry_balance(None, None, target)

    def test_zero_debit_and_credit_passes(self):
        target = MagicMock(
            entry_number="JE-0", total_debit=Decimal("0"), total_credit=Decimal("0")
        )
        gl_auto_service.validate_journal_entry_balance(None, None, target)

    def test_unbalanced_entry_raises(self):
        target = MagicMock(
            entry_number="JE-2", total_debit=Decimal("100"), total_credit=Decimal("50")
        )
        with pytest.raises(ValueError, match="غير متوازن"):
            gl_auto_service.validate_journal_entry_balance(None, None, target)

    def test_none_totals_treated_as_zero(self):
        target = MagicMock(entry_number="JE-3", total_debit=None, total_credit=None)
        gl_auto_service.validate_journal_entry_balance(None, None, target)

    def test_unexpected_error_is_reraised(self):
        target = MagicMock()
        type(target).total_debit = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        with pytest.raises(RuntimeError, match="boom"):
            gl_auto_service.validate_journal_entry_balance(None, None, target)


class TestRegisterEventListeners:
    def test_register_gl_event_listeners_is_noop(self):
        with patch("sqlalchemy.event.listens_for") as mock_listens:
            gl_auto_service.register_gl_event_listeners()
            assert (
                mock_listens.call_count == 0
            )  # model/gl.py handles balance validation

    def test_register_validation_event_listeners_attaches_handlers(self):
        with patch("sqlalchemy.event.listens_for") as mock_listens:
            gl_auto_service.register_validation_event_listeners()
            assert mock_listens.call_count >= 5

    def test_sale_negative_amount_logs_error(self, caplog):
        with patch(
            "sqlalchemy.event.listens_for", side_effect=lambda *a, **k: lambda fn: fn
        ):
            gl_auto_service.register_validation_event_listeners()

        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()

        sale_handler = handlers[0]
        target = MagicMock(sale_number="S-1", amount_aed=Decimal("-5"))
        with caplog.at_level("ERROR"):
            sale_handler(None, None, target)

    def test_receipt_invalid_amount_logs_error(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()

        receipt_handler = handlers[4]
        target = MagicMock(receipt_number="R-1", amount_aed=Decimal("0"))
        with caplog.at_level("ERROR"):
            receipt_handler(None, None, target)

    def test_product_negative_stock_logs_warning(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()

        product_handler = handlers[-1]
        target = MagicMock(name="Widget", current_stock=Decimal("-1"))
        with caplog.at_level("WARNING"):
            product_handler(None, None, target)

    def test_purchase_negative_amount_logs_error(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()
        purchase_handler = handlers[1]
        target = MagicMock(purchase_number="P-1", amount_aed=Decimal("-1"))
        with caplog.at_level("ERROR"):
            purchase_handler(None, None, target)

    def test_payment_invalid_amount_logs_error(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()
        payment_handler = handlers[5]
        target = MagicMock(amount_aed=Decimal("-1"))
        with caplog.at_level("ERROR"):
            payment_handler(None, None, target)

    def test_sale_validation_exception_logged(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()
        sale_handler = handlers[0]
        target = MagicMock()
        type(target).amount_aed = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with caplog.at_level("ERROR"):
            sale_handler(None, None, target)

    def test_receipt_validation_exception_logged(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()
        receipt_handler = handlers[4]
        target = MagicMock()
        type(target).amount_aed = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with caplog.at_level("ERROR"):
            receipt_handler(None, None, target)

    def test_product_validation_exception_logged(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()
        product_handler = handlers[-1]
        target = MagicMock()
        type(target).current_stock = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with caplog.at_level("ERROR"):
            product_handler(None, None, target)

    def test_purchase_validation_exception_logged(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()
        purchase_handler = handlers[1]
        target = MagicMock()
        type(target).amount_aed = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with caplog.at_level("ERROR"):
            purchase_handler(None, None, target)

    def test_payment_validation_exception_logged(self, caplog):
        handlers = []
        with patch(
            "sqlalchemy.event.listens_for",
            side_effect=lambda model, event: lambda fn: handlers.append(fn) or fn,
        ):
            gl_auto_service.register_validation_event_listeners()
        payment_handler = handlers[5]
        target = MagicMock()
        type(target).amount_aed = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with caplog.at_level("ERROR"):
            payment_handler(None, None, target)

    def test_gl_validate_balance_passes_balanced(self):
        target = MagicMock(
            entry_number="JE-9", total_debit=Decimal("10"), total_credit=Decimal("10")
        )
        gl_auto_service.validate_journal_entry_balance(None, None, target)
