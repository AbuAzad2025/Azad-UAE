"""RBAC unit tests for the central AI tool registry (Dual-Layer Zero-Trust)."""

from types import SimpleNamespace

from ai_knowledge.tool_registry import (
    _STANDALONE_TOOLS,
    get_permitted_tool_names,
    get_tool_registry,
    get_tools_for_user,
    register_ai_tool,
    user_can_use_tool,
)


def _user(perms=(), owner=False, authenticated=True):
    return SimpleNamespace(
        is_authenticated=authenticated,
        is_owner=owner,
        has_permission=lambda p: p in perms,
    )


ALL_PERMS = {
    "manage_customers",
    "manage_products",
    "manage_warehouse",
    "manage_sales",
    "manage_payments",
    "manage_expenses",
    "manage_suppliers",
    "manage_purchases",
    "manage_employees",
    "manage_users",
    "view_reports",
}


class TestRegistryCompleteness:
    def test_registry_bridges_all_dispatcher_actions(self):
        from ai_knowledge.action_dispatcher import action_dispatcher

        registry = get_tool_registry()
        assert set(action_dispatcher.get_registered_actions()) <= set(registry.keys())
        # Core directive-mapped operations present
        for name in (
            "create_sale",
            "list_sales",
            "cancel_sale",
            "create_purchase",
            "transfer_stock",
            "check_stock",
            "create_customer",
            "create_supplier",
            "customer_balance",
            "add_expense",
            "profit_summary",
        ):
            assert name in registry, name

    def test_every_tool_has_schema_and_description(self):
        for name, meta in get_tool_registry().items():
            assert meta["schema"] is not None, name
            assert meta["description"], name


class TestLayer1PreLLMFiltering:
    def test_owner_gets_all_tools(self):
        tools = get_tools_for_user(_user(owner=True))
        names = {t["function"]["name"] for t in tools}
        assert names == {m["name"] for m in get_tool_registry().values() if m["schema"] is not None}

    def test_cashier_gets_only_permitted_tools(self):
        cashier = _user(perms={"manage_sales", "manage_warehouse"})
        names = set(get_permitted_tool_names(cashier))
        assert "create_sale" in names
        assert "list_sales" in names
        assert "check_stock" in names
        # Cashier must NOT see user/admin/finance tools
        assert "create_user" not in names
        assert "create_employee" not in names
        assert "add_expense" not in names
        assert "profit_summary" not in names

    def test_tools_payload_excludes_unpermitted(self):
        viewer = _user(perms={"view_reports"})
        tools = get_tools_for_user(viewer)
        names = {t["function"]["name"] for t in tools}
        assert names == {"sales_summary", "profit_summary"}

    def test_unauthenticated_user_gets_no_tools(self):
        assert get_tools_for_user(_user(authenticated=False)) == []
        assert get_tools_for_user(None) == []

    def test_user_without_has_permission_gets_no_tools(self):
        user = SimpleNamespace(is_authenticated=True, is_owner=False)
        assert get_tools_for_user(user) == []


class TestExecutionGuardLogic:
    def test_owner_can_use_any_tool(self):
        meta = {"permission": "manage_users"}
        assert user_can_use_tool(_user(owner=True), meta) is True

    def test_permissionless_tool_open_to_authenticated(self):
        meta = {"permission": ""}
        assert user_can_use_tool(_user(), meta) is True
        assert user_can_use_tool(_user(authenticated=False), meta) is False

    def test_unauthorized_blocked(self):
        meta = {"permission": "manage_users"}
        assert user_can_use_tool(_user(perms={"manage_sales"}), meta) is False


class TestRegisterAiToolDecorator:
    def test_decorator_registers_standalone_tool(self):
        from pydantic import BaseModel

        class _Args(BaseModel):
            x: int = 1

        @register_ai_tool(
            name="_test_standalone_tool",
            description="اختبار",
            permission="manage_sales",
            schema=_Args,
        )
        def _handler(args):
            return args

        try:
            assert "_test_standalone_tool" in _STANDALONE_TOOLS
            registry = get_tool_registry()
            assert registry["_test_standalone_tool"]["handler"] is _handler
            assert registry["_test_standalone_tool"]["source"] == "decorator"
            tools = get_tools_for_user(_user(owner=True))
            assert any(t["function"]["name"] == "_test_standalone_tool" for t in tools)
        finally:
            _STANDALONE_TOOLS.pop("_test_standalone_tool", None)
