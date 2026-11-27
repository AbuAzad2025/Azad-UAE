"""Stage 1 security regressions: no tenant-owner bypass, execute gating, CSRF."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from utils.ai_permissions import user_has_ai_permission

ROOT = Path(__file__).resolve().parents[3]


def _tenant_owner(*, permitted: bool = False):
    return SimpleNamespace(
        id=1,
        tenant_id=1,
        is_authenticated=True,
        is_active=True,
        is_owner=True,
        role=SimpleNamespace(slug="owner"),
        has_permission=lambda _code: permitted,
    )


def _platform_owner():
    return SimpleNamespace(
        id=2,
        tenant_id=None,
        is_authenticated=True,
        is_active=True,
        is_owner=True,
        role=SimpleNamespace(slug="owner"),
        has_permission=lambda _code: True,
    )


def test_tenant_owner_is_not_platform_authority_in_dispatcher():
    import ai_knowledge.action_dispatcher as dispatcher_module

    with patch.object(dispatcher_module, "current_user", _tenant_owner()):
        assert dispatcher_module._is_owner() is False


def test_platform_owner_is_still_platform_authority_in_dispatcher():
    import ai_knowledge.action_dispatcher as dispatcher_module

    with patch.object(dispatcher_module, "current_user", _platform_owner()):
        assert dispatcher_module._is_owner() is True


def test_tenant_owner_without_permission_is_denied_by_dispatcher():
    import ai_knowledge.action_dispatcher as dispatcher_module

    dispatcher = dispatcher_module.ActionDispatcher()
    with (
        patch.object(dispatcher_module, "current_user", _tenant_owner()),
        patch.object(dispatcher_module, "_log_ai_error"),
    ):
        result = dispatcher.dispatch("create_sale", {"customer_name": "x", "product_name": "y"})

    assert result.success is False
    assert result.needs_permission == "manage_sales"


def test_tenant_owner_with_permission_is_not_blocked_by_dispatcher_gate():
    import ai_knowledge.action_dispatcher as dispatcher_module

    with patch.object(dispatcher_module, "current_user", _tenant_owner(permitted=True)):
        assert dispatcher_module._is_owner() is False
        assert dispatcher_module._has_permission("manage_sales") is True


def test_ai_permission_matrix_does_not_grant_tenant_owner_blanket_access():
    assert user_has_ai_permission("create_sale", _tenant_owner()) is False
    assert user_has_ai_permission("unknown_action", _tenant_owner()) is False
    assert user_has_ai_permission("create_sale", _platform_owner()) is True


def test_wizard_coarse_gate_requires_platform_authority_or_erp_permission():
    from routes.ai_routes import _user_can_ai_execute_actions

    assert _user_can_ai_execute_actions(_tenant_owner()) is False
    assert _user_can_ai_execute_actions(_tenant_owner(permitted=True)) is True
    assert _user_can_ai_execute_actions(_platform_owner()) is True


def test_execute_capability_map_uses_the_registered_endpoint_name():
    source = (ROOT / "routes" / "ai_routes" / "__init__.py").read_text(encoding="utf-8")

    assert '"ai.add_customer": "execute"' in source
    assert "ai.system_add_customer" not in source


def test_ai_routes_are_not_csrf_exempt():
    for path in (ROOT / "routes" / "ai_routes").glob("*.py"):
        assert "@csrf.exempt" not in path.read_text(encoding="utf-8"), path.name


def test_basic_ai_level_blocks_mutation_endpoint(ai_client):
    state = {
        "allowed": True,
        "global_enabled": True,
        "tenant_enabled": True,
        "tenant_id": 1,
        "reason": None,
        "is_platform_user": False,
        "ai_level": "basic",
    }
    with patch("routes.ai_routes.get_ai_access_state", return_value=state):
        resp = ai_client.post(
            "/ai/system/add-customer",
            json={"name": "probe"},
            headers={"Accept": "application/json"},
        )

    assert resp.status_code == 403
    assert resp.get_json()["meta"]["required"] == "execute"
