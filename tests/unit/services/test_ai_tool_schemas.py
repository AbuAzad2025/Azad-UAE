"""Tests for ai_knowledge.tool_schemas — P3-1 native tool calling schemas."""

import pytest

from ai_knowledge.tool_schemas import (
    ACTION_ARG_MODELS,
    get_openai_tools,
    validate_tool_args,
)


class TestOpenAITools:
    def test_all_dispatcher_actions_have_schemas(self):
        from ai_knowledge.action_dispatcher import action_dispatcher

        registered = set(action_dispatcher.get_registered_actions())
        assert registered == set(ACTION_ARG_MODELS.keys())

    def test_tools_openai_compatible_shape(self):
        tools = get_openai_tools()
        assert len(tools) == len(ACTION_ARG_MODELS)
        for tool in tools:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert fn["name"] in ACTION_ARG_MODELS
            assert fn["description"]
            params = fn["parameters"]
            assert params["type"] == "object"
            assert "properties" in params

    def test_required_fields_marked(self):
        tools = {t["function"]["name"]: t["function"]["parameters"] for t in get_openai_tools()}
        assert "name" in tools["create_customer"]["required"]
        assert "customer_name" in tools["create_sale"]["required"]
        assert "amount" in tools["receive_payment"]["required"]
        assert tools["check_stock"].get("required", []) == []


class TestValidateToolArgs:
    def test_coerces_loose_types(self):
        args = validate_tool_args(
            "create_sale",
            {"customer_name": "أحمد", "product_name": "قلم", "quantity": "3"},
        )
        assert args["quantity"] == 3
        assert args["payment_method"] == "cash"

    def test_strips_unknown_keys(self):
        args = validate_tool_args("create_customer", {"name": "س", "evil": "drop table"})
        assert "evil" not in args
        assert args["name"] == "س"

    def test_rejects_missing_required(self):
        with pytest.raises(ValueError, match="معطيات غير صالحة"):
            validate_tool_args("create_customer", {"phone": "123"})

    def test_rejects_negative_amount(self):
        with pytest.raises(ValueError, match="معطيات غير صالحة"):
            validate_tool_args("receive_payment", {"customer_name": "أحمد", "amount": -10})

    def test_rejects_zero_quantity(self):
        with pytest.raises(ValueError, match="معطيات غير صالحة"):
            validate_tool_args("create_sale", {"customer_name": "أ", "product_name": "ب", "quantity": 0})

    def test_unknown_action_rejected(self):
        with pytest.raises(ValueError, match="غير معروفة"):
            validate_tool_args("delete_everything", {})

    def test_none_args_for_empty_schema_ok(self):
        assert validate_tool_args("check_stock", None) == {}
