from contextlib import ExitStack, contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

from tests.unit.routes.conftest import (
    _chain_query,
    unauthenticated_client,
)


def _mock_account(code="1101", balance=Decimal("1500")):
    acct = MagicMock()
    acct.id = 1
    acct.code = code
    acct.get_balance = MagicMock(return_value=balance)
    acct.is_active = True
    acct.is_header = False
    return acct


def _accounts_query(accounts=None):
    accounts = accounts or [_mock_account()]
    q = MagicMock()
    q.filter_by.return_value.order_by.return_value.all.return_value = accounts
    q.filter_by.return_value.limit.return_value.all.return_value = accounts
    return q


def _paginated(items=None):
    items = items or []
    pag = MagicMock()
    pag.items = items
    pag.page = 1
    pag.per_page = 20
    pag.total = len(items)
    pag.pages = 1
    return pag


@contextmanager
def _advanced_ledger_patches(**kwargs):
    accounts_q = kwargs.get("accounts_q") or _accounts_query()
    entries_q = kwargs.get("entries_q") or _chain_query(all=[])
    entries_q.order_by.return_value.paginate.return_value = _paginated()
    cheque_q = MagicMock()
    cheque_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = kwargs.get(
        "cheques", []
    )
    cheque_q.filter_by.return_value.count.return_value = kwargs.get("cheque_count", 0)
    cheque_q.count.return_value = kwargs.get("total_cheques", 0)
    cheque_q.filter_by.return_value.scalar.return_value = kwargs.get("cheque_sum", 0)

    customs = kwargs.get("customs", [])
    categories = kwargs.get("categories", [])
    expenses_pag = _paginated(kwargs.get("expenses", []))

    with ExitStack() as stack:
        stack.enter_context(patch("routes.advanced_ledger.gl_account_query", return_value=accounts_q))
        stack.enter_context(patch("routes.advanced_ledger.gl_entry_query", return_value=entries_q))
        stack.enter_context(patch("routes.advanced_ledger.active_tenant_id", return_value=1))
        tax_q = stack.enter_context(patch("routes.advanced_ledger.CustomsTax.query"))
        cat_q = stack.enter_context(patch("routes.advanced_ledger.ExpenseCategory.query"))
        exp_q = stack.enter_context(patch("routes.advanced_ledger.AdvancedExpense.query"))
        stack.enter_context(patch("routes.advanced_ledger.Cheque.query", cheque_q))
        session = stack.enter_context(patch("routes.advanced_ledger.db.session"))
        render = stack.enter_context(patch("routes.advanced_ledger.render_template", return_value="ok"))
        audit = stack.enter_context(patch("routes.advanced_ledger.LoggingCore.log_audit"))
        stack.enter_context(
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_trend_analysis",
                return_value=[{"month": "Jan", "revenue": 100, "expenses": 40, "profit": 60}],
            )
        )
        stack.enter_context(
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_expense_breakdown",
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_revenue_breakdown",
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_dashboard_summary",
                return_value={
                    "ratios": {},
                    "trends": [],
                    "expense_breakdown": [],
                    "revenue_breakdown": [],
                    "forecast": [],
                },
            )
        )
        stack.enter_context(
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_financial_ratios",
                return_value={"current_ratio": 1.5},
            )
        )
        stack.enter_context(
            patch(
                "routes.advanced_ledger.AdvancedFinancialAnalytics.get_forecasting_data",
                return_value={"months": []},
            )
        )
        stack.enter_context(
            patch(
                "routes.advanced_ledger.accounting_event_stream.get_recent_events",
                return_value=[{"type": "sale", "id": 1}],
            )
        )
        stack.enter_context(
            patch(
                "routes.advanced_ledger.accounting_event_stream.get_events_by_type",
                return_value=[{"type": "sale"}],
            )
        )
        stack.enter_context(
            patch(
                "routes.advanced_ledger.ChequeAccountingIntegration.get_cheque_accounting_summary",
                return_value={"status": "pending"},
            )
        )
        stack.enter_context(
            patch(
                "models.invoice_settings.InvoiceSettings.get_active",
                return_value=MagicMock(active_template="modern", enable_qr_code=False),
            )
        )
        stack.enter_context(patch("utils.tenant_branding.get_print_header_context", return_value={}))
        tax_q.filter_by.return_value.order_by.return_value.all.return_value = customs
        cat_q.filter_by.return_value.order_by.return_value.all.return_value = categories
        cat_q.filter_by.return_value.all.return_value = categories
        exp_q.filter_by.return_value.order_by.return_value.paginate.return_value = expenses_pag
        session.query.return_value.scalar.return_value = kwargs.get("cheque_sum", 0)
        yield {"render": render, "audit": audit, "session": session}


class TestAdvancedLedgerAuth:
    def test_professional_printing_requires_login(self, advanced_ledger_client):
        with unauthenticated_client(advanced_ledger_client):
            resp = advanced_ledger_client.get("/ledger/advanced/professional-printing")
        assert resp.status_code == 401


class TestAdvancedLedgerPages:
    def test_professional_printing(self, advanced_ledger_client):
        with _advanced_ledger_patches() as mocks:
            resp = advanced_ledger_client.get("/ledger/advanced/professional-printing")
        assert resp.status_code == 200
        mocks["render"].assert_called_once()

    def test_customs_taxes_list(self, advanced_ledger_client):
        tax = MagicMock(id=1, name_ar="VAT")
        with _advanced_ledger_patches(customs=[tax]):
            resp = advanced_ledger_client.get("/ledger/advanced/customs-taxes")
        assert resp.status_code == 200

    def test_add_customs_tax_get(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/customs-taxes/add")
        assert resp.status_code == 200

    def test_add_customs_tax_post_success(self, advanced_ledger_client):
        acct = _mock_account()
        with _advanced_ledger_patches(accounts_q=_accounts_query([acct])) as mocks:
            resp = advanced_ledger_client.post(
                "/ledger/advanced/customs-taxes/add",
                data={
                    "gl_account_id": "1",
                    "name": "Import",
                    "name_ar": "استيراد",
                    "tax_type": "customs",
                    "rate": "5",
                    "is_percentage": "on",
                    "fixed_amount": "0",
                    "effective_from": "2026-01-01",
                    "effective_to": "2026-12-31",
                    "description": "test",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mocks["audit"].assert_called_once()

    def test_expense_categories(self, advanced_ledger_client):
        with _advanced_ledger_patches(categories=[MagicMock(name="Ops")]):
            resp = advanced_ledger_client.get("/ledger/advanced/expense-categories")
        assert resp.status_code == 200

    def test_add_expense_category_missing_account(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.post("/ledger/advanced/expense-categories/add", data={"name": "Travel"})
        assert resp.status_code == 200

    def test_advanced_expenses_list(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/advanced-expenses")
        assert resp.status_code == 200

    def test_add_customs_tax_post_exception(self, advanced_ledger_client):
        acct = _mock_account()
        accounts_q = _accounts_query([acct])
        with (
            _advanced_ledger_patches(accounts_q=accounts_q) as mocks,
            patch(
                "routes.advanced_ledger.db.session.commit",
                side_effect=RuntimeError("db fail"),
            ),
            patch(
                "utils.error_messages.ErrorMessages.unexpected_error",
                return_value="err",
            ),
        ):
            resp = advanced_ledger_client.post(
                "/ledger/advanced/customs-taxes/add",
                data={
                    "gl_account_id": "1",
                    "name": "Bad",
                    "name_ar": "خطأ",
                    "tax_type": "customs",
                    "rate": "5",
                    "effective_from": "2026-01-01",
                },
            )
        assert resp.status_code == 200
        mocks["render"].assert_called()

    def test_add_expense_category_post_success(self, advanced_ledger_client):
        acct = _mock_account()
        with _advanced_ledger_patches(accounts_q=_accounts_query([acct])) as mocks:
            resp = advanced_ledger_client.post(
                "/ledger/advanced/expense-categories/add",
                data={
                    "gl_account_id": "1",
                    "name": "Travel",
                    "name_ar": "سفر",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mocks["audit"].assert_called_once()

    def test_add_expense_category_post_exception(self, advanced_ledger_client):
        acct = _mock_account()
        with (
            _advanced_ledger_patches(accounts_q=_accounts_query([acct])),
            patch(
                "routes.advanced_ledger.db.session.commit",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "utils.error_messages.ErrorMessages.unexpected_error",
                return_value="err",
            ),
        ):
            resp = advanced_ledger_client.post(
                "/ledger/advanced/expense-categories/add",
                data={
                    "gl_account_id": "1",
                    "name": "Travel",
                    "name_ar": "سفر",
                },
            )
        assert resp.status_code == 200

    def test_add_advanced_expense_post(self, advanced_ledger_client):
        expense = MagicMock(expense_number="EXP-1", id=9)
        expense.calculate_taxes = MagicMock()
        with (
            _advanced_ledger_patches(categories=[MagicMock(id=1)]),
            patch("routes.advanced_ledger.AdvancedExpense", return_value=expense),
            patch("routes.advanced_ledger.resolve_default_currency", return_value="AED"),
        ):
            resp = advanced_ledger_client.post(
                "/ledger/advanced/advanced-expenses/add",
                data={
                    "expense_date": "2026-06-01",
                    "description": "Fuel",
                    "description_ar": "وقود",
                    "category_id": "1",
                    "amount": "100",
                    "currency": "AED",
                    "exchange_rate": "1",
                    "amount_aed": "100",
                    "taxable_amount": "100",
                    "tax_amount": "5",
                    "tax_rate": "5",
                    "customs_amount": "0",
                    "customs_rate": "0",
                    "payment_method": "cash",
                    "payment_status": "pending",
                    "approval_status": "pending",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_add_advanced_expense_get(self, advanced_ledger_client):
        with _advanced_ledger_patches(categories=[MagicMock(id=1)]):
            with patch("models.Supplier.query") as sup_q:
                sup_q.filter_by.return_value.with_entities.return_value.all.return_value = []
                resp = advanced_ledger_client.get("/ledger/advanced/advanced-expenses/add")
        assert resp.status_code == 200

    def test_journal_management(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/journal-management")
        assert resp.status_code == 200

    def test_cheque_integration(self, advanced_ledger_client):
        with _advanced_ledger_patches(cheques=[MagicMock()], total_cheques=3, cheque_count=1):
            resp = advanced_ledger_client.get("/ledger/advanced/cheque-integration")
        assert resp.status_code == 200

    def test_real_time_events(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/real-time-events")
        assert resp.status_code == 200

    def test_professional_reports(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/professional-reports")
        assert resp.status_code == 200

    def test_advanced_analytics(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/advanced-analytics")
        assert resp.status_code == 200


class TestAdvancedLedgerActions:
    def test_reverse_journal_entry(self, advanced_ledger_client):
        reversal = MagicMock(entry_number="REV-001")
        with (
            _advanced_ledger_patches(),
            patch(
                "routes.advanced_ledger.AdvancedJournalEntryManager.reverse_entry_advanced",
                return_value=reversal,
            ),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/journal-management/5/reverse", data={"reason": "fix"})
        assert resp.status_code == 302

    def test_reverse_journal_entry_error(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch(
                "routes.advanced_ledger.AdvancedJournalEntryManager.reverse_entry_advanced",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "utils.error_messages.ErrorMessages.unexpected_error",
                return_value="error",
            ),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/journal-management/5/reverse")
        assert resp.status_code == 302

    def test_delete_journal_entry_error(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch(
                "routes.advanced_ledger.AdvancedJournalEntryManager.delete_entry",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "utils.error_messages.ErrorMessages.unexpected_error",
                return_value="err",
            ),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/journal-management/3/delete")
        assert resp.status_code == 302

    def test_delete_journal_entry(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch("routes.advanced_ledger.AdvancedJournalEntryManager.delete_entry"),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/journal-management/3/delete")
        assert resp.status_code == 302

    def test_approve_journal_entry(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch("routes.advanced_ledger.AdvancedJournalEntryManager.approve_entry"),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/journal-management/2/approve")
        assert resp.status_code == 302

    def test_receive_cheque(self, advanced_ledger_client):
        entry = MagicMock(entry_number="JE-R")
        with (
            _advanced_ledger_patches(),
            patch(
                "routes.advanced_ledger.ChequeAccountingIntegration.receive_cheque",
                return_value=entry,
            ),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/cheque-integration/1/receive")
        assert resp.status_code == 302

    def test_clear_cheque(self, advanced_ledger_client):
        entry = MagicMock(entry_number="JE-C")
        with (
            _advanced_ledger_patches(),
            patch(
                "routes.advanced_ledger.ChequeAccountingIntegration.clear_cheque",
                return_value=entry,
            ),
        ):
            resp = advanced_ledger_client.post(
                "/ledger/advanced/cheque-integration/1/clear",
                data={
                    "bank_charges": "5",
                    "exchange_gain_loss": "0",
                },
            )
        assert resp.status_code == 302

    def test_approve_journal_entry_error(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch(
                "routes.advanced_ledger.AdvancedJournalEntryManager.approve_entry",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "utils.error_messages.ErrorMessages.unexpected_error",
                return_value="err",
            ),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/journal-management/2/approve")
        assert resp.status_code == 302

    def test_receive_cheque_error(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch(
                "routes.advanced_ledger.ChequeAccountingIntegration.receive_cheque",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "utils.error_messages.ErrorMessages.unexpected_error",
                return_value="err",
            ),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/cheque-integration/1/receive")
        assert resp.status_code == 302

    def test_clear_cheque_error(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch(
                "routes.advanced_ledger.ChequeAccountingIntegration.clear_cheque",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "utils.error_messages.ErrorMessages.unexpected_error",
                return_value="err",
            ),
        ):
            resp = advanced_ledger_client.post("/ledger/advanced/cheque-integration/1/clear")
        assert resp.status_code == 302


class TestAdvancedLedgerAPI:
    def test_events_stream_api(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/api/events/stream?limit=10")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["total"] >= 1

    def test_events_stream_by_type(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/api/events/stream?type=sale")
        assert resp.get_json()["success"] is True

    def test_cheque_accounting_summary_api(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch("routes.advanced_ledger.tenant_get_or_404", return_value=MagicMock(id=9)),
        ):
            resp = advanced_ledger_client.get("/ledger/advanced/api/cheque/9/accounting-summary")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_cheque_summary_api_cross_tenant_blocked(self, advanced_ledger_client):
        """A cheque outside the active tenant must 404 — never leak summary data."""
        from werkzeug.exceptions import NotFound

        with (
            _advanced_ledger_patches(),
            patch("routes.advanced_ledger.tenant_get_or_404", side_effect=NotFound()),
        ):
            resp = advanced_ledger_client.get("/ledger/advanced/api/cheque/9/accounting-summary")
        assert resp.status_code == 404

    def test_cheque_summary_api_error(self, advanced_ledger_client):
        with (
            _advanced_ledger_patches(),
            patch("routes.advanced_ledger.tenant_get_or_404", return_value=MagicMock(id=9)),
            patch(
                "routes.advanced_ledger.ChequeAccountingIntegration.get_cheque_accounting_summary",
                side_effect=ValueError("missing"),
            ),
        ):
            resp = advanced_ledger_client.get("/ledger/advanced/api/cheque/9/accounting-summary")
        assert resp.status_code == 400

    def test_api_financial_ratios(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get(
                "/ledger/advanced/api/financial-ratios?date_from=2026-01-01&date_to=2026-06-01"
            )
        assert resp.get_json()["ratios"]["current_ratio"] == 1.5

    def test_api_trend_analysis(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/api/trend-analysis?months=6")
        assert len(resp.get_json()["trends"]) == 1

    def test_api_forecasting(self, advanced_ledger_client):
        with _advanced_ledger_patches():
            resp = advanced_ledger_client.get("/ledger/advanced/api/forecasting?months=3")
        assert resp.get_json()["success"] is True
