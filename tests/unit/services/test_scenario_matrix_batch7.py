"""Scenario matrix batch 7 — sequential distribution grid (mocked boundary).

Cartes�ian grid of (warehouse%, branch%, company%) × profit, each checked
against the hand formula: warehouse first, branch on remainder, company on
remainder. Fast unit-level, independently computed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.unit.services.test_partner_distribution_scenarios import _partner, _pnl, _run


def _expected(profit, w, b, c):
    p = Decimal(str(profit))
    wh = (p * Decimal(str(w)) / Decimal("100")).quantize(Decimal("0.001"))
    br = ((p - wh) * Decimal(str(b)) / Decimal("100")).quantize(Decimal("0.001"))
    co = ((p - wh - br) * Decimal(str(c)) / Decimal("100")).quantize(Decimal("0.001"))
    return wh, br, co


class TestSequentialGrid:
    @pytest.mark.parametrize(
        "profit,w,b,c",
        [
            (p, w, bb, cc)
            for p in (500, 1000, 2000)
            for (w, bb, cc) in (("20", "30", "50"), ("50", "50", "50"), ("10", "20", "30"))
        ],
    )
    def test_grid(self, mocker, profit, w, b, c):
        partners = [
            _partner(id=1, scope_type="warehouse", scope_id=7, share_percentage=Decimal(w)),
            _partner(id=2, scope_type="branch", scope_id=5, share_percentage=Decimal(b)),
            _partner(id=3, scope_type="company", scope_id=None, share_percentage=Decimal(c)),
        ]
        pnl = {
            ("warehouse", 7): _pnl(profit),
            ("branch", 5): _pnl(profit),
            ("company", None): _pnl(profit),
        }
        _ids, made = _run(mocker, partners, pnl)
        by_partner = {d.kwargs["partner_id"]: d.kwargs["net_due"] for d in made}
        wh, br, co = _expected(profit, w, b, c)
        assert by_partner[1] == wh
        assert by_partner[2] == br
        assert by_partner[3] == co
        assert wh + br + co <= Decimal(str(profit))

    @pytest.mark.parametrize("loss_w,loss_b,loss_c", [("50", "50", "50"), ("100", "100", "100"), ("20", "30", "40")])
    def test_loss_grid(self, mocker, loss_w, loss_b, loss_c):
        partners = [
            _partner(id=1, scope_type="warehouse", scope_id=7, loss_share_percentage=Decimal(loss_w)),
            _partner(id=2, scope_type="branch", scope_id=5, loss_share_percentage=Decimal(loss_b)),
            _partner(id=3, scope_type="company", scope_id=None, loss_share_percentage=Decimal(loss_c)),
        ]
        pnl = {
            ("warehouse", 7): _pnl(-1000),
            ("branch", 5): _pnl(-1000),
            ("company", None): _pnl(-1000),
        }
        _ids, made = _run(mocker, partners, pnl)
        by_partner = {d.kwargs["partner_id"]: d.kwargs["net_due"] for d in made}
        wh = -(Decimal("1000") * Decimal(loss_w) / Decimal("100"))
        rem1 = Decimal("-1000") - wh
        br = -(abs(rem1) * Decimal(loss_b) / Decimal("100"))
        rem2 = rem1 - br
        co = -(abs(rem2) * Decimal(loss_c) / Decimal("100"))
        assert by_partner[1] == wh.quantize(Decimal("0.001"))
        assert by_partner[2] == br.quantize(Decimal("0.001"))
        assert by_partner[3] == co.quantize(Decimal("0.001"))
