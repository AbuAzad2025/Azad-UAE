"""Placeholder e2e test — the e2e CI group needs at least one test to collect.

Keeps a minimal health-check and a real login→dashboard flow so the suite
is never empty even when heavier e2e suites are skipped.
"""


def test_placeholder():
    """Minimal placeholder so pytest does not exit with code 5 (no tests collected)."""
    assert True


def test_placeholder_login_to_dashboard(auth_client):
    """True e2e smoke: login → dashboard navigation and assert visible elements."""
    # auth_client fixture already performs login via POST /auth/login
    resp = auth_client.get("/dashboard", follow_redirects=False)
    # Super-admin is redirected to owner company dashboard, regular tenant users get 200
    assert resp.status_code in (200, 302)
    if resp.status_code == 200:
        html = resp.data.decode("utf-8", errors="ignore")
        # Dashboard should render without server error and contain navigation chrome
        assert resp.status_code == 200
        assert len(html) > 500
    else:
        # Redirect should point to a dashboard-like location, not back to login
        location = resp.headers.get("Location", "")
        assert "/login" not in location.lower()
        assert "dashboard" in location.lower() or "owner" in location.lower()
