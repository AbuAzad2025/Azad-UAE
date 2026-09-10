"""Coverage boost for routes/expenses.py.

Targets: lines 168, 248, 270, 347, 407 + arcs 115->117, 444->450, 478-480.
Real response paths via test client; services/DB mocked only at boundaries.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


def _mock_expense(**kwargs):
    exp = MagicMock()
    exp.id = kwargs.get("id", 1)
    exp.tenant_id = kwargs.get("tenant_id", 1)
    exp.branch_id = kwargs.get("branch_id", 1)
    exp.expense_number = kwargs.get("expense_number", "EXP-001")
    exp.status = kwargs.get("status", "confirmed")
    exp.amount = kwargs.get("amount", Decimal("100"))
    exp.currency = kwargs.get("currency", "AED")
    exp.category_id = kwargs.get("category_id", 1)
    exp.payment_method = kwargs.get("payment_method", "cash")
    exp.description = kwargs.get("description", "Office supplies")
    exp.expense_date = kwargs.get("expense_date", date(2026, 1, 15))
    exp.is_reversed = False
    category = kwargs.get("category")
    if category is None:
        category = MagicMock(gl_account_code="5100")
    exp.category = category
    return exp


def _mock_category(gl_code="5100"):
    cat = MagicMock()
    cat.id = 1
    cat.name = "Ops"
    cat.gl_account_code = gl_code
    return cat


def _chain_query(**terminals):
    q = MagicMock(name="query_chain")
    q.return_value = q
    for method in (
        "filter",
        "filter_by",
        "order_by",
        "join",
        "outerjoin",
        "group_by",
        "limit",
        "offset",
        "execution_options",
    ):
        getattr(q, method).return_value = q
    inner = q.filter.return_value
    inner.first.return_value = terminals.get("first")
    inner.scalar.return_value = terminals.get("scalar", 0)
    inner.all.return_value = terminals.get("all", [])
    inner.count.return_value = terminals.get("count", 0)
    pag = MagicMock(name="pagination")
    pag.items = terminals.get("all", [])
    pag.page = 1
    pag.per_page = 20
    pag.total = len(pag.items)
    pag.pages = 1
    q.order_by.return_value.paginate.return_value = pag
    q.paginate.return_value = pag
    return q


@contextmanager
def _expense_patches(expense=None, branch_scope=None):
    expense_q = _chain_query(all=[expense] if expense else [])
    cat_q = _chain_query(all=[_mock_category()])
    with ExitStack() as stack:
        stack.enter_context(patch("routes.expenses.render_template", return_value="ok"))
        stack.enter_context(
            patch(
                "routes.expenses.tenant_query",
                side_effect=lambda m: cat_q if getattr(m, "__name__", "") == "ExpenseCategory" else expense_q,
            )
        )
        stack.enter_context(patch("routes.expenses.get_active_tenant_id", return_value=1))
        stack.enter_context(patch("routes.expenses.require_active_tenant_id", return_value=1))
        stack.enter_context(patch("routes.expenses.tenant_get_or_404", return_value=expense))
        stack.enter_context(patch("routes.expenses.branch_scope_id", return_value=branch_scope))
        stack.enter_context(patch("routes.expenses.should_show_all_branch_columns", return_value=False))
        stack.enter_context(patch("routes.printing.branch_scope_id", return_value=branch_scope))
        stack.enter_context(patch("extensions.db.session"))
        stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
        stack.enter_context(patch("services.currency_service.CurrencyService.get_all_rates", return_value={}))
        stack.enter_context(
            patch("services.currency_service.CurrencyService.get_exchange_rate", return_value=Decimal("1"))
        )
        stack.enter_context(patch("routes.expenses.resolve_default_currency", return_value="AED"))
        stack.enter_context(patch("routes.expenses.generate_number", return_value="EXP-NEW"))
        stack.enter_context(patch("routes.expenses._resolve_transaction_rate", return_value=Decimal("1")))
        stack.enter_context(patch("routes.expenses.post_or_fail"))
        stack.enter_context(patch("routes.expenses.GLService.ensure_core_accounts"))
        stack.enter_context(patch("routes.expenses.GLService.get_payment_credit_account", return_value="1101"))
        stack.enter_context(patch("routes.expenses.GLService.get_payment_credit_concept", return_value="CASH"))
        stack.enter_context(patch("services.cheque_service.process_cheque_issue"))
        stack.enter_context(patch("extensions.limiter.limit", return_value=lambda f: f))
        stack.enter_context(patch("services.budget_enforcement.check_budget_for_account", return_value=None))
        stack.enter_context(patch("routes.expenses.convert_and_quantize_aed", return_value=Decimal("0")))
        stack.enter_context(patch("routes.printing.PrintService.get_document", return_value=expense))
        stack.enter_context(patch("routes.printing.PrintService.create_snapshot"))
        stack.enter_context(patch("routes.printing.PrintService.audit_print"))
        stack.enter_context(patch("routes.printing.PrintService.render_print", return_value="ok"))
        stack.enter_context(
            patch("routes.printing.PrintService.resolve_template", return_value="expenses/print_voucher.html")
        )
        stack.enter_context(patch("routes.printing.render_template", return_value="ok"))
        yield {"expense": expense}


@pytest.fixture
def expenses_cov2_client(app_factory, bypass_permission_auth):
    from routes.expenses import expenses_bp

    app = app_factory(expenses_bp)
    return app.test_client()


class TestCreateMissingAmount:
    """Line 168 (raise missing amount) -> line 270 (ValueError flash)."""

    def test_create_post_without_amount(self, expenses_cov2_client):
        with _expense_patches():
            resp = expenses_cov2_client.post(
                "/expenses/create",
                data={"category_id": "1", "payment_method": "cash"},
            )
        assert resp.status_code == 200


class TestCreateBudgetBlocked:
    """Line 248 (budget denied) -> line 270 (ValueError flash)."""

    def test_create_post_budget_denied(self, expenses_cov2_client):
        expense = MagicMock(
            id=20,
            expense_number="EXP-NEW",
            tenant_id=1,
            branch_id=1,
            payment_method="cash",
        )
        with (
            _expense_patches(),
            patch("routes.expenses.Expense", return_value=expense),
            patch("routes.expenses._build_expense_gl_lines", return_value=[]),
            patch(
                "services.budget_enforcement.check_budget_for_account",
                return_value={"allowed": False, "message": "over budget"},
            ),
        ):
            resp = expenses_cov2_client.post(
                "/expenses/create",
                data={"amount": "50", "category_id": "1", "payment_method": "cash"},
            )
        assert resp.status_code == 200


class TestEditMissingAmount:
    """Line 347 (raise missing amount in edit) -> line 407 (ValueError flash)."""

    def test_edit_post_without_amount(self, expenses_cov2_client):
        expense = _mock_expense()
        with (
            _expense_patches(expense=expense),
            patch(
                "services.expense_service.ExpenseService.is_expense_archived",
                return_value=False,
            ),
            patch("services.gl_helpers.assert_period_open"),
        ):
            resp = expenses_cov2_client.post(
                "/expenses/1/edit",
                data={"currency": "AED", "category_id": "1"},
            )
        assert resp.status_code == 200


class TestIndexNoTenant:
    """Arc 115->117: _tid is None so archived tenant filter is skipped."""

    def test_index_without_active_tenant(self, expenses_cov2_client):
        subq = MagicMock()
        select_chain = MagicMock()
        select_chain.filter.return_value.scalar_subquery.return_value = subq
        with (
            _expense_patches(expense=_mock_expense()),
            patch("sqlalchemy.select", return_value=select_chain),
            patch("utils.tenanting.get_active_tenant_id", return_value=None),
        ):
            resp = expenses_cov2_client.get("/expenses/")
        assert resp.status_code == 200


class TestDeleteWithLinksNoChequeArchive:
    """Arc 444->450: has_links True but cheque falsy at second check."""

    def test_delete_skips_cheque_archive(self, expenses_cov2_client):
        expense = _mock_expense()
        cheque = MagicMock(status="cleared")
        # First bool() True (has_links check), second bool() False (archive check).
        cheque.__bool__.side_effect = [True, False]
        archive_svc = MagicMock()
        with (
            _expense_patches(expense=expense),
            patch(
                "services.expense_service.ExpenseService.get_expense_cheque",
                return_value=cheque,
            ),
            patch("services.archive_service.ArchiveService", return_value=archive_svc),
        ):
            resp = expenses_cov2_client.post("/expenses/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        archive_svc.archive_record.assert_called_once()


class TestDeleteException:
    """Lines 478-480: archive failure flashes and redirects to view."""

    def test_delete_archive_failure_redirects_to_view(self, expenses_cov2_client):
        expense = _mock_expense()
        with (
            _expense_patches(expense=expense),
            patch(
                "services.expense_service.ExpenseService.get_expense_cheque",
                return_value=None,
            ),
            patch(
                "services.archive_service.ArchiveService.archive_record",
                side_effect=RuntimeError("archive down"),
            ),
        ):
            resp = expenses_cov2_client.post("/expenses/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert "/expenses/1" in resp.headers["Location"]
