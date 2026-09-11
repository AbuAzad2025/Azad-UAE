"""Coverage-4 for services.partner_service — scope/else/except arcs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.partner_service import PartnerService


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield
        db_session.rollback()


def _period():
    return date(2026, 1, 1), date(2026, 1, 31)


class TestScopeAggregations:
    def test_revenue_warehouse_scope(self, mocker):

        q = MagicMock()
        q.select_from.return_value = q
        q.join.return_value = q
        q.filter.return_value = q
        q.scalar.return_value = Decimal("123.45")
        sess = mocker.patch("services.partner_service.db.session")
        sess.query.return_value = q
        out = PartnerService.get_scope_revenue(1, *_period(), scope_type="warehouse", scope_id=5)
        assert out == Decimal("123.45")

    def test_revenue_branch_scope(self, mocker):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = None
        sess = mocker.patch("services.partner_service.db.session")
        sess.query.return_value = q
        assert PartnerService.get_scope_revenue(1, *_period(), scope_type="branch", scope_id=2) == Decimal("0")

    def test_cogs_warehouse_scope(self, mocker):
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.scalar.return_value = Decimal("10")
        sess = mocker.patch("services.partner_service.db.session")
        sess.query.return_value = q
        assert PartnerService.get_scope_cogs(1, *_period(), scope_type="warehouse", scope_id=4) == Decimal("10")

    def test_expenses_warehouse_returns_zero(self):
        assert PartnerService.get_scope_expenses(1, *_period(), scope_type="warehouse") == Decimal("0")

    def test_calculate_profit_math(self, mocker):
        mocker.patch.object(PartnerService, "get_scope_revenue", return_value=Decimal("100"))
        mocker.patch.object(PartnerService, "get_scope_cogs", return_value=Decimal("30"))
        mocker.patch.object(PartnerService, "get_scope_expenses", return_value=Decimal("20"))
        out = PartnerService.calculate_scope_profit(1, *_period())
        assert out["gross_profit"] == 70.0
        assert out["net_profit"] == 50.0


class TestDistributions:
    def test_no_partners_returns_empty(self, mocker):
        from models import Partner

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.all.return_value = []
        mocker.patch.object(Partner, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert PartnerService.create_distributions(1, *_period()) == []

    def test_share_over_100_raises(self, mocker):
        from models import Partner

        p1 = SimpleNamespace(share_percentage=Decimal("60"))
        p2 = SimpleNamespace(share_percentage=Decimal("50"))
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.all.return_value = [p1, p2]
        mocker.patch.object(Partner, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        with pytest.raises(ValueError, match="100%"):
            PartnerService.create_distributions(1, *_period())

    def test_pnl_failure_wraps_value_error(self, mocker):
        from models import Partner, PartnerProfitDistribution

        p = SimpleNamespace(id=1, share_percentage=Decimal("10"), scope_type="company", scope_id=None)
        mq = MagicMock()
        mq.filter_by.return_value = mq
        mq.all.return_value = [p]
        mocker.patch.object(Partner, "query", new_callable=mocker.PropertyMock, return_value=mq)
        dq = MagicMock()
        dq.filter_by.return_value = dq
        dq.first.return_value = None
        mocker.patch.object(PartnerProfitDistribution, "query", new_callable=mocker.PropertyMock, return_value=dq)
        mocker.patch.object(PartnerService, "calculate_scope_profit", side_effect=RuntimeError("db"))
        with pytest.raises(ValueError, match="فشل حساب"):
            PartnerService.create_distributions(1, *_period())

    def test_loss_without_loss_pct_raises(self, mocker):
        from models import Partner, PartnerProfitDistribution

        p = SimpleNamespace(
            id=2, share_percentage=Decimal("10"), expense_share_percentage=Decimal("0"),
            loss_share_percentage=Decimal("0"), fixed_monthly_amount=Decimal("0"),
            min_profit_threshold=Decimal("0"), scope_type="company", scope_id=None,
        )
        mq = MagicMock()
        mq.filter_by.return_value = mq
        mq.all.return_value = [p]
        mocker.patch.object(Partner, "query", new_callable=mocker.PropertyMock, return_value=mq)
        dq = MagicMock()
        dq.filter_by.return_value = dq
        dq.first.return_value = None
        mocker.patch.object(PartnerProfitDistribution, "query", new_callable=mocker.PropertyMock, return_value=dq)
        mocker.patch.object(
            PartnerService, "calculate_scope_profit",
            return_value={"revenue": 0.0, "cogs": 0.0, "expenses": 0.0, "net_profit": -100.0},
        )
        with pytest.raises(ValueError, match="خسارة"):
            PartnerService.create_distributions(1, *_period())

    def test_approve_wrong_status_and_tenant(self, mocker):
        sess = mocker.patch("services.partner_service.db.session")
        sess.get.return_value = SimpleNamespace(status="approved", tenant_id=1)
        assert PartnerService.approve_distribution(1, 9, tenant_id=1) is False
        sess.get.return_value = None
        assert PartnerService.approve_distribution(999, 9) is False
        sess.get.return_value = SimpleNamespace(status="draft", tenant_id=2)
        assert PartnerService.approve_distribution(1, 9, tenant_id=1) is False

    def test_pay_wrong_status(self, mocker):
        sess = mocker.patch("services.partner_service.db.session")
        sess.get.return_value = SimpleNamespace(status="draft", tenant_id=1)
        assert PartnerService.pay_distribution(1) is False
        sess.get.return_value = None
        assert PartnerService.pay_distribution(1) is False

    def test_add_transaction_missing_and_mismatch(self, mocker):
        sess = mocker.patch("services.partner_service.db.session")
        sess.get.return_value = None
        assert PartnerService.add_transaction(999, "profit_share", Decimal("10")) is None
        sess.get.return_value = SimpleNamespace(tenant_id=2)
        assert PartnerService.add_transaction(1, "profit_share", Decimal("10"), tenant_id=1) is None

    def test_statement_missing_partner(self, mocker):
        sess = mocker.patch("services.partner_service.db.session")
        sess.get.return_value = None
        assert PartnerService.get_partner_statement(999, *_period()) == {}

    def test_statement_empty_moves(self, mocker):
        from models import PartnerTransaction

        sess = mocker.patch("services.partner_service.db.session")
        sess.get.return_value = SimpleNamespace(current_balance=Decimal("50"), tenant_id=1)
        mq = MagicMock()
        mq.filter.return_value = mq
        mq.order_by.return_value = mq
        mq.all.return_value = []
        mocker.patch.object(PartnerTransaction, "query", new_callable=mocker.PropertyMock, return_value=mq)
        out = PartnerService.get_partner_statement(1, *_period())
        assert out["closing_balance"] == 50.0
        assert out["net_movement"] == 0

    def test_activity_without_tid_and_list_with_status(self, mocker):
        from models import PartnerProfitDistribution, PartnerTransaction

        dq = MagicMock()
        dq.filter_by.return_value = dq
        dq.filter.return_value = dq
        dq.order_by.return_value = dq
        dq.limit.return_value = dq
        dq.all.return_value = ["d"]
        mocker.patch.object(PartnerProfitDistribution, "query", new_callable=mocker.PropertyMock, return_value=dq)
        tq = MagicMock()
        tq.filter_by.return_value = tq
        tq.filter.return_value = tq
        tq.order_by.return_value = tq
        tq.limit.return_value = tq
        tq.all.return_value = ["t"]
        mocker.patch.object(PartnerTransaction, "query", new_callable=mocker.PropertyMock, return_value=tq)
        dists, txs = PartnerService.get_partner_activity(1, None)
        assert dists == ["d"]
        lq = MagicMock()
        lq.filter_by.return_value = lq
        lq.order_by.return_value = lq
        lq.limit.return_value = lq
        lq.all.return_value = ["x"]
        mocker.patch.object(PartnerProfitDistribution, "query", new_callable=mocker.PropertyMock, return_value=lq)
        assert PartnerService.list_distributions(1, status="draft") == ["x"]
