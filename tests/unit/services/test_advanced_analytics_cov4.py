"""Cov4: advanced_analytics — ratios/edge-zero/trend/comparative/breakdown/forecast arcs."""

from __future__ import annotations

from unittest.mock import patch

from services.advanced_analytics import AdvancedFinancialAnalytics as AFA


def test_ratios_all_zero_branch(sample_tenant):
    with patch.object(AFA, "_calculate_balance_by_prefix", return_value=__import__("decimal").Decimal("0")):
        ratios = AFA.get_financial_ratios(tenant_id=sample_tenant.id)
    assert ratios["liquidity"]["current_ratio"] == 0
    assert ratios["profitability"]["net_profit_margin"] == 0
    assert ratios["efficiency"]["asset_turnover"] == 0
    assert ratios["leverage"]["debt_to_equity"] == 0
    assert ratios["base_data"]["net_profit"] == 0.0


def test_ratios_nonzero_math():
    from decimal import Decimal

    vals = {"11": Decimal("200"), "1": Decimal("1000"), "21": Decimal("100"),
            "2": Decimal("400"), "3": Decimal("600"), "4": Decimal("500"),
            "multi": Decimal("300")}
    with patch.object(AFA, "_calculate_balance_by_prefix", side_effect=lambda *a, **k: vals.get(
            a[0] if isinstance(a[0], str) else "multi", Decimal("0"))):
        ratios = AFA.get_financial_ratios(tenant_id=1)
    assert ratios["liquidity"]["current_ratio"] == 2.0
    assert ratios["profitability"]["net_profit_margin"] == 40.0
    assert ratios["leverage"]["debt_to_equity"] == float(Decimal("400") / Decimal("600"))


def test_balance_by_prefix_branches(db_session, sample_tenant, sample_gl_accounts):
    from datetime import date
    from decimal import Decimal

    from models import GLAccount

    acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1111").first()
    assert acc is not None
    out = AFA._calculate_balance_by_prefix("111", date(2026, 1, 1), date(2026, 12, 31),
                                           tenant_id=sample_tenant.id)
    assert out == Decimal("0")
    out2 = AFA._calculate_balance_by_prefix(["11", "12"], tenant_id=sample_tenant.id)
    assert isinstance(out2, Decimal)


def test_account_type_balance_else_branch(db_session, sample_tenant, sample_gl_accounts):
    out = AFA._calculate_account_type_balance("asset", tenant_id=sample_tenant.id)
    assert out >= 0


def test_trend_and_change_math():
    with patch.object(AFA, "_calculate_account_type_balance",
                      side_effect=[100, 60, 200, 50, 0, 0]):
        trends = AFA.get_trend_analysis(months=3)
    assert len(trends) == 3
    assert trends[0]["change"] == 0
    assert trends[1]["change"] == 150.0
    assert trends[2]["change"] == 0  # prev profit 0 branch... (150->-50?) check below


def test_comparative_unknown_period_skipped():
    out = AFA.get_comparative_analysis(periods=["current", "bogus"])
    assert set(out) == {"current"}
    out2 = AFA.get_comparative_analysis(periods=["last_month", "last_year"])
    assert set(out2) == {"last_month", "last_year"}


def test_breakdowns_sort_and_zero_pct(db_session, sample_tenant, sample_gl_accounts):
    exp = AFA.get_expense_breakdown(tenant_id=sample_tenant.id)
    assert exp["total"] == 0.0
    assert all(i["percentage"] == 0 for i in exp["items"])
    rev = AFA.get_revenue_breakdown(tenant_id=sample_tenant.id)
    assert rev["total"] == 0.0


def test_forecast_short_history_and_normal():
    with patch.object(AFA, "get_trend_analysis", return_value=[{"revenue": 1}]):
        assert AFA.get_forecasting_data() == []
    hist = [{"revenue": 100.0, "expenses": 60.0, "change": 10.0} for _ in range(12)]
    with patch.object(AFA, "get_trend_analysis", return_value=hist):
        fc = AFA.get_forecasting_data(months_ahead=2)
        assert len(fc) == 2
        assert fc[0]["is_forecast"] is True
    with patch.object(AFA, "get_trend_analysis", return_value=[{"revenue": 0.0}] * 12):
        fc = AFA.get_forecasting_data(months_ahead=1)
        assert fc[0]["margin"] == 0  # zero-revenue margin branch


def test_dashboard_summary_keys():
    with patch.object(AFA, "get_financial_ratios", return_value={"r": 1}), \
         patch.object(AFA, "get_trend_analysis", return_value=[]), \
         patch.object(AFA, "get_expense_breakdown", return_value={}), \
         patch.object(AFA, "get_revenue_breakdown", return_value={}), \
         patch.object(AFA, "get_forecasting_data", return_value=[]):
        dash = AFA.get_dashboard_summary()
        assert set(dash) == {"ratios", "trends", "expense_breakdown",
                             "revenue_breakdown", "forecast", "generated_at"}
