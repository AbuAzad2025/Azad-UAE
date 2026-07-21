"""Coverage gap tests for routes/owner/users.py — RBAC, validation, and edge cases.

Targets missing lines: 114-117, 127-128, 139-142, 154-157, 179-224, 274-312.
Uses app_factory + bypass_owner_auth + targeted patches at source modules.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch


from routes.owner import owner_bp
from tests.unit.routes.conftest import _chain_query


def _mock_role(slug="seller", level=10, role_id=2):
    role = MagicMock()
    role.slug = slug
    role.is_active = True
    role.id = role_id
    return role


def _mock_user_entity(**kwargs):
    user = MagicMock()
    user.id = kwargs.get("id", 1)
    user.username = kwargs.get("username", "panel-user")
    user.email = kwargs.get("email", "user@test.com")
    user.is_owner = kwargs.get("is_owner", False)
    user.is_active = kwargs.get("is_active", True)
    user.tenant_id = kwargs.get("tenant_id", 1)
    user.role_id = kwargs.get("role_id", 2)
    user.branch_id = kwargs.get("branch_id", None)
    return user


def _model_query(**terminals):
    q = _chain_query(**terminals)
    fb = q.filter_by.return_value
    fb.first.return_value = terminals.get("first")
    fb.all.return_value = terminals.get("all", [])
    q.get_or_404.return_value = terminals.get("entity")
    return q


def _model_class(**terminals):
    cls = MagicMock(name="model_class")
    cls.query = _model_query(**terminals)
    return cls


@contextmanager
def _users_patches(**overrides):
    """Patches for routes.owner.users — patches at module-level and source-level."""
    role = overrides.get("role") or _mock_role()
    user_entity = overrides.get("user_entity") or _mock_user_entity()
    mock_db = overrides.get("mock_db") or MagicMock()

    role_cls = _model_class(all=[role], entity=role)
    user_cls = _model_class(entity=user_entity)
    branch_cls = _model_class(all=[])
    tenant_cls = _model_class(all=[])

    mock_db.session.get.side_effect = lambda model, pk: role if pk == role.id else MagicMock()

    atomic_mock = MagicMock()
    atomic_mock.return_value.__enter__ = MagicMock()
    atomic_mock.return_value.__exit__ = MagicMock(return_value=False)

    patches = [
        patch("routes.owner.users.render_template", return_value="ok"),
        patch("routes.owner.users.url_for", return_value="/"),
        patch("routes.owner.users.db", mock_db),
        patch("routes.owner.users.User", user_cls),
        patch("routes.owner.users.Branch", branch_cls),
        patch("routes.owner.users.Tenant", tenant_cls),
        patch("routes.owner.users.AuditLog", _model_class(all=[])),
        patch("routes.owner.users.get_active_tenant_id", return_value=1),
        patch("routes.owner.users.role_level_for_user", return_value=100),
        patch("routes.owner.users.role_level_for", return_value=10),
        patch("routes.owner.users.func", MagicMock()),
        patch("models.Role", role_cls),
        patch("utils.branching.role_requires_branch", return_value=False),
        patch("routes.owner.shared._invalidate_owner_changes"),
        patch("utils.db_safety.atomic_transaction", atomic_mock),
        patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        patch("utils.auth_helpers.enforce_company_user_tenant"),
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()


class TestCreateUserValidation:
    """Lines 114-117 (missing username/password), 127-128 (missing role),
    139-142 (weak password), 154-157 (existing user)."""

    def test_missing_username_and_password(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _users_patches():
            resp = app.test_client().post(
                "/owner/users/create",
                data={"email": "test@example.com", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_missing_role_id(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _users_patches():
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "newuser",
                    "password": "Str0ng!Pass123",
                    "email": "new@test.com",
                },
            )
        assert resp.status_code == 200

    def test_weak_password(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _users_patches(),
            patch(
                "utils.password_validator.PasswordValidator.validate",
                return_value=(False, ["too short"]),
            ),
        ):
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "newuser",
                    "password": "weak",
                    "email": "new@test.com",
                    "role_id": "2",
                },
            )
        assert resp.status_code == 200

    def test_existing_user(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        existing = _mock_user_entity(username="exists")
        user_cls = _model_class(first=existing, entity=existing)
        with _users_patches(user_entity=existing), patch("routes.owner.users.User", user_cls):
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "exists",
                    "password": "Str0ng!Pass123",
                    "email": "new@test.com",
                    "role_id": "2",
                },
            )
        assert resp.status_code == 200


class TestCreateUserBranchAndRoleGuards:
    """Lines 169-188 — role_requires_branch + role level escalation check."""

    def test_role_requires_branch_but_none_given(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _users_patches(), patch("utils.branching.role_requires_branch", return_value=True):
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "newuser",
                    "password": "Str0ng!Pass123",
                    "email": "new@test.com",
                    "role_id": "2",
                },
            )
        assert resp.status_code == 200

    def test_role_level_too_high(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _users_patches(), patch("routes.owner.users.role_level_for", return_value=200):
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "newuser",
                    "password": "Str0ng!Pass123",
                    "email": "new@test.com",
                    "role_id": "2",
                },
            )
        assert resp.status_code == 200


class TestCreateUserSuccessAndException:
    """Lines 190-224 — successful creation path + exception handler."""

    def test_successful_user_creation(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        mock_db = MagicMock()
        role = _mock_role()
        mock_db.session.get.side_effect = lambda model, pk: role
        user_cls = _model_class(first=None, entity=None)
        with (
            _users_patches(mock_db=mock_db),
            patch("routes.owner.users.User", user_cls),
            patch(
                "utils.password_validator.PasswordValidator.validate",
                return_value=(True, []),
            ),
        ):
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "newuser",
                    "password": "Str0ng!Pass123",
                    "email": "new@test.com",
                    "role_id": "2",
                    "is_active": "on",
                },
            )
        assert resp.status_code == 302

    def test_create_user_exception_returns_form(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _users_patches(),
            patch(
                "utils.sanitizer.InputSanitizer.sanitize_text",
                side_effect=RuntimeError("sanitize boom"),
            ),
        ):
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "newuser",
                    "password": "Str0ng!Pass123",
                    "email": "new@test.com",
                    "role_id": "2",
                },
            )
        assert resp.status_code == 200

    def test_invalid_email_returns_form(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        from utils.field_validators import FieldValidationError

        with (
            _users_patches(),
            patch(
                "utils.field_validators.normalize_user_email_required",
                side_effect=FieldValidationError("bad email"),
            ),
        ):
            resp = app.test_client().post(
                "/owner/users/create",
                data={
                    "username": "newuser",
                    "password": "Str0ng!Pass123",
                    "email": "invalid",
                    "role_id": "2",
                },
            )
        assert resp.status_code == 200

    def test_get_create_form_with_preselect_tenant(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _users_patches():
            resp = app.test_client().get("/owner/users/create?tenant_id=3")
        assert resp.status_code == 200


class TestEditUserGuards:
    """Lines 271-312 — edit_user branch/role guards + exception handler."""

    def test_edit_role_requires_branch(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        user_entity = _mock_user_entity(id=5)
        user_cls = _model_class(entity=user_entity)
        with (
            _users_patches(user_entity=user_entity),
            patch("routes.owner.users.User", user_cls),
            patch("utils.branching.role_requires_branch", return_value=True),
        ):
            resp = app.test_client().post(
                "/owner/users/5/edit",
                data={"role_id": "2"},
            )
        assert resp.status_code == 200

    def test_edit_role_level_too_high(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        user_entity = _mock_user_entity(id=5)
        user_cls = _model_class(entity=user_entity)
        with (
            _users_patches(user_entity=user_entity),
            patch("routes.owner.users.User", user_cls),
            patch("routes.owner.users.role_level_for", return_value=200),
        ):
            resp = app.test_client().post(
                "/owner/users/5/edit",
                data={"role_id": "2"},
            )
        assert resp.status_code == 200

    def test_edit_invalid_email_returns_form(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        from utils.field_validators import FieldValidationError

        user_entity = _mock_user_entity(id=5)
        user_cls = _model_class(entity=user_entity)
        with (
            _users_patches(user_entity=user_entity),
            patch("routes.owner.users.User", user_cls),
            patch(
                "utils.field_validators.normalize_user_email_required",
                side_effect=FieldValidationError("bad email"),
            ),
        ):
            resp = app.test_client().post(
                "/owner/users/5/edit",
                data={"role_id": "2", "email": "invalid"},
            )
        assert resp.status_code == 200

    def test_edit_successful_redirect(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        user_entity = _mock_user_entity(id=5)
        user_cls = _model_class(entity=user_entity)
        mock_db = MagicMock()
        role = _mock_role()
        mock_db.session.get.side_effect = lambda model, pk: role
        with _users_patches(mock_db=mock_db, user_entity=user_entity), patch("routes.owner.users.User", user_cls):
            resp = app.test_client().post(
                "/owner/users/5/edit",
                data={
                    "role_id": "2",
                    "username": "updated",
                    "email": "updated@test.com",
                    "is_active": "on",
                },
            )
        assert resp.status_code == 302

    def test_edit_exception_returns_form(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        user_entity = _mock_user_entity(id=5)
        user_cls = _model_class(entity=user_entity)
        with (
            _users_patches(user_entity=user_entity),
            patch("routes.owner.users.User", user_cls),
            patch(
                "utils.sanitizer.InputSanitizer.sanitize_text",
                side_effect=RuntimeError("boom"),
            ),
        ):
            resp = app.test_client().post(
                "/owner/users/5/edit",
                data={"role_id": "2", "username": "x", "email": "x@test.com"},
            )
        assert resp.status_code == 200

    def test_edit_get_form(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        user_entity = _mock_user_entity(id=5)
        user_cls = _model_class(entity=user_entity)
        with _users_patches(user_entity=user_entity), patch("routes.owner.users.User", user_cls):
            resp = app.test_client().get("/owner/users/5/edit")
        assert resp.status_code == 200


class TestDeleteUser:
    """Lines 383-399 — delete_user: owner guard, self-delete guard, success/failure."""

    def test_delete_owner_blocked(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        owner_entity = _mock_user_entity(id=10, is_owner=True)
        owner_cls = _model_class(entity=owner_entity)
        with _users_patches(user_entity=owner_entity), patch("routes.owner.users.User", owner_cls):
            resp = app.test_client().post("/owner/users/10/delete")
        assert resp.status_code == 302

    def test_delete_self_blocked(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        self_user = _mock_user_entity(id=1, is_owner=False)
        self_cls = _model_class(entity=self_user)
        with (
            _users_patches(user_entity=self_user),
            patch("routes.owner.users.User", self_cls),
            patch("flask_login.utils._get_user", return_value=self_user),
        ):
            resp = app.test_client().post("/owner/users/1/delete")
        assert resp.status_code == 302

    def test_delete_success(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        target = _mock_user_entity(id=7, is_owner=False)
        target_cls = _model_class(entity=target)
        with _users_patches(user_entity=target), patch("routes.owner.users.User", target_cls):
            resp = app.test_client().post("/owner/users/7/delete")
        assert resp.status_code == 302


class TestUserProfile:
    """Lines 317-372 — user_profile stats rendering."""

    def test_profile_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        target = _mock_user_entity(id=3)
        target_cls = _model_class(entity=target)
        mock_db = MagicMock()
        mock_db.session.query.return_value = _chain_query(scalar=0, count=0, all=[])
        with (
            _users_patches(mock_db=mock_db, user_entity=target),
            patch("routes.owner.users.User", target_cls),
            patch("models.Sale", _model_class()),
            patch("models.Payment", _model_class()),
        ):
            resp = app.test_client().get("/owner/users/3/profile")
        assert resp.status_code == 200


class TestUsersListAndRoles:
    """Lines 33-48 (users_list) + 403-417 (roles_permissions)."""

    def test_users_list_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _users_patches(),
            patch(
                "services.user_service.UserService.get_users_list_context",
                return_value={"users": [], "stats": {}, "active_tenant_id": 1, "tenants": []},
            ),
        ):
            resp = app.test_client().get("/owner/users-list")
        assert resp.status_code == 200

    def test_roles_permissions_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _users_patches(),
            patch(
                "services.role_service.RoleService.get_roles_permissions_context",
                return_value={
                    "roles": [],
                    "permissions": [],
                    "perm_categories": [],
                    "role_user_counts": {},
                },
            ),
        ):
            resp = app.test_client().get("/owner/roles-permissions")
        assert resp.status_code == 200
