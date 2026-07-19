from __future__ import annotations

import logging
from typing import Any

from flask_login import current_user

logger = logging.getLogger(__name__)

from extensions import db
from models.system_settings import SystemSettings
from models.tenant import Tenant
from utils.auth_helpers import is_global_owner_user
from utils.tenanting import get_active_tenant_id


def get_tenant_ai_level(tenant_id: int | None, default: str = "execute") -> str:
    level = str(default or "execute").strip().lower()
    if tenant_id is None:
        return level
    try:
        settings = SystemSettings.get_current()
        levels = settings.get_custom_setting("tenant_ai_levels", {}) or {}
        raw = str(levels.get(str(int(tenant_id)), level) or level).strip().lower()
        if raw in ("basic", "advanced", "execute"):
            return raw
    except Exception:
        logger.debug(
            "Failed to resolve tenant AI level for tenant %s", tenant_id, exc_info=True
        )
    return level


def set_tenant_ai_level(tenant_id: int, level: str) -> str:
    level = str(level or "execute").strip().lower()
    if level not in ("basic", "advanced", "execute"):
        level = "execute"
    settings = SystemSettings.get_current()
    levels = settings.get_custom_setting("tenant_ai_levels", {}) or {}
    levels[str(int(tenant_id))] = level
    settings.set_custom_setting("tenant_ai_levels", levels)
    return level


def get_ai_access_state(user=None) -> dict:
    """Return effective AI access state for current user/tenant."""
    user = user or current_user
    state: dict[str, Any] = {
        "allowed": False,
        "global_enabled": True,
        "tenant_enabled": None,
        "tenant_id": None,
        "reason": None,
        "is_platform_user": False,
        "ai_level": "execute",
    }

    if not user or not getattr(user, "is_authenticated", False):
        state["reason"] = "unauthenticated"
        return state

    try:
        settings = SystemSettings.get_current()
        state["global_enabled"] = bool(getattr(settings, "enable_ai_assistant", True))
    except Exception:
        state["global_enabled"] = True

    state["is_platform_user"] = is_global_owner_user(user)
    if state["is_platform_user"]:
        # Platform owner/developer can access AI management surfaces
        # even when tenant/global AI is disabled.
        state["allowed"] = True
        state["ai_level"] = "execute"
        return state

    tenant_id = get_active_tenant_id(user)
    state["tenant_id"] = tenant_id
    if tenant_id is None:
        state["reason"] = "missing_tenant"
        return state

    tenant = db.session.get(Tenant, int(tenant_id))
    if not tenant or not getattr(tenant, "is_active", False):
        state["tenant_enabled"] = False
        state["reason"] = "tenant_inactive"
        return state

    state["tenant_enabled"] = bool(getattr(tenant, "enable_ai", True))
    state["ai_level"] = get_tenant_ai_level(int(tenant_id), default="execute")
    if not state["global_enabled"]:
        state["reason"] = "global_disabled"
        return state
    if not state["tenant_enabled"]:
        state["reason"] = "tenant_disabled"
        return state

    state["allowed"] = True
    return state


def ai_level_allows(ai_level: str, capability: str) -> bool:
    """Capabilities by level:
    - basic: chat + light insights
    - advanced: basic + analytics/predictions
    - execute: advanced + DB-mutating AI actions
    """
    ai_level = str(ai_level or "basic").lower()
    capability = str(capability or "basic").lower()
    order = {"basic": 1, "advanced": 2, "execute": 3}
    return order.get(ai_level, 1) >= order.get(capability, 1)
