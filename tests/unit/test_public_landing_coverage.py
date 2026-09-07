"""Boost template coverage for the 2 remaining uncovered templates.

Coverage report showed 370/372 (99.5%) — missing:
  - public/landing.html
  - partials/seo-landing.html (included by landing.html)

Previous tests mocked render_template, so the signal was never fired.
These tests do real rendering, which triggers the template_rendered signal
tracked in tests/conftest.py -> templates_rendered.json.
"""

from unittest.mock import patch

from flask import render_template


def test_landing_renders_ar_and_en(app):
    """Real render of public/landing.html in both languages.

    Covers public/landing.html + via _expand_includes also covers
    partials/seo-landing.html (included at line 49 of landing.html).
    """
    with app.test_request_context("/", base_url="http://testserver"):
        html_ar = render_template("public/landing.html", packages=[], is_en=False)
        assert html_ar
        assert "landing" in html_ar.lower() or "أزاد" in html_ar or "Azad" in html_ar
        # seo-landing is included, ensure its JSON-LD is present
        assert "SoftwareApplication" in html_ar or "FAQPage" in html_ar

        html_en = render_template("public/landing.html", packages=[], is_en=True)
        assert html_en
        assert len(html_en) > 1000


def test_seo_landing_direct_render(app):
    """Direct render ensures the partial itself is tracked even if include logic changes."""
    with app.test_request_context("/", base_url="http://testserver"):
        html = render_template("partials/seo-landing.html")
        assert "SoftwareApplication" in html
        assert "FAQPage" in html


def test_landing_via_client_real_render(app):
    """End-to-end via test client with real template (no render_template mock).

    Patches only the DB-dependent helper _public_packages to avoid needing
    SaaS data, but lets Jinja actually render.
    """
    from tests.conftest import TestConfig  # noqa: F401 ensure app fixture uses test DB

    client = app.test_client()
    with patch("flask_login.current_user") as mock_user:
        mock_user.is_authenticated = False
        with patch("routes.public._public_packages", return_value=[]):
            resp = client.get("/", follow_redirects=False)
            assert resp.status_code == 200
            data = resp.get_data(as_text=True)
            assert "Azad" in data or "أزاد" in data
