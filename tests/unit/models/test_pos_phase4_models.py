"""POS Phase 4 model tests — cash-refund drawer math on sessions/shifts."""

from __future__ import annotations

from decimal import Decimal

from models.pos_session import PosSession
from models.pos_shift import PosShift


def _session(**totals):
    session = PosSession()
    session.opening_balance_cash = Decimal("100")
    session.total_cash_sales = Decimal("200")
    session.total_change_given = Decimal("10")
    session.total_cash_refunds = Decimal("0")
    session.total_pay_ins = Decimal("0")
    session.total_pay_outs = Decimal("0")
    for key, value in totals.items():
        setattr(session, key, Decimal(str(value)))
    return session


class TestSessionExpectedBalanceWithRefunds:
    def test_no_refunds_matches_phase3_formula(self):
        assert _session().compute_expected_balance() == Decimal("290.000")

    def test_cash_refund_decrements_expected_drawer(self):
        session = _session(total_cash_refunds=50)
        assert session.compute_expected_balance() == Decimal("240.000")

    def test_refunds_compose_with_pay_ins_outs(self):
        session = _session(total_cash_refunds=50, total_pay_ins=20, total_pay_outs=30)
        # 100 + 200 - 10 - 50 + 20 - 30 = 230
        assert session.compute_expected_balance() == Decimal("230.000")

    def test_none_refunds_treated_as_zero(self):
        session = _session()
        session.total_cash_refunds = None
        assert session.compute_expected_balance() == Decimal("290.000")


class TestShiftExpectedCashWithRefunds:
    def _shift(self, **totals):
        shift = PosShift()
        shift.starting_cash = Decimal("100")
        shift.total_cash_sales = Decimal("200")
        shift.total_change_given = Decimal("10")
        shift.total_cash_refunds = Decimal("0")
        shift.total_pay_ins = Decimal("0")
        shift.total_pay_outs = Decimal("0")
        for key, value in totals.items():
            setattr(shift, key, Decimal(str(value)))
        return shift

    def test_no_refunds_matches_phase3_formula(self):
        assert self._shift().compute_expected_cash() == Decimal("290")

    def test_cash_refund_decrements_expected(self):
        assert self._shift(total_cash_refunds=50).compute_expected_cash() == Decimal("240")

    def test_to_dict_exposes_refunds_only_when_sensitive(self):
        from datetime import datetime, timezone

        shift = self._shift(total_cash_refunds=50)
        shift.opened_at = datetime.now(timezone.utc)
        full = shift.to_dict(include_sensitive=True)
        blind = shift.to_dict(include_sensitive=False)
        assert full["total_cash_refunds"] == 50.0
        assert "total_cash_refunds" not in blind
