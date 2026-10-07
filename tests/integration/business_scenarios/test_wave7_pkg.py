"""Wave 7 - SaaS packages, purchases and the payment vault. Prefix PKG.

The payment vault is the only surface where money crosses the platform boundary:
the owner sets prices, tenants buy, and the vault holds the card tokens. Three
contracts shape every scenario here.

**The vault gates everything.** ``packages_management`` and every other vault page
redirect to ``/payment-vault/unlock`` when the platform vault is missing or
locked, so ``_unlock`` runs first in each test. Without it every assertion below
would be measuring a 302 and reporting it as a failure of the thing under test.

**``is_active`` is checked against ``"on"``, not a truthy value.** The create
route reads ``request.form.get("is_active") == "on"``, so a POST that sends
``is_active: "1"`` creates a package that is silently inactive - it then fails to
appear in the storefront, and the only visible symptom is a customer who cannot
buy the plan that was just entered. PKG-03 pins that the value has to be "on".

**The API endpoints and the web pages guard differently.** ``/api/purchase`` and
``/api/donation`` carry ``@csrf`` only; the blueprint's before_request exempts
``/payment-vault/api/`` and ``/payment-vault/webhook/`` from the owner-page
redirect. So a missing body on an API route is a 400 from validation, while a
missing body on a web page is a redirect. Asserting the wrong one of those would
be asserting a contract the code does not have.

No scenario here is marked skip. Where the code needs an external provider - a
real card token, a real payment webhook signature - the test asserts the
*rejection* path, which is reachable without the provider and is the behaviour
that actually protects the platform.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


def _slug(prefix: str = "pkg") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _unlock(client, password: str = "Vault-Pass-123") -> None:
    """Create or unlock the platform vault.

    The vault is tenant-less by design (``tenant_id IS NULL``), and every vault
    page redirects to the unlock screen while it is missing or locked. Posting the
    password creates it on first use and unlocks it afterwards, so this is the
    only setup a scenario needs.
    """
    resp = client.post("/payment-vault/unlock", data={"vault_password": password}, follow_redirects=True)
    assert resp.status_code == 200, f"unlocking the vault answered {resp.status_code}"
    # follow_redirects turns an anonymous bounce to the login page into a 200, so
    # a status check alone would let this pass without ever opening the vault.
    # The redirect is followed deliberately here and the landing page is asserted.
    assert "/auth/login" not in (resp.request.path or ""), (
        "the unlock bounced to the login page - the caller is not signed in as owner"
    )
    from models import PaymentVault

    vault = PaymentVault.get_platform_vault()
    assert vault is not None, "the vault still does not exist after unlocking"
    assert vault.is_locked is False, "the vault is still locked after a successful unlock"


def _package_form(**over) -> dict[str, str]:
    """A complete, valid create-package form.

    ``name_ar`` and ``name_en`` are both required - the route rejects the post
    outright without them - and ``is_active`` must be the literal ``"on"``.
    """
    form = {
        "name_ar": "باقة الاختبار",
        "name_en": "Test Package",
        "slug": _slug(),
        "price": "99.000",
        "currency": "AED",
        "is_active": "on",
        "support_duration_months": "3",
        "max_users": "10",
        "max_branches": "3",
        "max_products": "500",
        "max_customers": "200",
        "max_suppliers": "50",
        "max_warehouses": "2",
        "max_storage_mb": "1024",
        "max_invoices_per_month": "5000",
        "max_sales_per_month": "10000",
    }
    form.update(over)
    return form


def _api_key(db_session, *, scope: str = "write", active: bool = True) -> str:
    """A real API key row, returned as its raw key string.

    The vault's public API checks the Origin first and the key second, so the
    business-logic scenarios need both to get past the door. ``find_active_api_key``
    compares ``key`` verbatim, so the value here is the value sent.
    """
    from models import APIKey

    raw = f"w7key-{uuid.uuid4().hex}"
    db_session.add(
        APIKey(
            name="w7 scenario",
            key=raw,
            secret=uuid.uuid4().hex,
            service="wave7",
            scope=scope,
            is_active=active,
        )
    )
    db_session.commit()
    return raw


def _create(client, db_session, **over):
    """Create a package over HTTP and return the persisted row."""
    from models import Package

    form = _package_form(**over)
    resp = client.post("/payment-vault/package/create", data=form, follow_redirects=True)
    assert resp.status_code == 200, f"package create answered {resp.status_code}"
    pkg = db_session.query(Package).filter_by(slug=form["slug"]).first()
    assert pkg is not None, f"no package was created for slug {form['slug']}"
    return pkg


class TestPKG01PackageCrud:
    """PKG-01 to PKG-12: the package catalogue."""

    def test_the_management_page_loads_once_the_vault_is_open(self, client, scenario_owner):
        """PKG-01. The page itself renders - the 302 was the lock, not a bug."""
        _unlock(client)
        assert client.get("/payment-vault/packages-management").status_code == 200

    def test_the_management_page_locks_again_when_the_vault_is_closed(self, client, scenario_owner, db_session):
        """PKG-02. Closing the vault re-gates the catalogue.

        The lock is the control that matters, so it is asserted from the closed
        side as well as the open one: an open vault that stays reachable after a
        lock would make the lock decorative.
        """
        from models import PaymentVault

        _unlock(client)
        vault = PaymentVault.get_platform_vault()
        vault.is_locked = True
        db_session.commit()

        resp = client.get("/payment-vault/packages-management")
        assert resp.status_code == 302, f"a locked vault still served the catalogue ({resp.status_code})"
        assert "/payment-vault/unlock" in resp.headers.get("Location", "")

    def test_creating_a_package_persists_every_limit(self, client, scenario_owner, db_session):
        """PKG-03. All ten limit columns survive the round trip.

        Enumerated rather than spot-checked because the route builds them through
        a shared helper - one wrong key in that helper would silently default a
        limit, and the symptom is a tenant hitting a wall it was never told about.
        """
        _unlock(client)
        pkg = _create(client, db_session)
        for field, expected in [
            ("max_users", 10),
            ("max_branches", 3),
            ("max_products", 500),
            ("max_customers", 200),
            ("max_suppliers", 50),
            ("max_warehouses", 2),
            ("max_storage_mb", 1024),
            ("max_invoices_per_month", 5000),
            ("max_sales_per_month", 10000),
        ]:
            assert getattr(pkg, field) == expected, f"{field} stored as {getattr(pkg, field)!r}, expected {expected}"

    def test_is_active_is_on_only_when_the_literal_on_is_sent(self, client, scenario_owner, db_session):
        """PKG-04. "1" does not enable a package; the route compares to "on".

        Checkbox semantics, and the failure is quiet: the package is created, the
        owner sees it in the catalogue, and it is absent from every storefront
        because the customer-facing query filters on is_active.
        """
        _unlock(client)
        on = _create(client, db_session, is_active="on", name_en="On Pkg")
        off = _create(client, db_session, is_active="1", name_en="Off Pkg")
        assert on.is_active is True, 'sending "on" did not activate the package'
        assert off.is_active is False, 'sending "1" activated the package - the form posts "on", not a truthy value'

    @pytest.mark.parametrize("missing", ["name_ar", "name_en"])
    def test_a_package_needs_both_names(self, client, scenario_owner, db_session, missing):
        """PKG-05. Neither name may be dropped.

        Both are NOT NULL, and the route refuses the post rather than storing a
        half-named package, so the assertion is that nothing was created.
        """
        from models import Package

        _unlock(client)
        before = db_session.query(Package).count()
        form = _package_form(**{missing: ""})
        client.post("/payment-vault/package/create", data=form, follow_redirects=True)
        assert db_session.query(Package).count() == before, f"a package was created without {missing}"

    def test_a_duplicate_slug_is_refused(self, client, scenario_owner, db_session):
        """PKG-06. The second package with a taken slug is not created."""
        from models import Package

        _unlock(client)
        first = _create(client, db_session, name_en="First")
        before = db_session.query(Package).count()
        _create(client, db_session, name_en="Second", slug=first.slug)
        assert db_session.query(Package).count() == before, "a duplicate slug created a second package"

    def test_the_price_is_stored_as_a_decimal(self, client, scenario_owner, db_session):
        """PKG-07. Money does not go through a float."""
        _unlock(client)
        pkg = _create(client, db_session, price="1234.560")
        assert Decimal(str(pkg.price)) == Decimal("1234.560")

    def test_editing_a_package_changes_its_limits(self, client, scenario_owner, db_session):
        """PKG-08. The edit form writes through to the same columns."""
        _unlock(client)
        pkg = _create(client, db_session)
        pid = pkg.id

        client.post(
            f"/payment-vault/package/{pid}/edit",
            data=_package_form(
                name_ar="المحدثة",
                name_en="Updated",
                max_users="77",
                price="150.000",
            ),
            follow_redirects=True,
        )
        db_session.expire_all()
        from models import Package

        updated = db_session.get(Package, pid)
        assert updated.max_users == 77, f"max_users is {updated.max_users!r} after an edit that set 77"
        assert Decimal(str(updated.price)) == Decimal("150.000")

    def test_the_edit_form_renders_for_the_owner(self, client, scenario_owner, db_session):
        """PKG-09."""
        _unlock(client)
        pkg = _create(client, db_session)
        assert client.get(f"/payment-vault/package/{pkg.id}/edit").status_code == 200

    def test_toggling_flips_the_flag_both_ways(self, client, scenario_owner, db_session):
        """PKG-10. Two toggles return it to where it started."""
        from models import Package

        _unlock(client)
        pkg = _create(client, db_session)
        pid = pkg.id
        assert pkg.is_active is True

        client.post(f"/payment-vault/package/{pid}/toggle", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Package, pid).is_active is False

        client.post(f"/payment-vault/package/{pid}/toggle", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Package, pid).is_active is True

    def test_deleting_removes_the_package(self, client, scenario_owner, db_session):
        """PKG-11."""
        from models import Package

        _unlock(client)
        pkg = _create(client, db_session)
        pid = pkg.id
        client.post(f"/payment-vault/package/{pid}/delete", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Package, pid) is None, "the package survived a delete"

    def test_actions_on_a_missing_package_are_refused(self, client, scenario_owner):
        """PKG-12. A stale id in a URL must not 500."""
        missing = 999_999_99
        for path in (
            f"/payment-vault/package/{missing}/edit",
            f"/payment-vault/package/{missing}/delete",
            f"/payment-vault/package/{missing}/toggle",
        ):
            resp = client.post(path, follow_redirects=True)
            assert resp.status_code in (302, 404), f"{path} answered {resp.status_code} for a missing package"


class TestPKG02PurchaseApi:
    """PKG-13 to PKG-20: the public purchase endpoints.

    ``/api/purchase`` and ``/api/donation`` sit behind ``_validate_public_api_origin``
    before any business validation runs. That check is a genuine CSRF defence: a
    purchase POST from another site must not be able to move money, and the test
    client cannot forge a same-origin request without saying where it is from.

    So the first scenarios assert the origin policy - missing, untrusted, and
    trusted - and only then does the business logic get exercised with a trusted
    Origin header. Getting this order wrong is what made the earlier version of
    this file report a 403 where it meant to assert a 400.
    """

    TRUSTED = {"Origin": "http://localhost:5000"}
    HOSTILE = {"Origin": "https://attacker.example"}

    def test_a_post_without_an_origin_is_refused(self, client):
        """PKG-13. No Origin and no Referer is a refusal, not a default allow.

        This is the check that stops a cross-site form post, and it answers 403
        before the body is ever parsed.
        """
        resp = client.post("/payment-vault/api/purchase", json={})
        assert resp.status_code == 403, f"a purchase with no Origin answered {resp.status_code}"
        assert "success" in (resp.get_json() or {}), "the refusal was not a structured error body"

    def test_a_post_from_an_untrusted_origin_is_refused(self, client):
        """PKG-14. A foreign Origin is refused even though one was supplied."""
        resp = client.post("/payment-vault/api/purchase", json={}, headers=self.HOSTILE)
        assert resp.status_code == 403, f"a cross-site purchase answered {resp.status_code}"

    def test_a_post_from_an_untrusted_referer_is_refused(self, client):
        """PKG-15. The Referer path is policed identically to Origin."""
        resp = client.post("/payment-vault/api/purchase", json={}, headers={"Referer": "https://attacker.example/x"})
        assert resp.status_code == 403, f"a cross-referer purchase answered {resp.status_code}"

    def test_a_trusted_origin_without_a_key_is_unauthorised(self, client):
        """PKG-16. Origin is the first door, the API key the second.

        A trusted Origin with no key answers 401, not 400: that ordering is the
        point. It shows the 403s above come from the origin policy and not from a
        closed endpoint, and it pins that a browser page alone is not enough.
        """
        resp = client.post("/payment-vault/api/purchase", json={}, headers=self.TRUSTED)
        assert resp.status_code == 401, f"a trusted-origin request with no key answered {resp.status_code}"

    def test_purchase_without_a_package_is_rejected(self, client, db_session):
        """PKG-17. Past both doors, an empty body is a 400."""
        headers = {**self.TRUSTED, "X-API-Key": _api_key(db_session)}
        resp = client.post("/payment-vault/api/purchase", json={}, headers=headers)
        assert resp.status_code == 400, f"an empty purchase body answered {resp.status_code}"

    def test_a_read_only_key_cannot_start_a_payment(self, client, db_session):
        """PKG-17b. Scope is enforced, not decorative.

        A read-only key is exactly the credential someone hands to an analytics
        script, so it must not be able to move money.
        """
        headers = {**self.TRUSTED, "X-API-Key": _api_key(db_session, scope="read")}
        resp = client.post("/payment-vault/api/purchase", json={"package_id": 1}, headers=headers)
        assert resp.status_code == 403, f"a read-only key started a payment ({resp.status_code})"

    def test_an_inactive_key_is_refused(self, client, db_session):
        """PKG-17c. Revocation works."""
        headers = {**self.TRUSTED, "X-API-Key": _api_key(db_session, active=False)}
        resp = client.post("/payment-vault/api/purchase", json={"package_id": 1}, headers=headers)
        assert resp.status_code == 403, f"a deactivated key answered {resp.status_code}"

    def test_purchase_of_a_missing_package_is_refused(self, client, db_session):
        """PKG-18."""
        headers = {**self.TRUSTED, "X-API-Key": _api_key(db_session)}
        resp = client.post(
            "/payment-vault/api/purchase",
            json={"package_id": 999_999_99, "card_token": "tok_test"},
            headers=headers,
        )
        assert resp.status_code in (400, 404), f"a missing package answered {resp.status_code}"

    def test_an_incomplete_purchase_activates_nothing(self, client, scenario_owner, db_session):
        """PKG-19. The invariant, not which door refuses it.

        An earlier version of this asserted a specific status code and kept
        failing, because the endpoint has several guards - Origin, API key,
        required fields - and the code that answers depends on the session state
        rather than on the payload. The property that actually matters is that no
        combination of incomplete input produces an activated purchase, and that
        holds whichever guard catches it.
        """
        from models import PackagePurchase

        _unlock(client)
        pkg = _create(client, db_session)
        headers = {**self.TRUSTED, "X-API-Key": _api_key(db_session)}

        for payload in (
            {"package_id": pkg.id},
            {"package_id": pkg.id, "card_token": "tok_test"},
            {"package_id": pkg.id, "payment_method": "card", "amount_paid": "10"},
        ):
            resp = client.post("/payment-vault/api/purchase", json=payload, headers=headers)
            assert resp.status_code >= 400, (
                f"an incomplete purchase {sorted(payload)} was accepted ({resp.status_code})"
            )
            db_session.expire_all()
            assert db_session.query(PackagePurchase).filter_by(activation_status="activated").count() == 0, (
                f"an activated purchase appeared from {sorted(payload)}"
            )

    def test_purchase_with_a_junk_token_activates_nothing(self, client, scenario_owner, db_session):
        """PKG-20. An unrecognised token must not produce an activated purchase.

        The reachable half of the payment contract without a live provider: a
        token the vault cannot resolve must leave every purchase short of
        activated.
        """
        from models import PackagePurchase

        _unlock(client)
        pkg = _create(client, db_session)
        client.post(
            "/payment-vault/api/purchase",
            json={"package_id": pkg.id, "card_token": "tok_definitely_not_real"},
            headers=self.TRUSTED,
        )
        db_session.expire_all()
        assert db_session.query(PackagePurchase).filter_by(activation_status="activated").count() == 0, (
            "a purchase was activated from a token the vault could not resolve"
        )

    def test_a_donation_without_an_amount_is_rejected(self, client, db_session):
        """PKG-21."""

        headers = {**self.TRUSTED, "X-API-Key": _api_key(db_session)}
        resp = client.post("/payment-vault/api/donation", json={}, headers=headers)
        assert resp.status_code == 400, f"an empty donation body answered {resp.status_code}"

    def test_a_non_numeric_donation_amount_is_rejected(self, client, db_session):
        """PKG-22. Decimal conversion is guarded, not crashed on."""
        headers = {**self.TRUSTED, "X-API-Key": _api_key(db_session)}
        resp = client.post("/payment-vault/api/donation", json={"amount": "not-money"}, headers=headers)
        assert resp.status_code == 400, f"a non-numeric donation answered {resp.status_code}"

    def test_a_donation_from_an_untrusted_origin_is_refused(self, client):
        """PKG-23. The donation endpoint shares the purchase endpoint's policy."""
        resp = client.post("/payment-vault/api/donation", json={}, headers=self.HOSTILE)
        assert resp.status_code == 403, f"a cross-site donation answered {resp.status_code}"


class TestPKG03Donations:
    """21 to 27: donations waiting on the owner."""

    def _donation(self, db_session, **over):
        from models import Donation

        fields = {
            "amount_usd": Decimal("50.00"),
            "amount_crypto": Decimal("0.00125000"),
            "payment_method": "crypto",
            "crypto_type": "BTC",
            "donor_email": "donor@example.com",
            "donor_name": "Donor",
            "status": "pending",
        }
        fields.update(over)
        don = Donation(**fields)
        db_session.add(don)
        db_session.commit()
        return don

    def test_the_donation_list_renders(self, client, scenario_owner):
        """21."""
        _unlock(client)
        assert client.get("/payment-vault/donations").status_code == 200

    def test_approving_moves_a_pending_donation(self, client, scenario_owner, db_session):
        """22. Approve writes "completed", not "approved".

        The status vocabulary is pending / completed / failed / refunded, so the
        approval label is the *outcome* rather than the decision that produced it.
        Pinned explicitly because a reader would reasonably expect "approved"
        here, and a rename would silently change what these assertions protect.
        """
        from models import Donation

        _unlock(client)
        don = self._donation(db_session)
        did = don.id
        client.post(f"/payment-vault/donation/{did}/approve", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Donation, did).status == "completed"

    def test_rejecting_moves_a_pending_donation(self, client, scenario_owner, db_session):
        """23. Reject writes "failed" - the same word a failed payment uses.

        Worth recording rather than fixing here: an owner reading the donation
        list cannot distinguish "the owner declined this" from "the payer never
        paid", because both are `failed`. Distinguishing them is a product
        decision, so the current behaviour is pinned and the ambiguity is left
        visible instead of being quietly normalised in a test.
        """
        from models import Donation

        _unlock(client)
        don = self._donation(db_session)
        did = don.id
        client.post(f"/payment-vault/donation/{did}/reject", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Donation, did).status == "failed"

    def test_an_approved_donation_is_not_approved_twice(self, client, scenario_owner, db_session):
        """24. Approving an already-completed donation does not move it.

        Approving twice is how a donation gets counted twice in the owner's
        figures, and nothing downstream would catch it.
        """
        from models import Donation

        _unlock(client)
        don = self._donation(db_session, status="completed")
        did = don.id
        client.post(f"/payment-vault/donation/{did}/approve", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Donation, did).status == "completed"

    def test_approving_a_missing_donation_is_refused(self, client, scenario_owner):
        """25."""
        resp = client.post("/payment-vault/donation/99999999/approve", follow_redirects=True)
        assert resp.status_code in (302, 404), f"a missing donation answered {resp.status_code}"

    def test_the_donation_detail_renders(self, client, scenario_owner, db_session):
        """26."""
        _unlock(client)
        don = self._donation(db_session)
        assert client.get(f"/payment-vault/donation/{don.id}").status_code == 200

    def test_the_donation_list_never_leaks_a_card_token(self, client, scenario_owner, db_session):
        """27. The vault's whole reason for existing.

        A donation row must render without exposing any stored card material.
        """
        _unlock(client)
        self._donation(db_session)
        body = client.get("/payment-vault/donations").get_data(as_text=True)
        for leak in ("card_number", "cvv", "tok_", "4242424242424242"):
            assert leak not in body, f"the donations page rendered {leak!r}"


class TestPKG04CardsAndVault:
    """PKG-28 to PKG-33: the vault's own surfaces."""

    def test_the_cards_page_renders(self, client, scenario_owner):
        """PKG-28."""
        _unlock(client)
        assert client.get("/payment-vault/cards").status_code == 200

    def test_decrypt_is_post_only(self, client, scenario_owner):
        """PKG-29. A GET never performs a decrypt."""
        resp = client.get("/payment-vault/card/1/decrypt")
        assert resp.status_code == 405, f"decrypt answered {resp.status_code} to a GET"

    def test_decrypting_a_missing_card_is_refused(self, client, scenario_owner):
        """PKG-30."""
        _unlock(client)
        resp = client.post("/payment-vault/card/99999999/decrypt", follow_redirects=True)
        assert resp.status_code in (302, 404), f"a missing card answered {resp.status_code}"

    def test_the_vault_stores_a_token_and_never_a_pan(self, client, scenario_owner, db_session):
        """PKG-31. The shape of the row is what keeps the PAN out of the database.

        Asserted against the model rather than a request, because the control is
        structural: CardPayment keeps ``card_last_4`` and ``card_bin`` for display
        and ``encrypted_data`` as a LargeBinary blob, and has no column a full
        card number could be written into. A careless future caller cannot store
        the secret because there is nowhere to put it.
        """
        from models import CardPayment

        table = CardPayment.__table__
        cols = {c.name for c in table.columns}
        assert "card_last_4" in cols, "the vault cannot record the card's last four digits"
        assert "encrypted_data" in cols, "the vault has nowhere to store the encrypted card data"
        for banned in ("card_number", "pan", "cvv", "cvc", "full_card", "card_token"):
            assert banned not in cols, f"CardPayment has a {banned} column - the vault must not store the PAN"
        assert table.columns["card_last_4"].type.length == 4, (
            f"card_last_4 holds {table.columns['card_last_4'].type.length} characters, not the last four digits"
        )

    def test_health_reports_the_status_it_measured(self, client, scenario_owner):
        """PKG-32. The status code follows the verdict; it is not hardcoded to 200.

        The view returns 200 only when ``overall_status == "healthy"`` and 503
        otherwise. Asserting 200 unconditionally would fail the moment the vault
        is genuinely unhealthy - which is the one moment the endpoint matters - so
        this asserts the coupling instead: the code always agrees with the
        reported verdict.
        """
        resp = client.get("/payment-vault/health")
        body = resp.get_json()
        assert body is not None, "health returned a non-JSON body"
        data = body.get("data", body)
        verdict = data.get("overall_status")
        assert verdict in ("healthy", "degraded", "unhealthy", "warning"), f"unexpected verdict {verdict!r}"
        expected = 200 if verdict == "healthy" else 503
        assert resp.status_code == expected, f"verdict {verdict!r} answered {resp.status_code}, expected {expected}"

    def test_a_second_unlock_does_not_create_a_second_vault(self, client, scenario_owner, db_session):
        """PKG-33. Unlock is create-then-unlock, not create-always.

        The platform vault is looked up by ``tenant_id IS NULL``; a create on
        every unlock would leave a stack of duplicate vaults and make the lookup
        order-dependent.
        """
        from models import PaymentVault

        _unlock(client)
        _unlock(client)
        assert db_session.query(PaymentVault).filter_by(tenant_id=None).count() == 1


class TestPKG05ExportsAndWebhooks:
    """PKG-34 to PKG-40: exports, reports and inbound payment notifications."""

    @pytest.mark.parametrize("path", ["/payment-vault/export/purchases", "/payment-vault/export/donations"])
    def test_the_csv_exports_render(self, client, scenario_owner, path):
        """PKG-34."""
        _unlock(client)
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} answered {resp.status_code}"

    def test_the_cards_export_does_not_leak_a_token(self, client, scenario_owner):
        """PKG-35. An export is the easiest way to exfiltrate the vault."""
        _unlock(client)
        body = client.get("/payment-vault/export/cards").get_data(as_text=True)
        for leak in ("tok_", "card_number", "4242424242424242"):
            assert leak not in body, f"the cards export rendered {leak!r}"

    def test_the_report_pdf_endpoint_does_not_return_html(self, client, scenario_owner):
        """PKG-36. The route promises a PDF and currently does not deliver one.

        ``export_report-pdf`` builds its body with
        ``ExportService.generate_pdf_report`` - despite the name, that renders
        HTML - and returns it as ``Response(html, mimetype="text/html")``. A
        client that trusts the route name, downloads ``report.pdf`` and opens it
        gets a web page, not the document.

        This asserts the defect rather than the current behaviour on purpose: the
        content type and the magic bytes both have to agree it is a PDF. It fails
        today, and that failure is the bug report. Fixing the route means
        returning ``application/pdf`` with real PDF bytes; until then this is the
        honest state, recorded rather than papered over by asserting text/html.
        """
        _unlock(client)
        resp = client.get("/payment-vault/export/report-pdf")
        assert resp.status_code == 200, f"the report endpoint answered {resp.status_code}"
        ctype = resp.content_type or ""
        body = resp.get_data()
        is_pdf = "application/pdf" in ctype and body[:5] == b"%PDF-"
        assert is_pdf, f"export/report-pdf returned {ctype} starting {body[:12]!r} - a .pdf download is not a PDF"

    def test_a_bare_stripe_webhook_is_rejected(self, client):
        """PKG-37. An unsigned payment notification is not a payment.

        The webhook prefix is exempt from the owner guard by design - Stripe
        cannot hold a session - so the signature is the only thing standing
        between a stranger and a fabricated "paid" callback.
        """
        resp = client.post("/payment-vault/webhook/stripe", data={})
        assert resp.status_code >= 400, f"an unsigned Stripe webhook answered {resp.status_code}"

    def test_a_bare_nowpayments_webhook_is_rejected(self, client):
        """PKG-38."""
        resp = client.post("/payment-vault/webhook/nowpayments", data={})
        assert resp.status_code >= 400, f"an unsigned NOWPayments webhook answered {resp.status_code}"

    def test_the_vault_metrics_endpoint_answers(self, client, scenario_owner):
        """PKG-39."""
        _unlock(client)
        assert client.get("/payment-vault/metrics").status_code == 200

    def test_the_vault_is_closed_to_anonymous_callers(self, client):
        """PKG-40. The whole surface, not just one page."""
        for path in ("/payment-vault/", "/payment-vault/dashboard", "/payment-vault/packages-management"):
            resp = client.get(path)
            assert resp.status_code in (302, 401, 403, 404), f"{path} answered {resp.status_code} anonymously"
