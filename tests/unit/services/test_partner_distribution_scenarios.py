"""Golden partner-distribution scenarios with independently hand-computed values.

These are not characterization tests: every expected amount below was
calculated by hand from the approved policy (sequential warehouse → branch →
company allocation, fixed amount before the profit percentage, actual active
days, losses borne sequentially on the remainder, expenses never charged
twice). If the implementation drifts from the policy, these fail.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from services.partner_service import PartnerService

JAN = (date(2026, 1, 1), date(2026, 1, 31))


def _partner(**kwargs):
    p = MagicMock()
    defaults = {
        "id": 1,
        "tenant_id": 1,
        "is_active": True,
        "scope_type": "company",
        "scope_id": None,
        "share_percentage": Decimal("0"),
        "expense_share_percentage": Decimal("0"),
        "loss_share_percentage": Decimal("0"),
        "fixed_monthly_amount": Decimal("0"),
        "min_profit_threshold": Decimal("0"),
        "start_date": None,
        "end_date": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


def _pnl(net):
    return {
        "revenue": float(net + 200),
        "cogs": 200.0,
        "expenses": 0.0,
        "commissions": 0.0,
        "gross_profit": float(net),
        "net_profit": float(net),
    }


def _run(mocker, partners, pnl_by_scope, warehouse_branch=5):
    P = mocker.patch("models.Partner")
    P.query.filter_by.return_value.all.return_value = partners
    D = mocker.patch("models.PartnerProfitDistribution")
    D.query.filter_by.return_value.first.return_value = None
    made = []

    def _make(**kwargs):
        dist = MagicMock(id=len(made) + 1)
        dist.kwargs = kwargs
        made.append(dist)
        return dist

    D.side_effect = _make
    mocker.patch.object(
        PartnerService,
        "calculate_scope_profit",
        side_effect=lambda tenant, ps, pe, st, sid: pnl_by_scope[(st, sid)],
    )
    mock_db = mocker.patch("services.partner_service.db")
    mock_db.session.get.return_value = MagicMock(tenant_id=1, branch_id=warehouse_branch)
    ids = PartnerService.create_distributions(1, *JAN)
    return ids, made


class TestSequentialProfitAllocation:
    def test_warehouse_branch_company_share_remainder_only(self, mocker):
        # Same underlying 1000 profit at every level (nested scopes).
        # Warehouse 50% of 1000 = 500; branch 50% of (1000-500) = 250;
        # company 50% of (1000-750) = 125; company retains 125. Total = 1000.
        partners = [
            _partner(id=3, scope_type="company", share_percentage=Decimal("50")),
            _partner(id=1, scope_type="warehouse", scope_id=7, share_percentage=Decimal("50")),
            _partner(id=2, scope_type="branch", scope_id=5, share_percentage=Decimal("50")),
        ]
        pnl = {
            ("warehouse", 7): _pnl(1000),
            ("branch", 5): _pnl(1000),
            ("company", None): _pnl(1000),
        }
        ids, made = _run(mocker, partners, pnl)
        assert len(ids) == 3
        by_partner = {d.kwargs["partner_id"]: d.kwargs for d in made}
        assert by_partner[1]["net_due"] == Decimal("500.000")
        assert by_partner[2]["net_due"] == Decimal("250.000")
        assert by_partner[3]["net_due"] == Decimal("125.000")
        total = sum(d.kwargs["net_due"] for d in made)
        assert total == Decimal("875.000")

    def test_same_scope_partners_share_one_base(self, mocker):
        partners = [
            _partner(id=1, share_percentage=Decimal("30")),
            _partner(id=2, share_percentage=Decimal("20")),
        ]
        ids, made = _run(mocker, partners, {("company", None): _pnl(1000)})
        assert len(ids) == 2
        dues = sorted(d.kwargs["net_due"] for d in made)
        assert dues == [Decimal("200.000"), Decimal("300.000")]

    def test_threshold_applies_to_remainder_after_smaller_scope(self, mocker):
        # Company base after warehouse = 500 < threshold 600 → no share.
        partners = [
            _partner(id=1, scope_type="warehouse", scope_id=7, share_percentage=Decimal("50")),
            _partner(
                id=2,
                scope_type="company",
                scope_id=None,
                share_percentage=Decimal("50"),
                min_profit_threshold=Decimal("600"),
            ),
        ]
        pnl = {("warehouse", 7): _pnl(1000), ("company", None): _pnl(1000)}
        ids, made = _run(mocker, partners, pnl)
        by_partner = {d.kwargs["partner_id"]: d.kwargs for d in made}
        assert by_partner[1]["net_due"] == Decimal("500.000")
        assert by_partner[2]["share_amount"] == Decimal("0")
        assert by_partner[2]["net_due"] == Decimal("0")


class TestFixedBeforePercentage:
    def test_fixed_paid_first_percentage_on_remainder(self, mocker):
        partner = _partner(
            share_percentage=Decimal("50"),
            fixed_monthly_amount=Decimal("100"),
        )
        ids, made = _run(mocker, [partner], {("company", None): _pnl(1000)})
        kwargs = made[0].kwargs
        assert kwargs["fixed_amount"] == Decimal("100.000")
        assert kwargs["share_amount"] == Decimal("450.000")
        assert kwargs["net_due"] == Decimal("550.000")

    def test_fixed_exceeding_profit_leaves_no_percentage(self, mocker):
        partner = _partner(
            share_percentage=Decimal("50"),
            fixed_monthly_amount=Decimal("1200"),
        )
        ids, made = _run(mocker, [partner], {("company", None): _pnl(1000)})
        kwargs = made[0].kwargs
        assert kwargs["share_amount"] == Decimal("0")
        assert kwargs["net_due"] == Decimal("1200.000")


class TestActualDaysProration:
    def test_mid_period_start_prorates_fixed(self, mocker):
        # Active Jan 16–31 = 16 of 31 days. 310 * 16/31 = 160 exactly.
        partner = _partner(
            fixed_monthly_amount=Decimal("310"),
            start_date=date(2026, 1, 16),
        )
        ids, made = _run(mocker, [partner], {("company", None): _pnl(0)})
        assert made[0].kwargs["fixed_amount"] == Decimal("160.000")

    def test_partner_starting_after_period_gets_no_distribution(self, mocker):
        partner = _partner(start_date=date(2026, 2, 1))
        ids, made = _run(mocker, [partner], {("company", None): _pnl(1000)})
        assert ids == []
        assert made == []

    def test_partner_ending_before_period_gets_no_distribution(self, mocker):
        partner = _partner(end_date=date(2025, 12, 31))
        ids, made = _run(mocker, [partner], {("company", None): _pnl(1000)})
        assert ids == []
        assert made == []


class TestSequentialLosses:
    def test_losses_borne_sequentially_on_remainder(self, mocker):
        # Warehouse bears 50% of -1000 = -500; branch remainder -500, bears
        # 50% = -250; company remainder -250, bears 50% = -125.
        partners = [
            _partner(id=1, scope_type="warehouse", scope_id=7, loss_share_percentage=Decimal("50")),
            _partner(id=2, scope_type="branch", scope_id=5, loss_share_percentage=Decimal("50")),
            _partner(id=3, scope_type="company", scope_id=None, loss_share_percentage=Decimal("50")),
        ]
        pnl = {
            ("warehouse", 7): _pnl(-1000),
            ("branch", 5): _pnl(-1000),
            ("company", None): _pnl(-1000),
        }
        ids, made = _run(mocker, partners, pnl)
        by_partner = {d.kwargs["partner_id"]: d.kwargs for d in made}
        assert by_partner[1]["net_due"] == Decimal("-500.000")
        assert by_partner[2]["net_due"] == Decimal("-250.000")
        assert by_partner[3]["net_due"] == Decimal("-125.000")

    def test_loss_partner_without_loss_percentage_refused(self, mocker):
        partner = _partner(loss_share_percentage=Decimal("0"))
        with __import__("pytest").raises(ValueError, match="نسبة تحمل خسارة"):
            _run(mocker, [partner], {("company", None): _pnl(-100)})


class TestExpenseNotChargedTwice:
    def test_expense_share_percentage_is_metadata_only(self, mocker):
        # Scope net already includes expenses; partner keeps 50% of 800.
        partner = _partner(
            share_percentage=Decimal("50"),
            expense_share_percentage=Decimal("20"),
        )
        ids, made = _run(mocker, [partner], {("company", None): _pnl(800)})
        kwargs = made[0].kwargs
        assert kwargs["expense_share_amount"] == Decimal("0")
        assert kwargs["net_due"] == Decimal("400.000")
