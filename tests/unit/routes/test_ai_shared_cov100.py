"""Gap100 for routes/ai_routes/shared.py — interaction-log failure (370-371)
and trainer-learn failure (383-384) inside ``_stream_ai_response``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _stream_patches(**overrides):
    stream = overrides.get(
        "stream",
        iter([("final", "AI reply")]),
    )
    return [
        patch(
            "routes.ai_routes.shared.AIService.chat_response_stream",
            return_value=stream,
        ),
        patch(
            "routes.ai_routes.shared.get_ai_access_state",
            return_value={
                "allowed": True,
                "global_enabled": True,
                "tenant_enabled": True,
            },
        ),
        patch("routes.ai_routes.shared.current_user", id=1, tenant_id=1, is_owner=True),
    ]


class TestStreamLogFailure:
    def test_db_add_failure_is_swallowed(self):
        from routes.ai_routes.shared import _stream_ai_response

        mock_db = MagicMock()
        mock_db.session.add.side_effect = RuntimeError("db down")
        atomic = patch("utils.db_safety.atomic_transaction")
        patches = _stream_patches() + [
            atomic,
            patch("routes.ai_routes.shared.db", mock_db),
            patch("ai_knowledge.trainer.trainer"),
        ]
        for p in patches:
            started = p.start()
            if p is atomic:
                started.return_value.__enter__ = MagicMock()
                started.return_value.__exit__ = MagicMock(return_value=False)
        try:
            chunks = list(_stream_ai_response("hello", {}, "chat"))
        finally:
            for p in reversed(patches):
                p.stop()
        assert any(c.startswith("data: ") for c in chunks)

    def test_trainer_failure_is_swallowed(self):
        from routes.ai_routes.shared import _stream_ai_response

        trainer = MagicMock()
        trainer.learn_from_interaction.side_effect = RuntimeError("trainer down")
        atomic = patch("utils.db_safety.atomic_transaction")
        patches = _stream_patches() + [
            atomic,
            patch("routes.ai_routes.shared.db"),
            patch("ai_knowledge.trainer.trainer", trainer),
        ]
        for p in patches:
            started = p.start()
            if p is atomic:
                started.return_value.__enter__ = MagicMock()
                started.return_value.__exit__ = MagicMock(return_value=False)
        try:
            chunks = list(_stream_ai_response("hello", {}, "chat"))
        finally:
            for p in reversed(patches):
                p.stop()
        assert any(c.startswith("data: ") for c in chunks)
        trainer.learn_from_interaction.assert_called_once()
