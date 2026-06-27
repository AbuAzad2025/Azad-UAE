"""Advanced financial analytics — ratios, trends, zero-data edge cases."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestFinancialRatios:
    """get_financial_ratios — division-by-zero guards."""

    def test_zero_liabilities_yields_zero_liquidity_ratios(self, mocker):
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics._calculate_balance_by_prefix',
            side_effect=lambda prefix, *a, **kw: {
                '11': Decimal('100000'),
                '1': Decimal('200000'),
                '21': Decimal('0'),
                '2': Decimal('0'),
                '3': Decimal('150000'),
                '4': Decimal('50000'),
                ('5', '6'): Decimal('30000'),
            }.get(prefix if isinstance(prefix, str) else tuple(prefix), Decimal('0')),
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        ratios = AdvancedFinancialAnalytics.get_financial_ratios(
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            tenant_id=1,
        )
        assert ratios['liquidity']['current_ratio'] == 0
        assert ratios['profitability']['net_profit_margin'] == pytest.approx(40.0)
        assert ratios['base_data']['net_profit'] == pytest.approx(20000.0)

    def test_zero_revenue_zero_margins(self, mocker):
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics._calculate_balance_by_prefix',
            return_value=Decimal('0'),
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        ratios = AdvancedFinancialAnalytics.get_financial_ratios(tenant_id=2)
        assert ratios['profitability']['gross_profit_margin'] == 0
        assert ratios['efficiency']['expense_ratio'] == 0


class TestBalanceByPrefix:
    """_calculate_balance_by_prefix — asset vs credit-normal aggregation."""

    def _line(self, amount, account_type='asset'):
        line = MagicMock()
        line.amount_aed = Decimal(str(amount))
        acct = MagicMock()
        acct.type = account_type
        acct.id = 1
        return line, acct

    def test_asset_lines_sum_positive(self, mocker):
        line, acct = self._line(500, 'asset')
        mock_scope = mocker.patch('utils.gl_tenant.scope_gl_accounts')
        mock_scope.return_value.filter.return_value.all.return_value = [acct]

        lines_q = MagicMock()
        lines_q.join.return_value = lines_q
        lines_q.filter.return_value = lines_q
        lines_q.all.return_value = [line]
        mocker.patch.object(
            __import__('models', fromlist=['GLJournalLine']).GLJournalLine,
            'query',
            new_callable=mocker.PropertyMock,
            return_value=lines_q,
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        total = AdvancedFinancialAnalytics._calculate_balance_by_prefix(
            '11', date_to=date.today(), tenant_id=1
        )
        assert total == Decimal('500')

    def test_revenue_credit_normal_subtracts_debit(self, mocker):
        line, acct = self._line(-200, 'revenue')
        mock_scope = mocker.patch('utils.gl_tenant.scope_gl_accounts')
        mock_scope.return_value.filter.return_value.all.return_value = [acct]

        lines_q = MagicMock()
        lines_q.join.return_value = lines_q
        lines_q.filter.return_value = lines_q
        lines_q.all.return_value = [line]
        mocker.patch.object(
            __import__('models', fromlist=['GLJournalLine']).GLJournalLine,
            'query',
            new_callable=mocker.PropertyMock,
            return_value=lines_q,
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        total = AdvancedFinancialAnalytics._calculate_balance_by_prefix(
            '4',
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
            is_pl=True,
            tenant_id=1,
        )
        assert total == Decimal('200')

    def test_list_prefix_or_filter(self, mocker):
        mock_scope = mocker.patch('utils.gl_tenant.scope_gl_accounts')
        scoped = mock_scope.return_value
        scoped.filter.return_value.all.return_value = []

        from services.advanced_analytics import AdvancedFinancialAnalytics

        result = AdvancedFinancialAnalytics._calculate_balance_by_prefix(
            ['5', '6'], date_from=date.today(), date_to=date.today(), is_pl=True, tenant_id=1
        )
        assert result == Decimal('0')
        scoped.filter.assert_called_once()


class TestTrendAnalysis:
    """get_trend_analysis — monthly buckets and change percentages."""

    def test_zero_revenue_month_margin_and_change(self, mocker):
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics._calculate_account_type_balance',
            side_effect=[Decimal('0'), Decimal('0')] * 6,
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        trends = AdvancedFinancialAnalytics.get_trend_analysis(months=3)
        assert len(trends) == 3
        assert all(t['margin'] == 0 for t in trends)
        assert trends[0]['change'] == 0
        assert trends[1]['change'] == 0

    def test_profit_change_from_prior_month(self, mocker):
        balances = []
        for rev, exp in [(1000, 400), (1500, 500), (1200, 600)]:
            balances.extend([Decimal(rev), Decimal(exp)])

        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics._calculate_account_type_balance',
            side_effect=balances,
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        trends = AdvancedFinancialAnalytics.get_trend_analysis(months=3)
        assert trends[1]['profit'] == pytest.approx(1000.0)
        assert trends[2]['change'] == pytest.approx(-40.0)


class TestComparativeAndBreakdown:
    """Comparative periods, expense/revenue breakdown sorting."""

    def test_comparative_skips_unknown_period(self, mocker):
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics._calculate_account_type_balance',
            return_value=Decimal('100'),
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        data = AdvancedFinancialAnalytics.get_comparative_analysis(periods=['current', 'bogus'])
        assert 'current' in data
        assert 'bogus' not in data
        assert data['current']['margin'] == pytest.approx(0.0)

    def test_comparative_last_month_and_year(self, mocker):
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics._calculate_account_type_balance',
            return_value=Decimal('200'),
        )
        from services.advanced_analytics import AdvancedFinancialAnalytics

        data = AdvancedFinancialAnalytics.get_comparative_analysis(
            periods=['current', 'last_month', 'last_year']
        )
        assert set(data.keys()) == {'current', 'last_month', 'last_year'}

    def test_expense_breakdown_zero_total_percentages(self, mocker):
        acct = MagicMock()
        acct.code = '5100'
        acct.full_name = 'Rent'
        acct.get_balance.return_value = Decimal('0')
        mocker.patch('utils.gl_tenant.scope_gl_accounts').return_value.all.return_value = [acct]

        from services.advanced_analytics import AdvancedFinancialAnalytics

        result = AdvancedFinancialAnalytics.get_expense_breakdown(tenant_id=1)
        assert result['total'] == 0.0
        assert result['items'][0]['percentage'] == 0

    def test_revenue_breakdown_sorted_desc(self, mocker):
        low = MagicMock(code='4100', full_name='Low', get_balance=lambda: Decimal('100'))
        high = MagicMock(code='4200', full_name='High', get_balance=lambda: Decimal('900'))
        mocker.patch('utils.gl_tenant.scope_gl_accounts').return_value.all.return_value = [low, high]

        from services.advanced_analytics import AdvancedFinancialAnalytics

        result = AdvancedFinancialAnalytics.get_revenue_breakdown(tenant_id=1)
        assert result['items'][0]['amount'] == pytest.approx(900.0)
        assert result['items'][0]['percentage'] == pytest.approx(90.0)


class TestForecasting:
    """get_forecasting_data / get_dashboard_summary — sparse history guards."""

    def test_forecast_returns_empty_when_insufficient_history(self, mocker):
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics.get_trend_analysis',
            return_value=[{'revenue': 1, 'expenses': 0, 'change': 0}],
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        assert AdvancedFinancialAnalytics.get_forecasting_data() == []

    def test_forecast_builds_months_ahead(self, mocker):
        historical = [
            {'revenue': 1000, 'expenses': 400, 'change': 5},
            {'revenue': 1100, 'expenses': 450, 'change': 10},
            {'revenue': 1200, 'expenses': 500, 'change': 8},
        ]
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics.get_trend_analysis',
            return_value=historical,
        )
        from services.advanced_analytics import AdvancedFinancialAnalytics

        forecasts = AdvancedFinancialAnalytics.get_forecasting_data(months_ahead=2)
        assert len(forecasts) == 2
        assert forecasts[0]['is_forecast'] is True

    def test_dashboard_summary_includes_generated_at(self, mocker):
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics.get_financial_ratios',
            return_value={'liquidity': {}},
        )
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics.get_trend_analysis',
            return_value=[],
        )
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics.get_expense_breakdown',
            return_value={'items': [], 'total': 0},
        )
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics.get_revenue_breakdown',
            return_value={'items': [], 'total': 0},
        )
        mocker.patch(
            'services.advanced_analytics.AdvancedFinancialAnalytics.get_forecasting_data',
            return_value=[],
        )

        from services.advanced_analytics import AdvancedFinancialAnalytics

        summary = AdvancedFinancialAnalytics.get_dashboard_summary()
        assert 'generated_at' in summary
        assert 'ratios' in summary


class TestAccountTypeBalance:
    """_calculate_account_type_balance — dated vs full balance path."""

    def test_full_balance_when_no_date_range(self, mocker):
        acct = MagicMock()
        acct.get_balance.return_value = Decimal('-750')
        mocker.patch('utils.gl_tenant.scope_gl_accounts').return_value.all.return_value = [acct]

        from services.advanced_analytics import AdvancedFinancialAnalytics

        total = AdvancedFinancialAnalytics._calculate_account_type_balance('revenue', tenant_id=1)
        assert total == Decimal('750')

    def test_dated_account_type_balance_expense(self, mocker):
        line = MagicMock(amount_aed=Decimal('100'))
        acct = MagicMock()
        acct.get_balance.return_value = Decimal('0')
        mocker.patch('utils.gl_tenant.scope_gl_accounts').return_value.all.return_value = [acct]
        lines_q = MagicMock()
        lines_q.join.return_value = lines_q
        lines_q.filter.return_value = lines_q
        lines_q.all.return_value = [line]
        mocker.patch('models.GLJournalLine.query', lines_q)
        from services.advanced_analytics import AdvancedFinancialAnalytics
        from datetime import date
        total = AdvancedFinancialAnalytics._calculate_account_type_balance(
            'expense', date_from=date(2025, 1, 1), date_to=date(2025, 6, 1), tenant_id=1,
        )
        assert total == Decimal('100')

    def test_balance_by_prefix_expense_account(self, mocker):
        line = MagicMock(amount_aed=Decimal('40'))
        acct = MagicMock(type='expense')
        mock_scope = mocker.patch('utils.gl_tenant.scope_gl_accounts')
        mock_scope.return_value.filter.return_value.all.return_value = [acct]
        lines_q = MagicMock()
        lines_q.join.return_value = lines_q
        lines_q.filter.return_value = lines_q
        lines_q.all.return_value = [line]
        mocker.patch('models.GLJournalLine.query', lines_q)
        from services.advanced_analytics import AdvancedFinancialAnalytics
        from datetime import date
        total = AdvancedFinancialAnalytics._calculate_balance_by_prefix(
            '5', date_from=date(2025, 1, 1), date_to=date(2025, 6, 1), is_pl=True, tenant_id=1,
        )
        assert total == Decimal('40')
