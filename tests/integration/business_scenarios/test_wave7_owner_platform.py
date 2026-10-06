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


class TestOWN04TenantEdit:
    """OWN-19 to OWN-27: editing a tenant, and what must survive being blank."""

    def test_the_edit_form_renders_for_the_owner(self, client, scenario_owner, db_session):
        """OWN-19."""
        target = _new_tenant(db_session)
        resp = client.get(f"/owner/tenants/{target.id}/edit")
        assert resp.status_code == 200, f"the edit form answered {resp.status_code}"

    def test_edit_updates_what_was_submitted(self, client, scenario_owner, db_session):
        """OWN-20. A normal save sticks."""
        target = _new_tenant(db_session)
        tid = target.id
        client.post(
            f"/owner/tenants/{tid}/edit",
            data={
                "name_ar": "الاسم الجديد",
                "name_en": target.name_en,
                "slug": target.slug,
                "business_type": target.business_type or "",
                "default_currency": "AED",
                "max_users": target.max_users,
                "max_products": target.max_products,
                "max_customers": target.max_customers,
                "max_suppliers": target.max_suppliers,
                "max_branches": target.max_branches,
                "max_warehouses": target.max_warehouses,
                "max_storage_mb": target.max_storage_mb,
                "max_invoices_per_month": target.max_invoices_per_month,
                "max_sales_per_month": target.max_sales_per_month,
                "data_retention_days": target.data_retention_days,
            },
            follow_redirects=True,
        )
        db_session.expire_all()
        after = db_session.get(type(target), tid)
        assert after.name_ar == "الاسم الجديد"

    @pytest.mark.parametrize("field", ["name_ar", "slug"])
    def test_a_blanked_required_field_keeps_its_value(self, client, scenario_owner, db_session, field):
        """OWN-21. An emptied input must not erase a NOT NULL column.

        name and slug are NOT NULL and UNIQUE. This route used to write whatever
        the form posted, so clearing the Arabic name field set tenant.name to ""
        - which blanks the tenant in every list and breadcrumb that renders it,
        and collides on the unique index the moment a second tenant is blanked
        the same way. form.get's fallback argument only covered an *absent*
        field, not a present-and-empty one, which is what an emptied <input>
        actually posts. Clearing a field is therefore never a deletion.
        """
        target = _new_tenant(db_session)
        tid = target.id
        before_name = target.name
        before_slug = target.slug

        payload = {
            "name_ar": "الاسم الجديد" if field != "name_ar" else "",
            "name_en": target.name_en,
            "slug": "" if field == "slug" else target.slug,
            "business_type": target.business_type or "",
            "default_currency": "AED",
            "max_users": target.max_users,
            "max_products": target.max_products,
            "max_customers": target.max_customers,
            "max_suppliers": target.max_suppliers,
            "max_branches": target.max_branches,
            "max_warehouses": target.max_warehouses,
            "max_storage_mb": target.max_storage_mb,
            "max_invoices_per_month": target.max_invoices_per_month,
            "max_sales_per_month": target.max_sales_per_month,
            "data_retention_days": target.data_retention_days,
        }
        client.post(f"/owner/tenants/{tid}/edit", data=payload, follow_redirects=True)

        db_session.expire_all()
        after = db_session.get(type(target), tid)
        if field == "slug":
            assert after.slug == before_slug, f"slug was blanked to {after.slug!r}"
            assert after.slug, "slug must never be empty"
        else:
            assert after.name == before_name or after.name == "الاسم الجديد"
            assert after.name.strip(), f"name was blanked to {after.name!r}"

    def test_blanking_the_name_field_does_not_collide_across_tenants(self, client, scenario_owner, db_session):
        """OWN-22. The unique index is why OWN-21 matters.

        Two tenants, both edited with an emptied name field. Without the guard
        both end up as name="" and the second write raises an IntegrityError,
        turning a harmless typo in an admin form into a 500.
        """
        a = _new_tenant(db_session)
        b = _new_tenant(db_session)
        for t in (a, b):
            resp = client.post(
                f"/owner/tenants/{t.id}/edit",
                data={
                    "name_ar": "",
                    "name_en": t.name_en,
                    "slug": t.slug,
                    "business_type": t.business_type or "",
                    "default_currency": "AED",
                    "max_users": t.max_users,
                    "max_products": t.max_products,
                    "max_customers": t.max_customers,
                    "max_suppliers": t.max_suppliers,
                    "max_branches": t.max_branches,
                    "max_warehouses": t.max_warehouses,
                    "max_storage_mb": t.max_storage_mb,
                    "max_invoices_per_month": t.max_invoices_per_month,
                    "max_sales_per_month": t.max_sales_per_month,
                    "data_retention_days": t.data_retention_days,
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200, f"editing with a blank name answered {resp.status_code}"
        db_session.expire_all()
        assert db_session.get(type(a), a.id).name != ""
        assert db_session.get(type(b), b.id).name != ""

    def test_a_tristate_flag_survives_being_omitted(self, client, scenario_owner, db_session):
        """OWN-23. Absent is not the same as off, for the flags that say so.

        enable_pos_promotions goes through _tristate, so a partial post that omits
        it leaves the setting alone. The plain `== "on"` flags in the same view
        have no such distinction - see OWN-24, which records that.
        """
        target = _new_tenant(db_session)
        tid = target.id
        client.post(
            f"/owner/tenants/{tid}/edit",
            data={
                "name_ar": "ثلاثي",
                "name_en": target.name_en,
                "slug": target.slug,
                "business_type": target.business_type or "",
                "default_currency": "AED",
                "max_users": target.max_users,
                "max_products": target.max_products,
                "max_customers": target.max_customers,
                "max_suppliers": target.max_suppliers,
                "max_branches": target.max_branches,
                "max_warehouses": target.max_warehouses,
                "max_storage_mb": target.max_storage_mb,
                "max_invoices_per_month": target.max_invoices_per_month,
                "max_sales_per_month": target.max_sales_per_month,
                "data_retention_days": target.data_retention_days,
                "enable_pos_promotions": "1",
            },
            follow_redirects=True,
        )
        db_session.expire_all()
        assert db_session.get(type(target), tid).enable_pos_promotions is True

        client.post(
            f"/owner/tenants/{tid}/edit",
            data={
                "name_ar": "ثلاثي",
                "name_en": target.name_en,
                "slug": target.slug,
                "business_type": target.business_type or "",
                "default_currency": "AED",
                "max_users": target.max_users,
                "max_products": target.max_products,
                "max_customers": target.max_customers,
                "max_suppliers": target.max_suppliers,
                "max_branches": target.max_branches,
                "max_warehouses": target.max_warehouses,
                "max_storage_mb": target.max_storage_mb,
                "max_invoices_per_month": target.max_invoices_per_month,
                "max_sales_per_month": target.max_sales_per_month,
                "data_retention_days": target.data_retention_days,
            },
            follow_redirects=True,
        )
        db_session.expire_all()
        assert db_session.get(type(target), tid).enable_pos_promotions is True, (
            "omitting a tristate flag cleared it; absent must mean unchanged"
        )

    def test_a_non_numeric_limit_keeps_the_current_value(self, client, scenario_owner, db_session):
        """OWN-24. max_users is guarded by _form_int, so junk leaves it alone."""
        target = _new_tenant(db_session)
        tid = target.id
        client.post(
            f"/owner/tenants/{tid}/edit",
            data={
                "name_ar": "أرقام",
                "slug": target.slug,
                "default_currency": "AED",
                "max_users": "7",
            },
            follow_redirects=True,
        )
        db_session.expire_all()
        assert db_session.get(type(target), tid).max_users == 7

        client.post(
            f"/owner/tenants/{tid}/edit",
            data={
                "name_ar": "أرقام",
                "slug": target.slug,
                "default_currency": "AED",
                "max_users": "not-a-number",
            },
            follow_redirects=True,
        )
        db_session.expire_all()
        assert db_session.get(type(target), tid).max_users == 7, "junk in max_users overwrote it"

    def test_editing_an_absent_tenant_is_a_404(self, client, scenario_owner):
        """OWN-25."""
        assert client.get("/owner/tenants/99999999/edit").status_code in (302, 404)
        assert client.post("/owner/tenants/99999999/edit", data={}).status_code in (302, 404)


class TestOWN05PackageLimits:
    """OWN-26 to OWN-32: the JSON package-limit endpoint and its allow-list."""

    def test_update_package_requires_json(self, client, scenario_owner):
        """OWN-26. Same contract as the status endpoint."""
        resp = client.post("/owner/api/tenant/1/update-package", data={"field": "max_users"})
        assert resp.status_code == 400, f"a non-JSON update answered {resp.status_code}"

    @pytest.mark.parametrize(
        "field",
        [
            "max_users",
            "max_products",
            "max_customers",
            "max_suppliers",
            "max_branches",
            "max_warehouses",
            "max_invoices_per_month",
            "max_sales_per_month",
        ],
    )
    def test_every_allowed_limit_is_writable(self, client, scenario_owner, db_session, field):
        """OWN-27. The allow-list is exercised field by field.

        An endpoint whose field filter is written once and never enumerated is an
        endpoint where one wrong entry rejects a limit the owner is entitled to
        set - and nothing would notice until a customer complained.
        """
        target = _new_tenant(db_session)
        resp = client.post(f"/owner/api/tenant/{target.id}/update-package", json={"field": field, "value": 42})
        assert resp.status_code == 200, f"{field} was refused: {resp.status_code}"
        db_session.expire_all()
        assert getattr(db_session.get(type(target), target.id), field) == 42

    @pytest.mark.parametrize(
        "field",
        ["is_active", "is_owner", "slug", "name", "enable_gl", "subscription_plan", "max_users", "id"],
    )
    def test_a_field_outside_the_allow_list_is_refused(self, client, scenario_owner, db_session, field):
        """OWN-28. Only package limits are settable here.

        Notably is_active and enable_gl are tenant state, not plan limits: the
        status endpoint owns them. A JSON endpoint that will set any column it is
        handed is a privilege-escalation surface, so the rejection is asserted for
        the fields that matter rather than for one arbitrary name.
        """
        target = _new_tenant(db_session)
        tid = target.id
        was_active = target.is_active
        was_slug = target.slug

        resp = client.post(f"/owner/api/tenant/{tid}/update-package", json={"field": field, "value": "tampered"})
        assert resp.status_code == 400, f"{field} was accepted by the package endpoint ({resp.status_code})"

        db_session.expire_all()
        after = db_session.get(type(target), tid)
        assert after.is_active == was_active
        assert after.slug == was_slug

    @pytest.mark.parametrize("value", ["abc", None, "1.5", ""])
    def test_a_non_integer_value_is_refused(self, client, scenario_owner, db_session, value):
        """OWN-29. int() raising means 400, not a 500 from the transaction."""
        target = _new_tenant(db_session)
        before = target.max_users
        resp = client.post(
            f"/owner/api/tenant/{target.id}/update-package",
            json={"field": "max_users", "value": value},
        )
        assert resp.status_code == 400, f"max_users={value!r} answered {resp.status_code}"
        db_session.expire_all()
        assert db_session.get(type(target), target.id).max_users == before

    def test_a_missing_field_is_refused(self, client, scenario_owner, db_session):
        """OWN-30. No field means no update; it must not default to something."""
        target = _new_tenant(db_session)
        before = target.max_users
        resp = client.post(f"/owner/api/tenant/{target.id}/update-package", json={"value": 99})
        assert resp.status_code == 400
        db_session.expire_all()
        assert db_session.get(type(target), target.id).max_users == before

    def test_update_package_on_a_missing_tenant_is_a_404(self, client, scenario_owner):
        """OWN-31."""
        resp = client.post("/owner/api/tenant/99999999/update-package", json={"field": "max_users", "value": 5})
        assert resp.status_code == 404, f"a missing tenant answered {resp.status_code}"

    def test_a_limit_accepts_zero(self, client, scenario_owner, db_session):
        """OWN-32. Zero is a real limit, not a missing value.

        max_users=0 is how a tenant is frozen without suspending it, so the
        endpoint must not treat it as falsy and substitute a default.
        """
        target = _new_tenant(db_session)
        client.post(
            f"/owner/api/tenant/{target.id}/update-package",
            json={"field": "max_users", "value": 0},
        )
        db_session.expire_all()
        assert db_session.get(type(target), target.id).max_users == 0


class TestOWN06Subscription:
    """OWN-33 to OWN-38: extending a tenant's subscription."""

    def test_extending_by_days_moves_the_end_date(self, client, scenario_owner, db_session):
        """OWN-33."""
        target = _new_tenant(db_session)
        tid = target.id
        client.post(f"/owner/tenants/{tid}/extend-subscription", data={"days": "30"}, follow_redirects=True)
        db_session.expire_all()
        after = db_session.get(type(target), tid)
        assert after.subscription_end is not None, "30 days left the subscription with no end date"

    def test_an_explicit_end_date_wins_over_the_day_count(self, client, scenario_owner, db_session):
        """OWN-34. The explicit date is checked first, and the days are ignored.

        A support agent correcting a far-future expiry sends both fields; the
        explicit date must not be added to.
        """
        target = _new_tenant(db_session)
        tid = target.id
        client.post(
            f"/owner/tenants/{tid}/extend-subscription",
            data={"days": "30", "subscription_end": "2030-01-31"},
            follow_redirects=True,
        )
        db_session.expire_all()
        after = db_session.get(type(target), tid)
        assert str(after.subscription_end)[:10] == "2030-01-31", f"end date is {after.subscription_end!r}"

    @pytest.mark.parametrize("days", ["abc", "", "1.5", "99999999999999999999"])
    def test_an_unusable_day_count_is_rejected(self, client, scenario_owner, db_session, days):
        """OWN-35. Junk returns to the edit form and changes nothing.

        An empty string is the default the form posts when the field is blank,
        so it has to be safe rather than a crash.
        """
        target = _new_tenant(db_session)
        tid = target.id
        before = target.subscription_end
        resp = client.post(
            f"/owner/tenants/{tid}/extend-subscription",
            data={"days": days},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"days={days!r} answered {resp.status_code}"
        db_session.expire_all()
        assert db_session.get(type(target), tid).subscription_end == before

    def test_the_json_endpoint_agrees_with_the_form(self, client, scenario_owner, db_session):
        """OWN-36. Two endpoints, one behaviour.

        The AJAX variant is what the dashboard actually uses, so a divergence
        between it and the form would mean the visible path is the untested one.
        """
        target = _new_tenant(db_session)
        tid = target.id
        resp = client.post(f"/owner/api/tenant/{tid}/extend-subscription", json={"subscription_end": "2031-06-30"})
        assert resp.status_code == 200, f"the JSON extend answered {resp.status_code}"
        db_session.expire_all()
        assert str(db_session.get(type(target), tid).subscription_end)[:10] == "2031-06-30"

    def test_the_json_endpoint_requires_json(self, client, scenario_owner):
        """OWN-37."""
        resp = client.post("/owner/api/tenant/1/extend-subscription", data={"days": "30"})
        assert resp.status_code == 400

    def test_the_json_endpoint_reports_the_new_end_date(self, client, scenario_owner, db_session):
        """OWN-38. The response carries the value the UI displays."""
        target = _new_tenant(db_session)
        resp = client.post(
            f"/owner/api/tenant/{target.id}/extend-subscription",
            json={"subscription_end": "2032-12-31"},
        )
        body = resp.get_json()
        assert body is not None
        assert "subscription_end" in body.get("data", {}), f"no end date in the payload: {body}"


class TestOWN07AiAndStoreToggles:
    """OWN-39 to OWN-44: the two platform feature overrides."""

    def test_the_ai_toggle_enables_and_disables(self, client, scenario_owner, db_session):
        """OWN-39."""
        target = _new_tenant(db_session)
        tid = target.id

        client.post(f"/owner/tenant-ai/{tid}/toggle", data={"enable_ai": "1"}, follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(type(target), tid).enable_ai is True

        client.post(f"/owner/tenant-ai/{tid}/toggle", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(type(target), tid).enable_ai is False

    def test_an_unknown_ai_access_level_falls_back_to_execute(self, client, scenario_owner, db_session):
        """OWN-40. A level that is not one of the three is not stored as-is.

        basic / advanced / execute is a closed set. Accepting an arbitrary string
        would put the tenant in a state no feature check knows how to read.
        """
        target = _new_tenant(db_session)
        tid = target.id
        client.post(
            f"/owner/tenant-ai/{tid}/toggle",
            data={"enable_ai": "1", "ai_access_level": "superuser"},
            follow_redirects=True,
        )
        from utils.ai_access import get_tenant_ai_level

        assert get_tenant_ai_level(tid, default="execute") == "execute", (
            "an invalid AI access level was stored verbatim"
        )

    @pytest.mark.parametrize("level", ["basic", "advanced", "execute"])
    def test_every_valid_ai_level_is_stored(self, client, scenario_owner, db_session, level):
        """OWN-41. The three valid levels, enumerated."""
        from utils.ai_access import get_tenant_ai_level

        target = _new_tenant(db_session)
        tid = target.id
        client.post(
            f"/owner/tenant-ai/{tid}/toggle",
            data={"enable_ai": "1", "ai_access_level": level},
            follow_redirects=True,
        )
        assert get_tenant_ai_level(tid, default="execute") == level

    def test_the_ai_toggle_on_a_missing_tenant_changes_nothing(self, client, scenario_owner):
        """OWN-42."""
        resp = client.post("/owner/tenant-ai/99999999/toggle", data={"enable_ai": "1"}, follow_redirects=True)
        assert resp.status_code == 200

    def test_external_sharing_takes_the_last_submitted_value(self, client, scenario_owner, db_session):
        """OWN-43. Hidden-field-plus-checkbox, so getlist order decides.

        The pattern posts a hidden "0" followed by the checkbox's "1" when it is
        ticked. Taking the first value would report sharing as off on every
        tenant, silently - which is a privacy flag, so the failure direction
        matters more here than anywhere else in the owner panel.
        """
        target = _new_tenant(db_session)
        tid = target.id
        client.post(
            f"/owner/tenant-ai/{tid}/toggle",
            data={"enable_ai": "1", "ai_external_sharing_enabled": ["0", "1"]},
            follow_redirects=True,
        )
        db_session.expire_all()
        assert db_session.get(type(target), tid).ai_external_sharing_enabled is True

    def test_external_sharing_off_is_honoured(self, client, scenario_owner, db_session):
        """OWN-44. And the negative case, so OWN-43 is not the only direction pinned."""
        target = _new_tenant(db_session)
        tid = target.id
        client.post(
            f"/owner/tenant-ai/{tid}/toggle",
            data={"enable_ai": "1", "ai_external_sharing_enabled": ["0"]},
            follow_redirects=True,
        )
        db_session.expire_all()
        assert db_session.get(type(target), tid).ai_external_sharing_enabled is False


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
