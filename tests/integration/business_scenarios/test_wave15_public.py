"""Wave 15 - the public surface: landing, pricing, donations and the SEO files.

Everything on this blueprint is reachable without signing in, which is exactly
why it needs a scenario suite. A public page is the one surface where a
mistake is read by strangers rather than by the people who can fix it, and
where a mistake in the *data* is a mistake in the world: the donation page
shows the platform's bank details, so what it exposes is a public decision
rather than a rendering detail.

Two rules are pinned here. The first is the donation gate: the page and the
submit both answer 404 unless the platform vault has switched donations on
(PUB-14, PUB-16). A donation form that renders while donations are switched
off invites a payment that nothing will reconcile.

The second is the amount range. The submit refuses an amount below the
minimum and above the maximum (PUB-17, PUB-18), and both refusals leave the
donation unrecorded - which is the part that matters, because a donation row
that says "pending" for an amount the vault never accepted is money the
platform thinks it is owed.

The rest of the blueprint is the marketing shell, and its rules are about
honesty rather than money: the landing sends a signed-in user to the
dashboard instead of showing them the marketing page (PUB-02), the legacy
alias redirects permanently so the search engines see one canonical landing
(PUB-03), and robots.txt keeps the owner and money surfaces out of the index
(PUB-21).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

PUBLIC_PATHS = [
    "/",
    "/welcome",
    "/pricing",
    "/features",
    "/user-guide",
    "/contact",
    "/sitemap.xml",
    "/robots.txt",
    "/humans.txt",
]


def _vault(db_session, **flags):
    """The platform vault, with the donation switches as the scenario wants them.

    The platform vault is tenant-less by design - its ``tenant_id`` is NULL -
    so it is created the same way: a vault that belongs to no tenant is what
    the platform's own money is kept in.
    """
    from models.payment_vault import PaymentVault

    vault = PaymentVault.get_platform_vault()
    if vault is None:
        vault = PaymentVault(
            tenant_id=None,
            vault_name="Platform Vault",
            vault_password_hash="not-a-real-hash",
            is_locked=False,
        )
        db_session.add(vault)
        db_session.flush()
    for field, value in flags.items():
        setattr(vault, field, value)
    db_session.flush()
    return vault


class TestPUB01ThePublicShell:
    """PUB-01 to PUB-06: the marketing pages."""

    def test_the_landing_page_answers_to_a_visitor(self, client):
        """PUB-01. The first screen of the product is open to the world."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_landing_sends_a_signed_in_user_to_the_dashboard(self, client, db_session, demo_tenant, demo_branch):
        """PUB-02. A customer who works here does not need the marketing page."""
        from models import Permission, Role, User

        role = Role(name="Public Reader", slug=f"public-reader-{uuid.uuid4().hex[:6]}", is_active=True)
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()
        unique = uuid.uuid4().hex[:8]
        user = User(
            username=f"public-{unique}",
            email=f"public-{unique}@example.com",
            full_name="Public Reader",
            tenant_id=demo_tenant.id,
            role_id=role.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()

        client.post(
            "/auth/login",
            data={"username": user.username, "password": "Str0ng!Pass99"},
            follow_redirects=True,
        )
        resp = client.get("/")
        assert resp.status_code in (302, 301), f"the landing answered {resp.status_code} to a signed-in user"
        assert "/dashboard" in resp.headers.get("Location", "")

    def test_the_legacy_landing_alias_redirects_permanently(self, client):
        """PUB-03. A permanent redirect keeps one canonical landing page."""
        resp = client.get("/welcome")
        assert resp.status_code == 301, f"the alias answered {resp.status_code}"
        assert resp.headers.get("Location", "").endswith("/")

    def test_the_alias_keeps_the_language(self, client):
        """PUB-04. The hreflang variant is not lost by the redirect."""
        resp = client.get("/welcome?lang=en")
        assert resp.status_code == 301
        assert "lang=en" in resp.headers.get("Location", "")

    def test_the_pricing_page_answers(self, client):
        """PUB-05."""
        resp = client.get("/pricing")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_features_and_guide_pages_answer(self, client):
        """PUB-06."""
        for path in ("/features", "/user-guide", "/contact"):
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} answered {resp.status_code}"


class TestPUB10TheDonationGate:
    """PUB-10 to PUB-19: the one public page that takes money."""

    def test_the_donation_page_is_hidden_when_donations_are_off(self, client, db_session):
        """PUB-10."""
        _vault(db_session, donations_enabled=False, donation_page_enabled=False)
        resp = client.get("/donate")
        assert resp.status_code == 404, f"the donation page answered {resp.status_code}"

    def test_the_support_alias_is_hidden_too(self, client, db_session):
        """PUB-11. Two URLs, one gate."""
        _vault(db_session, donations_enabled=False, donation_page_enabled=False)
        resp = client.get("/support-azad")
        assert resp.status_code == 404, f"the alias answered {resp.status_code}"

    def test_the_donation_page_answers_when_donations_are_on(self, client, db_session):
        """PUB-12."""
        _vault(
            db_session,
            donations_enabled=True,
            donation_page_enabled=True,
            donation_title_ar="تبرع",
            donation_title_en="Donate",
        )
        resp = client.get("/donate")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_donation_page_does_not_expose_the_vault(self, client, db_session):
        """PUB-13. The page shows the donation details, not the vault."""
        _vault(
            db_session,
            donations_enabled=True,
            donation_page_enabled=True,
            paypal_business_email="secret-paypal@example.com",
        )
        resp = client.get("/donate")
        assert resp.status_code == 200
        assert "secret-paypal@example.com" not in resp.get_data(as_text=True)

    def test_the_submit_is_hidden_when_donations_are_off(self, client, db_session):
        """PUB-14. A submit that answers while donations are off is a payment nobody reconciles."""
        _vault(db_session, donations_enabled=False, donation_page_enabled=False)
        resp = client.post("/donate/submit", data={"amount": "50"})
        assert resp.status_code == 404, f"the submit answered {resp.status_code}"

    def test_a_donation_below_the_minimum_is_refused(self, client, db_session):
        """PUB-15."""
        _vault(
            db_session,
            donations_enabled=True,
            donation_page_enabled=True,
            min_donation_amount=Decimal("10.00"),
            max_donation_amount=Decimal("10000.00"),
        )
        resp = client.post("/donate/submit", data={"amount": "1"})
        assert resp.status_code in (200, 302)

        from models.donation import Donation

        assert db_session.query(Donation).count() == 0, "a refused donation was still recorded"

    def test_a_donation_above_the_maximum_is_refused(self, client, db_session):
        """PUB-16."""
        _vault(
            db_session,
            donations_enabled=True,
            donation_page_enabled=True,
            min_donation_amount=Decimal("10.00"),
            max_donation_amount=Decimal("100.00"),
        )
        resp = client.post("/donate/submit", data={"amount": "1000"})
        assert resp.status_code in (200, 302)

        from models.donation import Donation

        assert db_session.query(Donation).count() == 0, "a refused donation was still recorded"

    def test_a_donation_inside_the_range_is_recorded_as_pending(self, client, db_session):
        """PUB-17. A donation is recorded, not paid."""
        _vault(
            db_session,
            donations_enabled=True,
            donation_page_enabled=True,
            min_donation_amount=Decimal("10.00"),
            max_donation_amount=Decimal("10000.00"),
        )
        resp = client.post(
            "/donate/submit",
            data={"amount": "50", "donor_name": "Probe Donor", "donor_email": "donor@example.com"},
        )
        assert resp.status_code in (200, 302)

        from models.donation import Donation

        donation = db_session.query(Donation).order_by(Donation.id.desc()).first()
        assert donation is not None, "the donation was not recorded"
        assert donation.status == "pending"
        assert Decimal(str(donation.amount_usd)) == Decimal("50")
        assert donation.donor_name == "Probe Donor"

    def test_a_donation_carries_the_transaction_type(self, client, db_session):
        """PUB-18. A donation that does not say it is a donation is not a donation."""
        _vault(
            db_session,
            donations_enabled=True,
            donation_page_enabled=True,
            min_donation_amount=Decimal("1.00"),
            max_donation_amount=Decimal("10000.00"),
        )
        client.post("/donate/submit", data={"amount": "25"})

        from models.donation import Donation

        donation = db_session.query(Donation).order_by(Donation.id.desc()).first()
        assert donation is not None
        assert donation.transaction_type == "donation"

    def test_the_donation_page_needs_both_switches(self, client, db_session):
        """PUB-19. One switch on its own is not a donation page."""
        _vault(db_session, donations_enabled=True, donation_page_enabled=False)
        resp = client.get("/donate")
        assert resp.status_code == 404, f"the donation page answered {resp.status_code}"


class TestPUB20TheSeoFiles:
    """PUB-20 to PUB-25: what the crawlers are told."""

    def test_the_sitemap_answers_as_xml(self, client):
        """PUB-20."""
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/xml")
        assert "<urlset" in resp.get_data(as_text=True)

    def test_the_sitemap_lists_the_pricing_page(self, client):
        """PUB-21. A page that is not in the sitemap is a page nobody finds."""
        resp = client.get("/sitemap.xml")
        assert "/pricing" in resp.get_data(as_text=True)

    def test_the_robots_file_answers_as_text(self, client):
        """PUB-22."""
        resp = client.get("/robots.txt")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/plain")
        assert "User-agent" in resp.get_data(as_text=True)

    def test_the_robots_file_keeps_the_owner_surface_out(self, client):
        """PUB-23. The owner panel is not for the index."""
        body = client.get("/robots.txt").get_data(as_text=True)
        assert "Disallow: /owner/" in body

    def test_the_robots_file_keeps_the_money_surfaces_out(self, client):
        """PUB-24."""
        body = client.get("/robots.txt").get_data(as_text=True)
        for path in ("/payments/", "/sales/", "/ledger/", "/cheques/"):
            assert f"Disallow: {path}" in body, f"{path} is not kept out of the index"

    def test_the_robots_file_points_at_the_sitemap(self, client):
        """PUB-25."""
        body = client.get("/robots.txt").get_data(as_text=True)
        assert "Sitemap:" in body
