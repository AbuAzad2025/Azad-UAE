"""Tests for services.main_site_service — covers uncovered dashboard/chart branches."""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.main_site_service import MainSiteService


def _mock_query_chain(return_value=None, scalar_value=None):
    """Helper to build a chainable mock query."""
    q = MagicMock()
    q.filter.return_value = q
    q.filter_by.return_value = q
    q.filter.return_value = q
    # For order_by, group_by, join etc.
    q.order_by.return_value = q
    q.group_by.return_value = q
    q.join.return_value = q
    q.select_from.return_value = q
    q.limit.return_value = q
    q.options.return_value = q
    q.all.return_value = return_value if return_value is not None else []
    q.first.return_value = return_value
    q.scalar.return_value = scalar_value
    # For chaining filter_by after join
    q.filter_by.return_value = q
    return q


class TestCountActiveProducts:
    def test_count(self):
        mock_product = MagicMock()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.count.return_value = 7
        mock_product.query = mock_q
        with patch("models.Product", mock_product):
            assert MainSiteService.count_active_products(tenant_id=1) == 7
            mock_q.filter_by.assert_called_once_with(is_active=True, tenant_id=1)


class TestTodaySalesTotals:
    def test_without_branch(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(return_value=(3, Decimal("123.000")))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            result = MainSiteService.today_sales_totals(tenant_id=1, today=datetime.date(2026, 1, 1))
            assert result == (3, Decimal("123.000"))
            # filter called at least once, not with branch
            assert mock_q.filter.called

    def test_with_branch(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(return_value=(1, Decimal("10")))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            result = MainSiteService.today_sales_totals(tenant_id=1, today=datetime.date(2026, 1, 1), branch_id=5)
            assert result == (1, Decimal("10"))
            # branch filter should have been added
            assert mock_q.filter.call_count >= 2


class TestMonthSalesTotals:
    def test_with_branch(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(return_value=(5, Decimal("500")))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.month_sales_totals(1, datetime.date(2026, 8, 1), branch_id=2)
            assert out == (5, Decimal("500"))

    def test_without_branch(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(return_value=(0, None))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.month_sales_totals(1, datetime.date(2026, 8, 1))
            assert out == (0, None)


class TestMonthProfitTotal:
    def test_profit_with_branch(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(scalar_value=Decimal("99.500"))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.month_profit_total(1, datetime.date(2026, 8, 1), branch_id=9)
            assert out == Decimal("99.500")

    def test_profit_empty_returns_zero(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(scalar_value=None)
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.month_profit_total(1, datetime.date(2026, 8, 1))
            assert out == Decimal("0")


class TestTotalReceivables:
    def test_with_branch(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(scalar_value=Decimal("250"))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.total_receivables(branch_id=3)
            assert out == Decimal("250")

    def test_without_branch_none_returns_zero(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(scalar_value=None)
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.total_receivables()
            assert out == Decimal("0")


class TestLiquidityBalance:
    def test_no_accounts_returns_zero(self):
        mock_account_q = MagicMock()
        mock_account_q.filter.return_value = mock_account_q
        mock_account_q.all.return_value = []
        mock_account = MagicMock()
        mock_account.query = mock_account_q
        with patch("models.GLAccount", mock_account):
            # Need to patch db for early return before debit queries
            out = MainSiteService.liquidity_balance("cash", tenant_id=1)
            assert out == Decimal("0")

    def test_with_accounts_and_branch(self):
        # Account query returns two accounts
        acc1 = MagicMock(id=10)
        acc2 = MagicMock(id=20)
        mock_account_q = MagicMock()
        mock_account_q.filter.return_value = mock_account_q
        mock_account_q.all.return_value = [acc1, acc2]
        mock_account = MagicMock()
        mock_account.query = mock_account_q
        mock_account.tenant_id = MagicMock()
        mock_account.is_active = MagicMock()
        mock_account.is_header = MagicMock(is_=MagicMock(return_value=MagicMock()))
        mock_account.liquidity_kind = MagicMock()
        mock_account.branch_id = MagicMock()

        # db queries for debit/credit
        mock_db = MagicMock()
        debit_q = MagicMock()
        credit_q = MagicMock()
        # db.session.query returns debit_q first, credit_q second
        mock_db.session.query.side_effect = [debit_q, credit_q]
        debit_q.filter.return_value = debit_q
        credit_q.filter.return_value = credit_q
        debit_q.join.return_value.filter_by.return_value = debit_q
        credit_q.join.return_value.filter_by.return_value = credit_q
        debit_q.scalar.return_value = Decimal("1000")
        credit_q.scalar.return_value = Decimal("400")

        with patch("models.GLAccount", mock_account), patch("extensions.db", mock_db), patch("models.GLJournalLine", MagicMock()):
            out = MainSiteService.liquidity_balance("cash", tenant_id=1, branch_id=7)
            assert out == Decimal("600")

    def test_with_accounts_no_branch(self):
        acc = MagicMock(id=5)
        mock_account_q = MagicMock()
        mock_account_q.filter.return_value = mock_account_q
        mock_account_q.all.return_value = [acc]
        mock_account = MagicMock()
        mock_account.query = mock_account_q
        mock_account.is_header = MagicMock(is_=MagicMock(return_value=MagicMock()))
        mock_db = MagicMock()
        debit_q = MagicMock()
        credit_q = MagicMock()
        mock_db.session.query.side_effect = [debit_q, credit_q]
        debit_q.filter.return_value = debit_q
        credit_q.filter.return_value = credit_q
        debit_q.scalar.return_value = Decimal("10")
        credit_q.scalar.return_value = None  # should coalesce to 0
        with patch("models.GLAccount", mock_account), patch("extensions.db", mock_db), patch("models.GLJournalLine", MagicMock()):
            out = MainSiteService.liquidity_balance("bank", tenant_id=2)
            assert out == Decimal("10")


class TestInventoryGlValue:
    def test_with_branch(self):
        inv_account = MagicMock(id=99)
        mock_db = MagicMock()
        debit_q = MagicMock()
        credit_q = MagicMock()
        mock_db.session.query.side_effect = [debit_q, credit_q]
        debit_q.filter_by.return_value = debit_q
        credit_q.filter_by.return_value = credit_q
        debit_q.join.return_value.filter_by.return_value = debit_q
        credit_q.join.return_value.filter_by.return_value = credit_q
        debit_q.scalar.return_value = Decimal("500")
        credit_q.scalar.return_value = Decimal("200")
        with patch("extensions.db", mock_db):
            out = MainSiteService.inventory_gl_value(inv_account, branch_id=1)
            assert out == Decimal("300")

    def test_without_branch_none(self):
        inv_account = MagicMock(id=11)
        mock_db = MagicMock()
        debit_q = MagicMock()
        credit_q = MagicMock()
        mock_db.session.query.side_effect = [debit_q, credit_q]
        debit_q.filter_by.return_value = debit_q
        credit_q.filter_by.return_value = credit_q
        debit_q.scalar.return_value = None
        credit_q.scalar.return_value = None
        with patch("extensions.db", mock_db):
            out = MainSiteService.inventory_gl_value(inv_account)
            assert out == Decimal("0")


class TestRecentConfirmedSales:
    def test_with_tenant_and_branch(self):
        mock_sale = MagicMock()
        mock_q = MagicMock()
        mock_sale.query = mock_q
        mock_q.options.return_value = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = ["a", "b"]
        with patch("models.Sale", mock_sale):
            out = MainSiteService.recent_confirmed_sales(tenant_id=1, branch_id=2, limit=5)
            assert out == ["a", "b"]
            # tenant filter should have been called, branch filter too
            assert mock_q.filter.call_count >= 2

    def test_tenant_none_only_branch(self):
        mock_sale = MagicMock()
        mock_q = MagicMock()
        mock_sale.query = mock_q
        mock_q.options.return_value = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = []
        with patch("models.Sale", mock_sale):
            out = MainSiteService.recent_confirmed_sales(tenant_id=None, branch_id=1, limit=10)
            assert out == []
            # tenant filter not called when tenant_id is None, only branch filter
            # Ensure at least one filter (branch) happened
            assert mock_q.filter.called

    def test_tenant_none_no_branch(self):
        mock_sale = MagicMock()
        mock_q = MagicMock()
        mock_sale.query = mock_q
        mock_q.options.return_value = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = []
        with patch("models.Sale", mock_sale):
            out = MainSiteService.recent_confirmed_sales(tenant_id=None, branch_id=None)
            assert out == []


class TestSellerSalesTotals:
    def test_seller_totals(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(return_value=(2, Decimal("300")))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.seller_sales_totals(seller_id=42)
            assert out == (2, Decimal("300"))


class TestSellerSalesTotalsOn:
    def test_on_day(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(return_value=(1, Decimal("50")))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.seller_sales_totals_on(seller_id=9, day=datetime.date(2026, 8, 1))
            assert out == (1, Decimal("50"))


class TestSellerSalesTotalsSince:
    def test_since(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(return_value=(4, Decimal("700")))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.seller_sales_totals_since(seller_id=5, start_day=datetime.date(2026, 7, 1))
            assert out == (4, Decimal("700"))


class TestPaymentTotalsForUser:
    def test_payment_totals(self):
        mock_db = MagicMock()
        mock_q = _mock_query_chain(return_value=(10, Decimal("1000")))
        mock_db.session.query.return_value = mock_q
        with patch("extensions.db", mock_db):
            out = MainSiteService.payment_totals_for_user(user_id=7)
            assert out == (10, Decimal("1000"))


class TestRecentSalesForSeller:
    def test_recent(self):
        mock_sale = MagicMock()
        mock_q = MagicMock()
        mock_sale.query = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = ["x"]
        with patch("models.Sale", mock_sale):
            out = MainSiteService.recent_sales_for_seller(seller_id=3, limit=7)
            assert out == ["x"]


class TestEmailExists:
    def test_exists(self):
        mock_user = MagicMock()
        mock_q = MagicMock()
        mock_user.query = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = MagicMock(id=99)
        with patch("models.User", mock_user):
            out = MainSiteService.email_exists("a@b.com", exclude_user_id=1, tenant_id=10)
            assert out.id == 99


class TestTenantBySlug:
    def test_lookup(self):
        mock_tenant = MagicMock()
        mock_q = MagicMock()
        mock_tenant.query = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.first_or_404.return_value = MagicMock(slug="acme")
        with patch("models.tenant.Tenant", mock_tenant):
            out = MainSiteService.tenant_by_slug("acme")
            assert out.slug == "acme"


class TestActiveBranchesForTenant:
    def test_active(self):
        mock_branch = MagicMock()
        mock_q = MagicMock()
        mock_branch.query = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [MagicMock(name="A"), MagicMock(name="B")]
        with patch("models.branch.Branch", mock_branch):
            out = MainSiteService.active_branches_for_tenant(tenant_id=12)
            assert len(out) == 2


class TestSalesTrendDaily:
    def test_zero_filled(self):
        mock_db = MagicMock()
        mock_q = MagicMock()
        mock_db.session.query.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        # query.group_by(day_expr).all() returns one entry on second day
        start = datetime.date(2026, 8, 10)
        mock_q.all.return_value = [(start + datetime.timedelta(days=1), Decimal("100"))]
        with patch("extensions.db", mock_db):
            series = MainSiteService.sales_trend_daily(tenant_id=1, start_day=start, days=3)
            assert len(series) == 3
            assert series[0]["date"] == start.isoformat()
            assert series[0]["total_aed"] == 0.0
            assert series[1]["total_aed"] == 100.0
            assert series[2]["total_aed"] == 0.0

    def test_with_branch_filter(self):
        mock_db = MagicMock()
        mock_q = MagicMock()
        mock_db.session.query.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.all.return_value = []
        start = datetime.date(2026, 8, 1)
        with patch("extensions.db", mock_db):
            series = MainSiteService.sales_trend_daily(tenant_id=2, start_day=start, days=2, branch_id=5)
            assert len(series) == 2
            # branch filter should have added extra filter call
            assert mock_q.filter.call_count >= 2

    def test_grouped_totals_float_conversion(self):
        mock_db = MagicMock()
        mock_q = MagicMock()
        mock_db.session.query.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        start = datetime.date(2026, 1, 1)
        mock_q.all.return_value = [
            (start, Decimal("123.45")),
            (start + datetime.timedelta(days=1), None),
        ]
        with patch("extensions.db", mock_db):
            series = MainSiteService.sales_trend_daily(1, start, days=2)
            assert series[0]["total_aed"] == 123.45
            assert series[1]["total_aed"] == 0.0


class TestTopCustomers:
    def test_without_start_branch(self):
        mock_db = MagicMock()
        mock_q = MagicMock()
        mock_db.session.query.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [(1, "Alice", Decimal("500")), (2, "Bob", Decimal("300"))]
        with patch("extensions.db", mock_db):
            out = MainSiteService.top_customers(tenant_id=1)
            assert out == [
                {"customer_id": 1, "name": "Alice", "total_aed": 500.0},
                {"customer_id": 2, "name": "Bob", "total_aed": 300.0},
            ]

    def test_with_start_day_and_branch(self):
        mock_db = MagicMock()
        mock_q = MagicMock()
        mock_db.session.query.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [(3, "Carol", None)]
        with patch("extensions.db", mock_db):
            out = MainSiteService.top_customers(tenant_id=1, start_day=datetime.date(2026, 7, 1), limit=5, branch_id=4)
            assert out[0]["total_aed"] == 0.0
            assert out[0]["name"] == "Carol"
            # Ensure extra filter calls for start_day and branch_id
            assert mock_q.filter.call_count >= 2

    def test_limit_is_respected(self):
        mock_db = MagicMock()
        mock_q = MagicMock()
        mock_db.session.query.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [(1, "A", Decimal("100"))]
        with patch("extensions.db", mock_db):
            MainSiteService.top_customers(tenant_id=1, limit=1)
            mock_q.limit.assert_called_once_with(1)


class TestStockAlertSummary:
    def test_stock_alert_none_fallback(self):
        mock_stock = MagicMock()
        mock_stock.get_low_stock_products.return_value = None
        mock_stock.get_out_of_stock_products.return_value = None
        with patch("services.stock_service.StockService", mock_stock):
            out = MainSiteService.stock_alert_summary(user=MagicMock(), limit=10)
            assert out["low_stock"] == []
            assert out["out_of_stock"] == []
            assert out["low_stock_count"] == 0
            assert out["out_of_stock_count"] == 0

    def test_stock_alert_with_products(self):
        p1 = MagicMock(id=1, name="Paracetamol", current_stock=2, min_stock_alert=10)
        p1.name_ar = None
        p1.name = "Paracetamol"
        p2 = MagicMock(id=2, name="Ibuprofen", current_stock=0, min_stock_alert=5)
        p2.name_ar = "ايبوبروفين"
        p2.name = "Ibuprofen"
        p2.current_stock = 0
        p2.min_stock_alert = 5
        # Ensure name_ar vs name logic: p2 name_ar truthy should be used
        p1.current_stock = Decimal("2")
        p1.min_stock_alert = Decimal("10")
        mock_stock = MagicMock()
        mock_stock.get_low_stock_products.return_value = [p1]
        mock_stock.get_out_of_stock_products.return_value = [p1, p2, p2, p2, p2, p2, p2, p2, p2, p2, p2, p2]
        with patch("services.stock_service.StockService", mock_stock):
            out = MainSiteService.stock_alert_summary(user=MagicMock(), limit=5)
            assert out["low_stock_count"] == 1
            assert out["out_of_stock_count"] == 12
            # low_stock row uses name fallback
            assert out["low_stock"][0]["name"] == "Paracetamol"
            assert out["low_stock"][0]["qty"] == 2.0
            # out_of_stock limited to 5
            assert len(out["out_of_stock"]) == 5
            assert out["out_of_stock"][0]["name"] == "Paracetamol"

    def test_stock_alert_qty_missing_attrs(self):
        p = MagicMock(id=3, name="Void")
        p.name_ar = None
        # no current_stock attr -> getattr returns None fallback
        del p.current_stock
        del p.min_stock_alert
        # Use spec-like magic to ensure getattr returns None
        p.__dict__.pop("current_stock", None)
        p.__dict__.pop("min_stock_alert", None)
        type(p).__getattr__ = lambda self, name: None  # not needed, MagicMock returns mock
        # Instead explicitly set to None via mock's side
        p2 = MagicMock(id=3, name="Void")
        p2.name_ar = None
        p2.configure_mock(**{"current_stock": None, "min_stock_alert": None})
        mock_stock = MagicMock()
        mock_stock.get_low_stock_products.return_value = [p2]
        mock_stock.get_out_of_stock_products.return_value = []
        with patch("services.stock_service.StockService", mock_stock):
            out = MainSiteService.stock_alert_summary(user=MagicMock(), limit=10)
            assert out["low_stock"][0]["qty"] == 0.0
            assert out["low_stock"][0]["min_qty"] == 0.0
