"""Stage 5 regressions: legacy delegation, tenant feedback, audit/cache hooks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import ai_knowledge.action_dispatcher as dispatcher_module
from ai_knowledge.learning.continuous_learner import evaluate_and_learn
from routes.ai_routes.actions import _process_user_action


def _user():
    return SimpleNamespace(
        id=7,
        tenant_id=1,
        is_authenticated=True,
        is_owner=False,
        has_permission=lambda code: False,
    )


def test_legacy_wizard_keeps_direct_callers_compatible():
    """Direct wizard callers keep their legacy contract after consolidation.

    The chat route tries ActionDispatcher first; the wizard is only a fallback
    for interactive/malformed flows and must not change for existing callers.
    """
    with patch("routes.ai_routes.actions._conversation_ctx", return_value={}):
        result = _process_user_action("رصيد", _user())
    assert isinstance(result, str) and result
    assert "لا يوجد تينانت" not in result


def test_interactive_wizard_stays_available():
    with patch("routes.ai_routes.actions._conversation_ctx", return_value={}):
        result = _process_user_action("رصيد", _user())
    assert "رصيد" in result


def test_successful_dispatch_invalidates_tenant_reads():
    dispatcher = dispatcher_module.ActionDispatcher()
    dispatcher._registry = {
        "probe": {
            "permission": "",
            "confirm_required": False,
            "handler": lambda _args: dispatcher_module.ActionResult(True, "ok"),
        }
    }
    with (
        patch.object(dispatcher_module, "_get_active_tenant_id", return_value=1),
        patch("ai_knowledge.cognitive.read_cache.invalidate_tenant_reads") as invalidate,
    ):
        result = dispatcher.dispatch("probe", {})

    assert result.success is True
    invalidate.assert_called_once_with(1)


def test_failed_dispatch_does_not_invalidate_reads():
    dispatcher = dispatcher_module.ActionDispatcher()
    dispatcher._registry = {
        "probe": {
            "permission": "",
            "confirm_required": False,
            "handler": lambda _args: dispatcher_module.ActionResult(False, "denied"),
        }
    }
    with (
        patch.object(dispatcher_module, "_get_active_tenant_id", return_value=1),
        patch("ai_knowledge.cognitive.read_cache.invalidate_tenant_reads") as invalidate,
    ):
        result = dispatcher.dispatch("probe", {})

    assert result.success is False
    invalidate.assert_not_called()


def test_continuous_learner_feedback_is_tenant_scoped():
    service = MagicMock()
    service.ask_genius.return_value = {"answer": " grounded "}
    memory = MagicMock()
    service.get_learning_system.return_value = memory

    evaluate_and_learn(
        [
            {
                "question": "sales?",
                "expected_keywords": ["grounded"],
                "context": {"tenant_id": 42},
            }
        ],
        ai_service=service,
    )

    memory.learn_from_interaction.assert_called_once()
    assert memory.learn_from_interaction.call_args.kwargs["tenant_id"] == 42


def test_continuous_learner_error_feedback_is_tenant_scoped():
    service = MagicMock()
    service.ask_genius.side_effect = RuntimeError("boom")
    memory = MagicMock()
    service.get_learning_system.return_value = memory

    evaluate_and_learn(
        [{"question": "sales?", "expected_keywords": ["x"], "context": {"tenant_id": 9}}],
        ai_service=service,
    )

    assert memory.learn_from_interaction.call_args.kwargs["tenant_id"] == 9
