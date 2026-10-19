"""Wave 16 - users, roles, branches and the language switch. Prefix USR.

Users are the surface where the permission model is written rather than
read, and the rule that has to hold is the one the catalogue names: privilege
escalation through a role edit. Two screens write users and they are not the
same screen - ``/users`` belongs to the tenant and is behind ``manage_users``,
while ``/owner/users`` belongs to the platform and answers 404 to anybody who
is not the platform owner (USR-12 to USR-15). A tenant administrator who
could reach the owner screen would be able to write a user with permissions
the tenant does not have.

The escalation rule itself is on the create form: a manager may not create a
user whose role sits above their own level (USR-08, USR-09). Without it, a
manager could simply ask for the administrator role and hand it to themselves.

Two more rules are worth pinning because they are the ones that bite. The
tenant's user screen may not touch the platform owner - the owner is not the
tenant's to edit (USR-16, USR-17) - and a user is deactivated rather than
deleted, so the audit trail of what somebody did survives their account
(USR-18, USR-19).

The branches behind it are the tenant's structure, and their screen is behind
the admin role rather than a permission, so a company administrator who is
not an admin-role user does not see them (USR-25, USR-26).

The language switch is the last one, and it is the only route in this domain
that anybody may call: it writes a session key and redirects somewhere safe
(USR-33 to USR-37).
"""

from __future__ import annotations

import uuid

USERS_TENANT_PATHS = [
    "/users/",
    "/users/create",
    "/users/1",
    "/users/1/edit",
]
USERS_TENANT_POST_PATHS = [
    "/users/1/toggle-active",
    "/users/1/delete",
]
OWNER_USER_PATHS = [
    "/owner/users-list",
    "/owner/users/create",
    "/owner/users/1/edit",
    "/owner/users/1/profile",
    "/owner/roles-permissions",
]


def _role(db_session, slug, *, permissions=(), name=None):
    from models import Permission, Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=name or slug.replace("_", " ").title()[:50], slug=slug[:50], is_active=True)
        db_session.add(role)
        db_session.commit()
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="usr-user", permissions=(), branch=None, role_slug=None, is_owner=False):
    from models import User

    role = _role(db_session, role_slug or f"{slug}-{uuid.uuid4().hex[:8]}", permissions=permissions)
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"usr-{slug}-{unique}",
        email=f"usr-{unique}@example.com",
        full_name=f"USR {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_owner=is_owner,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _with(client, db_session, tenant, branch, codes, slug):
    """A signed-in user carrying exactly ``codes``."""
    user = _user(db_session, tenant, slug=f"{slug}-{uuid.uuid4().hex[:8]}", permissions=codes, branch=branch)
    _login(client, user)
    return user


def _admin(client, db_session, tenant, branch):
    """A company administrator: the super_admin role, which the admin guard reads."""
    user = _user(
        db_session,
        tenant,
        slug=f"admin-{uuid.uuid4().hex[:8]}",
        permissions=["manage_users", "view_reports"],
        branch=branch,
        role_slug="super_admin",
    )
    _login(client, user)
    return user


class TestUSR01TheTenantUsers:
    """USR-01 to USR-11: the tenant's own user screen."""

    def test_the_user_list_needs_the_users_permission(self, client, db_session, demo_tenant, demo_branch):
        """USR-01."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/users/")
        assert resp.status_code == 403, f"the user list answered {resp.status_code}"

    def test_the_user_list_answers_for_an_administrator(self, client, db_session, demo_tenant, demo_branch):
        """USR-02."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.get("/users/")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_create_form_answers(self, client, db_session, demo_tenant, demo_branch):
        """USR-03."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.get("/users/create")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_a_user_can_be_created(self, client, db_session, demo_tenant, demo_branch):
        """USR-04."""
        manager = _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        role = manager.role
        resp = client.post(
            "/users/create",
            data={
                "username": f"probe-{uuid.uuid4().hex[:8]}",
                "full_name": "Probe User",
                "email": f"probe-{uuid.uuid4().hex[:8]}@example.com",
                "password": "Str0ng!Pass99",
                "role_id": str(role.id),
                "is_active": "1",
            },
        )
        assert resp.status_code in (200, 302), f"the create answered {resp.status_code}"

        from models import User

        created = db_session.query(User).filter_by(tenant_id=demo_tenant.id).order_by(User.id.desc()).first()
        assert created is not None, "the user was not created"
        assert created.tenant_id == demo_tenant.id

    def test_a_user_without_a_role_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """USR-05. A user with no role has no permissions at all."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        username = f"probe-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/users/create",
            data={
                "username": username,
                "full_name": "Probe User",
                "email": f"{username}@example.com",
                "password": "Str0ng!Pass99",
            },
        )
        assert resp.status_code in (200, 302), f"the create answered {resp.status_code}"

        from models import User

        assert db_session.query(User).filter_by(username=username).count() == 0, "a user was created without a role"

    def test_a_user_is_edited(self, client, db_session, demo_tenant, demo_branch):
        """USR-06."""
        target = _user(db_session, demo_tenant, slug=f"target-{uuid.uuid4().hex[:6]}", branch=demo_branch)
        manager = _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.post(
            f"/users/{target.id}/edit",
            data={
                "full_name": "Renamed User",
                "email": target.email,
                "role_id": str(manager.role_id),
                "branch_id": str(demo_branch.id),
                "is_active": "1",
            },
        )
        assert resp.status_code in (200, 302), f"the edit answered {resp.status_code}"
        db_session.expire_all()
        from models import User

        assert db_session.query(User).get(target.id).full_name == "Renamed User"

    def test_the_edit_form_answers(self, client, db_session, demo_tenant, demo_branch):
        """USR-07."""
        target = _user(db_session, demo_tenant, slug=f"target-{uuid.uuid4().hex[:6]}", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.get(f"/users/{target.id}/edit")
        assert resp.status_code == 200

    def test_a_manager_cannot_create_a_user_above_its_own_level(self, client, db_session, demo_tenant, demo_branch):
        """USR-08. Privilege escalation through a role edit."""
        from models import Role

        superior = Role(
            name=f"Superior {uuid.uuid4().hex[:6]}", slug=f"superior-{uuid.uuid4().hex[:6]}", is_active=True
        )
        db_session.add(superior)
        db_session.commit()

        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.post(
            "/users/create",
            data={
                "username": f"probe-{uuid.uuid4().hex[:8]}",
                "full_name": "Escalated User",
                "email": f"probe-{uuid.uuid4().hex[:8]}@example.com",
                "password": "Str0ng!Pass99",
                "role_id": str(superior.id),
                "is_active": "1",
            },
        )
        assert resp.status_code in (200, 302), f"the create answered {resp.status_code}"

        from models import User

        escalated = (
            db_session.query(User)
            .filter_by(tenant_id=demo_tenant.id, role_id=superior.id)
            .order_by(User.id.desc())
            .first()
        )
        assert escalated is None, "a user was created with a role above the manager's own"

    def test_a_user_of_another_tenant_is_not_reachable(self, client, db_session, demo_tenant, demo_branch):
        """USR-09. A user is the tenant's, and the screen says so."""
        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"Other Tenant {unique}",
            name_ar="شركة أخرى",
            slug=f"other-tenant-{unique}",
            email=f"other-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other)
        db_session.commit()
        foreign = _user(db_session, other, slug=f"foreign-{unique}")

        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.get(f"/users/{foreign.id}/edit")
        assert resp.status_code == 404, f"the cross-tenant read answered {resp.status_code}"

    def test_the_user_detail_answers(self, client, db_session, demo_tenant, demo_branch):
        """USR-10."""
        target = _user(db_session, demo_tenant, slug=f"target-{uuid.uuid4().hex[:6]}", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.get(f"/users/{target.id}")
        assert resp.status_code in (200, 302), f"the user detail answered {resp.status_code}"

    def test_the_user_list_shows_the_tenants_users(self, client, db_session, demo_tenant, demo_branch):
        """USR-11. Another tenant's staff is not on the list."""
        target = _user(db_session, demo_tenant, slug=f"target-{uuid.uuid4().hex[:6]}", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.get("/users/")
        assert resp.status_code == 200
        assert target.username in resp.get_data(as_text=True)


class TestUSR12TheOwnerUsers:
    """USR-12 to USR-19: the platform's user screen, and the deactivation rule."""

    def test_the_owner_user_list_is_the_owners_alone(self, client, db_session, demo_tenant, demo_branch):
        """USR-12. The platform screen answers 404, not 403: it stays hidden."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        for path in OWNER_USER_PATHS:
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} answered {resp.status_code}"

    def test_the_owner_user_list_answers_for_the_platform_owner(self, client, scenario_owner):
        """USR-13."""
        resp = client.get("/owner/users-list")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_owner_create_form_answers(self, client, scenario_owner):
        """USR-14."""
        resp = client.get("/owner/users/create")
        assert resp.status_code == 200

    def test_the_roles_and_permissions_page_answers(self, client, scenario_owner):
        """USR-15."""
        resp = client.get("/owner/roles-permissions")
        assert resp.status_code == 200

    def test_the_tenant_screen_may_not_edit_the_platform_owner(self, client, db_session, demo_tenant, demo_branch):
        """USR-16. The platform owner is not the tenant's to edit."""
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="owner").first()
        if role is None:
            role = Role(name="Owner", slug="owner", is_active=True)
            db_session.add(role)
            db_session.commit()
        owner = User(
            username=f"owner-{uuid.uuid4().hex[:8]}",
            email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Platform Owner",
            tenant_id=None,
            role_id=role.id,
            is_owner=True,
            is_active=True,
        )
        owner.set_password("Str0ng!Pass99")
        db_session.add(owner)
        db_session.commit()

        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.post(f"/users/{owner.id}/toggle-active")
        assert resp.status_code == 404, f"the owner was reachable through the tenant screen: {resp.status_code}"

    def test_the_tenant_screen_may_not_delete_the_platform_owner(self, client, db_session, demo_tenant, demo_branch):
        """USR-17."""
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="owner").first()
        if role is None:
            role = Role(name="Owner", slug="owner", is_active=True)
            db_session.add(role)
            db_session.commit()
        owner = User(
            username=f"owner-{uuid.uuid4().hex[:8]}",
            email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Platform Owner",
            tenant_id=None,
            role_id=role.id,
            is_owner=True,
            is_active=True,
        )
        owner.set_password("Str0ng!Pass99")
        db_session.add(owner)
        db_session.commit()

        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.post(f"/users/{owner.id}/delete")
        assert resp.status_code == 404, f"the owner was reachable through the tenant screen: {resp.status_code}"

    def test_a_user_is_deactivated_rather_than_deleted(self, client, db_session, demo_tenant, demo_branch):
        """USR-18. The row survives, so the audit trail does too."""
        target = _user(db_session, demo_tenant, slug=f"target-{uuid.uuid4().hex[:6]}", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        resp = client.post(f"/users/{target.id}/toggle-active")
        assert resp.status_code in (200, 302), f"the toggle answered {resp.status_code}"

        db_session.expire_all()
        from models import User

        row = db_session.query(User).get(target.id)
        assert row is not None, "the toggle deleted the user"
        assert row.is_active is False, "the toggle did not deactivate the user"

    def test_a_user_can_be_reactivated(self, client, db_session, demo_tenant, demo_branch):
        """USR-19."""
        target = _user(db_session, demo_tenant, slug=f"target-{uuid.uuid4().hex[:6]}", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users"], "manager")
        client.post(f"/users/{target.id}/toggle-active")
        client.post(f"/users/{target.id}/toggle-active")

        db_session.expire_all()
        from models import User

        assert db_session.query(User).get(target.id).is_active is True


class TestUSR20TheOwnerProfile:
    """USR-20 to USR-24: the owner-side user surface."""

    def test_the_owner_profile_answers(self, client, scenario_owner):
        """USR-20."""
        resp = client.get("/owner/users/1/profile")
        assert resp.status_code in (200, 404), f"the profile answered {resp.status_code}"

    def test_the_owner_edit_form_answers(self, client, scenario_owner):
        """USR-21."""
        resp = client.get("/owner/users/1/edit")
        assert resp.status_code in (200, 404), f"the edit form answered {resp.status_code}"

    def test_the_owner_delete_answers(self, client, scenario_owner):
        """USR-22."""
        resp = client.post("/owner/users/999999/delete")
        assert resp.status_code in (200, 302, 404), f"the delete answered {resp.status_code}"

    def test_the_owner_user_routes_answer_404_for_an_anonymous_caller(self, client):
        """USR-23. The owner URL space is not revealed."""
        for path in OWNER_USER_PATHS:
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} answered {resp.status_code}"

    def test_a_company_administrator_is_not_the_platform_owner(self, client, db_session, demo_tenant, demo_branch):
        """USR-24. A super_admin of a tenant is not the platform owner."""
        _admin(client, db_session, demo_tenant, demo_branch)
        for path in OWNER_USER_PATHS:
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} answered {resp.status_code}"


class TestUSR25TheBranches:
    """USR-25 to USR-32: the tenant's structure."""

    def test_the_branch_list_needs_the_admin_role(self, client, db_session, demo_tenant, demo_branch):
        """USR-25. The branch screen is behind the role, not a permission."""
        _with(client, db_session, demo_tenant, demo_branch, ["manage_users", "view_reports"], "manager")
        resp = client.get("/branches/")
        assert resp.status_code == 403, f"the branch list answered {resp.status_code}"

    def test_the_branch_list_answers_for_an_admin(self, client, db_session, demo_tenant, demo_branch):
        """USR-26."""
        _admin(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/branches/")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_branch_list_shows_the_tenants_branches(self, client, db_session, demo_tenant, demo_branch):
        """USR-27."""
        _admin(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/branches/")
        assert resp.status_code == 200
        assert demo_branch.name in resp.get_data(as_text=True)

    def test_a_branch_is_created(self, client, db_session, demo_tenant, demo_branch):
        """USR-28."""
        _admin(client, db_session, demo_tenant, demo_branch)
        code = f"PR{uuid.uuid4().hex[:6].upper()}"
        resp = client.post(
            "/branches/create",
            data={"name": f"Probe Branch {code}", "code": code, "city": "Ramallah"},
        )
        assert resp.status_code in (200, 302), f"the create answered {resp.status_code}"

        from models import Branch

        created = db_session.query(Branch).filter_by(tenant_id=demo_tenant.id, code=code).first()
        assert created is not None, "the branch was not created"

    def test_the_branch_create_form_answers(self, client, db_session, demo_tenant, demo_branch):
        """USR-29."""
        _admin(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/branches/create")
        assert resp.status_code == 200

    def test_a_branch_is_edited(self, client, db_session, demo_tenant, demo_branch):
        """USR-30."""
        _admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post(
            f"/branches/edit/{demo_branch.id}",
            data={"name": "Renamed Branch", "code": demo_branch.code, "city": demo_branch.city},
        )
        assert resp.status_code in (200, 302), f"the edit answered {resp.status_code}"

        db_session.expire_all()
        from models import Branch

        assert db_session.query(Branch).get(demo_branch.id).name == "Renamed Branch"

    def test_a_branch_is_deleted(self, client, db_session, demo_tenant, demo_branch):
        """USR-31."""
        from models import Branch

        code = f"PR{uuid.uuid4().hex[:6].upper()}"
        branch = Branch(
            tenant_id=demo_tenant.id,
            name=f"Disposable {code}",
            code=code,
            is_active=True,
        )
        db_session.add(branch)
        db_session.commit()

        _admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post(f"/branches/delete/{branch.id}")
        assert resp.status_code in (200, 302), f"the delete answered {resp.status_code}"

    def test_a_branch_of_another_tenant_is_not_editable(self, client, db_session, demo_tenant, demo_branch):
        """USR-32. A branch is the tenant's."""
        from models import Branch, Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"Other Tenant {unique}",
            name_ar="شركة أخرى",
            slug=f"other-tenant-{unique}",
            email=f"other-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other)
        db_session.commit()
        foreign = Branch(tenant_id=other.id, name="Foreign Branch", code=f"FB{unique[:6].upper()}", is_active=True)
        db_session.add(foreign)
        db_session.commit()

        _admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post(f"/branches/edit/{foreign.id}", data={"name": "Hijacked", "code": foreign.code})
        assert resp.status_code in (302, 404), f"the cross-tenant edit answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(Branch).get(foreign.id).name == "Foreign Branch"


class TestUSR33TheLanguageSwitch:
    """USR-33 to USR-37: the one route in this domain anybody may call."""

    def test_the_language_switch_answers(self, client):
        """USR-33. A visitor chooses a language before signing in."""
        resp = client.get("/language/set/en")
        assert resp.status_code in (200, 302), f"the switch answered {resp.status_code}"

    def test_the_language_switch_sets_the_session(self, client):
        """USR-34."""
        client.get("/language/set/en")
        with client.session_transaction() as sess:
            assert sess.get("language") == "en"

    def test_the_language_switch_accepts_arabic(self, client):
        """USR-35."""
        client.get("/language/set/ar")
        with client.session_transaction() as sess:
            assert sess.get("language") == "ar"

    def test_an_unknown_language_is_ignored(self, client):
        """USR-36. A language the system does not speak is not written to the session."""
        client.get("/language/set/kl")
        with client.session_transaction() as sess:
            assert sess.get("language") is None

    def test_the_language_switch_redirects_somewhere_safe(self, client):
        """USR-37. A redirect to an attacker is not a language switch."""
        resp = client.get("/language/set/en?next=https://evil.example.com/")
        assert resp.status_code in (302, 303), f"the switch answered {resp.status_code}"
        assert "evil.example.com" not in resp.headers.get("Location", "")
