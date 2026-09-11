"""Coverage for routes/owner/users.py remainder arcs.

Targets: users_list, create_user email-error/username-missing/role-missing/
weak-password/conflict/branch-required/higher-role/global-owner-null-tenant/
non-global-tenant/generic-exception/preselect arcs, edit_user branch/role/
email-error/password/exception arcs, profile/delete/roles arcs.
Real test-client paths; service/DB boundaries mocked only.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest

from routes.owner import owner_bp
from tests.unit.routes.conftest import _chain_query


def _role(slug="seller", role_id=2):
    r = MagicMock()
    r.slug = slug
    r.id = role_id
    r.is_active = True
    return r


def _entity(**kw):
    u = MagicMock()
    u.id = kw.get("id", 5)
    u.username = kw.get("username", "panel-user")
    u.email = kw.get("email", "user@test.com")
    u.is_owner = kw.get("is_owner", False)
    u.is_active = True
    u.tenant_id = 1
    u.role_id = 2
    u.branch_id = None
    u.full_name = "Full"
    return u


def _model(**kw):
    cls = MagicMock(name="model_class")
    q = _chain_query(**kw)
    cls.query = q
    return cls


@contextmanager
def _base(**over):
    role = over.get("role") or _role()
    user = over.get("user") or _entity()
    mock_db = MagicMock()
    mock_db.session.get.side_effect = lambda model, pk: role
    specs = [
        patch("routes.owner.users.render_template", return_value="ok"),
        patch("routes.owner.users.url_for", return_value="/"),
        patch("routes.owner.users.db", mock_db),
        patch("routes.owner.users.User", _model(entity=user)),
        patch("routes.owner.users.get_active_tenant_id", return_value=1),
        patch("routes.owner.users.role_level_for_user", return_value=100),
        patch("routes.owner.users.role_level_for", return_value=over.get("role_level", 10)),
        patch("services.user_service.UserService.creatable_roles", return_value=[role]),
        patch("services.user_service.UserService.roles_visible_to_level", return_value=[role]),
        patch("services.user_service.UserService.tenant_branches", return_value=[]),
        patch("services.user_service.UserService.active_tenants", return_value=[]),
        patch("services.user_service.UserService.get_role", return_value=role),
        patch(
            "services.user_service.UserService.find_username_conflict_in_tenant",
            return_value=over.get("conflict"),
        ),
        patch("services.user_service.UserService.get_user_or_404", return_value=user),
        patch(
            "services.user_service.UserService.get_users_list_context",
            return_value={"users": [], "stats": {}, "active_tenant_id": 1, "tenants": []},
        ),
        patch(
            "services.user_service.UserService.user_profile_context",
            return_value={"stats": {}, "recent_sales": [], "recent_audits": []},
        ),
        patch("utils.branching.role_requires_branch", return_value=over.get("need_branch", False)),
        patch("utils.auth_helpers.is_global_owner_user", return_value=over.get("global_owner", True)),
        patch(
            "utils.auth_helpers.user_may_have_null_tenant",
            return_value=over.get("may_null", False),
        ),
        patch("utils.auth_helpers.enforce_company_user_tenant"),
        patch("routes.owner.users.atomic_transaction"),
        patch("routes.owner.users._invalidate_owner_changes"),
    ]
    with ExitStack() as stack:
        for spec in specs:
            stack.enter_context(spec)
        yield {"role": role, "user": user}


@pytest.fixture
def owner_users_cov3_client(app_factory, bypass_owner_auth):
    app = app_factory(owner_bp)
    return app.test_client()


class TestUsersList:
    def test_list_ok(self, owner_users_cov3_client):
        with _base():
            assert owner_users_cov3_client.get("/owner/users-list").status_code == 200


class TestCreateUser:
    def test_get_with_preselect(self, owner_users_cov3_client):
        with _base():
            resp = owner_users_cov3_client.get("/owner/users/create?tenant_id=3")
        assert resp.status_code == 200

    def test_email_error_rerenders(self, owner_users_cov3_client):
        from utils.field_validators import FieldValidationError

        with (
            _base(),
            patch(
                "utils.field_validators.normalize_user_email_required",
                side_effect=FieldValidationError("bad email"),
            ),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/create",
                data={"username": "u1", "email": "bad", "password": "Strong1!x"},
            )
        assert resp.status_code == 200

    def test_missing_username_password(self, owner_users_cov3_client):
        with (
            _base(),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
        ):
            resp = owner_users_cov3_client.post("/owner/users/create", data={"username": "", "password": ""})
        assert resp.status_code == 200

    def test_missing_role(self, owner_users_cov3_client):
        with (
            _base(),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/create",
                data={"username": "u1", "email": "a@b.com", "password": "Strong1!x"},
            )
        assert resp.status_code == 200

    def test_weak_password(self, owner_users_cov3_client):
        with (
            _base(),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
            patch("utils.password_validator.PasswordValidator.validate", return_value=(False, ["short"])),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/create",
                data={"username": "u1", "email": "a@b.com", "password": "x", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_username_conflict(self, owner_users_cov3_client):
        with (
            _base(conflict=_entity()),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
            patch("utils.password_validator.PasswordValidator.validate", return_value=(True, [])),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/create",
                data={"username": "dup", "email": "a@b.com", "password": "Strong1!x", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_branch_required(self, owner_users_cov3_client):
        with (
            _base(need_branch=True),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
            patch("utils.password_validator.PasswordValidator.validate", return_value=(True, [])),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/create",
                data={"username": "u1", "email": "a@b.com", "password": "Strong1!x", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_higher_role_blocked(self, owner_users_cov3_client):
        with (
            _base(role_level=999),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
            patch("utils.password_validator.PasswordValidator.validate", return_value=(True, [])),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/create",
                data={"username": "u1", "email": "a@b.com", "password": "Strong1!x", "role_id": "2"},
            )
        assert resp.status_code == 200

    def test_global_owner_null_tenant_success(self, owner_users_cov3_client, bypass_owner_auth):
        bypass_owner_auth.is_owner = True
        with (
            _base(global_owner=True, may_null=True),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
            patch("utils.password_validator.PasswordValidator.validate", return_value=(True, [])),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/create",
                data={
                    "username": "nu",
                    "email": "a@b.com",
                    "password": "Strong1!x",
                    "role_id": "2",
                    "is_owner": "on",
                },
            )
        assert resp.status_code == 302

    def test_non_global_owner_uses_active_tenant(self, owner_users_cov3_client):
        with (
            _base(global_owner=False),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
            patch("utils.password_validator.PasswordValidator.validate", return_value=(True, [])),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/create",
                data={"username": "nu", "email": "a@b.com", "password": "Strong1!x", "role_id": "2"},
            )
        assert resp.status_code == 302

    def test_generic_exception(self, owner_users_cov3_client):
        with (
            _base(),
            patch(
                "utils.field_validators.normalize_user_email_required",
                side_effect=RuntimeError("down"),
            ),
        ):
            resp = owner_users_cov3_client.post("/owner/users/create", data={"username": "u"})
        assert resp.status_code == 200


class TestEditProfileDelete:
    def test_edit_branch_required(self, owner_users_cov3_client):
        with _base(need_branch=True):
            resp = owner_users_cov3_client.post("/owner/users/5/edit", data={"role_id": "2"})
        assert resp.status_code == 200

    def test_edit_higher_role(self, owner_users_cov3_client):
        with _base(role_level=999):
            resp = owner_users_cov3_client.post("/owner/users/5/edit", data={"role_id": "2"})
        assert resp.status_code == 200

    def test_edit_email_error(self, owner_users_cov3_client):
        from utils.field_validators import FieldValidationError

        with (
            _base(),
            patch(
                "utils.field_validators.normalize_user_email_required",
                side_effect=FieldValidationError("bad"),
            ),
        ):
            resp = owner_users_cov3_client.post("/owner/users/5/edit", data={"role_id": "2"})
        assert resp.status_code == 200

    def test_edit_success_with_password(self, owner_users_cov3_client):
        with (
            _base(),
            patch("utils.field_validators.normalize_user_email_required", return_value="a@b.com"),
        ):
            resp = owner_users_cov3_client.post(
                "/owner/users/5/edit",
                data={"username": "nn", "email": "a@b.com", "role_id": "2", "new_password": "New1!xx"},
            )
        assert resp.status_code == 302

    def test_edit_generic_exception(self, owner_users_cov3_client):
        with (
            _base(),
            patch("services.user_service.UserService.get_role", side_effect=Exception("down")),
        ):
            resp = owner_users_cov3_client.post("/owner/users/5/edit", data={"role_id": "2"})
        assert resp.status_code == 200

    def test_profile_ok(self, owner_users_cov3_client):
        with _base():
            assert owner_users_cov3_client.get("/owner/users/5/profile").status_code == 200

    def test_delete_owner_blocked(self, owner_users_cov3_client):
        with _base(user=_entity(is_owner=True)):
            assert owner_users_cov3_client.post("/owner/users/5/delete").status_code == 302

    def test_delete_self_blocked(self, owner_users_cov3_client, bypass_owner_auth):
        me = _entity(id=bypass_owner_auth.id)
        with _base(user=me):
            assert owner_users_cov3_client.post(f"/owner/users/{me.id}/delete").status_code == 302

    def test_delete_success_and_exception(self, owner_users_cov3_client):
        with _base(user=_entity(id=9)):
            assert owner_users_cov3_client.post("/owner/users/9/delete").status_code == 302
        with (
            _base(user=_entity(id=9)),
            patch("routes.owner.users.atomic_transaction", side_effect=Exception("down")),
        ):
            assert owner_users_cov3_client.post("/owner/users/9/delete").status_code == 302

    def test_roles_permissions(self, owner_users_cov3_client):
        with (
            _base(),
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
            assert owner_users_cov3_client.get("/owner/roles-permissions").status_code == 200
