"""Phase-2 action packs — purchase returns / cheque lifecycle / payroll.

Verifies RBAC permission rejections, Pydantic validation failures,
confirmation gates, tenant guards, and successful service-layer
executions (services mocked at the boundary; no direct ORM writes).
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    """Neutralise DB-touching seams across the three new packs."""
    import ai_knowledge.actions.cheque_lifecycle as lifecycle
    import ai_knowledge.actions.payroll_processing as payroll
    import ai_knowledge.actions.purchase_returns as pret

    class _DummyCtx:
        def __enter__(self):
            return None

        def __exit__(self, *exc):
            return False

    with (
        patch.object(pret, "atomic_transaction", return_value=_DummyCtx()),
        patch.object(lifecycle, "atomic_transaction", return_value=_DummyCtx()),
        patch.object(payroll, "atomic_transaction", return_value=_DummyCtx()),
        patch("extensions.db") as mock_db,
    ):
        mock_db.session.flush.return_value = None
        yield mock_db


class TestPhase2Registration:
    EXPECTED = {
        "create_purchase_return": ("manage_purchases", True),
        "purchase_return_details": ("manage_purchases", False),
        "deposit_cheque": ("manage_payments", True),
        "clear_cheque": ("manage_payments", True),
        "bounce_cheque": ("manage_payments", True),
        "calculate_monthly_payroll": ("manage_payroll", False),
        "approve_and_post_payroll": ("manage_payroll", True),
    }

    def test_registry_holds_35_actions(self):
        assert len(action_dispatcher.get_registered_actions()) == 35

    def test_permissions_and_confirmation_gates(self):
        for action, (perm, confirm) in self.EXPECTED.items():
            meta = action_dispatcher.get_action_metadata(action)
            assert meta is not None, action
            assert meta["permission"] == perm, action
            assert bool(meta["confirm_required"]) is confirm, action

    def test_tool_registry_bridges_new_packs(self):
        from ai_knowledge.tool_registry import get_permitted_tool_names

        names = get_permitted_tool_names(_owner())
        for action in self.EXPECTED:
            assert action in names


class TestPhase2CommandParsing:
    CASES = [
        ("مرتجع مشتريات: P-10, فلتر, 2", "create_purchase_return"),
        ("تفاصيل مرتجع: PR-3", "purchase_return_details"),
        ("عرض مرتجعات المشتريات", "purchase_return_details"),
        ("إيداع شيك: 555", "deposit_cheque"),
        ("إيداع شيك: 555, 2026-10-01", "deposit_cheque"),
        ("تحصيل شيك: 555", "clear_cheque"),
        ("ارتداد شيك: 555, رصيد غير كاف", "bounce_cheque"),
        ("مسير الرواتب: 9, 2026", "calculate_monthly_payroll"),
        ("اعتماد الرواتب: 9, 2026", "approve_and_post_payroll"),
    ]

    @pytest.mark.parametrize("message,expected", CASES)
    def test_new_commands_parse(self, message, expected):
        hit = ActionDispatcher.parse_chat_action(message)
        assert hit is not None, message
        assert hit[0] == expected, message

    def test_month_year_mapping(self):
        _, args = ActionDispatcher.parse_chat_action("مسير الرواتب: 9, 2026")
        assert args == {"month": 9, "year": 2026}

    def test_bounce_args_mapped(self):
        _, args = ActionDispatcher.parse_chat_action("ارتداد شيك: 555, رصيد غير كاف, 25")
        assert args["cheque_number"] == "555"
        assert args["reason"] == "رصيد غير كاف"
        assert args["bounce_fee"] == 25

    def test_sale_returns_still_win_plain_lists(self):
        hit = ActionDispatcher.parse_chat_action("عرض المرتجعات")
        assert hit is not None and hit[0] == "list_returns"


class TestPhase2Schemas:
    def test_purchase_return_requires_identifier(self):
        from ai_knowledge.tool_schemas import ToolValidationError, validate_tool_args

        with pytest.raises(ToolValidationError) as exc:
            validate_tool_args("create_purchase_return", {"product_name": "x", "quantity": 1})
        assert "الشراء" in str(exc.value)

    def test_bounce_requires_reason(self):
        from ai_knowledge.tool_schemas import ToolValidationError, validate_tool_args

        with pytest.raises(ToolValidationError):
            validate_tool_args("bounce_cheque", {"cheque_number": "1", "reason": ""})

    def test_payroll_rejects_bad_month(self):
        from ai_knowledge.tool_schemas import ToolValidationError, validate_tool_args

        with pytest.raises(ToolValidationError):
            validate_tool_args("calculate_monthly_payroll", {"month": 13, "year": 2026})

    def test_valid_args_pass(self):
        from ai_knowledge.tool_schemas import validate_tool_args

        clean = validate_tool_args(
            "deposit_cheque",
            {"cheque_number": "555", "deposit_date": "2026-10-01"},
        )
        assert clean["cheque_number"] == "555"
        clean = validate_tool_args(
            "approve_and_post_payroll",
            {"month": 9, "year": 2026, "adjustments": [{"employee_name": "سالم"}]},
        )
        assert clean["month"] == 9


class TestPhase2Rbac:
    def test_unpermitted_actions_rejected(self, mocker):
        cases = [
            ("create_purchase_return", "manage_purchases"),
            ("purchase_return_details", "manage_purchases"),
            ("deposit_cheque", "manage_payments"),
            ("clear_cheque", "manage_payments"),
            ("bounce_cheque", "manage_payments"),
            ("calculate_monthly_payroll", "manage_payroll"),
            ("approve_and_post_payroll", "manage_payroll"),
        ]
        for action, perm in cases:
            mocker.patch("ai_knowledge.action_dispatcher.current_user", _low_user())
            result = ActionDispatcher().dispatch(action, {})
            assert result.success is False, action
            assert result.needs_permission == perm, action

    def test_layer1_hides_payroll_from_purchasing_clerk(self):
        from ai_knowledge.tool_registry import get_permitted_tool_names

        names = get_permitted_tool_names(_low_user("manage_purchases"))
        assert "create_purchase_return" in names
        assert "calculate_monthly_payroll" not in names
        assert "deposit_cheque" not in names

    def test_owner_passes_gate_to_validation(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        result = ActionDispatcher().dispatch("bounce_cheque", {})
        assert not result.needs_permission
        assert result.success is False

    def test_confirmation_gates(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        gated = [
            ("create_purchase_return", {"purchase_number": "P-1", "product_name": "x", "quantity": 1}),
            ("deposit_cheque", {"cheque_number": "1"}),
            ("clear_cheque", {"cheque_number": "1"}),
            ("bounce_cheque", {"cheque_number": "1", "reason": "r"}),
            ("approve_and_post_payroll", {"month": 9, "year": 2026}),
        ]
        for action, args in gated:
            result = ActionDispatcher().dispatch(action, args)
            assert result.needs_confirmation is True, action
            assert result.success is False, action


class TestPhase2TenantGuard:
    def test_no_tenant_fails_closed(self, mocker):
        owner_without_tenant = SimpleNamespace(
            is_authenticated=True, is_owner=True, tenant_id=None, has_permission=lambda code: True
        )
        mocker.patch("ai_knowledge.action_dispatcher.current_user", owner_without_tenant)
        result = ActionDispatcher().dispatch("purchase_return_details", {})
        assert result.success is False
        assert "تينانت" in result.message


class TestPhase2Execution:
    def test_create_purchase_return_success(self, mocker):
        import ai_knowledge.actions.purchase_returns as pret

        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        line = SimpleNamespace(id=21, product_id=31, product=SimpleNamespace(name="فلتر زيت"), unit_cost=40)
        purchase = SimpleNamespace(id=12, purchase_number="P-10", status="confirmed", supplier_id=5, lines=[line])
        mocker.patch.object(pret, "_resolve_purchase", return_value=purchase)
        mocker.patch.object(pret, "actor", return_value=_owner())
        fake_service = mocker.patch("services.purchase_service.PurchaseService")
        fake_service.create_purchase_return.return_value = SimpleNamespace(id=13, return_number="PR-1", total_amount=80)
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "create_purchase_return",
                {"purchase_number": "P-10", "product_name": "فلتر", "quantity": 2, "confirmed": True},
            )
        assert result.success is True
        assert "PR-1" in result.message
        fake_service.create_purchase_return.assert_called_once()

    def test_purchase_return_details_single(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        line = SimpleNamespace(product=SimpleNamespace(name="فلتر"), quantity=2, unit_cost=40, line_total=80)
        record = SimpleNamespace(
            id=13, return_number="PR-1", purchase_id=12, total_amount=80, reason="تالف", lines=[line]
        )
        pr_cls = MagicMock()
        pr_cls.query.filter_by.return_value.first.return_value = record
        mocker.patch("models.PurchaseReturn", pr_cls)
        with _no_db_writes():
            result = ActionDispatcher().dispatch("purchase_return_details", {"return_number": "PR-1"})
        assert result.success is True
        assert result.data["number"] == "PR-1"
        assert len(result.data["lines"]) == 1

    def test_deposit_cheque_success(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        cheque_cls = MagicMock()
        cheque_cls.query.filter_by.return_value.first.return_value = SimpleNamespace(id=20, cheque_number="555")
        mocker.patch("models.Cheque", cheque_cls)
        deposit = mocker.patch("services.cheque_service.process_cheque_deposit")
        with _no_db_writes():
            result = ActionDispatcher().dispatch("deposit_cheque", {"cheque_number": "555", "confirmed": True})
        assert result.success is True
        assert "555" in result.message
        deposit.assert_called_once()

    def test_bounce_cheque_passes_fee(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        cheque_cls = MagicMock()
        cheque_cls.query.filter_by.return_value.first.return_value = SimpleNamespace(id=21, cheque_number="556")
        mocker.patch("models.Cheque", cheque_cls)
        bounce = mocker.patch("services.cheque_service.process_cheque_bounce")
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "bounce_cheque",
                {"cheque_number": "556", "reason": "رصيد غير كاف", "bounce_fee": 25, "confirmed": True},
            )
        assert result.success is True
        bounce.assert_called_once()
        assert bounce.call_args[0][1] == "رصيد غير كاف"
        assert bounce.call_args[0][2] == 25

    def test_clear_cheque_bad_state_surfaces(self, mocker):
        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        cheque_cls = MagicMock()
        cheque_cls.query.filter_by.return_value.first.return_value = SimpleNamespace(id=22, cheque_number="557")
        mocker.patch("models.Cheque", cheque_cls)
        mocker.patch(
            "services.cheque_service.process_cheque_clear",
            side_effect=ValueError("لا يمكن التحصيل بحالة: cleared"),
        )
        with _no_db_writes():
            result = ActionDispatcher().dispatch("clear_cheque", {"cheque_number": "557", "confirmed": True})
        assert result.success is False
        assert "cleared" in result.message

    def test_calculate_payroll_read_only(self, mocker):
        import ai_knowledge.actions.payroll_processing as payroll

        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        emp = SimpleNamespace(
            id=30, name="سالم", basic_salary=3000, employment_type="salary", iban="AE1", bank_code="033"
        )
        mocker.patch("services.payroll_service.PayrollService.list_active_employees", return_value=[emp])
        mocker.patch.object(payroll, "_already_posted", return_value=False)
        mocker.patch.object(payroll, "_pending_advances_total", return_value=Decimal("200"))
        with _no_db_writes():
            result = ActionDispatcher().dispatch("calculate_monthly_payroll", {"month": 9, "year": 2026})
        assert result.success is True
        assert result.data["total_net"] == 2800.0
        assert result.data["wps_eligible"] == 1

    def test_approve_payroll_posts_and_reports_wps(self, mocker):
        import ai_knowledge.actions.payroll_processing as payroll

        mocker.patch("ai_knowledge.action_dispatcher.current_user", _owner())
        mocker.patch.object(payroll, "actor", return_value=_owner())
        emp = SimpleNamespace(id=30, name="سالم", employment_type="salary")
        fake_service = mocker.patch("services.payroll_service.PayrollService")
        fake_service.list_active_employees.return_value = [emp]
        fake_service.process_payroll.return_value = SimpleNamespace(net_salary=2900)
        fake_service.get_wps_rows.return_value = [{"wps_id": "00000030"}]
        mocker.patch.object(payroll, "_already_posted", return_value=False)
        with _no_db_writes():
            result = ActionDispatcher().dispatch(
                "approve_and_post_payroll", {"month": 9, "year": 2026, "confirmed": True}
            )
        assert result.success is True
        assert "سالم" in result.data["posted"]
        assert result.data["wps_rows"] == 1
        fake_service.process_payroll.assert_called_once()

    def test_format_help_lists_phase2(self):
        text = ActionDispatcher.format_help()
        assert "مردودات المشتريات" in text
        assert "دورة الشيكات" in text
        assert "الرواتب" in text
