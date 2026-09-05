"""AI action packs — independent domain modules, one registry.

Each pack (cheques / cheque_lifecycle / returns / purchase_returns /
quotations / catalog / payroll_processing) owns its handlers, command
patterns, and help lines. This package only wires them — with LAZY imports
so merely importing the package never loads a pack (import-cycle safe by
construction; packs load on first register/match/help call, when the
dispatcher core is guaranteed complete):

- :func:`register_action_packs` — called once from
  ``ActionDispatcher._ensure_packs``; every action still flows through the
  dispatcher's RBAC + schema + confirmation + audit guards.
- :func:`match_pack_command` — tried first by
  ``ActionDispatcher.parse_chat_action``; legacy patterns stay untouched.
- :data:`EXTRA_ACTION_ARG_MODELS` — merged into ``tool_schemas`` so the LLM
  discovers pack tools natively with the same permission filtering.

To add a domain: create ``ai_knowledge/actions/<domain>.py`` with
``PATTERNS`` / ``register()`` / ``HELP_LINES`` and append it to
:func:`_packs`. No core file grows.
"""

from __future__ import annotations

import logging

from ai_knowledge.actions.schemas import EXTRA_ACTION_ARG_MODELS

logger = logging.getLogger(__name__)

__all__ = [
    "EXTRA_ACTION_ARG_MODELS",
    "register_action_packs",
    "match_pack_command",
    "get_pack_help_lines",
    "get_pack_action_names",
]


def _packs():
    """Import pack modules on first use (lazy — never at package import)."""
    from ai_knowledge.actions import (
        catalog,
        cheque_lifecycle,
        cheques,
        payroll_processing,
        purchase_returns,
        quotations,
        returns,
    )

    return (cheques, cheque_lifecycle, returns, purchase_returns, quotations, catalog, payroll_processing)


def register_action_packs(register_fn) -> None:
    """Register every pack on the dispatcher registry (called once)."""
    for pack in _packs():
        pack.register(register_fn)


def match_pack_command(message: str):
    """Match a message against pack command patterns.

    Returns ``(action_type, args)`` or ``None``. Pack patterns run before
    the legacy dispatcher patterns so explicit new commands resolve
    deterministically.
    """
    msg = (message or "").strip()
    if not msg:
        return None
    for pack in _packs():
        for pattern, builder in getattr(pack, "PATTERNS", ()):
            try:
                match = pattern.match(msg)
            except Exception as exc:
                logger.debug("Pack pattern match skipped for %s: %s", getattr(pack, "__name__", pack), exc)
                continue
            if match:
                try:
                    hit = builder(match)
                except Exception as exc:
                    logger.debug("Pack command build skipped for %s: %s", getattr(pack, "__name__", pack), exc)
                    continue
                if hit:
                    return hit
    return None


def get_pack_help_lines() -> list[str]:
    """Help lines contributed by every pack (appended to format_help)."""
    lines: list[str] = []
    for pack in _packs():
        lines.extend(getattr(pack, "HELP_LINES", ()))
    return lines


def get_pack_action_names() -> list[str]:
    """Action names contributed by packs (diagnostics/tests)."""
    return sorted(EXTRA_ACTION_ARG_MODELS.keys())
