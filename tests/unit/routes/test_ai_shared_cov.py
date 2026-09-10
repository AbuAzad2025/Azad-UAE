"""Coverage tests for routes/ai_routes/shared.py gaps.

Route-driven tests (via POST /ai/chat on the test client) target:

- lines 320-329: empty stream yields the empty_stream payload
- arcs 354-355: bad stream telemetry confidence coerced to None
- arcs 370-371: stream interaction-log DB failure is swallowed
- arcs 383-384: stream trainer failure is swallowed

Arc 269->279 (non-dict context skips context sanitization) is unreachable
via HTTP because chat.py requires a dict-like context before delegating;
it is covered by a direct helper test below.
"""

from unittest.mock import patch


def _post_chat_stream(ai_client, payload, stream_events, **patches):
    """Post to /ai/chat with streaming enabled and a stubbed token stream."""
    with (
        patch(
            "routes.ai_routes.shared.AIService.chat_response_stream",
            return_value=iter(stream_events),
        ),
        patch("routes.ai_routes.shared.db.session.add", **patches.get("add", {})),
        patch("routes.ai_routes.shared.db.session.commit"),
        patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
    ):
        return ai_client.post(
            "/ai/chat",
            json=payload,
            headers={"Accept": "text/event-stream"},
        )


class TestSharedCovSanitize:
    def test_sanitize_non_dict_context_arc269_279(self):
        from routes.ai_routes.shared import _sanitize_ai_prompt

        with patch(
            "utils.sanitizer.InputSanitizer.sanitize_text",
            side_effect=lambda v, max_length=8000: v,
        ):
            safe, err = _sanitize_ai_prompt("hello", None)
            assert err is None
            assert safe == "hello"
            safe2, err2 = _sanitize_ai_prompt("hello", "not-a-dict")
            assert err2 is None
            assert safe2 == "hello"


class TestSharedCovEmptyStream:
    def test_chat_empty_stream_lines320_329(self, ai_client):
        resp = _post_chat_stream(ai_client, {"message": "hello"}, [])
        assert resp.status_code == 200
        assert "empty_stream" in resp.get_data(as_text=True)


class TestSharedCovStreamConfidence:
    def test_chat_stream_bad_confidence_lines354_355(self, ai_client):
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
        resp = _post_chat_stream(ai_client, payload, [("final", "streamed-reply")])
        assert resp.status_code == 200
        assert "streamed-reply" in resp.get_data(as_text=True)


class TestSharedCovStreamDbFailure:
    def test_chat_stream_db_failure_lines370_371(self, ai_client):
        with (
            patch(
                "routes.ai_routes.shared.AIService.chat_response_stream",
                return_value=iter([("final", "streamed-reply")]),
            ),
            patch(
                "routes.ai_routes.shared.db.session.add",
                side_effect=RuntimeError("db down"),
            ),
            patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
        ):
            resp = ai_client.post(
                "/ai/chat",
                json={"message": "hello"},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
        assert "streamed-reply" in resp.get_data(as_text=True)


class TestSharedCovStreamTrainerFailure:
    def test_chat_stream_trainer_failure_lines383_384(self, ai_client):
        with (
            patch(
                "routes.ai_routes.shared.AIService.chat_response_stream",
                return_value=iter([("final", "streamed-reply")]),
            ),
            patch("routes.ai_routes.shared.db.session.add"),
            patch("routes.ai_routes.shared.db.session.commit"),
            patch(
                "ai_knowledge.trainer.trainer.learn_from_interaction",
                side_effect=RuntimeError("trainer down"),
            ),
        ):
            resp = ai_client.post(
                "/ai/chat",
                json={"message": "hello"},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
        assert "streamed-reply" in resp.get_data(as_text=True)
