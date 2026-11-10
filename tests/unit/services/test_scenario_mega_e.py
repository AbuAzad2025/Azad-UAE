"""Scenario mega-grid E — sequential distribution cartesian grid (mocked).

Profit × warehouse% × branch% × company% with the hand sequential formula.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.unit.services.test_partner_distribution_scenarios import _partner, _pnl, _run


class TestSequentialMega:
    @pytest.mark.parametrize(
        "profit,w,b,c",
        [
            (p, w, bb, cc)
            for p in (400, 800, 1500, 3000, 6000, 10000)
            for w in ("10", "25", "40", "60", "80")
            for bb in ("10", "30", "50", "70", "90")
            for cc in ("10", "30", "50", "70", "90")
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
        p = Decimal(str(profit))
        wh = (p * Decimal(w) / Decimal("100")).quantize(Decimal("0.001"))
        br = ((p - wh) * Decimal(b) / Decimal("100")).quantize(Decimal("0.001"))
        co = ((p - wh - br) * Decimal(c) / Decimal("100")).quantize(Decimal("0.001"))
        assert by_partner[1] == wh
        assert by_partner[2] == br
        assert by_partner[3] == co
