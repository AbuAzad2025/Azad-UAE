"""Cov5: real_time_listeners — no-account and no-approval exit arcs."""

from __future__ import annotations

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
