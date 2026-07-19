"""Financial service — period closures, sums, margin math, branch scoping."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestSumHelpers:
    """sum_sales / sum_purchases / sum_receipts — centralized filters."""

    @staticmethod
    def _scalar_chain(mocker, value):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = value
        mocker.patch("services.financial_service.db.session").query.return_value = q
        return q

    def test_sum_sales_applies_branch_and_dates(self, mocker):
        q = self._scalar_chain(mocker, Decimal("5000"))
        from services.financial_service import FinancialService

        result = FinancialService.sum_sales(
            1,
            branch_id=3,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
        )
        assert result == Decimal("5000")
        assert q.filter.call_count >= 4

    def test_sum_sales_zero_when_no_rows(self, mocker):
        self._scalar_chain(mocker, None)
        from services.financial_service import FinancialService

        assert FinancialService.sum_sales(1) == 0

    def test_sum_purchases_status_filter(self, mocker):
        q = self._scalar_chain(mocker, Decimal("1200"))
        from services.financial_service import FinancialService

        assert FinancialService.sum_purchases(1, status="confirmed") == Decimal("1200")
        q.filter.assert_called()

    def test_sum_receipts_branch_scoped(self, mocker):
        self._scalar_chain(mocker, Decimal("800"))
        from services.financial_service import FinancialService

        assert FinancialService.sum_receipts(2, branch_id=5) == Decimal("800")


class TestDashboardContext:
    """get_financial_dashboard_advanced_context — closure KPI math."""

    def test_twelve_month_margin_and_growth(self, mocker):
        mocker.patch(
            "services.financial_service.FinancialService.sum_sales",
            side_effect=[Decimal("1500")] + [Decimal("1000")] * 11,
        )
        expense_q = MagicMock()
        expense_q.filter.return_value = expense_q
        expense_q.scalar.return_value = Decimal("400")
        mocker.patch(
            "services.financial_service.db.session"
        ).query.return_value = expense_q

        from services.financial_service import FinancialService

        ctx = FinancialService.get_financial_dashboard_advanced_context(tenant_id=1)
        assert len(ctx["months_data"]) == 12
        assert ctx["months_data"][-1]["revenue"] == pytest.approx(1500.0)
        assert ctx["kpis"]["avg_revenue"] > 0
        assert float(ctx["months_data"][-1]["margin"]) == pytest.approx(73.33, rel=0.01)

    def test_zero_revenue_month_margin_safe(self, mocker):
        mocker.patch(
            "services.financial_service.FinancialService.sum_sales",
            return_value=Decimal("0"),
        )
        expense_q = MagicMock()
        expense_q.filter.return_value = expense_q
        expense_q.scalar.return_value = Decimal("0")
        mocker.patch(
            "services.financial_service.db.session"
        ).query.return_value = expense_q

        from services.financial_service import FinancialService

        ctx = FinancialService.get_financial_dashboard_advanced_context(tenant_id=1)
        assert all(m["margin"] == 0 for m in ctx["months_data"])
        assert ctx["kpis"]["growth_rate"] == 0


class TestFinancialOverview:
    """financial_overview — period selection and platform mode."""

    def test_month_period_renders_template(self, app, mocker):
        mocker.patch(
            "services.financial_service.FinancialService.sum_sales",
            return_value=Decimal("3000"),
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_purchases",
            return_value=Decimal("1000"),
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_receipts",
            return_value=Decimal("500"),
        )

        session = mocker.patch("services.financial_service.db.session")
        pay_q = MagicMock()
        pay_q.filter.return_value = pay_q
        pay_q.scalar.side_effect = [Decimal("2500"), 10, 4]
        session.query.return_value = pay_q

        mock_render = mocker.patch(
            "services.financial_service.render_template",
            return_value="<html/>",
        )

        from services.financial_service import FinancialService

        with app.app_context():
            html = FinancialService.financial_overview(
                "month", tid=1, scoped_branch_id=None
            )

        assert html == "<html/>"
        data = mock_render.call_args.kwargs["financial_data"]
        assert data["net_revenue"] == pytest.approx(2000.0)
        assert data["platform_mode"] is False

    def test_platform_mode_when_tid_none(self, app, mocker):
        mocker.patch(
            "services.financial_service.FinancialService.sum_sales", return_value=0
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_purchases", return_value=0
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_receipts", return_value=0
        )

        session = mocker.patch("services.financial_service.db.session")
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = 0
        session.query.return_value = q

        mock_render = mocker.patch(
            "services.financial_service.render_template",
            return_value="ok",
        )

        from services.financial_service import FinancialService

        with app.app_context():
            FinancialService.financial_overview("year", tid=None, scoped_branch_id=None)

        assert mock_render.call_args.kwargs["financial_data"]["platform_mode"] is True

    def test_unknown_period_defaults_to_month_start(self, app, mocker):
        sum_sales = mocker.patch(
            "services.financial_service.FinancialService.sum_sales",
            return_value=0,
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_purchases", return_value=0
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_receipts", return_value=0
        )
        session = mocker.patch("services.financial_service.db.session")
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = 0
        session.query.return_value = q
        mocker.patch("services.financial_service.render_template", return_value="ok")

        from services.financial_service import FinancialService

        with app.app_context():
            FinancialService.financial_overview("invalid", tid=1, scoped_branch_id=2)

        assert sum_sales.call_args.kwargs["branch_id"] == 2

    def test_today_period(self, app, mocker):
        sum_sales = mocker.patch(
            "services.financial_service.FinancialService.sum_sales", return_value=0
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_purchases", return_value=0
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_receipts", return_value=0
        )
        session = mocker.patch("services.financial_service.db.session")
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = 0
        session.query.return_value = q
        mocker.patch("services.financial_service.render_template", return_value="ok")

        from services.financial_service import FinancialService

        with app.app_context():
            FinancialService.financial_overview("today", tid=1, scoped_branch_id=None)
        assert sum_sales.call_args.kwargs["date_from"] is not None

    def test_week_period(self, app, mocker):
        sum_sales = mocker.patch(
            "services.financial_service.FinancialService.sum_sales", return_value=0
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_purchases", return_value=0
        )
        mocker.patch(
            "services.financial_service.FinancialService.sum_receipts", return_value=0
        )
        session = mocker.patch("services.financial_service.db.session")
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = 0
        session.query.return_value = q
        mocker.patch("services.financial_service.render_template", return_value="ok")

        from services.financial_service import FinancialService

        with app.app_context():
            FinancialService.financial_overview("week", tid=1, scoped_branch_id=4)
        assert sum_sales.call_args.kwargs["branch_id"] == 4


class TestSumFiltersExtended:
    @staticmethod
    def _scalar_chain(mocker, value):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = value
        mocker.patch("services.financial_service.db.session").query.return_value = q
        return q

    def test_sum_sales_seller_and_date_to(self, mocker):
        q = self._scalar_chain(mocker, Decimal("100"))
        from services.financial_service import FinancialService

        FinancialService.sum_sales(1, seller_id=9, date_to=date(2025, 12, 31))
        assert q.filter.call_count >= 3

    def test_sum_purchases_branch_id(self, mocker):
        q = self._scalar_chain(mocker, Decimal("50"))
        from services.financial_service import FinancialService

        FinancialService.sum_purchases(1, branch_id=2)
        q.filter.assert_called()

    def test_sum_purchases_date_from_and_to(self, mocker):
        q = self._scalar_chain(mocker, Decimal("50"))
        from services.financial_service import FinancialService

        FinancialService.sum_purchases(
            1,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
        )
        assert q.filter.call_count >= 3

    def test_sum_receipts_date_to(self, mocker):
        self._scalar_chain(mocker, Decimal("25"))
        from services.financial_service import FinancialService

        FinancialService.sum_receipts(
            1, date_from=date(2025, 1, 1), date_to=date(2025, 6, 30)
        )

    def test_dashboard_december_month_end(self, mocker):
        mocker.patch(
            "services.financial_service.FinancialService.sum_sales",
            return_value=Decimal("1000"),
        )
        expense_q = MagicMock()
        expense_q.filter.return_value = expense_q
        expense_q.scalar.return_value = Decimal("100")
        mocker.patch(
            "services.financial_service.db.session"
        ).query.return_value = expense_q
        mocker.patch(
            "services.financial_service.datetime",
        )
        import services.financial_service as fs_mod
        from datetime import datetime as real_dt

        dec_today = real_dt(2025, 12, 15).date()
        mocker.patch.object(fs_mod, "datetime")
        fs_mod.datetime.now.return_value.date.return_value = dec_today

        from services.financial_service import FinancialService

        ctx = FinancialService.get_financial_dashboard_advanced_context(
            tenant_id=1, branch_id=2
        )
        assert len(ctx["months_data"]) == 12
        expense_q.filter.assert_called()

    def test_dashboard_branch_filter_on_expenses(self, mocker):
        mocker.patch(
            "services.financial_service.FinancialService.sum_sales",
            return_value=Decimal("500"),
        )
        expense_q = MagicMock()
        expense_q.filter.return_value = expense_q
        expense_q.scalar.return_value = Decimal("50")
        mocker.patch(
            "services.financial_service.db.session"
        ).query.return_value = expense_q

        from services.financial_service import FinancialService

        FinancialService.get_financial_dashboard_advanced_context(
            tenant_id=1, branch_id=3
        )
        assert expense_q.filter.call_count >= 3
