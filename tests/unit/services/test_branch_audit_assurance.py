"""Branch audit service — liquidity account provisioning on branch events."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest


class TestEnsureBranchLiquidityAccount:
    def test_skips_when_parent_missing(self):
        from services.branch_audit_service import ensure_branch_liquidity_account

        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        branch = MagicMock(id=3, tenant_id=1, name="Branch A")
        ensure_branch_liquidity_account(conn, branch, "1110", "cash", "Cashbox", "صندوق")
        assert conn.execute.call_count == 1

    def test_updates_existing_liquidity_account(self):
        from services.branch_audit_service import ensure_branch_liquidity_account

        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [(10,), (55,)]
        branch = MagicMock(id=3, tenant_id=1, name="Branch A")
        ensure_branch_liquidity_account(conn, branch, "1110", "cash", "Cashbox", "صندوق")
        assert conn.execute.call_count == 3

    def test_inserts_new_liquidity_account(self):
        from services.branch_audit_service import ensure_branch_liquidity_account

        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [(10,), None]
        branch = MagicMock(id=4, tenant_id=2, name="Branch B")
        ensure_branch_liquidity_account(conn, branch, "1120", "bank", "Bank", "بنك")
        assert conn.execute.call_count == 3


def _capture_branch_handlers(mocker):
    handlers = []

    def capture(model, event):
        def decorator(fn):
            handlers.append(fn)
            return fn

        return decorator

    mocker.patch("sqlalchemy.event.listens_for", side_effect=capture)
    import services.branch_audit_service as bas

    importlib.reload(bas)
    bas.register_branch_event_listeners()
    return bas, handlers


class TestRegisterBranchEventListeners:
    def test_handler_skips_inactive_branch(self, mocker):
        bas, handlers = _capture_branch_handlers(mocker)
        ensure = mocker.patch.object(bas, "ensure_branch_liquidity_account")
        target = MagicMock(id=1, tenant_id=1, is_active=False)
        for handler in handlers:
            handler(None, MagicMock(), target)
        ensure.assert_not_called()

    def test_handler_provisions_cash_and_bank(self, mocker):
        bas, handlers = _capture_branch_handlers(mocker)
        ensure = mocker.patch.object(bas, "ensure_branch_liquidity_account")
        target = MagicMock(id=5, tenant_id=1, is_active=True, name="HQ")
        conn = MagicMock()
        for handler in handlers:
            handler(None, conn, target)
        assert ensure.call_count == len(handlers) * 2

    def test_handler_skips_falsy_branch_id(self, mocker):
        bas, handlers = _capture_branch_handlers(mocker)
        ensure = mocker.patch.object(bas, "ensure_branch_liquidity_account")
        target = MagicMock(id=0, tenant_id=1, is_active=True)
        for handler in handlers:
            handler(None, MagicMock(), target)
        ensure.assert_not_called()

    def test_handler_reraises_on_failure(self, mocker):
        bas, handlers = _capture_branch_handlers(mocker)
        assert handlers, "expected branch event handlers to be registered"
        err = mocker.patch.object(bas.logger, "error")
        mocker.patch.object(bas, "ensure_branch_liquidity_account", side_effect=RuntimeError("db fail"))
        target = MagicMock(id=6, tenant_id=1, is_active=True, name="HQ")
        with pytest.raises(RuntimeError, match="db fail"):
            handlers[0](None, MagicMock(), target)
        err.assert_called_once()
