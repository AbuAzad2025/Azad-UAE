"""POS Phase 3 model tests — session state machine, expected-balance
formulas, blind-close serialization, and alembic single-head invariant.

Pure model logic: no DB access except the head-scan test (filesystem only).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from models.pos_session import PosSession
from models.pos_shift import PosShift


def _session(**overrides):
    session = PosSession(
        tenant_id=1,
        branch_id=2,
        user_id=3,
        session_number="POS-SES-T1",
        opening_balance_cash=Decimal("100"),
        status=PosSession.STATUS_OPEN,
    )
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


class TestPosSessionStateMachine:
    def test_open_to_paused(self):
        session = _session()
        session.pause()
        assert session.status == PosSession.STATUS_PAUSED
        assert session.paused_at is not None

    def test_paused_to_open_resume(self):
        session = _session(status=PosSession.STATUS_PAUSED)
        session.resume()
        assert session.status == PosSession.STATUS_OPEN
        assert session.paused_at is None

    def test_open_to_closed(self):
        session = _session()
        session.close(Decimal("100"))
        assert session.status == PosSession.STATUS_CLOSED
        assert session.closed_at is not None

    def test_paused_to_closed_allowed(self):
        session = _session(status=PosSession.STATUS_PAUSED)
        session.close(Decimal("100"))
        assert session.status == PosSession.STATUS_CLOSED

    def test_pause_twice_blocked(self):
        session = _session(status=PosSession.STATUS_PAUSED)
        with pytest.raises(ValueError):
            session.pause()

    def test_resume_open_blocked(self):
        session = _session()
        with pytest.raises(ValueError):
            session.resume()

    def test_close_twice_blocked(self):
        session = _session(status=PosSession.STATUS_CLOSED)
        with pytest.raises(ValueError, match="مغلقة"):
            session.close(Decimal("100"))

    def test_closed_to_paused_blocked(self):
        session = _session(status=PosSession.STATUS_CLOSED)
        with pytest.raises(ValueError):
            session.pause()

    def test_closed_to_open_blocked(self):
        session = _session(status=PosSession.STATUS_CLOSED)
        with pytest.raises(ValueError):
            session.resume()


class TestPosSessionExpectedBalance:
    def test_expected_formula_decimal_exact(self):
        """expected = opening + cash tendered − change + pay-ins − pay-outs."""
        session = _session(
            total_cash_sales=Decimal("250.500"),
            total_change_given=Decimal("50.250"),
            total_pay_ins=Decimal("75.125"),
            total_pay_outs=Decimal("20.000"),
        )
        # 100 + 250.500 − 50.250 + 75.125 − 20.000 = 355.375
        session.close(Decimal("355.375"))
        assert session.expected_balance == Decimal("355.375")
        assert session.difference == Decimal("0.000")

    def test_expected_defaults_zero_columns(self):
        session = _session(
            total_cash_sales=Decimal("50"),
            total_change_given=None,
            total_pay_ins=None,
            total_pay_outs=None,
        )
        session.close(Decimal("150"))
        assert session.expected_balance == Decimal("150.000")
        assert session.difference == Decimal("0.000")

    def test_shortage_difference_sign(self):
        session = _session(total_cash_sales=Decimal("50"))
        session.close(Decimal("140"))
        assert session.expected_balance == Decimal("150.000")
        assert session.difference == Decimal("-10.000")

    def test_overage_difference_sign(self):
        session = _session(total_cash_sales=Decimal("50"))
        session.close(Decimal("160"))
        assert session.difference == Decimal("10.000")


class TestPosShiftExpectedCash:
    def _shift(self, **overrides):
        shift = PosShift(
            tenant_id=1,
            session_id=5,
            user_id=3,
            shift_number="SHF-T1",
            starting_cash=Decimal("200"),
            status=PosShift.SHIFT_OPEN,
            opened_at=datetime.now(timezone.utc),
        )
        for key, value in overrides.items():
            setattr(shift, key, value)
        return shift

    def test_reconcile_formula_decimal_exact(self):
        shift = self._shift(
            total_cash_sales=Decimal("300.000"),
            total_change_given=Decimal("40.500"),
            total_pay_ins=Decimal("10.000"),
            total_pay_outs=Decimal("25.250"),
        )
        # 200 + 300 − 40.5 + 10 − 25.25 = 444.25
        shift.reconcile(Decimal("444.250"))
        assert shift.system_sales_expected == Decimal("444.250")
        assert shift.discrepancy == Decimal("0.000")
        assert shift.status == PosShift.SHIFT_RECONCILED

    def test_reconcile_discrepancy_sign(self):
        shift = self._shift(total_cash_sales=Decimal("100"))
        shift.reconcile(Decimal("295"))
        assert shift.system_sales_expected == Decimal("300")
        assert shift.discrepancy == Decimal("-5")

    def test_blind_to_dict_hides_sensitive(self):
        shift = self._shift(total_cash_sales=Decimal("100"))
        shift.reconcile(Decimal("300"))
        blind = shift.to_dict(include_sensitive=False)
        assert "system_sales_expected" not in blind
        assert "actual_cash_counted" not in blind
        assert "discrepancy" not in blind
        assert "total_cash_sales" not in blind
        assert blind["starting_cash"] == 200.0
        full = shift.to_dict(include_sensitive=True)
        assert full["system_sales_expected"] == 300.0
        assert full["total_change_given"] == 0.0


class TestAlembicSingleHead:
    def test_single_migration_head(self):
        versions = Path(__file__).resolve().parents[3] / "migrations" / "versions"
        revisions: dict[str, str] = {}
        down_revisions: set[str] = set()
        for path in versions.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            rev = re.search(r'^revision = "([^"]+)"', text, re.M)
            down = re.search(r'^down_revision = "([^"]+)"', text, re.M)
            if rev:
                revisions[rev.group(1)] = path.name
            if down:
                down_revisions.add(down.group(1))
        heads = [rev for rev in revisions if rev not in down_revisions]
        assert heads == ["d4a2b8c91e07"]
