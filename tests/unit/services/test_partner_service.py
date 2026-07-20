from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import models

from services.partner_service import PartnerService


def _partner(**kwargs):
    p = MagicMock()
    defaults = dict(
        id=1,
        tenant_id=1,
        is_active=True,
        scope_type="company",
        scope_id=None,
        share_percentage=Decimal("50"),
        expense_share_percentage=Decimal("10"),
        loss_share_percentage=Decimal("0"),
        fixed_monthly_amount=Decimal("0"),
        min_profit_threshold=Decimal("0"),
        current_balance=Decimal("0"),
        total_profit_received=Decimal("0"),
        total_loss_borne=Decimal("0"),
        total_withdrawals=Decimal("0"),
        total_additional_investment=Decimal("0"),
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


def _query_chain(scalar_value):
    q = MagicMock()
    q.filter.return_value = q
    q.join.return_value.filter.return_value = q
    q.select_from.return_value.join.return_value.filter.return_value = q
    q.scalar.return_value = scalar_value
    return q


class TestScopeAggregation:
    def test_get_scope_revenue_company(self, mocker):
        mocker.patch(
            "services.partner_service.db.session.query",
            return_value=_query_chain(Decimal("1000")),
        )
        result = PartnerService.get_scope_revenue(1, date(2026, 1, 1), date(2026, 1, 31))
        assert result == Decimal("1000")

    def test_get_scope_revenue_branch_filter(self, mocker):
        q = _query_chain(Decimal("500"))
        mocker.patch("services.partner_service.db.session.query", return_value=q)
        result = PartnerService.get_scope_revenue(1, date(2026, 1, 1), date(2026, 1, 31), "branch", 2)
        q.filter.assert_called()
        assert result == Decimal("500")

    def test_get_scope_revenue_warehouse(self, mocker):
        q = _query_chain(Decimal("300"))
        mocker.patch("services.partner_service.db.session.query", return_value=q)
        result = PartnerService.get_scope_revenue(1, date(2026, 1, 1), date(2026, 1, 31), "warehouse", 9)
        assert result == Decimal("300")

    def test_get_scope_revenue_none_scalar(self, mocker):
        mocker.patch("services.partner_service.db.session.query", return_value=_query_chain(None))
        assert PartnerService.get_scope_revenue(1, date(2026, 1, 1), date(2026, 1, 31)) == Decimal("0")

    def test_get_scope_cogs_branch_and_warehouse(self, mocker):
        q = _query_chain(Decimal("200"))
        mocker.patch("services.partner_service.db.session.query", return_value=q)
        assert PartnerService.get_scope_cogs(1, date(2026, 1, 1), date(2026, 1, 31), "branch", 1) == Decimal("200")
        assert PartnerService.get_scope_cogs(1, date(2026, 1, 1), date(2026, 1, 31), "warehouse", 1) == Decimal("200")

    def test_get_scope_expenses_warehouse_zero(self):
        assert PartnerService.get_scope_expenses(1, date(2026, 1, 1), date(2026, 1, 31), "warehouse", 1) == Decimal("0")

    def test_get_scope_expenses_branch(self, mocker):
        mocker.patch(
            "services.partner_service.db.session.query",
            return_value=_query_chain(Decimal("150")),
        )
        assert PartnerService.get_scope_expenses(1, date(2026, 1, 1), date(2026, 1, 31), "branch", 3) == Decimal("150")

    def test_calculate_scope_profit(self, mocker):
        mocker.patch.object(PartnerService, "get_scope_revenue", return_value=Decimal("1000"))
        mocker.patch.object(PartnerService, "get_scope_cogs", return_value=Decimal("400"))
        mocker.patch.object(PartnerService, "get_scope_expenses", return_value=Decimal("100"))
        pnl = PartnerService.calculate_scope_profit(1, date(2026, 1, 1), date(2026, 1, 31))
        assert pnl["net_profit"] == 500.0


class TestCreateDistributions:
    def test_empty_partners_returns_empty(self, mocker):
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = []
        assert PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31)) == []

    def test_skips_existing_period(self, mocker):
        partner = _partner()
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = [partner]
        D = mocker.patch("models.PartnerProfitDistribution")
        D.query.filter_by.return_value.first.return_value = MagicMock()
        mocker.patch.object(
            PartnerService,
            "calculate_scope_profit",
            return_value={
                "revenue": 0,
                "cogs": 0,
                "expenses": 0,
                "gross_profit": 0,
                "net_profit": 0,
            },
        )
        assert PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31)) == []

    def test_profit_distribution_commits(self, mocker):
        partner = _partner(share_percentage=Decimal("40"), min_profit_threshold=Decimal("0"))
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = [partner]
        D = mocker.patch("models.PartnerProfitDistribution")
        D.query.filter_by.return_value.first.return_value = None
        dist = MagicMock(id=99)
        D.return_value = dist
        mocker.patch.object(
            PartnerService,
            "calculate_scope_profit",
            return_value={
                "revenue": 10000.0,
                "cogs": 2000.0,
                "expenses": 1000.0,
                "gross_profit": 8000.0,
                "net_profit": 7000.0,
            },
        )
        mock_db = mocker.patch("services.partner_service.db")
        ids = PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31), created_by=1)
        assert ids == [99]
        mock_db.session.flush.assert_called()

    def test_create_distributions_rollback(self, mocker):
        partner = _partner(loss_share_percentage=Decimal("50"))
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = [partner]
        D = mocker.patch("models.PartnerProfitDistribution")
        D.query.filter_by.return_value.first.return_value = None
        D.return_value = MagicMock(id=1)
        mocker.patch.object(
            PartnerService,
            "calculate_scope_profit",
            return_value={
                "revenue": 0,
                "cogs": 0,
                "expenses": 0,
                "gross_profit": 0,
                "net_profit": -1000.0,
            },
        )
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.flush.side_effect = RuntimeError("fail")
        with pytest.raises(RuntimeError):
            PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31))

    def test_scope_calculation_failure_wrapped(self, mocker):
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = [_partner()]
        mocker.patch("models.PartnerProfitDistribution").query.filter_by.return_value.first.return_value = None
        mocker.patch.object(PartnerService, "calculate_scope_profit", side_effect=RuntimeError("boom"))
        with pytest.raises(ValueError, match="فشل حساب أرباح"):
            PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31))


class TestDistributionLifecycle:
    def test_approve_distribution_not_draft(self, mocker):
        dist = MagicMock(status="approved")
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = dist
        assert PartnerService.approve_distribution(1, 1) is False

    def test_approve_distribution_wrong_tenant(self, mocker):
        dist = MagicMock(status="draft", tenant_id=2)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = dist
        assert PartnerService.approve_distribution(1, 1, tenant_id=1) is False

    def test_approve_distribution_positive_net(self, mocker):
        dist = MagicMock(
            status="draft",
            tenant_id=1,
            net_due=100.0,
            partner_id=1,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )
        partner = _partner(current_balance=Decimal("0"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [dist, partner]
        mocker.patch("models.PartnerTransaction", return_value=MagicMock(amount=100.0))
        assert PartnerService.approve_distribution(1, 5, tenant_id=1) is True
        mock_db.session.flush.assert_called()

    def test_approve_distribution_negative_net(self, mocker):
        dist = MagicMock(
            status="draft",
            tenant_id=1,
            net_due=-50.0,
            partner_id=1,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )
        partner = _partner(current_balance=Decimal("0"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [dist, partner]
        mocker.patch("models.PartnerTransaction", return_value=MagicMock(amount=-50.0))
        assert PartnerService.approve_distribution(1, 5) is True

    def test_approve_rollback(self, mocker):
        dist = MagicMock(status="draft", tenant_id=1, net_due=0.0)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = dist
        mock_db.session.flush.side_effect = RuntimeError("x")
        with pytest.raises(RuntimeError):
            PartnerService.approve_distribution(1, 1)

    def test_pay_distribution_success(self, mocker):
        dist = MagicMock(status="approved", tenant_id=1, net_due=200.0, id=7)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = dist
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            return_value="2150",
        )
        mocker.patch(
            "services.gl_service.GLService.get_default_liquidity_account",
            return_value="1120",
        )
        mocker.patch("services.gl_posting.post_or_fail")
        assert PartnerService.pay_distribution(7, tenant_id=1) is True
        mock_db.session.flush.assert_called()

    def test_pay_distribution_gl_fallback(self, mocker):
        dist = MagicMock(status="approved", tenant_id=1, net_due=50.0, id=3)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = dist
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            side_effect=RuntimeError(),
        )
        mocker.patch(
            "services.gl_service.GLService.get_default_liquidity_account",
            side_effect=RuntimeError(),
        )
        post = mocker.patch("services.gl_posting.post_or_fail")
        PartnerService.pay_distribution(3)
        post.assert_called_once()

    def test_pay_distribution_not_approved(self, mocker):
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = MagicMock(status="draft")
        assert PartnerService.pay_distribution(1) is False

    def test_pay_distribution_wrong_tenant_returns_false(self, mocker):
        dist = MagicMock(status="approved", tenant_id=2, net_due=100.0, id=8)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = dist
        assert PartnerService.pay_distribution(8, tenant_id=1) is False
        mock_db.session.flush.assert_not_called()

    def test_pay_distribution_commit_rollback(self, mocker):
        dist = MagicMock(status="approved", tenant_id=1, net_due=0.0, id=9)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = dist
        mock_db.session.flush.side_effect = RuntimeError("pay fail")
        with pytest.raises(RuntimeError):
            PartnerService.pay_distribution(9, tenant_id=1)


class TestAddTransaction:
    def test_partner_not_found(self, mocker):
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = None
        assert PartnerService.add_transaction(1, "withdrawal", Decimal("10")) is None

    def test_tenant_mismatch(self, mocker):
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = _partner(tenant_id=2)
        assert PartnerService.add_transaction(1, "withdrawal", Decimal("10"), tenant_id=1) is None

    def test_withdrawal_updates_totals_and_posts_gl(self, mocker):
        partner = _partner(current_balance=Decimal("0"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="AED")
        tx_cls = mocker.patch("models.PartnerTransaction")
        tx = MagicMock(id=55)
        tx_cls.return_value = tx
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            return_value="2150",
        )
        mocker.patch(
            "services.gl_service.GLService.get_default_liquidity_account",
            return_value="1120",
        )
        post = mocker.patch("services.gl_posting.post_or_fail")
        tx_id = PartnerService.add_transaction(1, "withdrawal", Decimal("-100"), notes="cash out")
        assert tx_id == 55
        mock_db.session.flush.assert_called()
        post.assert_called_once()

    def test_additional_investment_positive_gl(self, mocker):
        partner = _partner(current_balance=Decimal("0"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="AED")
        tx_cls = mocker.patch("models.PartnerTransaction")
        tx = MagicMock(id=77)
        tx_cls.return_value = tx
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            side_effect=RuntimeError(),
        )
        mocker.patch(
            "services.gl_service.GLService.get_default_liquidity_account",
            side_effect=RuntimeError(),
        )
        post = mocker.patch("services.gl_posting.post_or_fail")
        PartnerService.add_transaction(1, "additional_investment", Decimal("500"))
        post.assert_called_once()

    def test_zero_amount_skips_gl(self, mocker):
        partner = _partner(current_balance=Decimal("0"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="AED")
        mocker.patch("models.PartnerTransaction", return_value=MagicMock(id=1))
        post = mocker.patch("services.gl_posting.post_or_fail")
        PartnerService.add_transaction(1, "adjustment", Decimal("0"))
        post.assert_not_called()

    def test_add_transaction_rollback(self, mocker):
        partner = _partner(current_balance=Decimal("0"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="AED")
        mocker.patch("models.PartnerTransaction", return_value=MagicMock(id=1))
        mocker.patch("services.gl_posting.post_or_fail")
        mock_db.session.flush.side_effect = RuntimeError("fail")
        with pytest.raises(RuntimeError):
            PartnerService.add_transaction(1, "adjustment", Decimal("10"))


class _ComparableCol:
    def __ge__(self, other):
        return MagicMock()

    def __le__(self, other):
        return MagicMock()

    def __eq__(self, other):
        return MagicMock()


def _fake_partner_transaction_module(txs):
    pt = MagicMock()
    pt.partner_id = _ComparableCol()
    pt.transaction_date = _ComparableCol()
    pt.id = _ComparableCol()
    pt.query.filter.return_value.order_by.return_value.all.return_value = txs
    return pt


class TestPartnerStatement:
    def test_missing_partner(self, mocker):
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = None
        assert PartnerService.get_partner_statement(1, date(2026, 1, 1), date(2026, 1, 31)) == {}

    def test_statement_with_transactions(self, mocker):
        partner = _partner(current_balance=Decimal("200"))
        tx1 = MagicMock(amount_base=Decimal("100"), balance_after=Decimal("100"))
        tx2 = MagicMock(amount_base=Decimal("-30"), balance_after=Decimal("70"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        pt = _fake_partner_transaction_module([tx1, tx2])
        with patch.object(models, "PartnerTransaction", pt):
            stmt = PartnerService.get_partner_statement(1, date(2026, 1, 1), date(2026, 1, 31))
        assert stmt["total_credit"] == 100.0
        assert stmt["total_debit"] == 30.0
        assert stmt["closing_balance"] == 70.0

    def test_statement_empty_transactions(self, mocker):
        partner = _partner(current_balance=Decimal("50"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        pt = _fake_partner_transaction_module([])
        with patch.object(models, "PartnerTransaction", pt):
            stmt = PartnerService.get_partner_statement(1, date(2026, 1, 1), date(2026, 1, 31))
        assert stmt["opening_balance"] == 0
        assert stmt["closing_balance"] == 50.0
