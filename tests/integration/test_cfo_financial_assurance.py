"""CFO-grade assurance: every posted entry is balanced, in base currency,
and FX conversion is arithmetically correct with no exploitable drift.

These tests run the REAL posting gateway (post_or_fail) against the test
database, with a foreign-currency tenant, and assert the numbers a reviewer
would recompute by hand.
"""

from __future__ import annotations

from decimal import Decimal

import pytest


def _entry_lines(db_session, entry_id):
    from models import GLJournalLine

    return db_session.query(GLJournalLine).filter_by(entry_id=entry_id).all()


def test_foreign_currency_entry_converts_and_balances(db_session, sample_tenant, sample_gl_accounts):
    """100 USD at rate 3.6725 into an AED tenant => 367.250 AED on each side."""
    from services.gl_posting import post_or_fail

    tid = sample_tenant.id
    entry = post_or_fail(
        [
            {"account": "1111", "debit": Decimal("100"), "credit": 0, "description": "USD receipt"},
            {"account": "4100", "debit": 0, "credit": Decimal("100"), "description": "USD revenue"},
        ],
        description="CFO FX test",
        reference_type="manual",
        reference_id=999991,
        currency="USD",
        exchange_rate=Decimal("3.6725"),
        tenant_id=tid,
    )
    db_session.flush()
    lines = _entry_lines(db_session, entry.id)
    assert len(lines) == 2
    by_code = {}
    from models import GLAccount

    codes = {a.id: a.code for a in db_session.query(GLAccount).filter_by(tenant_id=tid).all()}
    for line in lines:
        by_code[codes[line.account_id]] = line

    expected = (Decimal("100") * Decimal("3.6725")).quantize(Decimal("0.001"))
    assert by_code["1111"].debit == expected
    assert by_code["4100"].credit == expected
    # The stored entry's own totals must match the lines exactly.
    assert entry.total_debit == entry.total_credit == expected
    # Original-currency perspective is preserved.
    assert by_code["1111"].amount == Decimal("100")


def test_rounding_plug_never_breaks_balance(db_session, sample_tenant, sample_gl_accounts):
    """Odd rates create per-line rounding drift; the entry must still balance."""
    from services.gl_posting import post_or_fail

    entry = post_or_fail(
        [
            {"account": "1111", "debit": Decimal("0.01"), "credit": 0, "description": "a"},
            {"account": "1111", "debit": Decimal("0.01"), "credit": 0, "description": "b"},
            {"account": "4100", "debit": 0, "credit": Decimal("0.02"), "description": "c"},
        ],
        description="CFO rounding test",
        reference_type="manual",
        reference_id=999992,
        currency="USD",
        exchange_rate=Decimal("1.0005"),
        tenant_id=sample_tenant.id,
    )
    db_session.flush()
    lines = _entry_lines(db_session, entry.id)
    total_dr = sum((line.debit for line in lines), Decimal("0"))
    total_cr = sum((line.credit for line in lines), Decimal("0"))
    assert total_dr == total_cr, f"ledger drift: dr={total_dr} cr={total_cr}"
    assert entry.total_debit == entry.total_credit


def test_rejected_zero_rate_for_foreign_currency(sample_tenant, sample_gl_accounts):
    """A foreign-currency entry with a zero rate must be refused, not posted at parity."""
    from services.gl_posting import GlPostingError, post_or_fail

    with pytest.raises(GlPostingError):
        post_or_fail(
            [
                {"account": "1111", "debit": Decimal("100"), "credit": 0},
                {"account": "4100", "debit": 0, "credit": Decimal("100")},
            ],
            description="CFO bad rate test",
            reference_type="manual",
            reference_id=999993,
            currency="USD",
            exchange_rate=Decimal("0"),
            tenant_id=sample_tenant.id,
        )


def test_trial_balance_holds_across_all_real_fx_entries(db_session, sample_tenant, sample_gl_accounts):
    """After several FX postings, the tenant's whole GL nets to exactly zero."""
    from models import GLJournalEntry, GLJournalLine
    from services.gl_posting import post_or_fail

    tid = sample_tenant.id
    for i in range(5):
        post_or_fail(
            [
                {"account": "1111", "debit": Decimal("10.05"), "credit": 0},
                {"account": "4100", "debit": 0, "credit": Decimal("10.05")},
            ],
            description=f"CFO series {i}",
            reference_type="manual",
            reference_id=990000 + i,
            currency="EUR",
            exchange_rate=Decimal("3.765") + Decimal(i) / 1000,
            tenant_id=tid,
        )
    db_session.flush()
    # Explicit onclause: the composite tenant FK adds a second path between
    # these tables, so a bare .join() is ambiguous.
    dr = (
        db_session.query(GLJournalLine.debit)
        .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
        .filter(GLJournalEntry.tenant_id == tid)
        .all()
    )
    cr = (
        db_session.query(GLJournalLine.credit)
        .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
        .filter(GLJournalEntry.tenant_id == tid)
        .all()
    )
    total_dr = sum((d[0] for d in dr), Decimal("0"))
    total_cr = sum((c[0] for c in cr), Decimal("0"))
    assert total_dr == total_cr, f"tenant GL drift: dr={total_dr} cr={total_cr}"
