"""Cov5: real_time_listeners — no-account and no-approval exit arcs."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock


def test_journal_line_without_account_skips_balance_update(capsys):
    from services.real_time_listeners import RealTimeAccountingListeners

    line = MagicMock(
        id=1,
        entry_id=2,
        account=None,
        account_id=None,
        debit=0,
        credit=0,
        description="",
    )
    RealTimeAccountingListeners._on_journal_line_created(line)
    assert "journal_line_created" in capsys.readouterr().out


def test_expense_without_approval_skips_notification(capsys):
    from services.real_time_listeners import RealTimeAccountingListeners

    expense = MagicMock()
    expense.id = 2
    expense.expense_number = "EXP-COV5"
    expense.description_ar = "مصروف"
    expense.amount_aed = Decimal("100")
    expense.category = MagicMock(name_ar="Travel", approval_limit=Decimal("1000"))
    expense.tax_amount = Decimal("0")
    expense.customs_amount = Decimal("0")
    expense.requires_approval = False
    RealTimeAccountingListeners._on_expense_created(expense)
    out = capsys.readouterr().out
    assert "expense_created" in out
    assert "موافقة مطلوبة" not in out


def test_journal_entry_updated_neither_posted_nor_reversed(capsys):
    from services.real_time_listeners import RealTimeAccountingListeners

    entry = MagicMock(
        id=3,
        entry_number="JE-X",
        is_posted=False,
        is_reversed=False,
        updated_at=None,
    )
    RealTimeAccountingListeners._on_journal_entry_updated(entry)
    assert "خطأ" not in capsys.readouterr().out


def test_account_updated_normal_balance(capsys):
    from services.real_time_listeners import RealTimeAccountingListeners

    account = MagicMock()
    account.id = 4
    account.code = "1100"
    account.full_name = "Cash"
    account.get_balance.return_value = Decimal("50")
    account.updated_at = None
    RealTimeAccountingListeners._on_account_updated(account)
    out = capsys.readouterr().out
    assert "رصيد عالي" not in out


def test_cheque_updated_unknown_status_skips_notification(capsys):
    from services.real_time_listeners import RealTimeAccountingListeners

    cheque = MagicMock()
    cheque.id = 5
    cheque.cheque_bank_number = "CHQ-COV5"
    cheque.status = "pending"
    cheque.status_ar = "معلق"
    cheque.amount_aed = Decimal("500")
    cheque.cheque_type = "incoming"
    cheque.updated_at = datetime.now(UTC)
    RealTimeAccountingListeners._on_cheque_updated(cheque)
    assert "CHQ-COV5" in capsys.readouterr().out
