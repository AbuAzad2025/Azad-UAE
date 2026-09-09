"""Coverage for models/events.py duplicate-registration guards (lines 296, 304)."""

from __future__ import annotations


class TestAiListenerDuplicateGuard:
    def test_register_ai_listeners_second_call_returns_early(self, mocker):
        """Line 296: second call hits `if not _mark("ai"): return`."""
        reg = mocker.patch("services.events_ai_service.register_ai_event_listeners")

        from models.events import register_ai_listeners

        register_ai_listeners()
        register_ai_listeners()
        reg.assert_called_once()

    def test_register_neural_listeners_second_call_returns_early(self, mocker):
        """Line 304: second call hits `if not _mark("neural_training"): return`."""
        reg = mocker.patch("services.events_ai_service.register_neural_event_listeners")

        from models.events import register_neural_training_listeners

        register_neural_training_listeners()
        register_neural_training_listeners()
        reg.assert_called_once()
