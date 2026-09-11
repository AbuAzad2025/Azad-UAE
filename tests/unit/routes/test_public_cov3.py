"""Coverage for routes/public.py remaining arcs.

Targets: _safe_vault_for_public None arc, _public_packages exception arc,
landing ?lang invalid arc, donate 404 arcs, donate submit min/max/generic
arcs, sitemap/robots/humans/verify/suspended arcs. Real test-client paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def public_cov3_client(app_factory):
    from routes.public import public_bp

    app = app_factory(public_bp)
    return app.test_client()


def _vault(**kw):
    v = MagicMock()
    v.donations_enabled = kw.get("donations_enabled", True)
    v.donation_page_enabled = kw.get("donation_page_enabled", True)
    v.min_donation_amount = kw.get("min_donation_amount", 10)
    v.max_donation_amount = kw.get("max_donation_amount", 10000)
    v.donation_title_ar = "تبرع"
    v.donation_title_en = "Donate"
    v.donation_intro_ar = "م"
    v.donation_intro_en = "I"
    v.bitcoin_address = "bc1"
    v.bank_iban = "AE1"
    v.bank_account_number = "1"
    v.paypal_business_email = "p@t.com"
    v.bank_name = "B"
    return v


class TestHelpers:
    def test_safe_vault_none(self):
        from routes.public import _safe_vault_for_public

        assert _safe_vault_for_public(None) is None

    def test_safe_vault_fields(self):
        from routes.public import _safe_vault_for_public

        safe = _safe_vault_for_public(_vault())
        assert safe["bitcoin_address"] == "bc1"
        assert "donations_enabled" in safe

    def test_public_packages_exception(self):
        from routes import public as pub

        with patch(
            "services.saas_provisioning_service.SaaSProvisioningService.list_active_packages",
            side_effect=Exception("db down"),
        ):
            assert pub._public_packages() == []

    def test_landing_invalid_lang_falls_back_to_session(self, public_cov3_client):
        with public_cov3_client.session_transaction() as sess:
            sess["language"] = "en"
        with (
            patch("flask_login.current_user", MagicMock(is_authenticated=False)),
            patch("routes.public.render_template", return_value="landing") as render,
        ):
            resp = public_cov3_client.get("/?lang=fr")
        assert resp.status_code == 200
        render.assert_called_once()
        assert render.call_args[1]["is_en"] is True


class TestDonate:
    def test_donate_404_when_disabled(self, public_cov3_client):
        with patch(
            "models.payment_vault.PaymentVault.get_platform_vault",
            return_value=_vault(donations_enabled=False),
        ):
            resp = public_cov3_client.get("/donate")
        assert resp.status_code == 404

    def test_donate_404_when_no_vault(self, public_cov3_client):
        with patch("models.payment_vault.PaymentVault.get_platform_vault", return_value=None):
            resp = public_cov3_client.get("/support-azad")
        assert resp.status_code == 404

    def test_donate_renders_when_enabled(self, public_cov3_client):
        with (
            patch(
                "models.payment_vault.PaymentVault.get_platform_vault",
                return_value=_vault(),
            ),
            patch("routes.public.render_template", return_value="donate"),
        ):
            resp = public_cov3_client.get("/donate")
        assert resp.status_code == 200

    def test_submit_below_minimum_redirects(self, public_cov3_client):
        with patch(
            "models.payment_vault.PaymentVault.get_platform_vault",
            return_value=_vault(min_donation_amount=10),
        ):
            resp = public_cov3_client.post("/donate/submit", data={"amount": "1"})
        assert resp.status_code == 302

    def test_submit_above_maximum_redirects(self, public_cov3_client):
        with patch(
            "models.payment_vault.PaymentVault.get_platform_vault",
            return_value=_vault(max_donation_amount=100),
        ):
            resp = public_cov3_client.post("/donate/submit", data={"amount": "9999"})
        assert resp.status_code == 302

    def test_submit_404_when_disabled(self, public_cov3_client):
        with patch(
            "models.payment_vault.PaymentVault.get_platform_vault",
            return_value=_vault(donation_page_enabled=False),
        ):
            resp = public_cov3_client.post("/donate/submit", data={"amount": "50"})
        assert resp.status_code == 404

    def test_submit_success_renders_thanks(self, public_cov3_client):
        with (
            patch(
                "models.payment_vault.PaymentVault.get_platform_vault",
                return_value=_vault(),
            ),
            patch("routes.public.render_template", return_value="thanks"),
            patch("routes.public.atomic_transaction"),
            patch("extensions.db.session"),
        ):
            resp = public_cov3_client.post(
                "/donate/submit",
                data={"amount": "50", "payment_method": "cash", "donor_name": "A"},
            )
        assert resp.status_code == 200

    def test_submit_generic_exception_redirects(self, public_cov3_client):
        with (
            patch(
                "models.payment_vault.PaymentVault.get_platform_vault",
                return_value=_vault(),
            ),
            patch("routes.public.render_template", side_effect=Exception("tpl down")),
        ):
            resp = public_cov3_client.post("/donate/submit", data={"amount": "50"})
        assert resp.status_code == 302


class TestSeoAndVerify:
    def test_sitemap_xml(self, public_cov3_client):
        resp = public_cov3_client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert b"<urlset" in resp.data

    def test_robots_txt(self, public_cov3_client):
        resp = public_cov3_client.get("/robots.txt")
        assert resp.status_code == 200
        assert b"User-agent" in resp.data

    def test_humans_txt(self, public_cov3_client):
        resp = public_cov3_client.get("/humans.txt")
        assert resp.status_code == 200
        assert b"AZAD" in resp.data

    def test_verify_404_when_missing(self, public_cov3_client):
        with patch(
            "services.document_verification_service.DocumentVerificationService.lookup_by_token",
            return_value=None,
        ):
            resp = public_cov3_client.get("/verify/nope")
        assert resp.status_code == 404

    def test_verify_renders_when_found(self, public_cov3_client):
        with (
            patch(
                "services.document_verification_service.DocumentVerificationService.lookup_by_token",
                return_value={
                    "document": MagicMock(),
                    "document_type": "sale",
                    "document_id": 1,
                    "document_hash": "abc",
                },
            ),
            patch("routes.public.render_template", return_value="verified"),
        ):
            resp = public_cov3_client.get("/verify/tok123")
        assert resp.status_code == 200

    def test_suspended_page_renders(self, public_cov3_client):
        tenant = MagicMock()
        tenant.suspension_reason = "late"
        with (
            patch("models.Tenant.query") as q,
            patch("routes.public.render_template", return_value="suspended"),
        ):
            q.get_or_404.return_value = tenant
            resp = public_cov3_client.get("/suspended/5")
        assert resp.status_code == 200

    def test_contact_english(self, public_cov3_client):
        with public_cov3_client.session_transaction() as sess:
            sess["language"] = "en"
        with patch("routes.public.render_template", return_value="contact") as render:
            resp = public_cov3_client.get("/contact")
        assert resp.status_code == 200
        render.assert_called_once_with("public/contact_en.html")
