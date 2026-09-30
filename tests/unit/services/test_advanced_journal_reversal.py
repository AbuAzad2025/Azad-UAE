"""A reversed entry must net to zero, not to the negation.

Found by the parallel services audit, then confirmed by reading the code:

  GLAccount.get_balance()  (models/gl.py:154) filters on status == "posted"
  the before-insert hook    (models/gl.py:546) sets is_posted=True for BOTH
                            "posted" and "reversed"

``AdvancedJournalEntryManager.reverse_entry_advanced`` transitioned the original
entry to status="reversed", so the two flags disagreed and the reporting layer
split in two. Anything reading status dropped the original and kept the mirror;
anything reading is_posted kept both.

For a 10,000 debit that means the trial balance reported a 10,000 *credit* on
every account the entry touched, while ar_reconciliation, aging_analysis,
bank_reconciliation and inventory_reconciliation all reported zero for the same
period. The single entry is still internally balanced, so assert_balanced_lines
passes - it is the population that is wrong, and nothing tested the population.

The fix converges reverse_entry_advanced onto GLJournalEntry.reverse_entry(),
which every other financial reversal already used: the original stays "posted"
and is flagged with is_reversed. These tests pin that.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from extensions import db


def _balance(account_id):
    """Account balance via the real code path that filters status == 'posted'."""
    from models.gl import GLAccount

    account = db.session.get(GLAccount, account_id)
    return account.get_balance()


def _two_accounts(tenant_id):
    """A postable debit and credit account from the seeded chart.

    is_header = false matters: 1000 "Assets" and 2000 "Liabilities" are roll-up
    parents and create_entry_with_validation refuses to post to them.
    """
    debit = db.session.execute(
        text(
            "SELECT id, code FROM gl_accounts WHERE tenant_id = :t AND is_active = true "
            "AND is_header = false AND type = 'asset' ORDER BY code LIMIT 1"
        ),
        {"t": tenant_id},
    ).fetchone()
    credit = db.session.execute(
        text(
            "SELECT id, code FROM gl_accounts WHERE tenant_id = :t AND is_active = true "
            "AND is_header = false AND type = 'liability' ORDER BY code LIMIT 1"
        ),
        {"t": tenant_id},
    ).fetchone()
    assert debit is not None, "no postable asset account was seeded"
    assert credit is not None, "no postable liability account was seeded"
    return debit, credit


def _post(tenant_id, debit_row, credit_row, amount: str, description: str, owner=None):
    from services.advanced_journal_manager import AdvancedJournalEntryManager
    from utils.tenanting import set_active_tenant

    # create_manual_entry resolves the tenant itself and refuses to guess:
    #   ValueError: resolve_tenant_id failed: 12 active tenants found.
    #             Auto-selecting one would post to the wrong company.
    # That refusal is correct behaviour and it is what fails in CI, where the
    # session-scoped test database has accumulated a dozen tenants by the time
    # the services group runs. Locally the file runs alone against one tenant
    # and passes, which is exactly the kind of difference a shared test database
    # hides. The test has to name its tenant rather than inherit one.
    # set_active_tenant rejects a tenant id without an authenticated platform owner
    # ("Unauthenticated users cannot set tenant_id"), so the owner is threaded in.
    set_active_tenant(tenant_id, user=owner)
    try:
        entry = AdvancedJournalEntryManager.create_entry_with_validation(
            description=description,
            lines=[
                {
                    "account_code": debit_row.code,
                    "debit": amount,
                    "credit": "0",
                    "description": "d",
                },
                {
                    "account_code": credit_row.code,
                    "debit": "0",
                    "credit": amount,
                    "description": "c",
                },
            ],
            entry_date=datetime.date.today(),
            created_by=1,
        )
        AdvancedJournalEntryManager.validate_entry(entry.id, validated_by=1, commit=False)
        AdvancedJournalEntryManager.post_entry(entry.id, posted_by=1, commit=False)
        db.session.flush()
        return entry
    finally:
        set_active_tenant(None)


def test_reversal_keeps_the_original_counted(app, db_session, sample_gl_accounts, sample_owner):
    """The original must stay in the "posted" population.

    This is the whole bug. If status ever goes back to "reversed" here, the
    trial balance inverts on every reversal.
    """
    from services.advanced_journal_manager import AdvancedJournalEntryManager

    tenant = sample_gl_accounts
    debit_row, credit_row = _two_accounts(tenant.id)

    original = _post(tenant.id, debit_row, credit_row, "10000", "reversal population test", owner=sample_owner)
    db_session.flush()

    # Read back the account that actually received the debit line rather than
    # assuming it is debit_row. create_manual_entry resolves account_code to an
    # account id itself, and whether that resolution is tenant-scoped is a
    # separate question from this one - see the note in the module docstring.
    posted = db_session.execute(
        text(
            "SELECT l.account_id FROM gl_journal_lines l "
            "JOIN gl_journal_entries j ON j.id = l.entry_id "
            "WHERE l.entry_id = :e AND l.debit > 0"
        ),
        {"e": original.id},
    ).scalar()

    before = _balance(posted)
    assert before == Decimal("10000"), f"precondition failed, balance={before} on account {posted}"

    AdvancedJournalEntryManager.reverse_entry_advanced(original.id, 1, "test", create_reversal_entry=True)
    db_session.flush()
    db_session.refresh(original)

    assert original.status == "posted", (
        f"the original's status is {original.status!r}. Balances filter on 'posted', "
        "so any other value drops the original while its mirror is still counted - the "
        "account shows the exact negation of the entry. Flag it with is_reversed "
        "instead; see GLJournalEntry.reverse_entry()."
    )
    assert original.is_reversed is True, "the original must still be flagged as reversed"


def test_reversal_nets_the_account_to_zero(app, db_session, sample_gl_accounts, sample_owner):
    """Both legs counted, so the pair nets to zero - not the negation."""
    from services.advanced_journal_manager import AdvancedJournalEntryManager

    tenant = sample_gl_accounts
    debit_row, credit_row = _two_accounts(tenant.id)

    original = _post(tenant.id, debit_row, credit_row, "7500", "reversal zero test", owner=sample_owner)
    db_session.flush()

    posted = db_session.execute(
        text(
            "SELECT l.account_id FROM gl_journal_lines l "
            "JOIN gl_journal_entries j ON j.id = l.entry_id "
            "WHERE l.entry_id = :e AND l.debit > 0"
        ),
        {"e": original.id},
    ).scalar()

    AdvancedJournalEntryManager.reverse_entry_advanced(original.id, 1, "test", create_reversal_entry=True)
    db_session.flush()

    balance = _balance(posted)
    assert balance == Decimal("0"), (
        f"after reversing a 7500 debit the balance is {balance}, not 0. A negative value "
        "means the original was excluded while its mirror was counted - the accounting "
        "layer and the reconciliation services report opposite things for one period."
    )


def test_reversing_twice_is_refused(app, db_session, sample_gl_accounts, sample_owner):
    """The guard now keys off is_reversed, since status no longer changes."""
    from services.advanced_journal_manager import AdvancedJournalEntryManager

    tenant = sample_gl_accounts
    debit_row, credit_row = _two_accounts(tenant.id)

    entry = _post(tenant.id, debit_row, credit_row, "10", "double reversal", owner=sample_owner)
    AdvancedJournalEntryManager.reverse_entry_advanced(entry.id, 1, "first", create_reversal_entry=True)
    db_session.flush()

    with pytest.raises(ValueError):
        AdvancedJournalEntryManager.reverse_entry_advanced(entry.id, 1, "second", create_reversal_entry=True)
