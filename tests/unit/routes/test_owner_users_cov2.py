"""Coverage for routes/owner/users.py — lines 289, ranges 145-148, 161-162,
171-172, 185-188. Test client + service/DB boundary mocks only.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from routes.owner import owner_bp
from tests.unit.routes.conftest import _chain_query


def _role(slug="seller", role_id=2):
    r = MagicMock()
    r.slug = slug
    r.id = role_id
    r.is_active = True
    return r


def _user_entity(**kw):
    u = MagicMock()
    u.id = kw.get("id", 5)
    u.username = kw.get("username", "panel-user")
    u.email = kw.get("email", "user@test.com")
    u.is_owner = kw.get("is_owner", False)
    u.is_active = True
    u.tenant_id = kw.get("tenant_id", 1)
    u.role_id = 2
    u.branch_id = None
    return u


def _model_class(**terminals):
    cls = MagicMock(name="model_class")
    q = _chain_query(**terminals)
    fb = q.filter_by.return_value
    fb.first.return_value = terminals.get("first")
    fb.all.return_value = terminals.get("all", [])
    q.get_or_404.return_value = terminals.get("entity")
    cls.query = q
    return cls


@contextmanager
def _patches(**overrides):
    role = overrides.get("role") or _role()
    user_entity = overrides.get("user_entity") or _user_entity()
    mock_db = overrides.get("mock_db") or MagicMock()
    mock_db.session.get.side_effect = lambda model, pk: role if pk == role.id else MagicMock()
    atomic = MagicMock()
    atomic.return_value.__enter__ = MagicMock()
    atomic.return_value.__exit__ = MagicMock(return_value=False)
    role_cls = _model_class(all=[role], entity=role)
    user_cls = overrides.get("user_cls") or _model_class(entity=user_entity)
    patches = [
        patch("routes.owner.users.render_template", return_value="ok"),
        patch("routes.owner.users.url_for", return_value="/"),
        patch("routes.owner.users.db", mock_db),
        patch("routes.owner.users.User", user_cls),
        patch("models.User", user_cls),
        patch("models.Role", role_cls),
        patch("routes.owner.users.get_active_tenant_id", return_value=1),
        patch("routes.owner.users.role_level_for_user", return_value=100),
        patch("routes.owner.users.role_level_for", return_value=10),
        patch("services.user_service.UserService.get_role", return_value=role),
        patch(
            "services.user_service.UserService.find_username_conflict_in_tenant",
            return_value=overrides.get("conflict"),
        ),
        patch(
            "services.user_service.UserService.creatable_roles",
            return_value=[role],
        ),
        patch("services.user_service.UserService.tenant_branches", return_value=[]),
        patch("services.user_service.UserService.active_tenants", return_value=[]),
        patch("services.user_service.UserService.get_user_or_404", return_value=user_entity),
        patch("utils.branching.role_requires_branch", return_value=False),
        patch("routes.owner.shared._invalidate_owner_changes"),
        patch("utils.db_safety.atomic_transaction", atomic),
        patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        patch("utils.auth_helpers.enforce_company_user_tenant"),
        patch(
            "utils.password_validator.PasswordValidator.validate",
            return_value=(True, []),
        ),
    ]
    for p in patches:
        p.start()
    try:
        yield {"role": role, "user": user_entity, "db": mock_db}
    finally:
        for p in reversed(patches):
            p.stop()


def _create_payload(**kw):
    data = {
        "username": "newuser",
        "password": "Str0ng!Pass123",
        "email": "new@test.com",
        "role_id": "2",
        "is_active": "on",
    }
    data.update(kw)
    return data


class TestUsernameConflict:
    """Range 145-148 — duplicate username in target tenant."""

    def test_conflict_returns_form(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        existing = _user_entity(username="dupuser")
        with _patches(conflict=existing):
            resp = app.test_client().post("/owner/users/create", data=_create_payload(username="dupuser"))
        assert resp.status_code == 200


class TestBranchAndLevelGuards:
    """Ranges 161-162 (branch required) and 171-172 (level too high)."""

    def test_branch_required_returns_form(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _patches(),
            patch("utils.branching.role_requires_branch", return_value=True),
        ):
            resp = app.test_client().post("/owner/users/create", data=_create_payload())
        assert resp.status_code == 200

    def test_level_too_high_returns_form(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _patches(),
            patch("routes.owner.users.role_level_for", return_value=500),
        ):
            resp = app.test_client().post("/owner/users/create", data=_create_payload())
        assert resp.status_code == 200


class TestGlobalOwnerTenantBranches:
    """Range 185-188 — global owner null-tenant vs form-tenant paths."""

    def test_null_tenant_path(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _patches(),
            patch("utils.auth_helpers.is_global_owner_user", return_value=True),
            patch("utils.auth_helpers.user_may_have_null_tenant", return_value=True),
        ):
            resp = app.test_client().post("/owner/users/create", data=_create_payload())
        assert resp.status_code == 302

    def test_form_tenant_path(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _patches(),
            patch("utils.auth_helpers.is_global_owner_user", return_value=True),
            patch("utils.auth_helpers.user_may_have_null_tenant", return_value=False),
        ):
            resp = app.test_client().post(
                "/owner/users/create",
                data=_create_payload(tenant_id="7"),
            )
        assert resp.status_code == 302


class TestEditNewPassword:
    """Line 289 — new_password hashing branch."""

    def test_edit_with_new_password(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        target = _user_entity(id=5)
        user_cls = _model_class(entity=target)
        with (
            _patches(user_entity=target, user_cls=user_cls),
            patch("routes.owner.users.User", user_cls),
        ):
            resp = app.test_client().post(
                "/owner/users/5/edit",
                data={
                    "role_id": "2",
                    "username": "updated",
                    "email": "updated@test.com",
                    "is_active": "on",
                    "new_password": "N3w-Str0ng!Pass",
                },
            )
        assert resp.status_code == 302
