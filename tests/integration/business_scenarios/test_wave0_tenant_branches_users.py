"""Wave 0 - tenant, branches and users.

Everything downstream depends on this wave: a product cannot be sold without a
warehouse, a warehouse needs a branch, and a branch needs a tenant. Each test
drives the real endpoints as a signed-in platform owner or admin and then checks
what the database and the ledger actually contain.

The scenarios assert more than "200 OK". Tenant creation claims to provision an
accounting structure, so S-01 checks that the accounts exist and that the
transaction left the books balanced at zero.
"""

from __future__ import annotations

import uuid

import pytest


class TestS01CreateTenant:
    """S-01: a new tenant is created from the owner panel."""

    def test_tenant_create_provisions_gl_accounts_and_leaves_books_balanced(
        self, client, scenario_owner, db_session, ledger
    ):
        unique = str(uuid.uuid4())[:8]
        slug = f"wave0-{unique}"
        resp = client.post(
            "/owner/tenants/create",
            data={
                "name_ar": "شركة الموجة صفر",
                "slug": slug,
                "default_currency": "AED",
                "enable_pos": "on",
            },
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302), resp.data[:400]

        from models import GLAccount, Tenant

        tenant = Tenant.query.filter_by(slug=slug).one()

        # The chart of accounts must exist for a tenant that cannot post a
        # single journal entry without it. Baseline is 98 base accounts.
        accounts = GLAccount.query.filter_by(tenant_id=tenant.id).all()
        assert len(accounts) >= 90, f"expected the base chart, got {len(accounts)}"

        # The control and revenue anchors the revenue cycle posts against.
        codes = {a.code for a in accounts}
        for required in ("1130", "1140", "2110", "4100", "5100"):
            assert required in codes, f"missing core account {required}"

        # Provisioning must not invent transactions.
        assert ledger.balance("1130", tenant.id) == 0
        assert ledger.balance("4100", tenant.id) == 0
        assert ledger.entries(tenant.id) == []

    def test_duplicate_slug_is_rejected(self, client, scenario_owner, db_session):
        from models import Tenant

        unique = str(uuid.uuid4())[:8]
        first = Tenant(
            name=f"Dup {unique}",
            name_ar="مكرر",
            slug=f"dup-{unique}",
            email=f"dup-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(first)
        db_session.commit()

        resp = client.post(
            "/owner/tenants/create",
            data={
                "name_ar": "مكرر ثان",
                "slug": f"dup-{unique}",
                "default_currency": "AED",
            },
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302)
        # Only the original survives.
        assert Tenant.query.filter_by(slug=f"dup-{unique}").count() == 1

    def test_missing_required_slug_is_rejected(self, client, scenario_owner, db_session):
        from models import Tenant

        before = Tenant.query.count()
        resp = client.post(
            "/owner/tenants/create",
            data={"name_ar": "بلا معرّف", "default_currency": "AED"},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302)
        assert Tenant.query.count() == before, "tenant created without a slug"


class TestS02Branches:
    """S-02: branches, including the one the sale path resolves warehouses by.

    Branches attach to the session's active tenant, not to a tenant_id posted in
    the form - routes/branches.py:39 reads get_active_tenant_id(current_user) and
    ignores anything sent in the body. So the scenario switches context the way an
    owner actually does, through /tenants/switch, instead of posting a tenant_id
    and assuming it is honoured.
    """

    def test_create_two_branches_and_mark_one_main(self, client, scenario_owner, db_session, sample_tenant):
        from models import Branch

        unique = str(uuid.uuid4())[:6].upper()
        client.get(f"/tenants/switch/{sample_tenant.id}", follow_redirects=True)

        resp = client.post(
            "/branches/create",
            data={"name": f"HQ {unique}", "code": f"HQ{unique}", "is_main": "on"},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302)

        resp = client.post(
            "/branches/create",
            data={"name": f"Branch 2 {unique}", "code": f"B2{unique}"},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302)

        created = Branch.query.filter(
            Branch.tenant_id == sample_tenant.id,
            Branch.code.in_([f"HQ{unique}", f"B2{unique}"]),
        ).all()
        assert len(created) == 2, f"expected 2 branches, got {len(created)}"
        assert sum(1 for b in created if b.is_main) == 1, "expected exactly one main"

    def test_duplicate_branch_code_in_same_tenant_is_rejected(self, client, scenario_owner, db_session, sample_tenant):
        from models import Branch

        unique = str(uuid.uuid4())[:6].upper()
        client.get(f"/tenants/switch/{sample_tenant.id}", follow_redirects=True)

        first = client.post(
            "/branches/create",
            data={"name": f"First {unique}", "code": f"DC{unique}"},
            follow_redirects=True,
        )
        assert first.status_code in (200, 302)
        assert Branch.query.filter_by(tenant_id=sample_tenant.id, code=f"DC{unique}").count() == 1

        dup = client.post(
            "/branches/create",
            data={"name": f"Second {unique}", "code": f"DC{unique}"},
            follow_redirects=True,
        )
        assert dup.status_code in (200, 302)
        assert Branch.query.filter_by(tenant_id=sample_tenant.id, code=f"DC{unique}").count() == 1, (
            "duplicate branch code accepted within one tenant"
        )


class TestS03UserAndRole:
    """S-03: a cashier, which is the most restricted seeded role."""

    @pytest.fixture
    def cashier_role(self, db_session):
        from models import Role

        role = Role.query.filter_by(slug="cashier").first()
        if role is None:
            role = Role(name="Cashier", slug="cashier", is_active=True)
            db_session.add(role)
            db_session.commit()
        return role

    def test_cashier_requires_a_branch(self, client, scenario_owner, cashier_role):
        """A non-global role has no meaningful tenant-wide scope, so branch is
        mandatory. Posting without one must not create the user."""
        import uuid as _uuid

        from models import User

        unique = str(_uuid.uuid4())[:8]
        resp = client.post(
            "/owner/users/create",
            data={
                "username": f"cash-{unique}",
                "email": f"cash-{unique}@example.com",
                "password": "Str0ng!Pass99",
                "role_id": cashier_role.id,
                "branch_id": "",
                "tenant_id": "",
            },
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302)
        assert User.query.filter_by(username=f"cash-{unique}").count() == 0, "cashier created without a branch"

    def test_weak_password_is_rejected(self, client, scenario_owner, cashier_role):
        """MIN_LENGTH 10 plus upper, lower, digit and a special character."""
        import uuid as _uuid

        from models import User

        unique = str(_uuid.uuid4())[:8]
        resp = client.post(
            "/owner/users/create",
            data={
                "username": f"weak-{unique}",
                "email": f"weak-{unique}@example.com",
                "password": "password",
                "role_id": cashier_role.id,
                "branch_id": "1",
            },
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302)
        assert User.query.filter_by(username=f"weak-{unique}").count() == 0

    def test_cashier_cannot_reach_the_ledger(self, client, db_session, sample_tenant, sample_branch, cashier_role):
        """Cashier is seeded without view_ledger. The guard must hold over HTTP,
        not just in a unit test of the decorator."""
        from models import User

        unique = str(uuid.uuid4())[:8]
        user = User(
            username=f"nocash-{unique}",
            email=f"nocash-{unique}@example.com",
            full_name="No Cash",
            tenant_id=sample_tenant.id,
            role_id=cashier_role.id,
            branch_id=sample_branch.id,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()

        client.post(
            "/auth/login",
            data={"username": user.username, "password": "Str0ng!Pass99"},
            follow_redirects=True,
        )
        resp = client.get("/ledger/")
        assert resp.status_code == 403, f"cashier reached the ledger ({resp.status_code})"


class TestS04RolePermissionBoundary:
    """S-04: the same operation, two roles, different outcomes."""

    def test_cashier_denied_and_admin_allowed_on_the_same_route(self, db_session, client, sample_tenant, sample_branch):
        from models import Permission, Role, User

        def make(username, permission_codes):
            """Build a role carrying exactly the permissions under test.

            The roles are constructed here rather than looked up by slug. Both the
            seeder's `cashier` and its `accountant` are tenant-scoped seed data, so
            depending on them made this test report "not applicable" whenever the
            test database had not been through system_init - and the permission
            boundary went unasserted exactly when the environment was least
            trustworthy.

            Naming the deciding permission is also what makes the assertion
            readable: the only difference between the two users is view_ledger.
            """
            unique = str(uuid.uuid4())[:8]
            role = Role(name=f"BN {username} {unique}", slug=f"bn-{username}-{unique}", is_active=True)
            role.permissions = Permission.query.filter(Permission.code.in_(permission_codes)).all()
            assert role.permissions, f"these permissions are not in the DB: {permission_codes}"
            # The role has to be in the session before the cascade to permissions
            # and to the user below means anything; a bare constructor leaves
            # role_id NULL behind and the permission check then denies everyone.
            db_session.add(role)
            db_session.flush()
            user = User(
                username=f"{username}-{unique}",
                email=f"{username}-{unique}@example.com",
                full_name=username,
                tenant_id=sample_tenant.id,
                role_id=role.id,
                branch_id=sample_branch.id,
            )
            user.set_password("Str0ng!Pass99")
            db_session.add(user)
            db_session.commit()
            return user

        # Sales-side permissions, deliberately no view_ledger.
        cashier = make("bn-cash", ["manage_sales", "view_sales", "view_products"])
        client.post(
            "/auth/login",
            data={"username": cashier.username, "password": "Str0ng!Pass99"},
            follow_redirects=True,
        )
        denied = client.get("/ledger/")
        assert denied.status_code == 403, f"a role without view_ledger reached the ledger ({denied.status_code})"

        client.get("/auth/logout", follow_redirects=True)
        admin = make("bn-acc", ["view_ledger", "manage_ledger", "manage_accounting"])
        client.post(
            "/auth/login",
            data={"username": admin.username, "password": "Str0ng!Pass99"},
            follow_redirects=True,
        )
        allowed = client.get("/ledger/")
        assert allowed.status_code == 200, f"view_ledger still denied the ledger ({allowed.status_code})"
