"""Coverage for remaining action_dispatcher lines/arcs.

Targets (do not modify sources):
- line 443: _transfer_stock tenant-guard early return
- line 574: _cancel_sale tenant-guard early return
- line 962: _ensure_packs inner early return (concurrent registration)
- lines 1059-1060: parse_chat_action pack-matcher failure fallback
- arc 651->656: _add_expense category object with non-int id falls through
- arc 772->770: _profit_summary loop-back when product/cost missing
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_knowledge.action_dispatcher import ActionDispatcher


def _owner_ctx():
    return (
        patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
        patch("ai_knowledge.action_dispatcher._has_permission", return_value=True),
    )


class TestCovTransferStockTenantGuard:
    def test_no_tenant_returns_guard_line443(self):
        owner, perm = _owner_ctx()
        with (
            owner,
            perm,
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=None),
        ):
            result = ActionDispatcher().dispatch(
                "transfer_stock",
                {
                    "product_name": "Widget",
                    "from_warehouse_id": 1,
                    "to_warehouse_id": 2,
                    "quantity": 1,
                    "confirmed": True,
                },
            )
        assert result.success is False
        assert "تينانت" in result.message


class TestCovCancelSaleTenantGuard:
    def test_no_tenant_returns_guard_line574(self):
        owner, perm = _owner_ctx()
        with (
            owner,
            perm,
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=None),
        ):
            result = ActionDispatcher().dispatch("cancel_sale", {"sale_id": 5, "confirmed": True})
        assert result.success is False
        assert "تينانت" in result.message


class TestCovEnsurePacksInnerReturn:
    def test_concurrent_registration_hits_inner_return_line962(self):
        dispatcher = ActionDispatcher()
        dispatcher._packs_registered = False

        @contextmanager
        def _flipping_lock():
            dispatcher._packs_registered = True
            yield

        with (
            patch("ai_knowledge.action_dispatcher._packs_lock", _flipping_lock()),
            patch("ai_knowledge.actions.register_action_packs") as register,
        ):
            dispatcher._ensure_packs()
            register.assert_not_called()
        assert dispatcher._packs_registered is True


class TestCovParseChatPackFailure:
    def test_pack_matcher_exception_falls_back_lines1059_1060(self):
        with patch(
            "ai_knowledge.actions.match_pack_command",
            side_effect=RuntimeError("pack boom"),
        ):
            parsed = ActionDispatcher.parse_chat_action("عميل: أحمد, 0501234567, دبي")
        assert parsed is not None
        assert parsed[0] == "create_customer"
        assert parsed[1]["name"] == "أحمد"


class TestCovAddExpenseCategoryFallthrough:
    def test_category_object_without_int_id_falls_through_arc651_656(self):
        owner, perm = _owner_ctx()
        weird_category = SimpleNamespace(id="not-an-int")
        with (
            owner,
            perm,
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch(
                "ai_knowledge.action_dispatcher.current_user",
                SimpleNamespace(is_authenticated=True, id=7),
            ),
            patch("models.ExpenseCategory") as expense_category,
            patch("models.Expense") as expense_model,
            patch("ai_knowledge.action_dispatcher.db.session"),
            patch("ai_knowledge.action_dispatcher._audit"),
        ):
            expense_category.query.filter_by.return_value.first.return_value = weird_category
            expense_model.return_value = SimpleNamespace(id=42)
            result = ActionDispatcher().dispatch(
                "add_expense",
                {"description": "fuel", "amount": 50, "category": "Travel", "confirmed": True},
            )
        assert result.success is True
        assert result.data == {"expense_id": 42}
        expense_category.query.filter_by.assert_called_once_with(tenant_id=1, name="Travel")


class TestCovProfitSummaryMissingProduct:
    def test_product_without_cost_skips_accumulation_arc772_770(self):
        owner, perm = _owner_ctx()
        sales_query = MagicMock()
        sales_query.filter.return_value.scalar.return_value = Decimal("1000.00")
        lines_query = MagicMock()
        lines_query.join.return_value.filter.return_value.all.return_value = [
            SimpleNamespace(product_id=9, quantity=2),
        ]
        with (
            owner,
            perm,
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch("ai_knowledge.action_dispatcher.db") as mock_db,
            patch("models.Product") as product,
            patch("models.Sale"),
            patch("models.SaleLine"),
        ):
            mock_db.session.query.side_effect = [sales_query, lines_query]
            product.query.get.return_value = None
            result = ActionDispatcher().dispatch("profit_summary", {})
        assert result.success is True
        assert result.data["revenue"] == 1000.0
        assert result.data["cost"] == 0.0
        assert result.data["profit"] == 1000.0
        product.query.get.assert_called_once_with(9)
