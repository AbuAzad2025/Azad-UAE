"""Gap100 for routes/advanced_ledger.py — printing zero-balance arc (52->50) +
reports growth/delta arcs (568, 582)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_account(balance=0, **kwargs):
    account = MagicMock()
    account.id = kwargs.get("id", 1)
    account.code = kwargs.get("code", "1101")
    account.full_name = kwargs.get("full_name", "Cash")
    account.type_ar = kwargs.get("type_ar", "أصول")
    account.get_balance = MagicMock(return_value=balance)
    return account


@pytest.fixture
def advanced_ledger_cov100_client(app_factory, bypass_admin_auth):
    from routes.advanced_ledger import advanced_ledger_bp

    app = app_factory(advanced_ledger_bp)
    return app.test_client()


class TestProfessionalPrintingZeroBalances:
    def test_zero_balance_accounts_skip_rows(self, advanced_ledger_cov100_client):
        accounts = [_mock_account(balance=0, id=1), _mock_account(balance=0, id=2, code="1102")]
        q = MagicMock(name="printing_accounts_query")
        q.filter_by.return_value.limit.return_value.all.return_value = accounts
        with (
            patch("routes.advanced_ledger.gl_account_query", return_value=q),
            patch("routes.advanced_ledger.render_template", return_value="ok") as render,
            patch(
                "models.invoice_settings.InvoiceSettings.get_active",
                return_value=MagicMock(active_template="modern"),
            ),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
        ):
            resp = advanced_ledger_cov100_client.get("/ledger/advanced/professional-printing")
        assert resp.status_code == 200
        assert render.call_args[1]["trial_balance_data"] == []
        assert render.call_args[1]["trial_balance_json"] == []


class TestProfessionalReportsGrowth:
    def _trend(self, months=12, base=100, step=100):
        return [
            {
                "month": f"M{i + 1}",
                "revenue": base + i * step,
                "expenses": 40,
                "profit": base + i * step - 40,
                "margin": 60.0,
            }
            for i in range(months)
        ]

    def test_revenue_growth_and_deltas(self, advanced_ledger_cov100_client):
        trends = self._trend()
        trends[10]["expenses"] = 0
        with (
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_trend_analysis",
                return_value=trends,
            ),
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_expense_breakdown",
                return_value={"items": [], "total": 0},
            ),
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_financial_ratios",
                return_value={
                    "liquidity": {"current_ratio": 1.5, "quick_ratio": 1.0},
                    "profitability": {"net_profit_margin": 20.0},
                },
            ),
            patch("routes.advanced_ledger.render_template", return_value="ok") as render,
        ):
            resp = advanced_ledger_cov100_client.get("/ledger/advanced/professional-reports")
        assert resp.status_code == 200
        kwargs = render.call_args[1]
        assert kwargs["revenue_growth"] is not None
        assert kwargs["revenue_delta"] is not None
        assert kwargs["expense_delta"] is None
        assert kwargs["profit_delta"] is not None
        assert kwargs["margin_delta"] is not None


class TestFormFallbackArcs:
    def test_add_customs_tax_missing_account(self, advanced_ledger_cov100_client):
        q = MagicMock(name="cov100_accounts_query")
        q.filter_by.return_value.order_by.return_value.all.return_value = []
        with (
            patch("routes.advanced_ledger.gl_account_query", return_value=q),
            patch("routes.advanced_ledger.render_template", return_value="ok") as render,
        ):
            resp = advanced_ledger_cov100_client.post(
                "/ledger/advanced/customs-taxes/add",
                data={"name": "VAT"},
                follow_redirects=False,
            )
        assert resp.status_code == 200
        assert render.call_args[0][0] == "ledger/advanced/add_customs_tax.html"

    def test_add_expense_category_get_form(self, advanced_ledger_cov100_client):
        q = MagicMock(name="cov100_cat_accounts_query")
        q.filter_by.return_value.order_by.return_value.all.return_value = []
        with (
            patch("routes.advanced_ledger.gl_account_query", return_value=q),
            patch("routes.advanced_ledger.render_template", return_value="ok") as render,
        ):
            resp = advanced_ledger_cov100_client.get("/ledger/advanced/expense-categories/add")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "ledger/advanced/add_expense_category.html"

    def test_add_advanced_expense_currency_fallback(self, advanced_ledger_cov100_client):
        expense = MagicMock(expense_number="EXP-9", id=9)
        expense.calculate_taxes = MagicMock()
        with (
            patch("routes.advanced_ledger.gl_account_query"),
            patch("routes.advanced_ledger.render_template", return_value="ok"),
            patch("routes.advanced_ledger.db.session"),
            patch("routes.advanced_ledger.LoggingCore.log_audit"),
            patch("routes.advanced_ledger.AdvancedExpense", return_value=expense),
            patch(
                "routes.advanced_ledger.resolve_default_currency",
                side_effect=RuntimeError("fx down"),
            ),
            patch("routes.advanced_ledger.get_system_default_currency", return_value="AED"),
            patch("routes.advanced_ledger.active_tenant_id", return_value=1),
        ):
            resp = advanced_ledger_cov100_client.post(
                "/ledger/advanced/advanced-expenses/add",
                data={
                    "expense_date": "2026-06-01",
                    "description": "Fuel",
                    "category_id": "1",
                    "amount": "100",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_add_advanced_expense_invalid_date_errors(self, advanced_ledger_cov100_client):
        with (
            patch("routes.advanced_ledger.gl_account_query"),
            patch("routes.advanced_ledger.render_template", return_value="ok") as render,
            patch("routes.advanced_ledger.resolve_default_currency", return_value="AED"),
            patch("routes.advanced_ledger.active_tenant_id", return_value=1),
            patch("routes.advanced_ledger.AdvancedExpenseService.list_expense_categories", return_value=[]),
            patch("routes.advanced_ledger.AdvancedExpenseService.list_supplier_options", return_value=[]),
        ):
            resp = advanced_ledger_cov100_client.post(
                "/ledger/advanced/advanced-expenses/add",
                data={"description": "Bad date"},
                follow_redirects=False,
            )
        assert resp.status_code == 200
        assert render.call_args[0][0] == "ledger/advanced/add_advanced_expense.html"
