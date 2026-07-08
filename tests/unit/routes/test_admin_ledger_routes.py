from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


def _mock_account(code="1101", balance=Decimal("2000"), **kwargs):
    account = MagicMock()
    account.id = kwargs.get("id", 1)
    account.code = code
    account.full_name = kwargs.get("full_name", f"Account {code}")
    account.type = kwargs.get("type", "asset")
    account.level = kwargs.get("level", 0)
    account.parent_id = kwargs.get("parent_id")
    account.get_balance = MagicMock(return_value=balance)
    return account


def _accounts_query(**cfg):
    cash_accounts = cfg.get("cash_accounts", [_mock_account(code="1101", balance=Decimal("3000"))])
    balance_accounts = cfg.get(
        "balance_accounts",
        [
            _mock_account(code="1201", balance=Decimal("5000")),
            _mock_account(code="1202", balance=Decimal("50")),
        ],
    )
    all_accounts = cfg.get("all_accounts", balance_accounts)
    duplicate = cfg.get("duplicate")
    edit_account = cfg.get("edit_account")
    child_account = cfg.get("child_account")
    parent_account = cfg.get("parent_account")

    q = MagicMock(name="accounts_query")

    def filter_by(**kwargs):
        inner = MagicMock()
        if kwargs == {"is_active": True}:
            inner.count.return_value = cfg.get("active_count", 3)
        elif kwargs == {"is_active": True, "is_header": False}:
            inner.order_by.return_value.all.return_value = balance_accounts
            inner.limit.return_value.all.return_value = balance_accounts
        elif kwargs == {"is_header": True}:
            inner.order_by.return_value.all.return_value = cfg.get("parent_accounts", [])
        elif kwargs.get("code") and duplicate:
            inner.first.return_value = duplicate
        elif kwargs.get("id") is not None:
            if edit_account is None:
                inner.first_or_404.side_effect = NotFound()
            else:
                inner.first_or_404.return_value = edit_account
            inner.first.return_value = edit_account
        elif kwargs.get("parent_id") is not None:
            inner.first.return_value = child_account
        elif kwargs.get("parent_id") is not None and parent_account:
            inner.first.return_value = parent_account
        else:
            inner.first.return_value = None
            inner.first_or_404.side_effect = NotFound()
        return inner

    q.count.return_value = cfg.get("count", 5)
    q.filter_by.side_effect = filter_by
    q.filter.return_value.all.return_value = cash_accounts
    q.order_by.return_value.all.return_value = all_accounts
    return q


def _entries_query(**cfg):
    entry = cfg.get("entry")
    pag_items = cfg.get("pag_items", [])
    q = _chain_query(all=pag_items, count=len(pag_items))

    def filter_by(**kwargs):
        inner = MagicMock()
        if kwargs.get("id") is not None:
            if entry is None:
                inner.first_or_404.side_effect = NotFound()
            else:
                inner.first_or_404.return_value = entry
        else:
            inner.count.return_value = cfg.get("posted_count", 2)
        return inner

    q.count.return_value = cfg.get("count", 4)
    q.filter_by.side_effect = filter_by
    q.order_by.return_value.limit.return_value.all.return_value = cfg.get("recent", [])
    return q


def _cheques_query(**cfg):
    q = MagicMock(name="cheques_query")

    def filter_by(**kwargs):
        inner = MagicMock()
        if kwargs.get("status") == "pending":
            inner.count.return_value = cfg.get("pending", 1)
        elif kwargs.get("status") == "cleared":
            inner.count.return_value = cfg.get("cleared", 2)
        return inner

    q.count.return_value = cfg.get("count", 3)
    q.filter_by.side_effect = filter_by
    return q


def _vaults_query(**cfg):
    q = MagicMock(name="vaults_query")
    q.count.return_value = cfg.get("count", 2)
    locked = MagicMock()
    locked.count.return_value = cfg.get("active", 1)
    q.filter_by.return_value = locked
    q.all.return_value = cfg.get("all", [])
    return q


@contextmanager
def _ledger_patches(
    accounts_query=None,
    entries_query=None,
    cheques_query=None,
    vaults_query=None,
    journal_lines_first=None,
    statement=None,
):
    accounts_query = accounts_query or _accounts_query()
    entries_query = entries_query or _entries_query()
    cheques_query = cheques_query or _cheques_query()
    vaults_query = vaults_query or _vaults_query()
    lines_q = MagicMock()
    lines_q.filter_by.return_value.first.return_value = journal_lines_first

    with patch("routes.admin_ledger.gl_account_query", return_value=accounts_query), \
         patch("routes.admin_ledger.gl_entry_query", return_value=entries_query), \
         patch("routes.admin_ledger.tenant_query", return_value=cheques_query), \
         patch("routes.admin_ledger.scoped_model_query", return_value=lines_q), \
         patch("routes.admin_ledger.render_template", return_value="ok") as render, \
         patch("routes.admin_ledger.db.session") as session, \
         patch("routes.admin_ledger.LoggingCore.log_audit") as log_audit, \
         patch("routes.admin_ledger.GLService.get_account_statement", return_value=statement or []), \
         patch("routes.admin_ledger.GLService.get_all_account_balances", return_value={}), \
         patch("routes.admin_ledger._vaults", return_value=vaults_query):
        yield {
            "render": render,
            "session": session,
            "log_audit": log_audit,
            "accounts_query": accounts_query,
            "entries_query": entries_query,
            "lines_q": lines_q,
        }


@pytest.fixture
def ledger_client(app_factory, bypass_admin_auth):
    from routes.admin_ledger import admin_ledger_bp

    app = app_factory(admin_ledger_bp)
    return app.test_client()


class TestAdminLedgerAuth:
    def test_dashboard_unauthenticated(self, ledger_client):
        with unauthenticated_client(ledger_client):
            resp = ledger_client.get("/admin/ledger/")
        assert resp.status_code in (302, 401)

    def test_dashboard_non_admin_forbidden(self, ledger_client):
        with patch("utils.decorators.is_admin_surface_user", return_value=False):
            resp = ledger_client.get("/admin/ledger/")
        assert resp.status_code == 403


class TestAdminLedgerDashboard:
    def test_dashboard_renders_with_balances(self, ledger_client):
        with _ledger_patches() as mocks:
            resp = ledger_client.get("/admin/ledger/")
        assert resp.status_code == 200
        assert mocks["render"].called
        kwargs = mocks["render"].call_args[1]
        assert kwargs["total_cash"] == Decimal("3000")
        assert len(kwargs["high_balance_accounts"]) == 1
        assert kwargs["high_balance_accounts"][0]["balance"] == Decimal("5000")


class TestAdminLedgerAccounts:
    def test_accounts_management(self, ledger_client):
        accounts = [_mock_account(code="1000")]
        q = _accounts_query(all_accounts=accounts)
        with _ledger_patches(accounts_query=q) as mocks:
            resp = ledger_client.get("/admin/ledger/accounts")
        assert resp.status_code == 200
        assert mocks["render"].call_args[0][0] == "admin/ledger/accounts.html"

    def test_add_account_get(self, ledger_client):
        with _ledger_patches() as mocks:
            resp = ledger_client.get("/admin/ledger/accounts/add")
        assert resp.status_code == 200
        assert mocks["render"].call_args[0][0] == "admin/ledger/add_account.html"

    def test_add_account_post_missing_type(self, ledger_client):
        with _ledger_patches() as mocks:
            resp = ledger_client.post(
                "/admin/ledger/accounts/add",
                data={"code": "9999", "name": "Test"},
            )
        assert resp.status_code == 200
        assert mocks["render"].call_args[0][0] == "admin/ledger/add_account.html"
        mocks["session"].add.assert_not_called()

    def test_add_account_post_duplicate_code(self, ledger_client):
        duplicate = _mock_account(code="1001")
        q = _accounts_query(duplicate=duplicate)
        with _ledger_patches(accounts_query=q) as mocks:
            resp = ledger_client.post(
                "/admin/ledger/accounts/add",
                data={"code": "1001", "name": "Dup", "type": "asset"},
            )
        assert resp.status_code == 200
        mocks["session"].add.assert_not_called()

    def test_add_account_post_success(self, ledger_client):
        with _ledger_patches() as mocks, \
             patch("routes.admin_ledger.active_tenant_id", return_value=1), \
             patch("routes.admin_ledger.resolve_default_currency", return_value="AED"), \
             patch("routes.admin_ledger.GLAccount") as gl_cls:
            gl_cls.return_value.id = 99
            gl_cls.return_value.full_name = "New Account"
            resp = ledger_client.post(
                "/admin/ledger/accounts/add",
                data={"code": "2001", "name": "New", "type": "asset", "is_active": "on"},
            )
        assert resp.status_code == 302
        mocks["session"].add.assert_called_once()
        mocks["session"].commit.assert_called()
        mocks["log_audit"].assert_called_with("create", "gl_accounts", 99)

    def test_add_account_post_exception(self, ledger_client):
        with _ledger_patches() as mocks, \
             patch("routes.admin_ledger.active_tenant_id", return_value=1), \
             patch("routes.admin_ledger.resolve_default_currency", return_value="AED"), \
             patch("routes.admin_ledger.GLAccount"), \
             patch("utils.error_messages.ErrorMessages.unexpected_error", return_value="unexpected"):
            mocks["session"].commit.side_effect = RuntimeError("db fail")
            resp = ledger_client.post(
                "/admin/ledger/accounts/add",
                data={"code": "2002", "name": "Fail", "type": "asset"},
            )
        assert resp.status_code == 200
        mocks["session"].rollback.assert_called()

    def test_edit_account_get(self, ledger_client):
        account = _mock_account(code="3001", id=7)
        q = _accounts_query(edit_account=account)
        with _ledger_patches(accounts_query=q) as mocks:
            resp = ledger_client.get("/admin/ledger/accounts/7/edit")
        assert resp.status_code == 200
        assert mocks["render"].call_args[1]["account"] is account

    def test_edit_account_post_success(self, ledger_client):
        account = _mock_account(code="3001", id=7)
        q = _accounts_query(edit_account=account)
        with _ledger_patches(accounts_query=q) as mocks, \
             patch("routes.admin_ledger.resolve_default_currency", return_value="AED"):
            resp = ledger_client.post(
                "/admin/ledger/accounts/7/edit",
                data={"code": "3001", "name": "Updated", "type": "asset", "is_active": "on"},
            )
        assert resp.status_code == 302
        mocks["session"].commit.assert_called()
        mocks["log_audit"].assert_called_with("update", "gl_accounts", 7)

    def test_delete_account_blocked_by_entries(self, ledger_client):
        account = _mock_account(id=8)
        q = _accounts_query(edit_account=account)
        with _ledger_patches(accounts_query=q, journal_lines_first=MagicMock()):
            resp = ledger_client.post("/admin/ledger/accounts/8/delete")
        assert resp.status_code == 302
        assert "accounts" in resp.location

    def test_delete_account_blocked_by_children(self, ledger_client):
        account = _mock_account(id=9)
        child = _mock_account(id=10)
        q = _accounts_query(edit_account=account, child_account=child)
        with _ledger_patches(accounts_query=q, journal_lines_first=None):
            resp = ledger_client.post("/admin/ledger/accounts/9/delete")
        assert resp.status_code == 302

    def test_delete_account_success(self, ledger_client):
        account = _mock_account(id=11)
        q = _accounts_query(edit_account=account)
        with _ledger_patches(accounts_query=q, journal_lines_first=None) as mocks:
            resp = ledger_client.post("/admin/ledger/accounts/11/delete")
        assert resp.status_code == 302
        mocks["session"].delete.assert_called_with(account)
        mocks["log_audit"].assert_called_with("delete", "gl_accounts", 11)


class TestAdminLedgerVaultsAndJournals:
    def test_vaults_management(self, ledger_client):
        vaults = [MagicMock()]
        with _ledger_patches(vaults_query=_vaults_query(all=vaults)) as mocks:
            resp = ledger_client.get("/admin/ledger/vaults")
        assert resp.status_code == 200
        assert mocks["render"].call_args[1]["vaults"] == vaults

    def test_journals_paginate(self, ledger_client):
        entry = MagicMock()
        q = _entries_query(pag_items=[entry])
        with _ledger_patches(entries_query=q) as mocks:
            resp = ledger_client.get("/admin/ledger/journals?page=2")
        assert resp.status_code == 200
        assert mocks["render"].call_args[1]["entries"].items == [entry]

    def test_view_journal(self, ledger_client):
        entry = MagicMock()
        q = _entries_query(entry=entry)
        with _ledger_patches(entries_query=q) as mocks:
            resp = ledger_client.get("/admin/ledger/journals/5/view")
        assert resp.status_code == 200
        assert mocks["render"].call_args[1]["entry"] is entry

    def test_reverse_journal_success(self, ledger_client):
        entry = MagicMock()
        entry.entry_number = "JE-001"
        entry.reverse_entry.return_value = MagicMock()
        q = _entries_query(entry=entry)
        with _ledger_patches(entries_query=q) as mocks:
            resp = ledger_client.post("/admin/ledger/journals/5/reverse")
        assert resp.status_code == 302
        entry.reverse_entry.assert_called_once()
        mocks["log_audit"].assert_called_with("reverse", "gl_journal_entries", 5)


class TestAdminLedgerReports:
    def test_reports_index(self, ledger_client):
        with _ledger_patches() as mocks:
            resp = ledger_client.get("/admin/ledger/reports")
        assert resp.status_code == 200
        assert mocks["render"].call_args[0][0] == "admin/ledger/reports.html"

    def test_trial_balance_invalid_dates_fallback(self, ledger_client):
        acct = _mock_account(code="4001", balance=Decimal("100"))
        q = _accounts_query(balance_accounts=[acct])
        with _ledger_patches(accounts_query=q) as mocks:
            resp = ledger_client.get(
                "/admin/ledger/reports/trial-balance",
                query_string={"date_from": "bad", "date_to": "also-bad"},
            )
        assert resp.status_code == 200
        kwargs = mocks["render"].call_args[1]
        assert kwargs["date_from"] == date.today()
        assert kwargs["date_to"] == date.today()

    def test_balance_sheet(self, ledger_client):
        assets = [_mock_account(code="1000", type="asset", balance=Decimal("1000"))]
        liabilities = [_mock_account(code="2000", type="liability", balance=Decimal("-500"))]
        equity = [_mock_account(code="3000", type="equity", balance=Decimal("-500"))]

        def filter_by(**kwargs):
            inner = MagicMock()
            t = kwargs.get("type")
            if t == "asset":
                inner.order_by.return_value.all.return_value = assets
            elif t == "liability":
                inner.order_by.return_value.all.return_value = liabilities
            elif t == "equity":
                inner.order_by.return_value.all.return_value = equity
            return inner

        q = MagicMock()
        q.filter_by.side_effect = filter_by
        with _ledger_patches(accounts_query=q) as mocks, \
             patch("routes.admin_ledger.GLService.get_all_account_balances", return_value={1: Decimal("1000")}):
            resp = ledger_client.get("/admin/ledger/reports/balance-sheet")
        assert resp.status_code == 200
        kwargs = mocks["render"].call_args[1]
        assert kwargs["assets_total"] == Decimal("1000")

    def test_income_statement(self, ledger_client):
        revenues = [_mock_account(code="4100", type="revenue", balance=Decimal("-800"))]
        expenses = [_mock_account(code="5100", type="expense", balance=Decimal("300"))]

        def filter_by(**kwargs):
            inner = MagicMock()
            if kwargs.get("type") == "revenue":
                inner.order_by.return_value.all.return_value = revenues
            elif kwargs.get("type") == "expense":
                inner.order_by.return_value.all.return_value = expenses
            return inner

        q = MagicMock()
        q.filter_by.side_effect = filter_by
        with _ledger_patches(accounts_query=q) as mocks:
            resp = ledger_client.get("/admin/ledger/reports/income-statement")
        assert resp.status_code == 200
        assert mocks["render"].call_args[1]["net_income"] == Decimal("500")

    def test_settings(self, ledger_client):
        with _ledger_patches() as mocks:
            resp = ledger_client.get("/admin/ledger/settings")
        assert resp.status_code == 200
        assert mocks["render"].call_args[0][0] == "admin/ledger/settings.html"


class TestAdminLedgerApi:
    def test_api_account_balance(self, ledger_client):
        account = _mock_account(code="1105", balance=Decimal("1234.56"), id=15)
        q = _accounts_query(edit_account=account)
        with _ledger_patches(accounts_query=q):
            resp = ledger_client.get("/admin/ledger/api/account-balance/15")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["account_code"] == "1105"
        assert data["balance"] == 1234.56

    def test_api_account_statement(self, ledger_client):
        account = _mock_account(code="1106", id=16)
        statement = [{"debit": 100, "credit": 0}]
        q = _accounts_query(edit_account=account)
        with _ledger_patches(accounts_query=q, statement=statement):
            resp = ledger_client.get(
                "/admin/ledger/api/account-statement/16",
                query_string={"date_from": "2025-01-01", "branch_id": 2},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["statement"] == statement
        assert data["branch_id"] == 2


class TestAdminLedgerCoverageGaps:
    def test_vaults_helper_calls_scoped_query(self):
        vault_q = MagicMock()
        with patch("routes.admin_ledger.scoped_model_query", return_value=vault_q) as smq:
            from routes.admin_ledger import _vaults
            assert _vaults() is vault_q
        smq.assert_called_once()

    def test_add_account_currency_fallback(self, ledger_client):
        with _ledger_patches() as mocks, \
             patch("routes.admin_ledger.active_tenant_id", return_value=1), \
             patch("routes.admin_ledger.resolve_default_currency", side_effect=RuntimeError("no tenant")), \
             patch("routes.admin_ledger.get_system_default_currency", return_value="USD"), \
             patch("routes.admin_ledger.GLAccount") as gl_cls:
            gl_cls.return_value.id = 50
            gl_cls.return_value.full_name = "USD Account"
            resp = ledger_client.post(
                "/admin/ledger/accounts/add",
                data={"code": "2100", "name": "USD", "type": "asset", "currency": "USD"},
            )
        assert resp.status_code == 302
        mocks["session"].add.assert_called_once()

    def test_add_account_with_parent_level(self, ledger_client):
        parent = _mock_account(id=5, level=2)
        q = _accounts_query()
        orig_filter_by = q.filter_by.side_effect

        def filter_by(**kwargs):
            if kwargs.get("id") == 5:
                inner = MagicMock()
                inner.first.return_value = parent
                return inner
            return orig_filter_by(**kwargs)

        q.filter_by.side_effect = filter_by
        with _ledger_patches(accounts_query=q), \
             patch("routes.admin_ledger.active_tenant_id", return_value=1), \
             patch("routes.admin_ledger.resolve_default_currency", return_value="AED"), \
             patch("routes.admin_ledger.GLAccount") as gl_cls:
            gl_cls.return_value.id = 51
            gl_cls.return_value.full_name = "Child"
            resp = ledger_client.post(
                "/admin/ledger/accounts/add",
                data={"code": "2101", "name": "Child", "type": "asset", "parent_id": "5"},
            )
        assert resp.status_code == 302
        assert gl_cls.call_args[1]["level"] == 3

    def test_edit_account_currency_fallback_and_parent(self, ledger_client):
        account = _mock_account(code="3100", id=12, parent_id=5)
        parent = _mock_account(id=5, level=1)
        q = _accounts_query(edit_account=account)
        orig_filter_by = q.filter_by.side_effect

        def filter_by(**kwargs):
            pid = kwargs.get("id")
            if pid in (5, "5"):
                inner = MagicMock()
                inner.first.return_value = parent
                return inner
            return orig_filter_by(**kwargs)

        q.filter_by.side_effect = filter_by
        account.parent_id = None
        with _ledger_patches(accounts_query=q), \
             patch("routes.admin_ledger.resolve_default_currency", side_effect=RuntimeError("fail")), \
             patch("routes.admin_ledger.get_system_default_currency", return_value="AED"):
            resp = ledger_client.post(
                "/admin/ledger/accounts/12/edit",
                data={"code": "3100", "name": "Edited", "type": "asset", "parent_id": "5", "is_active": "on"},
            )
        assert resp.status_code == 302
        assert account.level == parent.level + 1

    def test_edit_account_exception(self, ledger_client):
        account = _mock_account(code="3101", id=13)
        q = _accounts_query(edit_account=account)
        with _ledger_patches(accounts_query=q) as mocks, \
             patch("routes.admin_ledger.resolve_default_currency", return_value="AED"), \
             patch("utils.error_messages.ErrorMessages.unexpected_error", return_value="err"):
            mocks["session"].commit.side_effect = RuntimeError("db")
            resp = ledger_client.post(
                "/admin/ledger/accounts/13/edit",
                data={"code": "3101", "name": "Fail", "type": "asset"},
            )
        assert resp.status_code == 200
        mocks["session"].rollback.assert_called()

    def test_delete_account_exception(self, ledger_client):
        account = _mock_account(id=14)
        q = _accounts_query(edit_account=account)
        with _ledger_patches(accounts_query=q, journal_lines_first=None) as mocks:
            mocks["session"].commit.side_effect = RuntimeError("delete fail")
            resp = ledger_client.post("/admin/ledger/accounts/14/delete")
        assert resp.status_code == 302
        mocks["session"].rollback.assert_called()

    def test_reverse_journal_exception(self, ledger_client):
        entry = MagicMock()
        entry.entry_number = "JE-ERR"
        entry.reverse_entry.side_effect = RuntimeError("cannot reverse")
        q = _entries_query(entry=entry)
        with _ledger_patches(entries_query=q) as mocks:
            resp = ledger_client.post("/admin/ledger/journals/6/reverse")
        assert resp.status_code == 302
        mocks["session"].rollback.assert_called()

    def test_trial_balance_valid_dates(self, ledger_client):
        acct = _mock_account(code="4002", balance=Decimal("200"))
        q = _accounts_query(balance_accounts=[acct])
        with _ledger_patches(accounts_query=q) as mocks:
            resp = ledger_client.get(
                "/admin/ledger/reports/trial-balance",
                query_string={"date_from": "2025-01-01", "date_to": "2025-06-01"},
            )
        assert resp.status_code == 200
        kwargs = mocks["render"].call_args[1]
        assert kwargs["date_from"] == date(2025, 1, 1)
        assert kwargs["date_to"] == date(2025, 6, 1)

    def test_balance_sheet_invalid_date(self, ledger_client):
        assets = [_mock_account(code="1000", type="asset", balance=Decimal("0"))]
        q = MagicMock()
        q.filter_by.return_value.order_by.return_value.all.return_value = assets
        with _ledger_patches(accounts_query=q) as mocks:
            resp = ledger_client.get(
                "/admin/ledger/reports/balance-sheet",
                query_string={"as_of_date": "not-a-date"},
            )
        assert resp.status_code == 200
        assert mocks["render"].call_args[1]["as_of_date"] == date.today()

    def test_income_statement_invalid_dates(self, ledger_client):
        revenues = [_mock_account(code="4100", type="revenue", balance=Decimal("0"))]
        expenses = [_mock_account(code="5100", type="expense", balance=Decimal("0"))]
        q = MagicMock()

        def filter_by(**kwargs):
            inner = MagicMock()
            if kwargs.get("type") == "revenue":
                inner.order_by.return_value.all.return_value = revenues
            elif kwargs.get("type") == "expense":
                inner.order_by.return_value.all.return_value = expenses
            return inner

        q.filter_by.side_effect = filter_by
        with _ledger_patches(accounts_query=q) as mocks:
            resp = ledger_client.get(
                "/admin/ledger/reports/income-statement",
                query_string={"date_from": "x", "date_to": "y"},
            )
        assert resp.status_code == 200
        kwargs = mocks["render"].call_args[1]
        assert kwargs["date_from"] == date.today() - __import__("datetime").timedelta(days=30)
        assert kwargs["date_to"] == date.today()
