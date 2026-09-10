"""Coverage tests for routes/ai_routes/chat.py gaps.

Each test drives the /ai/chat route via the test client and targets one
exact listed production line/arc:

- line 204: missing JSON body -> 400
- line 232: SSE streaming branch
- arcs 213->215, 215->218: caller-supplied dialect/beginners_mode preserved
- line 269: RBAC/confirmation-gate decision is final
- arcs 301-302: bad telemetry confidence coerced to None
- arcs 317-318: interaction-log DB failure is swallowed
- arcs 330-331: trainer failure is swallowed
"""

from unittest.mock import MagicMock, patch


def _post_chat_plain(ai_client, payload, **kwargs):
    """Post to /ai/chat bypassing the action wizard, with chat stubbed."""
    with (
        patch("routes.ai_routes.chat._user_can_ai_execute_actions", return_value=False),
        patch(
            "routes.ai_routes.chat.AIService.chat_response",
            return_value="ok-reply",
        ) as chat_resp,
        patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
    ):
        resp = ai_client.post("/ai/chat", json=payload, **kwargs)
    return resp, chat_resp


class TestChatCovMissingJson:
    def test_chat_no_json_body_400_line204(self, ai_client):
        resp = ai_client.post("/ai/chat", data=b"x", content_type="application/json")
        assert resp.status_code == 400


class TestChatCovStreaming:
    def test_chat_sse_stream_branch_line232(self, ai_client):
        chunks = ['data: {"delta": "hi"}\n\n']
        with patch(
            "routes.ai_routes.chat._stream_ai_response",
            return_value=iter(chunks),
        ):
            resp = ai_client.post(
                "/ai/chat",
                json={"message": "hello"},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"
        assert "hi" in resp.get_data(as_text=True)


class TestChatCovContextDefaults:
    def test_chat_existing_dialect_beginners_arcs213_215(self, ai_client):
        payload = {
            "message": "hello",
            "context": {"dialect": "egyptian", "beginners_mode": True},
        }
        resp, chat_resp = _post_chat_plain(ai_client, payload)
        assert resp.status_code == 200
        call_ctx = chat_resp.call_args[0][1]
        assert call_ctx["dialect"] == "egyptian"
        assert call_ctx["beginners_mode"] is True


class TestChatCovConfirmationGate:
    def test_chat_needs_confirmation_final_line269(self, ai_client):
        dispatch_result = MagicMock(
            success=False,
            message="confirm needed",
            needs_confirmation=True,
            needs_permission="",
        )
        with patch("ai_knowledge.action_dispatcher.action_dispatcher") as dispatcher:
            dispatcher.parse_chat_action.return_value = ("create_sale", {})
            dispatcher.dispatch.return_value = dispatch_result
            resp = ai_client.post("/ai/chat", json={"message": "approve sale"})
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert body["action_executed"] is True
        assert body["response"] == "confirm needed"


class TestChatCovTelemetry:
    def test_chat_bad_confidence_value_lines301_302(self, ai_client):
        payload = {
            "message": "hello",
            "context": {
                "ai_telemetry": {
                    "confidence": "not-a-float",
                    "tool_names": "t",
                    "fallback_path": "p",
                }
            },
        }
        resp, _ = _post_chat_plain(ai_client, payload)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["response"] == "ok-reply"


class TestChatCovLogFailure:
    def test_chat_interaction_log_failure_lines317_318(self, ai_client):
        with (
            patch("routes.ai_routes.chat._user_can_ai_execute_actions", return_value=False),
            patch(
                "routes.ai_routes.chat.AIService.chat_response",
                return_value="ok-reply",
            ),
            patch(
                "routes.ai_routes.chat.db.session.add",
                side_effect=RuntimeError("db down"),
            ),
            patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
        ):
            resp = ai_client.post("/ai/chat", json={"message": "hello"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["response"] == "ok-reply"


class TestChatCovTrainerFailure:
    def test_chat_trainer_failure_lines330_331(self, ai_client):
        with (
            patch("routes.ai_routes.chat._user_can_ai_execute_actions", return_value=False),
            patch(
                "routes.ai_routes.chat.AIService.chat_response",
                return_value="ok-reply",
            ),
            patch(
                "ai_knowledge.trainer.trainer.learn_from_interaction",
                side_effect=RuntimeError("trainer down"),
            ),
        ):
            resp = ai_client.post("/ai/chat", json={"message": "hello"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["response"] == "ok-reply"
