"""Wave 7 debt, part three - what a tenant create actually requires.

``test_wave7_owner_platform.py`` proved the owner can create a tenant and that
the books open at zero. It did not walk the refusals in the create form, and
those refusals are the interesting part: every one of them is a case where the
route could have guessed and chose not to.

- No Arabic name and no slug: refused. A slug is the tenant's identity in
  every URL and in the tenant switcher, so an invented one is worse than none.
- No currency: refused. Defaulting to a currency would silently book a
  customer in the wrong money.
- A slug that already exists: refused. Two tenants sharing a slug is the kind
  of collision that surfaces months later as "why did this open the wrong
  company".

The lifecycle pair is walked as a round trip, because that is the property
worth having: suspending sets ``is_active`` false and ``is_suspended`` true and
records a reason; activating clears all three. A suspend that left
``is_suspended`` set after an activate would block the tenant switcher while
the panel said it was active - the two disagreeing is the defect.

Finally, the owner can suspend *any* tenant. An earlier version of this route
refused ``tenant_id == 1`` as a "default tenant" guard, which meant the
operator could never touch the first row in the table regardless of what it
was. OWN-96 walks the id-1 case specifically, because that guard is exactly
the kind of thing that looks like protection and is not.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.business_scenarios.test_wave7_debt_owner import _owner


def _slug():
    return f"own-c-{uuid.uuid4().hex[:10]}"


class TestOWN84CreatingATenant:
    """OWN-84 to OWN-89: the create form's refusals."""

    def _create(self, client, **over):
        data = {
            "name_ar": "شركة جديدة",
            "name_en": "New Company",
            "slug": _slug(),
            "default_currency": "AED",
            "country": "AE",
        }
        data.update(over)
        return client.post("/owner/tenants/create", data=data, follow_redirects=True)

    def _count(self, db_session):
        from models import Tenant

        return db_session.query(Tenant).count()

    @pytest.mark.parametrize(
        "payload",
        [
            {"name_ar": "", "slug": ""},
            {"name_ar": "", "slug": _slug()},
            {"name_ar": "بلا slugg", "slug": ""},
        ],
    )
    def test_a_tenant_without_a_name_and_slug_is_refused(self, client, db_session, payload):
        """OWN-84. Identity is not invented.

        The slug is the tenant's key in every URL and in the switcher. Making
        one up would produce a tenant that exists and cannot be reached.
        """
        _owner(db_session, client)
        before = self._count(db_session)

        resp = self._create(client, **payload)
        assert resp.status_code == 200, f"an incomplete create answered {resp.status_code}"

        db_session.expire_all()
        after = self._count(db_session)
        assert after == before, f"an incomplete tenant was stored anyway ({before} -> {after})"

    def test_a_tenant_without_a_currency_is_refused(self, client, db_session):
        """OWN-85. Defaulting the currency would book in the wrong money.

        Every downstream figure - the trial balance, VAT, the reporting
        currency - derives from this one field, so an unlabelled default is not
        a convenience, it is a silent misstatement.
        """
        _owner(db_session, client)
        before = self._count(db_session)

        resp = self._create(client, default_currency="")
        assert resp.status_code == 200, f"a currency-less create answered {resp.status_code}"

        db_session.expire_all()
        after = self._count(db_session)
        assert after == before, f"a tenant with no currency was stored ({before} -> {after})"

    def test_a_duplicate_slug_is_refused(self, client, db_session):
        """OWN-86. Two tenants cannot share a slug.

        This is the collision that surfaces months later as "why did this link
        open the wrong company". The refusal is the whole point of the check.
        """
        from models import Tenant

        _owner(db_session, client)
        existing = _slug()
        db_session.add(
            Tenant(
                name="OWN Slug Holder",
                name_ar="OWN Slug Holder",
                slug=existing,
                email=f"{existing}@example.com",
                country="AE",
                default_currency="AED",
            )
        )
        db_session.commit()
        before = self._count(db_session)

        resp = self._create(client, slug=existing)
        assert resp.status_code == 200, f"a duplicate slug answered {resp.status_code}"

        db_session.expire_all()
        after = self._count(db_session)
        assert after == before, f"a duplicate slug was stored ({before} -> {after})"

    def test_a_valid_create_stores_the_currency_it_was_given(self, client, db_session):
        """OWN-87. The accepted case, so the refusals above are discriminating.

        Every scenario before this one would pass against a create form that
        refused everything. The currency is stored upper-cased, which is why the
        assertion is on the value rather than on the presence of a row.
        """
        from models import Tenant

        _owner(db_session, client)
        slug = _slug()

        resp = self._create(client, slug=slug, default_currency="usd")
        assert resp.status_code == 200, f"a valid create answered {resp.status_code}"

        db_session.expire_all()
        tenant = db_session.query(Tenant).filter_by(slug=slug).first()
        assert tenant is not None, f"the tenant with slug {slug} was reported created but is not stored"
        assert tenant.default_currency == "USD", (
            f"the stored currency is {tenant.default_currency!r}; the form is upper-cased before saving"
        )

    def test_the_create_form_renders(self, client, db_session):
        """OWN-88. And the form the refusals redirect back to."""
        _owner(db_session, client)

        resp = client.get("/owner/tenants/create", follow_redirects=False)
        assert resp.status_code == 200, f"the tenant create form answered {resp.status_code}"


class TestOWN89TheSuspendActivateRoundTrip:
    """OWN-89 to OWN-96: the lifecycle, and the guard that used to be there."""

    def _tenant(self, db_session, name="OWN Lifecycle"):
        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        tenant = Tenant(
            name=f"{name} {unique}",
            name_ar=f"{name} {unique}",
            slug=f"own-lc-{unique}",
            email=f"own-lc-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
            default_currency="AED",
            is_active=True,
        )
        db_session.add(tenant)
        db_session.commit()
        return tenant

    def test_suspending_records_both_flags_and_a_reason(self, client, db_session):
        """OWN-89. A suspension is three facts, and all three are written.

        ``is_active`` false stops the tenant's users, ``is_suspended`` true is
        what the switcher reads, and ``suspension_reason`` is the only record
        of why. Setting the first without the third leaves an operator staring
        at a tenant that stopped working for no stated reason.
        """
        _owner(db_session, client)
        tenant = self._tenant(db_session)

        resp = client.post(
            f"/owner/tenants/{tenant.id}/suspend",
            data={"reason": "non-payment"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"suspending answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(type(tenant), tenant.id)
        assert not row.is_active, "the tenant is still active after a suspension"
        assert row.is_suspended, "is_suspended was not set"
        assert row.suspension_reason == "non-payment", (
            f"the suspension reason is {row.suspension_reason!r}, not the one given"
        )

    def test_suspending_without_a_reason_still_records_one(self, client, db_session):
        """OWN-90. The fallback reason, so the column is never empty.

        An operator who suspends without typing why still leaves a trace. The
        alternative - a NULL reason - is what makes a suspension impossible to
        explain to the customer three months later.
        """
        _owner(db_session, client)
        tenant = self._tenant(db_session)

        client.post(f"/owner/tenants/{tenant.id}/suspend", data={}, follow_redirects=True)
        db_session.expire_all()

        row = db_session.get(type(tenant), tenant.id)
        assert row.suspension_reason, "a suspension with no reason left the column empty"

    def test_activating_clears_everything_the_suspension_set(self, client, db_session):
        """OWN-91. The round trip is the property.

        If activate cleared ``is_active`` but left ``is_suspended`` or the
        reason behind, the panel would report the tenant as active while the
        switcher still refused to enter it. The two disagreeing is the defect,
        so all three fields are asserted together.
        """
        _owner(db_session, client)
        tenant = self._tenant(db_session)

        client.post(f"/owner/tenants/{tenant.id}/suspend", data={"reason": "dispute"}, follow_redirects=True)
        db_session.expire_all()
        assert not db_session.get(type(tenant), tenant.id).is_active, "the suspension did not take"

        resp = client.post(f"/owner/tenants/{tenant.id}/activate", follow_redirects=True)
        assert resp.status_code == 200, f"activating answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(type(tenant), tenant.id)
        assert row.is_active, "the tenant is still inactive after an activation"
        assert not row.is_suspended, "is_suspended survived the activation"
        assert row.suspension_reason is None, (
            f"the suspension reason survived the activation as {row.suspension_reason!r}"
        )

    def test_the_first_tenant_can_be_suspended(self, client, db_session):
        """OWN-96. The owner may suspend *any* tenant, including the first.

        This route used to refuse ``tenant_id == 1`` as a guard against
        disabling the "default tenant" - and in doing so it locked the
        operator out of touching the first row in the table regardless of what
        that row actually was. A guard that looks like protection and silently
        blocks a legitimate action is worse than no guard, because it is
        believed.
        """
        from models import Tenant

        _owner(db_session, client)
        first = db_session.query(Tenant).order_by(Tenant.id.asc()).filter_by(is_active=True).first()
        assert first is not None, "this database has no active tenant to suspend"

        resp = client.post(f"/owner/tenants/{first.id}/suspend", follow_redirects=True)
        assert resp.status_code == 200, f"suspending the first tenant answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(Tenant, first.id)
        assert not row.is_active, (
            f"tenant {first.id} is still active; the id==1 guard is back and is blocking the operator"
        )

    def test_a_suspended_tenant_can_be_re_activated(self, client, db_session):
        """OWN-92. Suspension is reversible by design."""
        _owner(db_session, client)
        tenant = self._tenant(db_session, name="OWN Reversible")

        client.post(f"/owner/tenants/{tenant.id}/suspend", follow_redirects=True)
        client.post(f"/owner/tenants/{tenant.id}/activate", follow_redirects=True)
        db_session.expire_all()

        row = db_session.get(type(tenant), tenant.id)
        assert row.is_active and not row.is_suspended, (
            "the suspend/activate round trip left the tenant in a mixed state"
        )

    def test_suspending_an_inactive_tenant_is_handled(self, client, db_session):
        """OWN-93. The idempotent case: already off, suspended again."""
        _owner(db_session, client)
        tenant = self._tenant(db_session, name="OWN Doubly")
        tenant.is_active = False
        db_session.commit()

        resp = client.post(f"/owner/tenants/{tenant.id}/suspend", follow_redirects=True)
        assert resp.status_code == 200, f"re-suspending answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), "re-suspending an inactive tenant raised"

    def test_editing_a_tenant_cannot_strip_its_identity(self, client, db_session):
        """OWN-94. The edit form may not blank the slug or the currency.

        The same reasoning as create, applied to a row that already exists.
        Blanking the slug on a live tenant would break every URL pointing at it,
        so the edit has to refuse rather than apply.
        """
        from models import Tenant

        _owner(db_session, client)
        tenant = self._tenant(db_session, name="OWN Identified")
        original_slug = tenant.slug
        original_currency = tenant.default_currency

        resp = client.post(
            f"/owner/tenants/{tenant.id}/edit",
            data={"name_ar": "OWN Renamed", "slug": "", "default_currency": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"the edit answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(Tenant, tenant.id)
        assert row.slug == original_slug, f"the edit blanked the slug to {row.slug!r}"
        assert row.default_currency == original_currency, f"the edit blanked the currency to {row.default_currency!r}"

    def test_the_tenant_list_renders(self, client, db_session):
        """OWN-95. Where every lifecycle action redirects to."""
        _owner(db_session, client)

        resp = client.get("/owner/tenants", follow_redirects=False)
        assert resp.status_code == 200, f"the tenant list answered {resp.status_code}"

    def test_editing_a_tenant_can_change_its_currency_on_purpose(self, client, db_session):
        """OWN-97. Preservation is not the same as refusing.

        ``_text`` and the currency fallback keep the current value when a field
        comes back blank, which is right for an emptied box and wrong for an
        operator who has deliberately changed the currency. So the change has
        to go through, or a tenant whose reporting currency genuinely needs to
        move has no way to do it from this form.

        The slug is sent unchanged throughout: this scenario is about the one
        field that is allowed to move, and sending a blank slug would test the
        preservation rule instead.
        """
        from models import Tenant

        _owner(db_session, client)
        tenant = self._tenant(db_session, name="OWN Currency")
        assert tenant.default_currency == "AED", (
            f"the fixture tenant is in {tenant.default_currency}, not AED, so this proves nothing"
        )

        resp = client.post(
            f"/owner/tenants/{tenant.id}/edit",
            data={
                "name_ar": f"OWN Currency {uuid.uuid4().hex[:6]}",
                "slug": tenant.slug,
                "default_currency": "USD",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"the currency edit answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(Tenant, tenant.id)
        assert row.default_currency == "USD", (
            f"a deliberate currency change did not apply; the tenant is still in {row.default_currency!r}"
        )
        assert row.slug == tenant.slug, "the slug moved during an edit that did not name it"
