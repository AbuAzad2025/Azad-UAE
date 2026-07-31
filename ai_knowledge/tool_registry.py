"""
Central AI Tool Registry — Dual-Layer Zero-Trust RBAC (Master Directive).

Single source of truth describing every tool the AI assistant may expose:

- **Layer 1 (Pre-LLM filtering):** ``get_tools_for_user(user)`` builds the
  ``tools`` payload dynamically from the user's permissions — unpermitted
  tools never reach the model context at all.
- **Layer 2 (Execution guard):** remains enforced in
  ``ai_knowledge.action_dispatcher.ActionDispatcher.dispatch`` before any
  database operation; this module never bypasses it.

Tools are bridged automatically from the ActionDispatcher registry +
``tool_schemas.ACTION_ARG_MODELS`` (so the 16 core ERP actions stay in one
place), and additional standalone tools may be exposed via the
``@register_ai_tool`` decorator.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Standalone decorator-registered tools (name -> metadata)
_STANDALONE_TOOLS: dict[str, dict[str, Any]] = {}


def register_ai_tool(
    *,
    name: str,
    description: str,
    permission: str,
    schema: type,
    confirm_required: bool = False,
) -> Callable:
    """Decorator exposing a Python function as an AI-callable tool.

    The decorated function must accept a single ``args: dict`` parameter and
    return an ``ActionResult``-compatible object. Registration is metadata
    only — execution always flows through the dispatcher's RBAC guard.
    """

    def _decorator(func: Callable) -> Callable:
        _STANDALONE_TOOLS[name] = {
            "name": name,
            "description": description,
            "permission": permission,
            "schema": schema,
            "handler": func,
            "confirm_required": confirm_required,
            "source": "decorator",
        }
        return func

    return _decorator


def get_tool_registry() -> dict[str, dict[str, Any]]:
    """Unified metadata for every AI tool (dispatcher-bridged + decorator).

    Returns ``{name: {name, description, permission, schema, confirm_required,
    handler, source}}``. Dispatcher tools are the canonical core actions;
    decorator-registered tools may extend or document overrides.
    """
    from ai_knowledge.action_dispatcher import action_dispatcher
    from ai_knowledge.tool_schemas import ACTION_ARG_MODELS

    registry: dict[str, dict[str, Any]] = {}
    for action_type in action_dispatcher.get_registered_actions():
        meta = action_dispatcher.get_action_metadata(action_type) or {}
        schema_entry = ACTION_ARG_MODELS.get(action_type)
        registry[action_type] = {
            "name": action_type,
            "description": (schema_entry[1] if schema_entry else meta.get("description", "")),
            "permission": meta.get("permission", ""),
            "schema": schema_entry[0] if schema_entry else None,
            "handler": meta.get("handler"),
            "confirm_required": bool(meta.get("confirm_required")),
            "source": "dispatcher",
        }
    registry.update(_STANDALONE_TOOLS)
    return registry


def _is_owner_user(user) -> bool:
    return bool(getattr(user, "is_owner", False))


def _user_has_permission(user, permission: str) -> bool:
    checker = getattr(user, "has_permission", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(permission))
    except Exception:
        logger.debug("Permission check failed for %s", permission, exc_info=True)
        return False


def user_can_use_tool(user, meta: dict[str, Any]) -> bool:
    """Zero-trust check: may ``user`` see/execute the tool described by ``meta``?"""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _is_owner_user(user):
        return True
    permission = meta.get("permission") or ""
    if not permission:
        # Read-only / conversational tools with no permission requirement
        return True
    return _user_has_permission(user, permission)


def get_tools_for_user(user) -> list[dict[str, Any]]:
    """Layer 1 — OpenAI/Groq ``tools`` payload filtered by user permissions.

    Owners receive 100% of tools; other roles receive only tools whose
    permission they hold (plus permission-free read-only tools). Unpermitted
    tools are strictly hidden from the model context. Returns ``[]`` when the
    user has no actionable tools (pure conversational mode).
    """
    tools: list[dict[str, Any]] = []
    for name, meta in get_tool_registry().items():
        schema = meta.get("schema")
        if schema is None:
            continue
        if not user_can_use_tool(user, meta):
            continue
        params = schema.model_json_schema()
        params.pop("title", None)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": meta.get("description") or name,
                    "parameters": params,
                },
            }
        )
    return tools


def get_permitted_tool_names(user) -> list[str]:
    """Names of tools the user may use (diagnostics/tests)."""
    return [name for name, meta in get_tool_registry().items() if user_can_use_tool(user, meta)]
