"""Tests for action_dispatcher — parsing, permissions, security helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ai_knowledge.action_dispatcher import (
    ActionDispatcher,
    ActionResult,
    _audit,
    _escape_ilike,
    _get_active_tenant_id,
    _has_permission,
    _is_owner,
    _log_ai_error,
    action_dispatcher,
)


class TestHelpers:
    def test_escape_ilike(self):
        assert _escape_ilike("a%b_c") == r"a\%b\_c"

    def test_get_active_tenant_from_g(self, app):
        with app.app_context():
            from flask import g

            g.active_tenant_id = 99
            assert _get_active_tenant_id() == 99

    def test_get_active_tenant_from_user(self):
        with patch(
            "ai_knowledge.action_dispatcher.current_user",
            SimpleNamespace(is_authenticated=True, tenant_id=5),
        ):
            assert _get_active_tenant_id() == 5

    def test_has_permission_true(self):
        user = SimpleNamespace(is_authenticated=True, has_permission=MagicMock(return_value=True))
        with patch("ai_knowledge.action_dispatcher.current_user", user):
            assert _has_permission("manage_sales") is True

    def test_has_permission_failure_returns_false(self):
        user = MagicMock(is_authenticated=True)
        user.has_permission.side_effect = RuntimeError("x")
        with patch("ai_knowledge.action_dispatcher.current_user", user):
            assert _has_permission("manage_sales") is False

    def test_is_owner(self):
        user = SimpleNamespace(is_owner=True)
        with (
            patch("ai_knowledge.action_dispatcher.current_user", user),
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=False),
        ):
            assert _is_owner() is True

    def test_audit_logs_warning_on_failure(self):
        with patch(
            "ai_knowledge.action_dispatcher.LoggingCore.log_audit",
            side_effect=RuntimeError(),
        ):
            _audit("create", "Customer", 1, {"name": "x"})

    def test_log_ai_error_rollback(self):
        with (
            patch("ai_knowledge.action_dispatcher.db.session"),
            patch("models.ErrorAuditLog", side_effect=RuntimeError()),
        ):
            _log_ai_error("test", "boom")


class TestActionResult:
    def test_to_dict(self):
        r = ActionResult(True, "ok", {"id": 1}, "create_customer", "manage_customers")
        d = r.to_dict()
        assert d["success"] is True
        assert d["message"] == "ok"


class TestParseChatAction:
    @pytest.fixture
    def dispatcher(self):
        return ActionDispatcher()

    def test_create_customer(self, dispatcher):
        parsed = dispatcher.parse_chat_action("عميل: أحمد, 0501234567, دبي")
        assert parsed[0] == "create_customer"
        assert parsed[1]["name"] == "أحمد"

    def test_customer_balance(self, dispatcher):
        parsed = dispatcher.parse_chat_action("رصيد: أحمد")
        assert parsed == ("customer_balance", {"name": "أحمد"})

    def test_list_customers(self, dispatcher):
        assert dispatcher.parse_chat_action("عرض العملاء")[0] == "list_customers"

    def test_create_product(self, dispatcher):
        parsed = dispatcher.parse_chat_action("product: Filter, 100, 5")
        assert parsed[0] == "create_product"

    def test_check_stock(self, dispatcher):
        assert dispatcher.parse_chat_action("فحص المخزون")[0] == "check_stock"

    def test_create_sale(self, dispatcher):
        parsed = dispatcher.parse_chat_action("فاتورة: عميل, منتج, 2")
        assert parsed[0] == "create_sale"
        assert parsed[1]["quantity"] == 2

    def test_receive_payment(self, dispatcher):
        parsed = dispatcher.parse_chat_action("استلام: عميل, 500")
        assert parsed[0] == "receive_payment"
        assert parsed[1]["amount"] == 500.0

    def test_add_expense(self, dispatcher):
        parsed = dispatcher.parse_chat_action("مصروف: وقود, 200")
        assert parsed[0] == "add_expense"

    def test_create_supplier(self, dispatcher):
        parsed = dispatcher.parse_chat_action("مورد: شركة, هاتف")
        assert parsed[0] == "create_supplier"

    def test_create_employee(self, dispatcher):
        parsed = dispatcher.parse_chat_action("موظف: علي, 050, 5000")
        assert parsed[0] == "create_employee"

    def test_create_purchase(self, dispatcher):
        parsed = dispatcher.parse_chat_action("شراء: مورد, منتج, 3")
        assert parsed[0] == "create_purchase"

    def test_profit_summary(self, dispatcher):
        assert dispatcher.parse_chat_action("تقرير الأرباح")[0] == "profit_summary"

    def test_greeting(self, dispatcher):
        with patch(
            "ai_knowledge.action_dispatcher.current_user",
            SimpleNamespace(full_name="Ali"),
        ):
            assert dispatcher.parse_chat_action("مرحبا")[0] == "greeting"

    def test_help(self, dispatcher):
        assert dispatcher.parse_chat_action("مساعدة")[0] == "help"

    def test_no_match(self, dispatcher):
        assert dispatcher.parse_chat_action("سؤال عام عن النظام") is None

    def test_format_help_nonempty(self, dispatcher):
        assert "الأوامر" in dispatcher.format_help()


class TestDispatch:
    def test_unknown_action(self):
        result = action_dispatcher.dispatch("not_real", {})
        assert result.success is False

    def test_permission_denied(self):
        with (
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=False),
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=False),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
        ):
            result = action_dispatcher.dispatch("create_customer", {"name": "x"})
            assert result.success is False
            assert result.needs_permission

    def test_create_customer_success(self, mock_ai_user):
        customer = MagicMock(id=10)
        with (
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("models.Customer") as Customer,
            patch("ai_knowledge.action_dispatcher.db.session"),
            patch("ai_knowledge.action_dispatcher._audit"),
        ):
            Customer.return_value = customer
            result = action_dispatcher.dispatch("create_customer", {"name": "Acme"})
            assert result.success is True

    def test_list_customers_search_escaped(self, mock_ai_user):
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value.limit.return_value.all.return_value = []
        with (
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("models.Customer") as Customer,
        ):
            Customer.query = mock_q
            Customer.name = MagicMock()
            result = action_dispatcher.dispatch("list_customers", {"search": "%_drop"})
            assert result.success is True
            mock_q.filter.assert_called_once()

    def test_registered_actions_nonempty(self):
        assert "create_customer" in action_dispatcher.get_registered_actions()
