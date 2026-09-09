"""
Real regression tests for the branch-delete guard.

Prevents the production 500 (IntegrityError on RESTRICT FKs like
gl_accounts.branch_id) from ever reaching the owner again: deleting a
branch with linked accounting data must redirect with an explanation,
never crash; deleting a clean branch must actually delete.

No mocks: real tenant/branch/GL rows, real HTTP, real assertions.
"""

import uuid


def _uid():
    return str(uuid.uuid4())[:8]


def _make_tenant(db_session):
    from models import Tenant

    tid = _uid()
    t = Tenant(
        name=f"DelGuard {tid}",
        name_ar=f"DelGuard {tid}",
        slug=f"delguard-{tid}",
        default_currency="ILS",
        base_currency="ILS",
        is_active=True,
    )
    db_session.add(t)
    db_session.flush()
    return t


def _make_owner(db_session):
    from models import Role, User

    suffix = _uid()
    role = Role.query.filter_by(slug="developer").first()
    if not role:
        role = Role(name=f"OwnerRole_{suffix}", slug="developer", is_active=True)
        db_session.add(role)
        db_session.flush()
    u = User(
        tenant_id=None,
        username=f"owner_{suffix}",
        email=f"owner_{suffix}@test.com",
        is_active=True,
        password_hash="fakehash",
        role_id=role.id,
        is_owner=True,
    )
    u.set_password("ownerpass")
    db_session.add(u)
    db_session.flush()
    return u


class TestBranchDeleteGuardReal:
    def _setup(self, db_session):
        from models import Branch
        from models.gl import GLAccount

        tenant = _make_tenant(db_session)
        owner = _make_owner(db_session)
        linked = Branch(tenant_id=tenant.id, name=f"Linked {_uid()}", code=f"LK{_uid()[:4].upper()}")
        db_session.add(linked)
        db_session.flush()
        db_session.add(
            GLAccount(
                tenant_id=tenant.id,
                code=f"GL{_uid()[:4].upper()}",
                name="Linked Account",
                type="asset",
                branch_id=linked.id,
            )
        )
        clean = Branch(tenant_id=tenant.id, name=f"Clean {_uid()}", code=f"CL{_uid()[:4].upper()}")
        db_session.add(clean)
        db_session.flush()
        db_session.commit()
        return tenant, owner, linked, clean

    def _login_and_switch(self, client, owner, tenant):
        assert (
            client.post(
                "/auth/login",
                data={"username": owner.username, "password": "ownerpass"},
                follow_redirects=False,
            ).status_code
            == 302
        )
        # Login auto-picks the first active tenant; a real owner switches
        # to the working tenant explicitly before managing its branches.
        resp = client.get(f"/tenants/switch/{tenant.id}", follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_linked_branch_redirects_without_500(self, app, db_session):
        from models import Branch

        tenant, owner, linked, _ = self._setup(db_session)
        bid = linked.id
        with app.test_client() as client:
            self._login_and_switch(client, owner, tenant)
            resp = client.post(f"/branches/delete/{bid}", follow_redirects=False)
            assert resp.status_code == 302
        with app.app_context():
            # blocked by the guard: row survives, no IntegrityError crash
            assert db_session.get(Branch, bid) is not None

    def test_delete_clean_branch_actually_deletes(self, app, db_session):
        from models import Branch

        tenant, owner, _, clean = self._setup(db_session)
        bid = clean.id
        with app.test_client() as client:
            self._login_and_switch(client, owner, tenant)
            resp = client.post(f"/branches/delete/{bid}", follow_redirects=False)
            assert resp.status_code == 302
        with app.app_context():
            assert db_session.get(Branch, bid) is None
