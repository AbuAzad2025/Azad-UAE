"""Action-pack acceptance tests — cheques / returns / quotations / catalog.

Verifies the Master Directive expansion stays modular and guarded:
- All 10 pack actions register with permissions + confirmation gates.
- Pack command patterns parse to the right action/args; legacy intact.
- Pydantic schemas reject bad input with Arabic clarification.
- RBAC: unpermitted users are rejected before any service is touched.
- Tenant guard fails closed without a tenant context.
- Success paths execute through mocked service-layer boundaries only.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ai_knowledge.action_dispatcher import ActionDispatcher, action_dispatcher


def _owner():
    return SimpleNamespace(
        is_authenticated=True,
        is_owner=True,
        tenant_id=1,
        id=1,
        branch_id=None,
        has_permission=lambda code: True,
    )


def _low_user(*perms):
    allowed = set(perms)
    return SimpleNamespace(
        is_authenticated=True,
        is_owner=False,
        tenant_id=1,
        id=2,
        branch_id=None,
        has_permission=lambda code: code in allowed,
    )


@contextmanager
def _no_db_writes():
    """Neutralise DB-touching seams: atomic blocks + session flush."""
    from unittest.mock import patch

    import ai_knowledge.actions.catalog as catalog
    import ai_knowledge.actions.cheques as cheques
    import ai_knowledge.actions.quotations as quotations
    import ai_knowledge.actions.returns as returns

    class _DummyCtx:
        def __enter__(self):
            return None

        def __exit__(self, *exc):
            return False

    with (
        patch.object(cheques, "atomic_transaction", return_value=_DummyCtx()),
        patch.object(returns, "atomic_transaction", return_value=_DummyCtx()),
        patch.object(quotations, "atomic_transaction", return_value=_DummyCtx()),
        patch.object(catalog, "atomic_transaction", return_value=_DummyCtx()),
        patch("extensions.db") as mock_db,
    ):
        mock_db.session.flush.return_value = None
        yield mock_db


class TestPackRegistration:
    EXPECTED = {
        "create_cheque": ("manage_payments", True),
        "list_cheques": ("manage_payments", False),
        "create_sale_return": ("manage_sales", True),
        "list_returns": ("manage_sales", False),
        "create_quotation": ("manage_sales", True),
        "list_quotations": ("manage_sales", False),
        "advance_quotation": ("manage_sales", True),
        "update_customer": ("manage_customers", True),
        "update_product": ("manage_products", True),
        "adjust_stock": ("manage_warehouse", True),
    }

    def test_all_pack_actions_registered(self):
        registered = action_dispatcher.get_registered_actions()
        assert len(registered) == 28
        for action in self.EXPECTED:
            assert action in registered

    def test_permissions_and_confirmation_gates(self):
        for action, (perm, confirm) in self.EXPECTED.items():
            meta = action_dispatcher.get_action_metadata(action)
            assert meta["permission"] == perm, action
            assert bool(meta["confirm_required"]) is confirm, action

    def test_tool_registry_bridges_packs(self):
        from ai_knowledge.tool_registry import get_permitted_tool_names

        names = get_permitted_tool_names(_owner())
        for action in self.EXPECTED:
            assert action in names


class TestPackCommandParsing:
    CASES = [
        ("شيك: 123, 5000, وارد, بنك دبي, 2026-12-31", "create_cheque"),
        ("عرض الشيكات", "list_cheques"),
        ("مرتجع: S-100, فلتر زيت, 2", "create_sale_return"),
        ("عرض المرتجعات", "list_returns"),
        ("عرض سعر: أحمد, فلتر, 2", "create_quotation"),
        ("عرض عروض الأسعار", "list_quotations"),
        ("قبول عرض: QT-5", "advance_quotation"),
        ("تحويل عرض: QT-5", "advance_quotation"),
        ("تحديث عميل: أحمد, 0501234567", "update_customer"),
        ("تحديث منتج: فلتر, 50", "update_product"),
        ("تسوية مخزون: فلتر, -5, جرد سنوي", "adjust_stock"),
    ]

    @pytest.mark.parametrize("message,expected", CASES)
    def test_pack_commands_parse(self, message, expected):
        hit = ActionDispatcher.parse_chat_action(message)
        assert hit is not None, message
        assert hit[0] == expected, message

    def test_cheque_args_mapped(self):
        _, args = ActionDispatcher.parse_chat_action("شيك: 123, 5000, صادر, بنك دبي, 2026-12-31")
        assert args["cheque_number"] == "123"
        assert args["amount"] == 5000
        assert args["cheque_type"] == "outgoing"
        assert args["bank_name"] == "بنك دبي"

    def test_return_sale_reference_and_target(self):
        _, args = ActionDispatcher.parse_chat_action("مرتجع: 42, فلتر, 2")
        assert args["sale_id"] == 42
        assert args["quantity"] == 2
        _, args = ActionDispatcher.parse_chat_action("مرتجع: S-42, فلتر, 1")
        assert args["sale_number"] == "S-42"
        _, args = ActionDispatcher.parse_chat_action("رفض عرض: QT-9")
        assert args == {"quotation_number": "QT-9", "target": "rejected"}

    def test_adjust_delta_keeps_sign(self):
        _, args = ActionDispatcher.parse_chat_action("تسوية مخزون: فلتر, -5, جرد")
        assert args["quantity_delta"] == -5
        assert args["reason"] == "جرد"

    def test_unknown_returns_none_and_legacy_intact(self):
        from ai_knowledge.actions import match_pack_command

        assert match_pack_command("كلام بلا معنى إطلاقا ززز") is None
        legacy = ActionDispatcher.parse_chat_action("عميل: أحمد, 050, دبي")
        assert legacy is not None and legacy[0] == "create_customer"


class TestPackSchemas:
    def test_cheque_rejects_missing_bank(self):
        from ai_knowledge.tool_schemas import ToolValidationError, validate_tool_args

        with pytest.raises(ToolValidationError) as exc:
            validate_tool_args(
                "create_cheque",
                {"cheque_number": "1", "cheque_type": "incoming", "amount": 5, "due_date": "2026-01-01"},
            )
        assert "البنك" in str(exc.value)

    def test_return_requires_identifier(self):
        from ai_knowledge.tool_schemas import ToolValidationError, validate_tool_args

        with pytest.raises(ToolValidationError) as exc:
            validate_tool_args("create_sale_return", {"product_name": "x", "quantity": 1})
        assert "الفاتورة" in str(exc.value)

    def test_advance_rejects_unknown_target(self):
        from ai_knowledge.tool_schemas import ToolValidationError, validate_tool_args

        with pytest.raises(ToolValidationError):
            validate_tool_args("advance_quotation", {"quotation_number": "QT-1", "target": "explode"})

    def test_adjust_rejects_zero_and_missing_reason(self):
        from ai_knowledge.tool_schemas import ToolValidationError, validate_tool_args

        with pytest.raises(ToolValidationError):
            validate_tool_args("adjust_stock", {"product_name": "x", "quantity_delta": 0, "reason": "r"})
        with pytest.raises(ToolValidationError):
            validate_tool_args("adjust_stock", {"product_name": "x", "quantity_delta": 2, "reason": ""})

    def test_update_product_requires_identifier_and_change(self):
        from ai_knowledge.tool_schemas import ToolValidationError, validate_tool_args

        with pytest.raises(ToolValidationError):
            validate_tool_args("update_product", {"selling_price": 5})
        with pytest.raises(ToolValidationError):
            validate_tool_args("update_product", {"name": "x"})

    def test_valid_pack_args_pass(self):
        from ai_knowledge.tool_schemas import validate_tool_args

        clean = validate_tool_args(
            "create_cheque",
            {
                "cheque_number": "77",
                "cheque_type": "incoming",
                "amount": 100,
                "bank_name": "بنك",
                "due_date": "2026-06-01",
            },
        )
        assert clean["cheque_number"] == "77"


class TestPackRbac:
    def test_unpermitted_pack_tools_rejected(self, mocker):
        cases = [
            ("create_cheque", "manage_payments"),
            ("list_cheques", "manage_payments"),
            ("create_sale_return", "manage_sales"),
            ("advance_quotation", "manage_sales"),
            ("update_customer", "manage_customers"),
            ("update_product", "manage_products"),
            ("adjust_stock", "manage_warehouse"),
        ]
        for action, perm in cases:
            mocker.patch("ai_knowledge.action_dispatcher.current_user", _low_user())
            result = ActionDispatcher().dispatch(action, {})
            assert result.success is False, action
            assert result.needs_permission == perm, action

    def test_layer1_hides_unpermitted_pack_tools(self):
        from ai_knowledge.tool_registry import get_permitted_tool_names

        names = get_permitted_tool_names(_low_user("manage_sales"))
        assert "create_sale_return" in names
        assert "advance_quotation" in names
        assert "create_cheque" not in names
        assert "adjust_stock" not in names

    def test_owner_passes_gate_to_validation(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        result = ActionDispatcher().dispatch("create_cheque", {})
        assert not result.needs_permission
        assert result.success is False

    def test_confirmation_gate_before_execution(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        result = ActionDispatcher().dispatch(
            "create_cheque",
            {
                "cheque_number": "1",
                "cheque_type": "incoming",
                "amount": 5,
                "bank_name": "b",
                "due_date": "2026-01-01",
            },
        )
        assert result.needs_confirmation is True
        assert result.success is False


class TestPackTenantGuard:
    def test_no_tenant_fails_closed(self, mocker):
        # Permission gate passes (owner) so the tenant guard itself fires.
        owner_without_tenant = SimpleNamespace(
            is_authenticated=True, is_owner=True, tenant_id=None, has_permission=lambda code: True
        )
        mocker.patch("ai_knowledge.action_dispatcher.current_user", owner_without_tenant)
        for action in ("list_cheques", "list_returns", "list_quotations"):
            result = ActionDispatcher().dispatch(action, {})
            assert result.success is False, action
            assert "تينانت" in result.message, action

    def test_logged_out_denied_at_permission_gate(self, mocker):
        logged_out = SimpleNamespace(is_authenticated=False, is_owner=False, tenant_id=None)
        mocker.patch("ai_knowledge.action_dispatcher.current_user", logged_out)
        result = ActionDispatcher().dispatch("list_cheques", {})
        assert result.success is False
        assert result.needs_permission == "manage_payments"


class TestPackExecution:
    def test_create_cheque_success(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        mocker.patch("models.Cheque")
        fake_service = mocker.patch("services.cheque_service.ChequeService")
        fake_service.create_cheque.return_value = SimpleNamespace(id=7)
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "create_cheque",
                {
                    "cheque_number": "CHK-1",
                    "cheque_type": "incoming",
                    "amount": 500,
                    "bank_name": "بنك",
                    "due_date": "2026-06-01",
                    "confirmed": True,
                },
            )
        assert result.success is True
        assert "CHK-1" in result.message
        fake_service.create_cheque.assert_called_once()

    def test_create_cheque_duplicate_blocked(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        cheque_cls = MagicMock()
        cheque_cls.query.filter_by.return_value.first.return_value = SimpleNamespace(id=9)
        mocker.patch("models.Cheque", cheque_cls)
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "create_cheque",
                {
                    "cheque_number": "CHK-9",
                    "cheque_type": "incoming",
                    "amount": 500,
                    "bank_name": "بنك",
                    "due_date": "2026-06-01",
                    "confirmed": True,
                },
            )
        assert result.success is False
        assert "مسجل مسبقاً" in result.message

    def test_create_sale_return_success(self, mocker):
        import ai_knowledge.actions.returns as returns

        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        line = SimpleNamespace(id=11, product=SimpleNamespace(name="فلتر زيت"))
        sale = SimpleNamespace(id=5, sale_number="S-5", status="confirmed", lines=[line])
        mocker.patch.object(returns, "_resolve_sale", return_value=sale)
        fake_service = mocker.patch("services.return_service.ReturnService")
        fake_service.create_return.return_value = SimpleNamespace(
            id=3, return_number="R-1", refund_amount=100, total_amount=100
        )
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "create_sale_return",
                {"sale_number": "S-5", "product_name": "فلتر", "quantity": 1, "confirmed": True},
            )
        assert result.success is True
        assert "R-1" in result.message
        fake_service.create_return.assert_called_once()

    def test_advance_quotation_lifecycle(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        quotation_cls = MagicMock()
        quotation_cls.query.filter_by.return_value.first.return_value = SimpleNamespace(id=4, quotation_number="QT-4")
        mocker.patch("models.Quotation", quotation_cls)
        fake_service = mocker.patch("services.quotation_service.QuotationService")
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "advance_quotation",
                {"quotation_number": "QT-4", "target": "accepted", "confirmed": True},
            )
        assert result.success is True
        fake_service.accept_quotation.assert_called_once()

    def test_update_customer_whitelist(self, mocker):
        import ai_knowledge.actions.catalog as catalog

        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        customer = SimpleNamespace(id=6, name="أحمد", phone="", address="")
        mocker.patch.object(catalog, "resolve_customer", return_value=customer)
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "update_customer",
                {"name": "أحمد", "phone": "0501234567", "confirmed": True},
            )
        assert result.success is True
        assert customer.phone == "0501234567"

    def test_adjust_stock_routes_through_service(self, mocker):
        import ai_knowledge.actions.catalog as catalog

        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        product = SimpleNamespace(id=8, name="فلتر")
        mocker.patch.object(catalog, "resolve_product", return_value=product)
        fake_stock = mocker.patch("services.stock_service.StockService")
        fake_stock.adjust_stock.return_value = SimpleNamespace(id=9)
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "adjust_stock",
                {"product_name": "فلتر", "quantity_delta": -5, "reason": "جرد سنوي", "confirmed": True},
            )
        assert result.success is True
        fake_stock.adjust_stock.assert_called_once()
        assert fake_stock.adjust_stock.call_args.kwargs["quantity"] == -5

    def test_format_help_lists_packs(self):
        text = ActionDispatcher.format_help()
        assert "الشيكات" in text
        assert "المرتجعات" in text
        assert "عروض الأسعار" in text
        assert "الكتالوج" in text
