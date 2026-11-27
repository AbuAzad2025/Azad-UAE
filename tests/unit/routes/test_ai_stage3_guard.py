"""Stage 3 route guard: questions must never dispatch write actions."""

from __future__ import annotations

from unittest.mock import patch


def test_question_is_not_dispatched_as_create_sale(ai_client, mock_ai_service):
    with (
        patch(
            "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
            return_value=("create_sale", {"customer_name": "x", "product_name": "y"}),
        ),
        patch("routes.ai_routes.chat._user_can_ai_execute_actions", return_value=True),
    ):
        resp = ai_client.post("/ai/chat", json={"message": "كم رصيده؟"})

    assert resp.status_code == 200
    mock_ai_service.chat_response.assert_called_once()


def test_explicit_write_command_still_dispatches(ai_client, mock_ai_service):
    with (
        patch(
            "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
            return_value=("customer_balance", {"name": "Ahmad"}),
        ),
        patch("routes.ai_routes.chat._user_can_ai_execute_actions", return_value=True),
        patch(
            "ai_knowledge.action_dispatcher.action_dispatcher.dispatch",
            return_value=type("R", (), {"success": True, "message": "done"})(),
        ),
    ):
        resp = ai_client.post("/ai/chat", json={"message": "رصيد: أحمد"})

    assert resp.status_code == 200
    assert resp.get_json()["data"]["action_executed"] is True
    mock_ai_service.chat_response.assert_not_called()
