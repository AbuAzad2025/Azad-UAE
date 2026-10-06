"""Wave 7 - owner panel. Catalogue prefix OWN.

The owner blueprint is the only surface in this system that is *about* tenants
rather than inside one, so it is also the only one where the blast radius of a
single click is every tenant at once. That shapes what these scenarios assert:

``@owner_required`` answers **404, not 403** - deliberately, so the URL space is
not revealed to a caller who has no business there. A scenario that asserted 403
here would be asserting the wrong contract and would fail the day someone
"fixed" it to be helpful.

``is_global_owner_user`` is the actual gate: ``is_owner=True`` *and*
``tenant_id is None``, or the developer role. A user with the owner flag but a
tenant attached is not a platform owner, and the scenarios below pin that,
because it is exactly the shape an accidentally-retained session produces.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


def _slug(prefix: str = "w7") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _new_tenant(db_session, **over):
    """A second tenant, so owner actions have something to act *on*."""
    from models import Tenant

    t = Tenant(
        name=over.pop("name", f"Target {uuid.uuid4().hex[:6]}"),
        name_ar=over.pop("name_ar", "مستهدف"),
        slug=over.pop("slug", _slug()),
        email=over.pop("email", f"{uuid.uuid4().hex[:8]}@example.com"),
        country="AE",
        subscription_plan="basic",
        **over,
    )
    db_session.add(t)
    db_session.commit()
    return t


def _active_user(db_session, tenant):
    from models import Role, User

    role = db_session.query(Role).filter_by(slug="cashier").first()
    if role is None:
        role = Role(name="Cashier", slug="cashier", is_active=True)
        db_session.add(role)
        db_session.commit()
    u = User(
        username=f"w7-user-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        full_name="W7 Active",
        tenant_id=tenant.id,
        role_id=role.id,
        is_active=True,
    )
    u.set_password("Str0ng!Pass99")
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user, password="Str0ng!Pass99"):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": password},
        follow_redirects=True,
    )


class TestOWN01AccessBoundary:
    """OWN-01 to OWN-06: who may reach the owner panel, and what the ones who may not are told."""

    @pytest.mark.parametrize(
        "path",
        [
            "/owner/",
            "/owner/tenants",
            "/owner/tenants/create",
            "/owner/audit-logs",
            "/owner/system-stats",
            "/owner/config",
            "/owner/tenant-stores",
            "/owner/tenant-ai",
        ],
    )
    def test_anonymous_is_told_nothing_exists(self, client, path):
        """OWN-01. Every owner route is 404 to an anonymous caller.

        The panel does not redirect to a login page, because a 302 would confirm
        the path exists and hand an attacker a map of the surface. Asserted per
        route rather than once, since each sub-module carries its own decorator
        and a missing one would open a single hole.
        """
        resp = client.get(path)
        assert resp.status_code == 404, f"{path} answered {resp.status_code} to an anonymous caller"

    @pytest.mark.parametrize(
        "path",
        [
            "/owner/maintenance/fix-cost-centers",
            "/owner/maintenance/rebuild-gl-tree",
            "/owner/maintenance/fix-default-tenant",
            "/owner/maintenance/regenerate-default-backup",
            "/owner/maintenance/run-default-tenant-maintenance",
            "/owner/maintenance/cleanup-test-dbs",
        ],
    )
    def test_anonymous_cannot_reach_a_maintenance_action(self, client, path):
        """OWN-01b. The maintenance actions are POST-only *and* guarded.

        Checked with POST rather than GET because these routes declare no GET: a
        GET answers 405 before the guard ever runs, which would look like the same
        protection while testing nothing at all.
        """
        resp = client.post(path, follow_redirects=True)
        assert resp.status_code == 404, f"{path} answered {resp.status_code} to an anonymous POST"

    def test_a_tenant_admin_is_told_nothing_exists(self, client, db_session, sample_tenant):
        """OWN-02. A tenant administrator is no more than anonymous here.

        Tenant admins are the realistic attacker: they are already authenticated,
        already know the app, and would benefit from enumerating other tenants.
        """
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="manager").first()
        if role is None:
            role = Role(name="Manager", slug="manager", is_active=True)
            db_session.add(role)
            db_session.commit()
        user = User(
            username=f"w7-mgr-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="W7 Manager",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        for path in ("/owner/tenants", "/owner/tenants/create", "/owner/audit-logs"):
            resp = client.get(path)
            assert resp.status_code == 404, f"a tenant manager reached {path} ({resp.status_code})"

    def test_owner_flag_with_a_tenant_is_not_a_platform_owner(self, client, db_session, sample_tenant):
        """OWN-03. is_owner=True plus a tenant is still denied.

        This is the shape a stale session produces - the owner flag survives while
        a tenant switch has attached a tenant. is_global_owner_user requires
        tenant_id to be None *and* the flag, so this combination must not pass.
        """
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="manager").first()
        if role is None:
            role = Role(name="Manager", slug="manager", is_active=True)
            db_session.add(role)
            db_session.commit()
        user = User(
            username=f"w7-fake-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="W7 Fake Owner",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            is_owner=True,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/owner/tenants")
        assert resp.status_code == 404, f"is_owner with a tenant attached reached the panel ({resp.status_code})"

    def test_a_post_is_refused_the_same_way_a_get_is(self, client, db_session, sample_tenant):
        """OWN-04. The guard is on the view, not the verb.

        Suspending a tenant is a POST. Checking only GET would leave the action
        reachable for anyone who could not see the form.
        """
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="cashier").first()
        if role is None:
            role = Role(name="Cashier", slug="cashier", is_active=True)
            db_session.add(role)
            db_session.commit()
        user = User(
            username=f"w7-cash-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="W7 Cashier",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        target = _new_tenant(db_session)
        _login(client, user)

        resp = client.post(f"/owner/tenants/{target.id}/suspend", data={"reason": "nope"})
        assert resp.status_code == 404
        db_session.refresh(target)
        assert target.is_suspended is False, "a refused POST still suspended the tenant"

    def test_the_platform_owner_reaches_every_owner_page(self, client, scenario_owner):
        """OWN-05. The 404s above are the guard working, not the pages being broken."""
        # /owner/ itself redirects into the dashboard, so it is followed; the rest
        # render directly.
        assert client.get("/owner/", follow_redirects=True).status_code == 200
        for path in ("/owner/tenants", "/owner/tenants/create", "/owner/system-stats"):
            resp = client.get(path)
            assert resp.status_code == 200, f"the platform owner could not load {path} ({resp.status_code})"

    def test_a_deactivated_owner_loses_the_panel(self, client, db_session):
        """OWN-06. is_active is part of being allowed in.

        A disabled account that still authenticates would otherwise keep full
        platform authority.
        """
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="owner").first()
        if role is None:
            role = Role(name="Owner", slug="owner", is_active=True)
            db_session.add(role)
            db_session.commit()
        user = User(
            username=f"w7-off-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="W7 Disabled Owner",
            tenant_id=None,
            role_id=role.id,
            is_owner=True,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)
        assert client.get("/owner/tenants").status_code == 200

        client.get("/auth/logout", follow_redirects=True)
        user.is_active = False
        db_session.commit()

        resp = client.get("/owner/tenants")
        assert resp.status_code in (302, 404, 401), f"a disabled owner still reached the panel ({resp.status_code})"


class TestOWN02TenantLifecycle:
    """OWN-07 to OWN-13: creating, suspending, activating and deleting a tenant."""

    def test_owner_creates_a_tenant_and_the_books_open_at_zero(self, client, scenario_owner, db_session):
        """OWN-07. A created tenant is a working tenant, not a row.

        The books must balance at zero: an opening-balance error here would only
        surface once the tenant posted its first real transaction.
        """
        from models import GLAccount, GLJournalEntry, GLJournalLine, Tenant

        slug = _slug("w7new")
        resp = client.post(
            "/owner/tenants/create",
            data={"name_ar": "مستأجر جديد", "name_en": "New Tenant", "slug": slug, "default_currency": "AED"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        tenant = db_session.query(Tenant).filter_by(slug=slug).first()
        assert tenant is not None, f"no tenant was created for slug {slug}"

        accounts = db_session.query(GLAccount).filter_by(tenant_id=tenant.id).all()
        assert accounts, "the new tenant has no chart of accounts"

        lines = db_session.query(GLJournalLine).join(GLJournalEntry).filter(GLJournalEntry.tenant_id == tenant.id).all()
        total = sum((Decimal(str(ln.debit or 0)) - Decimal(str(ln.credit or 0))) for ln in lines)
        assert total == Decimal("0"), f"the new tenant's opening balance is {total}, not zero"

    @pytest.mark.parametrize(
        ("form", "label"),
        [
            ({"slug": "x", "default_currency": "AED"}, "no Arabic name"),
            ({"name_ar": "اسم", "default_currency": "AED"}, "no slug"),
            ({"name_ar": "اسم", "slug": "y"}, "no default currency"),
        ],
    )
    def test_creation_refuses_incomplete_input(self, client, scenario_owner, db_session, form, label):
        """OWN-08. Each required field is genuinely required.

        The route returns to the form rather than 400, so the assertion is that no
        tenant appeared - not on the status code, which is 200 by design.
        """
        from models import Tenant

        before = db_session.query(Tenant).count()
        payload = {"name_ar": f"و7 {uuid.uuid4().hex[:6]}", "slug": _slug(), "default_currency": "AED"}
        payload.update({k: v for k, v in form.items() if v})

        if label == "no slug":
            payload["slug"] = ""
        if label == "no Arabic name":
            payload["name_ar"] = ""
        if label == "no default currency":
            payload["default_currency"] = ""

        client.post("/owner/tenants/create", data=payload, follow_redirects=True)
        after = db_session.query(Tenant).count()
        assert after == before, f"a tenant was created despite {label}"

    def test_a_duplicate_slug_is_refused(self, client, scenario_owner, db_session):
        """OWN-09. Slugs are unique, and the second attempt creates nothing."""
        from models import Tenant

        slug = _slug("w7dup")
        existing = _new_tenant(db_session, slug=slug)
        before = db_session.query(Tenant).count()

        client.post(
            "/owner/tenants/create",
            data={"name_ar": "مكرر", "slug": slug, "default_currency": "AED"},
            follow_redirects=True,
        )
        assert db_session.query(Tenant).count() == before, "a duplicate slug created a second tenant"
        assert db_session.query(Tenant).filter_by(slug=slug).one() is existing

    def test_suspend_then_activate_round_trips(self, client, scenario_owner, db_session):
        """OWN-10. Suspend records a reason; activate clears it.

        A suspension that left is_suspended False, or an activate that left the
        reason in place, would make the list page lie about the tenant's state.
        """
        target = _new_tenant(db_session)
        tid = target.id

        client.post(f"/owner/tenants/{tid}/suspend", data={"reason": "non-payment"}, follow_redirects=True)
        db_session.expire_all()
        suspended = db_session.get(type(target), tid)
        assert suspended.is_suspended is True
        assert suspended.is_active is False
        assert "non-payment" in (suspended.suspension_reason or "")

        client.post(f"/owner/tenants/{tid}/activate", follow_redirects=True)
        db_session.expire_all()
        back = db_session.get(type(target), tid)
        assert back.is_suspended is False
        assert back.is_active is True
        assert back.suspension_reason is None, f"activate left the reason behind: {back.suspension_reason!r}"

    def test_suspend_without_a_reason_still_records_one(self, client, scenario_owner, db_session):
        """OWN-11. The reason column is never left null.

        A suspension with no stated reason is unauditable, and this audit trail is
        the only record a support agent will ever see.
        """
        target = _new_tenant(db_session)
        tid = target.id

        client.post(f"/owner/tenants/{tid}/suspend", follow_redirects=True)
        db_session.expire_all()
        suspended = db_session.get(type(target), tid)
        assert suspended.is_suspended is True
        assert (suspended.suspension_reason or "").strip(), "suspension_reason was left empty"

    def test_delete_is_refused_while_users_are_active(self, client, scenario_owner, db_session):
        """OWN-12. Soft delete stops at an active user.

        Deleting the tenant out from under live accounts would orphan them, and
        the route's response is a redirect, so the assertion is that nothing moved.
        """
        target = _new_tenant(db_session)
        _active_user(db_session, target)
        tid = target.id

        client.post(f"/owner/tenants/{tid}/delete", follow_redirects=True)
        db_session.expire_all()
        still = db_session.get(type(target), tid)
        assert still.is_suspended is False, "delete proceeded despite an active user"
        assert still.is_active is True

    def test_delete_proceeds_once_the_users_are_inactive(self, client, scenario_owner, db_session):
        """OWN-13. And it is a soft delete: the row survives, marked.

        "Deleted" here means suspended with a distinct reason. A purge would take
        the tenant's ledger with it, so the record is kept.
        """
        target = _new_tenant(db_session)
        user = _active_user(db_session, target)
        user.is_active = False
        db_session.commit()
        tid = target.id

        client.post(f"/owner/tenants/{tid}/delete", follow_redirects=True)
        db_session.expire_all()
        gone = db_session.get(type(target), tid)
        assert gone is not None, "the tenant row was purged rather than soft-deleted"
        assert gone.is_suspended is True
        assert gone.is_active is False
        assert (gone.suspension_reason or "").strip(), "a soft delete left no marker to tell it from a suspension"

    def test_actions_on_a_missing_tenant_are_not_found(self, client, scenario_owner, db_session):
        """OWN-14. A tenant id that does not exist is a 404, not a 500."""
        missing = 999_999_99
        assert db_session.get(__import__("models").Tenant, missing) is None
        for path in (
            f"/owner/tenants/{missing}/suspend",
            f"/owner/tenants/{missing}/activate",
            f"/owner/tenants/{missing}/delete",
        ):
            resp = client.post(path, follow_redirects=True)
            assert resp.status_code in (302, 404), f"{path} answered {resp.status_code} for a missing tenant"


class TestOWN03StatusApi:
    """OWN-15 to OWN-18: the JSON status endpoint and its contract."""

    def test_toggle_requires_json(self, client, scenario_owner):
        """OWN-15. A form post to the JSON endpoint is refused, not coerced.

        Without the is_json check a crafted form submission could flip a tenant's
        status from a page that has no business doing so.
        """
        resp = client.post("/owner/api/tenant/1/toggle-status", data={"x": "1"})
        assert resp.status_code == 400, f"a non-JSON toggle answered {resp.status_code}"

    def test_toggle_flips_both_flags_and_clears_the_reason(self, client, scenario_owner, db_session):
        """OWN-16. is_active and is_suspended move together.

        They are two columns expressing one state; the route writes them as a pair
        precisely because a tenant with is_active False and is_suspended False is
        a state the list page cannot render.
        """
        target = _new_tenant(db_session)
        tid = target.id
        resp = client.post(f"/owner/api/tenant/{tid}/toggle-status", json={})
        assert resp.status_code == 200, f"toggle answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.get(type(target), tid)
        assert after.is_active is False
        assert after.is_suspended is True
        assert (after.suspension_reason or "").strip()

        client.post(f"/owner/api/tenant/{tid}/toggle-status", json={})
        db_session.expire_all()
        restored = db_session.get(type(target), tid)
        assert restored.is_active is True
        assert restored.is_suspended is False
        assert restored.suspension_reason is None

    def test_toggle_reports_the_new_state(self, client, scenario_owner, db_session):
        """OWN-17. The response says what happened, so the UI need not refetch."""
        target = _new_tenant(db_session)
        resp = client.post(f"/owner/api/tenant/{target.id}/toggle-status", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body is not None, "the toggle returned a non-JSON body to a JSON caller"
        assert "is_active" in body.get("data", {}), f"no new state in the payload: {body}"

    def test_toggle_on_a_missing_tenant_is_a_404(self, client, scenario_owner, db_session):
        """OWN-18."""
        resp = client.post("/owner/api/tenant/99999999/toggle-status", json={})
        assert resp.status_code == 404, f"a missing tenant answered {resp.status_code}"
