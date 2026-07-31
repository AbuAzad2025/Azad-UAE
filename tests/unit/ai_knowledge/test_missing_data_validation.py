"""Missing-data & edge-case validation — Human-Operator directive.

Covers three mandates:
1. **Missing Required Fields** — incomplete payloads for EVERY registered
   tool produce structured validation errors (never unhandled exceptions).
2. **Boundary Validation** — zero/negative numbers, malformed strings and
   unsupported enums are rejected gracefully with Arabic reasons.
3. **Execution Safety** — zero database mutations occur when parameters
   are incomplete (the dispatcher stops before any service layer).
"""

from unittest.mock import MagicMock, patch

import pytest

from ai_knowledge.action_dispatcher import action_dispatcher
from ai_knowledge.tool_schemas import (
    ACTION_ARG_MODELS,
    ToolValidationError,
    get_missing_data_prompt,
    validate_tool_args,
    validate_tool_args_safe,
)

# ---------------------------------------------------------------------------
# Payloads missing at least one mandatory business field, per mutation tool
# ---------------------------------------------------------------------------
MISSING_PAYLOADS: dict[str, dict] = {
    "create_customer": {"phone": "0501234567"},  # missing name
    "customer_balance": {},  # missing name
    "create_product": {"selling_price": 10},  # missing name
    "transfer_stock": {"product_name": "زيت"},  # missing warehouses + qty
    "create_sale": {"customer_name": "أحمد"},  # missing product + quantity
    "cancel_sale": {},  # missing invoice identifier
    "receive_payment": {"amount": 100},  # missing customer
    "add_expense": {"description": "وقود"},  # missing amount
    "create_supplier": {"phone": "0599"},  # missing name
    "create_purchase": {"supplier_name": "شركة القدس"},  # missing product + qty
    "create_employee": {"salary": 3000},  # missing name
    "create_user": {"username": "user1"},  # missing password
}

# Read-only tools — every field optional, must never raise on empty input
READ_ONLY_TOOLS = ["list_customers", "list_products", "list_sales", "check_stock", "sales_summary", "profit_summary"]

# Mutation tools that must not touch the database with incomplete args
MUTATION_TOOLS = list(MISSING_PAYLOADS.keys())


class TestMissingRequiredFields:
    """Every registered tool: incomplete payload → structured error, no crash."""

    def test_every_registered_tool_has_schema(self):
        registered = set(action_dispatcher.get_registered_actions())
        assert registered == set(ACTION_ARG_MODELS.keys())

    @pytest.mark.parametrize("action_type", sorted(MISSING_PAYLOADS.keys()))
    def test_missing_fields_raise_structured_error(self, action_type):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args(action_type, MISSING_PAYLOADS[action_type])
        err = exc_info.value
        # Structured attributes — machine-readable for clarification prompts
        assert err.action_type == action_type
        assert err.missing_fields or err.invalid_fields, f"{action_type}: expected field errors"
        # Friendly Arabic clarification message
        msg = str(err)
        assert "معطيات غير صالحة" in msg
        assert "📋 البيانات الناقصة" in msg or "⚠️ قيم غير مقبولة" in msg
        assert msg.endswith("يرجى تزويدي بالبيانات الصحيحة لإكمال العملية دون تخمين.")

    @pytest.mark.parametrize("action_type", READ_ONLY_TOOLS)
    def test_read_only_tools_accept_empty_payloads(self, action_type):
        clean, err = validate_tool_args_safe(action_type, None)
        assert err is None
        assert clean == {}

    def test_unknown_action_is_value_error_not_crash(self):
        with pytest.raises(ValueError, match="غير معروفة"):
            validate_tool_args("drop_all_tables", {})

    def test_structured_error_is_value_error_subclass(self):
        # Legacy callers catching ValueError keep working
        with pytest.raises(ValueError, match="معطيات غير صالحة"):
            validate_tool_args("create_sale", {"customer_name": "أ"})


class TestClarificationPrompts:
    """Intelligent conversational interrogation helpers."""

    def test_prompt_lists_exact_missing_labels(self):
        prompt = get_missing_data_prompt("create_sale", {"customer_name": "أحمد"})
        assert prompt is not None
        assert "اسم المنتج" in prompt
        assert "الكمية" in prompt

    def test_prompt_none_when_valid(self):
        assert (
            get_missing_data_prompt(
                "create_sale",
                {"customer_name": "أحمد", "product_name": "زيت", "quantity": 2},
            )
            is None
        )

    def test_safe_variant_returns_tuple(self):
        clean, err = validate_tool_args_safe("receive_payment", {"customer_name": "أ", "amount": 50})
        assert err is None
        assert clean["amount"] == 50
        clean, err = validate_tool_args_safe("receive_payment", {"amount": 50})
        assert clean is None
        assert isinstance(err, ToolValidationError)
        assert err.missing_fields == ["customer_name"]


class TestBoundaryValidation:
    """Zero/negative numbers, malformed strings, unsupported enums."""

    @pytest.mark.parametrize(
        ("action_type", "args", "field"),
        [
            ("create_sale", {"customer_name": "أ", "product_name": "ب", "quantity": 0}, "quantity"),
            ("create_sale", {"customer_name": "أ", "product_name": "ب", "quantity": -3}, "quantity"),
            ("create_sale", {"customer_name": "أ", "product_name": "ب", "quantity": 1, "unit_price": -5}, "unit_price"),
            (
                "create_sale",
                {"customer_name": "أ", "product_name": "ب", "quantity": 1, "paid_amount": -1},
                "paid_amount",
            ),
            ("receive_payment", {"customer_name": "أ", "amount": 0}, "amount"),
            ("receive_payment", {"customer_name": "أ", "amount": -10}, "amount"),
            ("add_expense", {"description": "وقود", "amount": 0}, "amount"),
            ("add_expense", {"description": "وقود", "amount": -50}, "amount"),
            ("create_purchase", {"supplier_name": "س", "product_name": "ب", "quantity": 0}, "quantity"),
            (
                "create_purchase",
                {"supplier_name": "س", "product_name": "ب", "quantity": 1, "unit_cost": -1},
                "unit_cost",
            ),
            ("create_product", {"name": "ب", "selling_price": -5}, "selling_price"),
            ("create_product", {"name": "ب", "stock": -1}, "stock"),
            ("create_customer", {"name": "س", "credit_limit": -100}, "credit_limit"),
            ("create_employee", {"name": "م", "salary": -1}, "salary"),
            (
                "transfer_stock",
                {"product_name": "ب", "from_warehouse_id": 1, "to_warehouse_id": 2, "quantity": 0},
                "quantity",
            ),
        ],
    )
    def test_non_positive_numbers_rejected(self, action_type, args, field):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args(action_type, args)
        err = exc_info.value
        assert any(f == field for f, _ in err.invalid_fields)
        assert "⚠️ قيم غير مقبولة" in str(err)

    def test_transfer_to_same_warehouse_rejected(self):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args(
                "transfer_stock",
                {"product_name": "ب", "from_warehouse_id": 1, "to_warehouse_id": 1, "quantity": 5},
            )
        assert "نفس المستودع" in str(exc_info.value)

    def test_cancel_sale_requires_identifier(self):
        with pytest.raises(ToolValidationError, match="رقم الفاتورة"):
            validate_tool_args("cancel_sale", {})

    def test_cancel_sale_malformed_id_rejected(self):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args("cancel_sale", {"sale_id": "abc"})
        assert any(f == "sale_id" for f, _ in exc_info.value.invalid_fields)

    def test_unsupported_payment_method_lists_available_values(self):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args("receive_payment", {"customer_name": "أ", "amount": 10, "method": "bitcoin"})
        assert "القيم المتاحة" in str(exc_info.value)

    def test_weak_password_rejected(self):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args("create_user", {"username": "user1", "password": "123"})
        assert any(f == "password" for f, _ in exc_info.value.invalid_fields)

    def test_short_username_rejected(self):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args("create_user", {"username": "ab", "password": "secret6"})
        assert any(f == "username" for f, _ in exc_info.value.invalid_fields)

    @pytest.mark.parametrize("action_type", ["create_customer", "create_supplier", "create_employee"])
    def test_malformed_phone_rejected(self, action_type):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args(action_type, {"name": "س", "phone": "abc!!"})
        assert any(f == "phone" for f, _ in exc_info.value.invalid_fields)

    @pytest.mark.parametrize("action_type", ["create_customer", "create_supplier", "create_employee"])
    def test_malformed_email_rejected(self, action_type):
        with pytest.raises(ToolValidationError) as exc_info:
            validate_tool_args(action_type, {"name": "س", "email": "not-an-email"})
        assert any(f == "email" for f, _ in exc_info.value.invalid_fields)

    def test_valid_payloads_pass_with_safe_defaults(self):
        clean = validate_tool_args(
            "create_sale",
            {"customer_name": "أحمد", "product_name": "زيت", "quantity": 2},
        )
        assert clean["payment_method"] == "cash"  # safe smart default
        assert clean["quantity"] == 2


class TestExecutionSafety:
    """Zero DB mutations when parameters are incomplete (dispatcher level)."""

    @pytest.mark.parametrize("action_type", sorted(MUTATION_TOOLS))
    def test_dispatch_blocks_incomplete_payloads_before_db(self, action_type):
        session = MagicMock()
        with (
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=True),
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch("ai_knowledge.action_dispatcher.db.session", session),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
            patch("ai_knowledge.action_dispatcher._audit"),
        ):
            result = action_dispatcher.dispatch(
                action_type,
                {**MISSING_PAYLOADS[action_type], "confirmed": True},
            )
        assert result.success is False
        assert result.needs_confirmation is False
        assert "معطيات غير صالحة" in result.message
        # The absolute guarantee: nothing was staged or persisted
        session.add.assert_not_called()
        session.flush.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.parametrize(
        ("action_type", "args"),
        [
            ("create_sale", {"customer_name": "أ", "product_name": "ب", "quantity": 0}),
            ("receive_payment", {"customer_name": "أ", "amount": -5}),
            ("add_expense", {"description": "وقود", "amount": 0}),
            (
                "transfer_stock",
                {"product_name": "ب", "from_warehouse_id": 1, "to_warehouse_id": 1, "quantity": 5},
            ),
        ],
    )
    def test_dispatch_blocks_boundary_violations_before_db(self, action_type, args):
        session = MagicMock()
        with (
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=True),
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch("ai_knowledge.action_dispatcher.db.session", session),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
            patch("ai_knowledge.action_dispatcher._audit"),
        ):
            result = action_dispatcher.dispatch(action_type, {**args, "confirmed": True})
        assert result.success is False
        session.add.assert_not_called()
        session.flush.assert_not_called()

    def test_validation_runs_before_confirmation_gate(self):
        """Missing data is asked about first — not a premature confirmation."""
        with (
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
        ):
            # create_sale is confirm_required; incomplete args must NOT
            # produce needs_confirmation — they produce a data prompt.
            result = action_dispatcher.dispatch("create_sale", {"customer_name": "أحمد"})
        assert result.success is False
        assert result.needs_confirmation is False
        assert "الكمية" in result.message or "اسم المنتج" in result.message
