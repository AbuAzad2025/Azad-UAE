import io
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import app_factory


@pytest.fixture
def public_client(app_factory):
    from routes.public import public_bp
    app = app_factory(public_bp)
    return app.test_client()


def _mock_vault(enabled=True, page_enabled=True, min_amt=10, max_amt=10000):
    vault = MagicMock()
    vault.donations_enabled = enabled
    vault.donation_page_enabled = page_enabled
    vault.min_donation_amount = min_amt
    vault.max_donation_amount = max_amt
    vault.donation_title_ar = "تبرع"
    vault.donation_title_en = "Donate"
    vault.donation_intro_ar = "مقدمة"
    vault.donation_intro_en = "Intro"
    vault.bitcoin_address = "bc1test"
    vault.bank_iban = "AE123"
    vault.bank_account_number = "123"
    vault.paypal_business_email = "pay@test.com"
    vault.bank_name = "Test Bank"
    return vault


def _vault_patch(vault):
    return patch(
        "models.payment_vault.PaymentVault.get_platform_vault",
        return_value=vault,
    )


class TestPublicLanding:
    def test_landing_returns_200(self, public_client):
        with patch("routes.public.render_template", return_value="landing") as render:
            resp = public_client.get("/")
        assert resp.status_code == 200
        render.assert_called_once_with("public/landing.html", packages=[], is_en=False)


class TestPublicPricing:
    def test_pricing_arabic_default(self, public_client):
        with patch("routes.public.render_template", return_value="pricing") as render:
            resp = public_client.get("/pricing")
        assert resp.status_code == 200
        render.assert_called_once_with("public/pricing.html", packages=[], is_en=False, developer_whatsapp_link="")


    def test_pricing_english_session(self, public_client):
        with public_client.session_transaction() as sess:
            sess["language"] = "en"
        with patch("routes.public.render_template", return_value="pricing-en") as render:
            resp = public_client.get("/pricing")
        assert resp.status_code == 200
        render.assert_called_once_with("public/pricing.html", packages=[], is_en=True, developer_whatsapp_link="")

class TestPublicFeatures:
    def test_features_arabic_default(self, public_client):
        with patch("routes.public.render_template", return_value="features") as render:
            resp = public_client.get("/features")
        assert resp.status_code == 200
        render.assert_called_once_with("public/features.html")

    def test_features_english_session(self, public_client):
        with public_client.session_transaction() as sess:
            sess["language"] = "en"
        with patch("routes.public.render_template", return_value="features-en") as render:
            resp = public_client.get("/features")
        assert resp.status_code == 200
        render.assert_called_once_with("public/features_en.html")


class TestPublicUserGuide:
    def test_user_guide_arabic_default(self, public_client):
        with patch("routes.public.render_template", return_value="guide") as render:
            resp = public_client.get("/user-guide")
        assert resp.status_code == 200
        render.assert_called_once_with("public/user_guide.html")

    def test_user_guide_english_session(self, public_client):
        with public_client.session_transaction() as sess:
            sess["language"] = "en"
        with patch("routes.public.render_template", return_value="guide-en") as render:
            resp = public_client.get("/user-guide")
        assert resp.status_code == 200
        render.assert_called_once_with("public/user_guide_en.html")


class TestPublicContact:
    def test_contact_arabic_default(self, public_client):
        with patch("routes.public.render_template", return_value="contact") as render:
            resp = public_client.get("/contact")
        assert resp.status_code == 200
        render.assert_called_once_with("public/contact.html")

    def test_contact_english_session(self, public_client):
        with public_client.session_transaction() as sess:
            sess["language"] = "en"
        with patch("routes.public.render_template", return_value="contact-en") as render:
            resp = public_client.get("/contact")
        assert resp.status_code == 200
        render.assert_called_once_with("public/contact_en.html")


class TestPublicDonate:
    def test_donate_renders_when_enabled(self, public_client):
        vault = _mock_vault()
        with _vault_patch(vault), patch("routes.public.render_template", return_value="donate") as render:
            resp = public_client.get("/donate")
        assert resp.status_code == 200
        render.assert_called_once()
        assert render.call_args[0][0] == "public/donate_azad.html"
        assert render.call_args[1]["is_en"] is False

    def test_support_azad_alias(self, public_client):
        vault = _mock_vault()
        with _vault_patch(vault), patch("routes.public.render_template", return_value="donate"):
            resp = public_client.get("/support-azad")
        assert resp.status_code == 200

    def test_donate_english_session(self, public_client):
        vault = _mock_vault()
        with public_client.session_transaction() as sess:
            sess["language"] = "en"
        with _vault_patch(vault), patch("routes.public.render_template", return_value="donate") as render:
            resp = public_client.get("/donate")
        assert resp.status_code == 200
        assert render.call_args[1]["is_en"] is True

    def test_donate_404_no_vault(self, public_client):
        with _vault_patch(None):
            resp = public_client.get("/donate")
        assert resp.status_code == 404

    def test_donate_404_donations_disabled(self, public_client):
        vault = _mock_vault(enabled=False)
        with _vault_patch(vault):
            resp = public_client.get("/donate")
        assert resp.status_code == 404

    def test_donate_404_page_disabled(self, public_client):
        vault = _mock_vault(page_enabled=False)
        with _vault_patch(vault):
            resp = public_client.get("/donate")
        assert resp.status_code == 404


class TestPublicDonateSubmit:
    def _post_donation(self, public_client, data, lang="ar"):
        vault = _mock_vault()
        with public_client.session_transaction() as sess:
            sess["language"] = lang
        with _vault_patch(vault), patch("extensions.db.session") as mock_session, \
             patch("routes.public.render_template", return_value="thanks") as render, \
             patch("routes.public.redirect") as mock_redirect:
            mock_redirect.side_effect = lambda *a, **k: ("redirect", 302)
            resp = public_client.post("/donate/submit", data=data)
        return resp, render, mock_session, mock_redirect, vault

    def test_submit_success_arabic(self, public_client):
        resp, render, mock_session, _, vault = self._post_donation(
            public_client,
            {"amount": "50", "payment_method": "bank_transfer", "donor_name": "Ali"},
        )
        assert resp.status_code == 200
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        render.assert_called_once()
        assert render.call_args[0][0] == "public/donate_thanks.html"

    def test_submit_success_english(self, public_client):
        resp, render, mock_session, _, _ = self._post_donation(
            public_client,
            {"amount": "50", "donor_name": "John"},
            lang="en",
        )
        assert resp.status_code == 200
        assert render.call_args[1]["is_en"] is True

    def test_submit_404_when_disabled(self, public_client):
        with _vault_patch(_mock_vault(enabled=False)):
            resp = public_client.post("/donate/submit", data={"amount": "50"})
        assert resp.status_code == 404

    def test_submit_amount_below_minimum_ar(self, public_client):
        vault = _mock_vault(min_amt=10)
        with public_client.session_transaction() as sess:
            sess["language"] = "ar"
        with _vault_patch(vault), patch("flask.flash") as flash, \
             patch("routes.public.redirect", side_effect=lambda *a, **k: ("redirect", 302)):
            resp = public_client.post("/donate/submit", data={"amount": "5"})
        assert resp.status_code == 302
        flash.assert_called_once()
        assert "الحد الأدنى" in flash.call_args[0][0]

    def test_submit_amount_below_minimum_en(self, public_client):
        vault = _mock_vault(min_amt=10)
        with public_client.session_transaction() as sess:
            sess["language"] = "en"
        with _vault_patch(vault), patch("flask.flash") as flash, \
             patch("routes.public.redirect", side_effect=lambda *a, **k: ("redirect", 302)):
            resp = public_client.post("/donate/submit", data={"amount": "5"})
        assert resp.status_code == 302
        flash.assert_called_once()
        assert "below minimum" in flash.call_args[0][0]

    def test_submit_amount_above_maximum_ar(self, public_client):
        vault = _mock_vault(max_amt=100)
        with public_client.session_transaction() as sess:
            sess["language"] = "ar"
        with _vault_patch(vault), patch("flask.flash") as flash, \
             patch("routes.public.redirect", side_effect=lambda *a, **k: ("redirect", 302)):
            resp = public_client.post("/donate/submit", data={"amount": "500"})
        assert resp.status_code == 302
        assert "الحد الأقصى" in flash.call_args[0][0]

    def test_submit_amount_above_maximum_en(self, public_client):
        vault = _mock_vault(max_amt=100)
        with public_client.session_transaction() as sess:
            sess["language"] = "en"
        with _vault_patch(vault), patch("flask.flash") as flash, \
             patch("routes.public.redirect", side_effect=lambda *a, **k: ("redirect", 302)):
            resp = public_client.post("/donate/submit", data={"amount": "500"})
        assert resp.status_code == 302
        assert "exceeds maximum" in flash.call_args[0][0]

    def test_submit_generic_error_ar(self, public_client):
        vault = _mock_vault()
        with public_client.session_transaction() as sess:
            sess["language"] = "ar"
        with _vault_patch(vault), patch("extensions.db.session") as mock_session, \
             patch("flask.flash") as flash, \
             patch("routes.public.redirect", side_effect=lambda *a, **k: ("redirect", 302)):
            mock_session.commit.side_effect = RuntimeError("db fail")
            resp = public_client.post("/donate/submit", data={"amount": "50"})
        assert resp.status_code == 302
        mock_session.rollback.assert_called_once()
        assert "تعذر إرسال" in flash.call_args[0][0]

    def test_submit_generic_error_en(self, public_client):
        vault = _mock_vault()
        with public_client.session_transaction() as sess:
            sess["language"] = "en"
        with _vault_patch(vault), patch("extensions.db.session") as mock_session, \
             patch("flask.flash") as flash, \
             patch("routes.public.redirect", side_effect=lambda *a, **k: ("redirect", 302)):
            mock_session.commit.side_effect = RuntimeError("db fail")
            resp = public_client.post("/donate/submit", data={"amount": "50"})
        assert resp.status_code == 302
        assert "Could not submit" in flash.call_args[0][0]


class TestPublicSitemap:
    def test_sitemap_returns_xml(self, public_client):
        resp = public_client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert resp.mimetype == "application/xml"
        body = resp.get_data(as_text=True)
        assert "<?xml" in body
        assert "<urlset" in body
        assert "/pricing" in body
        assert "/features" in body
        assert "<lastmod>" in body


class TestPublicSafeVault:
    def test_safe_vault_for_public_none(self):
        from routes.public import _safe_vault_for_public
        assert _safe_vault_for_public(None) is None


class TestPublicRobots:
    def test_robots_returns_plain_text(self, public_client):
        resp = public_client.get("/robots.txt")
        assert resp.status_code == 200
        assert resp.mimetype == "text/plain"
        body = resp.get_data(as_text=True)
        assert "User-agent:" in body
        assert "Sitemap:" in body
        assert "Disallow: /owner/" in body


class TestPublicTenantSuspended:
    def test_tenant_suspend_page_renders(self, public_client):
        tenant = MagicMock()
        tenant.suspension_reason = "Payment overdue"
        with patch("models.Tenant") as tenant_model, \
             patch("routes.public.render_template", return_value="suspended") as render:
            tenant_model.query.get_or_404.return_value = tenant
            resp = public_client.get("/suspended/7")
        assert resp.status_code == 200
        render.assert_called_once_with(
            "public/tenant_suspended.html",
            tenant=tenant,
            reason="Payment overdue",
        )

    def test_tenant_suspend_default_reason(self, public_client):
        tenant = MagicMock()
        tenant.suspension_reason = None
        with patch("models.Tenant") as tenant_model, \
             patch("routes.public.render_template", return_value="suspended") as render:
            tenant_model.query.get_or_404.return_value = tenant
            resp = public_client.get("/suspended/3")
        assert resp.status_code == 200
        assert render.call_args[1]["reason"] == "Tenant suspended"
