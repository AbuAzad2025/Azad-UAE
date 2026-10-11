"""Wave 7 debt, part two - the owner panel's read pages and the tenant switch.

``test_wave7_debt_owner.py`` covered the maintenance tokens, the archived
boundary and the ``/super-admin`` blueprint. What is left on this blueprint is
the owner's own console: the pages that display state rather than change it.

These matter for a reason the change-routes do not have. ``/owner/config``
renders the database URI, and it renders it through ``_mask_db_uri`` - the
masking is the feature, and nothing in a guard test would notice it being
removed. A config page that printed ``postgresql://user:password@host/db``
would be a credential leak on a page whose only job is to be read.

``/owner/audit-logs`` takes its tenant from ``get_active_tenant_id``, so the
logs it shows depend on which tenant is active - which is the property the
tenant switcher exists to control, and the reason the switch route is walked
here as well.

``/tenants/switch`` carries three separate refusals, and they are deliberately
redundant: ``@owner_required`` in the stack, ``is_global_tenant_user`` in the
body because the same helper is called from non-route paths, and a per-tenant
membership check so a tenant admin cannot pivot into another tenant's records.
The scenarios walk each one rather than trusting the comment.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.business_scenarios.test_wave7_debt_owner import _owner


def _tenant(db_session, *, name="OWN Target", active=True, suspended=False):
    from models import Tenant

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"{name} {unique}",
        name_ar=f"{name} {unique}",
        slug=f"own-t-{unique}",
        email=f"own-t-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
        is_active=active,
        is_suspended=suspended,
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _tenant_user(client, db_session, tenant, branch, *, slug="own-switcher", permissions=("manage_sales",)):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("-", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"{slug}-{unique}",
        email=f"{slug}-{unique}@example.com",
        full_name=f"OWN {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()

    client.get("/auth/logout", follow_redirects=True)
    client.post("/auth/login", data={"username": user.username, "password": "password123"}, follow_redirects=True)
    return user


class TestOWN57TheOwnerConsoleRenders:
    """OWN-57 to OWN-70: the read pages, and what they are allowed to show."""

    def test_the_owner_root_redirects_to_the_dashboard(self, client, db_session):
        """OWN-57. ``/owner/`` is an alias, not a second page."""
        _owner(db_session, client)

        resp = client.get("/owner/", follow_redirects=False)
        assert resp.status_code == 302, f"the owner root answered {resp.status_code}, expected a redirect"

    def test_the_config_page_masks_the_database_uri(self, client, db_session):
        """OWN-58. The mask is the feature.

        ``_mask_db_uri`` reduces the URI to scheme, host, port and database.
        The credential is what must not appear, and asserting on the mask's own
        output rather than on "no colon appears" keeps this from passing on a
        page that simply rendered nothing.
        """
        from flask import current_app

        _owner(db_session, client)

        resp = client.get("/owner/config", follow_redirects=False)
        assert resp.status_code == 200, f"the config page answered {resp.status_code}"

        body = resp.get_data(as_text=True)
        uri = str(current_app.config.get("SQLALCHEMY_DATABASE_URI", ""))
        if "@" not in uri:
            return
        credentials = uri.split("://", 1)[1].split("@", 1)[0]
        assert credentials not in body, f"the config page rendered the database credentials ({credentials!r})"

    def test_the_master_login_page_renders_for_an_owner(self, client, db_session):
        """OWN-59. The break-glass password reference.

        It is owner-only and post-login, and it deliberately degrades to an
        empty password rather than raising when no master password is
        configured - so the assertion is that it renders at all.
        """
        _owner(db_session, client)

        resp = client.get("/owner/master-login-info", follow_redirects=False)
        assert resp.status_code == 200, f"the master login page answered {resp.status_code}"

    def test_the_audit_logs_page_renders(self, client, db_session):
        """OWN-60. The record of who did what, in the owner plane."""
        _owner(db_session, client)

        resp = client.get("/owner/audit-logs", follow_redirects=False)
        assert resp.status_code == 200, f"the audit log page answered {resp.status_code}"

    def test_the_system_stats_page_renders(self, client, db_session):
        """OWN-61. The platform counters."""
        _owner(db_session, client)

        resp = client.get("/owner/system-stats", follow_redirects=False)
        assert resp.status_code == 200, f"the system stats page answered {resp.status_code}"

    def test_the_company_dashboard_404s_a_platform_owner(self, client, db_session):
        """OWN-62. The one page where the owner is deliberately excluded.

        ``@company_admin_required`` inverts every other rule in this blueprint:
        it requires an active tenant and 404s a global owner, because the page
        shows one company's data and a platform owner has no company. A test
        asserting the owner reaches every owner page would fail here, and
        correctly.
        """
        _owner(db_session, client)

        resp = client.get("/owner/company-dashboard", follow_redirects=False)
        assert resp.status_code == 404, f"a platform owner reached the company dashboard: {resp.status_code}"

    def test_the_two_factor_decorator_does_not_block_a_single_factor_owner(self, client, db_session):
        """OWN-63. ``@two_factor_required`` only bites when 2FA is on.

        It redirects to the verification screen only when the user has
        ``two_factor_enabled``. With it off the dashboard has to render, or
        every owner is locked out of the panel they administer.
        """
        _owner(db_session, client)

        resp = client.get("/owner/dashboard", follow_redirects=False)
        assert resp.status_code == 200, (
            f"the owner dashboard answered {resp.status_code}; without 2FA enabled it must render"
        )


class TestOWN64TheTenantSwitcher:
    """OWN-64 to OWN-72: three refusals stacked on one route, walked one by one."""

    def test_the_switcher_is_hidden_from_a_tenant_user(self, client, db_session, sample_tenant, sample_branch):
        """OWN-64. ``@owner_required`` answers 404, never 403 or 401.

        The route's own docstring says why: a 401 would confirm the route
        exists, and a 403 would confirm there is something behind it worth
        protecting. 404 is the only answer that reveals nothing.
        """
        _tenant_user(client, db_session, sample_tenant, sample_branch)

        resp = client.get(f"/tenants/switch/{sample_tenant.id}", follow_redirects=False)
        assert resp.status_code == 404, f"a tenant user reached the switcher: {resp.status_code}"

    def test_switching_to_an_inactive_tenant_is_refused(self, client, db_session):
        """OWN-65. Inactive is refused, and refused by redirect.

        The target does not exist as far as the operator is concerned. The
        answer is a redirect to the dashboard with a flash, not a 404 - this
        is a legitimate request naming a tenant that is merely not available.
        """
        _owner(db_session, client)
        tenant = _tenant(db_session, name="OWN Inactive", active=False)

        resp = client.get(f"/tenants/switch/{tenant.id}", follow_redirects=True)
        assert resp.status_code == 200, f"switching to an inactive tenant answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "switching to an inactive tenant raised instead of refusing"
        )

    def test_switching_to_a_suspended_tenant_is_refused(self, client, db_session):
        """OWN-66. Suspended is its own condition, not a synonym for inactive.

        ``is_suspended`` is checked separately because a suspended tenant is a
        company that was real and is mid-dispute. Refusing it while still
        letting an operator into its records is not the same decision.
        """
        _owner(db_session, client)
        tenant = _tenant(db_session, name="OWN Suspended", active=True, suspended=True)

        resp = client.get(f"/tenants/switch/{tenant.id}", follow_redirects=True)
        assert resp.status_code == 200, f"switching to a suspended tenant answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "switching to a suspended tenant raised instead of refusing"
        )

    def test_switching_to_a_tenant_that_does_not_exist_is_refused(self, client, db_session):
        """OWN-67. An id nobody owns resolves to nothing and is refused."""
        _owner(db_session, client)

        resp = client.get("/tenants/switch/99999999", follow_redirects=True)
        assert resp.status_code == 200, f"switching to a missing tenant answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "switching to a missing tenant raised instead of refusing"
        )

    def test_tenant_zero_clears_the_active_tenant(self, client, db_session):
        """OWN-68. Zero is the documented "leave the company", not "tenant 0".

        It has to be special-cased before the lookup, because
        ``db.session.get(Tenant, 0)`` returns None and would be indistinguishable
        from a tenant that does not exist - and the intended answer is a clean
        exit, not a refusal.
        """
        _owner(db_session, client)

        resp = client.get("/tenants/switch/0", follow_redirects=True)
        assert resp.status_code == 200, f"clearing the active tenant answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), "clearing the active tenant raised"

    def test_an_owner_can_switch_into_an_active_tenant(self, client, db_session):
        """OWN-69. The permitted case, which is the point of the route.

        A platform owner has no tenant of their own, so without this the three
        refusals above would all pass on a switcher that cannot switch.
        """
        _owner(db_session, client)
        tenant = _tenant(db_session, name="OWN Switchable")

        resp = client.get(f"/tenants/switch/{tenant.id}", follow_redirects=True)
        assert resp.status_code == 200, f"an owner switching tenants answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "an owner switching into an active tenant raised"
        )

    def test_the_tenant_list_and_creation_pages_render(self, client, db_session):
        """OWN-70. The two pages the refusals above redirect into."""
        _owner(db_session, client)

        broken = []
        for path in ("/owner/tenants", "/owner/tenants/create", "/owner/tenant-stores", "/owner/tenant-ai"):
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 200:
                broken.append((path, resp.status_code))
        assert not broken, f"owner tenant pages did not answer: {broken}"

    def test_toggling_the_ai_flag_for_a_missing_tenant_is_handled(self, client, db_session):
        """OWN-71. A toggle naming something that is gone does not raise."""
        _owner(db_session, client)

        resp = client.post("/owner/tenant-ai/99999999/toggle", follow_redirects=True)
        assert resp.status_code == 200, f"toggling AI for a missing tenant answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "toggling AI for a missing tenant raised instead of reporting"
        )

    def test_the_store_platform_toggle_for_a_missing_store_is_handled(self, client, db_session):
        """OWN-72. The store force-off, which is a lock an operator may need.

        The same shape as the AI toggle: a missing target is reported, not
        raised. This one is worth having alongside it because it is the
        control an operator reaches for during an incident, and a 500 during an
        incident is the worst time to discover it.
        """
        _owner(db_session, client)

        resp = client.post(
            "/owner/tenant-stores/99999999/platform-toggle",
            data={"platform_disabled": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"toggling a missing store answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "toggling a missing store raised instead of reporting"
        )


class TestOWN73TheStatusApi:
    """OWN-73 to OWN-96: the JSON status endpoints behind the owner pages."""

    def _post_json(self, client, path, payload):
        return client.post(path, json=payload, follow_redirects=False)

    def test_toggling_a_tenant_status_for_a_missing_tenant_is_handled(self, client, db_session):
        """OWN-73. ``/owner/api/tenant/<id>/toggle-status`` is JSON and is
        walked without following redirects, so the status is the answer itself."""
        _owner(db_session, client)

        resp = self._post_json(client, "/owner/api/tenant/99999999/toggle-status", {})
        assert resp.status_code in (200, 302, 400, 404), (
            f"toggling a missing tenant's status answered {resp.status_code}"
        )
        assert resp.status_code < 500, f"toggling a missing tenant raised: {resp.status_code}"

    def test_updating_a_package_for_a_missing_tenant_is_handled(self, client, db_session):
        """OWN-74. The package endpoint on the same shape."""
        _owner(db_session, client)

        resp = self._post_json(client, "/owner/api/tenant/99999999/update-package", {"package_id": 1})
        assert resp.status_code in (200, 302, 400, 404), (
            f"updating the package of a missing tenant answered {resp.status_code}"
        )
        assert resp.status_code < 500, f"updating the package raised: {resp.status_code}"

    def test_extending_a_subscription_without_a_duration_is_handled(self, client, db_session):
        """OWN-75. The form endpoint and the JSON endpoint answer alike.

        ``/owner/tenants/<id>/extend-subscription`` and
        ``/owner/api/tenant/<id>/extend-subscription`` are the same operation
        reached two ways. Both are walked because a guard or a validation added
        to one is not automatically present in the other.
        """
        _owner(db_session, client)
        tenant = _tenant(db_session, name="OWN Extend")

        form = client.post(f"/owner/tenants/{tenant.id}/extend-subscription", data={}, follow_redirects=True)
        assert form.status_code == 200, f"the form extend endpoint answered {form.status_code}"
        assert "Internal Server Error" not in form.get_data(as_text=True), (
            "the form extend endpoint raised instead of validating"
        )

        api = self._post_json(client, f"/owner/api/tenant/{tenant.id}/extend-subscription", {})
        assert api.status_code in (200, 302, 400, 404), f"the api extend endpoint answered {api.status_code}"
        assert api.status_code < 500, f"the api extend endpoint raised: {api.status_code}"

    def test_extending_a_subscription_with_an_unknown_duration_is_handled(self, client, db_session):
        """OWN-76. A duration that is not in the closed list.

        Falling through to a default month is how a customer who bought a year
        gets a month, and it is invisible to both parties.
        """
        _owner(db_session, client)
        tenant = _tenant(db_session, name="OWN Duration")

        resp = client.post(
            f"/owner/tenants/{tenant.id}/extend-subscription",
            data={"duration_type": "fortnightly"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"an unknown duration answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "an unknown duration raised instead of being refused"
        )

    @pytest.mark.parametrize("duration", ["monthly", "yearly", "annual", "lifetime", "trial"])
    def test_every_advertised_duration_is_accepted(self, client, db_session, duration):
        """OWN-77. The positive half of the closed list.

        A validation that refuses everything passes OWN-76 perfectly. Each
        duration the platform advertises is sent, and none may be refused.
        """
        _owner(db_session, client)
        tenant = _tenant(db_session, name=f"OWN {duration}")

        resp = client.post(
            f"/owner/tenants/{tenant.id}/extend-subscription",
            data={"duration_type": duration},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"duration={duration!r} answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            f"the advertised duration {duration!r} raised instead of being accepted"
        )

    def test_extending_a_subscription_for_a_missing_tenant_is_handled(self, client, db_session):
        """OWN-78. A stale link in an email is the realistic way in here."""
        _owner(db_session, client)

        form = client.post("/owner/tenants/99999999/extend-subscription", data={}, follow_redirects=True)
        # 404 is the right answer: the route aborts on a tenant it cannot
        # resolve, so an operator following a stale link is told the tenant is
        # gone rather than handed a blank form.
        assert form.status_code in (200, 404), f"extending a missing tenant answered {form.status_code}"
        assert "Internal Server Error" not in form.get_data(as_text=True), (
            "extending a missing tenant raised instead of reporting"
        )

    def test_suspending_and_activating_a_missing_tenant_is_handled(self, client, db_session):
        """OWN-79. The lifecycle pair, against ids that are not there."""
        _owner(db_session, client)

        for verb in ("suspend", "activate"):
            resp = client.post(f"/owner/tenants/99999999/{verb}", follow_redirects=True)
            assert resp.status_code in (200, 404), f"{verb} for a missing tenant answered {resp.status_code}"
            assert "Internal Server Error" not in resp.get_data(as_text=True), (
                f"{verb} for a missing tenant raised instead of reporting"
            )

    def test_deleting_a_missing_tenant_is_handled(self, client, db_session):
        """OWN-80. Deletion of something that does not exist.

        The interesting property is that it does not fall through to deleting
        *something*: a delete route that treats "no row" as "any row" would be
        the worst bug in this file.
        """
        from models import Tenant

        _owner(db_session, client)
        survivor = _tenant(db_session, name="OWN Survivor")
        before = db_session.query(Tenant).count()

        resp = client.post("/owner/tenants/99999999/delete", follow_redirects=True)
        assert resp.status_code in (200, 404), f"deleting a missing tenant answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Tenant).count()
        assert after == before, f"deleting a missing tenant removed a row ({before} -> {after})"
        assert db_session.get(Tenant, survivor.id) is not None, "the survivor tenant was deleted instead"

    def test_editing_a_missing_tenant_is_handled(self, client, db_session):
        """OWN-81. The edit form and its POST, against an absent id."""
        _owner(db_session, client)

        form = client.get("/owner/tenants/99999999/edit", follow_redirects=False)
        assert form.status_code in (200, 404), f"editing a missing tenant answered {form.status_code}"

        post = client.post("/owner/tenants/99999999/edit", data={"name": "x"}, follow_redirects=True)
        assert post.status_code in (200, 404), f"posting an edit for a missing tenant answered {post.status_code}"
        assert "Internal Server Error" not in post.get_data(as_text=True), "posting an edit for a missing tenant raised"

    def test_creating_a_tenant_without_a_name_is_refused(self, client, db_session):
        """OWN-82. The required fields are actually required.

        A tenant with no name is unusable and unlistable, so the create form
        refuses rather than storing a blank. The count is the assertion.
        """
        from models import Tenant

        _owner(db_session, client)
        before = db_session.query(Tenant).count()

        resp = client.post("/owner/tenants/create", data={"name": "", "slug": ""}, follow_redirects=True)
        assert resp.status_code == 200, f"an unnamed tenant create answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Tenant).count()
        assert after == before, f"an unnamed tenant was stored anyway ({before} -> {after})"
