"""Gap coverage for models/pos_session.py — transitions, close, durations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from models.pos_session import PosSession


def _session(**kwargs):
    params = {
        "tenant_id": 1,
        "branch_id": 1,
        "user_id": 1,
        "session_number": "SES-COV3",
    }
    params.update(kwargs)
    return PosSession(**params)


class TestTransitions:
    def test_invalid_transition_raises(self):
        ses = _session(status="closed")
        with pytest.raises(ValueError, match="انتقال غير مسموح"):
            ses._transition("open")

    def test_pause_then_pause_raises(self):
        ses = _session(status="open")
        ses.pause()
        assert ses.status == "paused"
        assert ses.paused_at is not None
        with pytest.raises(ValueError, match="انتقال غير مسموح"):
            ses.pause()

    def test_resume_clears_paused_at(self):
        ses = _session(status="open")
        ses.pause()
        ses.resume()
        assert ses.status == "open"
        assert ses.paused_at is None

    def test_resume_from_open_raises(self):
        with pytest.raises(ValueError, match="انتقال غير مسموح"):
            _session(status="open").resume()


class TestExpectedBalance:
    def test_all_none_gives_zero(self):
        ses = _session()
        ses.opening_balance_cash = None
        ses.total_cash_sales = None
        ses.total_change_given = None
        ses.total_cash_refunds = None
        ses.total_pay_ins = None
        ses.total_pay_outs = None
        assert ses.compute_expected_balance() == Decimal("0.000")

    def test_full_formula(self):
        ses = _session(
            opening_balance_cash=Decimal("100"),
            total_cash_sales=Decimal("50"),
            total_change_given=Decimal("5"),
            total_cash_refunds=Decimal("10"),
            total_pay_ins=Decimal("20"),
            total_pay_outs=Decimal("7"),
        )
        assert ses.compute_expected_balance() == Decimal("148.000")


class TestClose:
    def test_close_closed_raises(self):
        with pytest.raises(ValueError, match="مغلقة"):
            _session(status="closed").close(Decimal("10"))

    def test_close_sets_balances(self):
        ses = _session(status="open", opening_balance_cash=Decimal("100"))
        ses.close(Decimal("120.5555"))
        assert ses.closing_balance_cash == Decimal("120.556")
        assert ses.expected_balance == Decimal("100.000")
        assert ses.difference == Decimal("20.556")
        assert ses.status == "closed"
        assert ses.closed_at is not None

    def test_close_with_notes(self):
        ses = _session(status="paused")
        ses.close("50", notes="end of day")
        assert ses.notes == "end of day"
        assert ses.status == "closed"

    def test_close_without_notes_keeps_none(self):
        ses = _session(status="open")
        ses.close(Decimal("0"))
        assert ses.notes is None


class TestDuration:
    def test_open_session_aware(self):
        ses = _session(opened_at=datetime.now(UTC) - timedelta(minutes=30))
        assert 29 <= ses.duration_minutes <= 31

    def test_open_session_naive(self):
        ses = _session(opened_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10))
        assert 9 <= ses.duration_minutes <= 11

    def test_closed_session_naive(self):
        start = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        ses = _session(opened_at=start)
        ses.closed_at = start + timedelta(hours=1)
        assert 59 <= ses.duration_minutes <= 61

    def test_closed_session_aware(self):
        start = datetime.now(UTC) - timedelta(hours=3)
        ses = _session(opened_at=start, closed_at=start + timedelta(minutes=45))
        assert 44 <= ses.duration_minutes <= 46

    def test_repr(self):
        assert "SES-COV3" in repr(_session())
