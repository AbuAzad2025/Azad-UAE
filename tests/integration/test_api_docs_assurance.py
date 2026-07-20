"""Deep assurance — routes/api_docs.py OpenAPI spec and UI endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestApiDocsPublic:
    """Docs are public in testing/debug mode."""

    def test_openapi_json_spec(self, app, client):
        with app.app_context():
            resp = client.get("/api-docs/openapi.json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["openapi"] == "3.0.3"
        assert "paths" in data
        assert "/health" in data["paths"]

    def test_openapi_contact_overrides_from_config(self, app, client):
        app.config["DEVELOPER_NAME"] = "Test Dev"
        app.config["DEVELOPER_EMAIL"] = "dev@test.com"
        with app.app_context():
            resp = client.get("/api-docs/openapi.json")
        contact = resp.get_json()["info"]["contact"]
        assert contact["name"] == "Test Dev"
        assert contact["email"] == "dev@test.com"

    def test_swagger_ui_renders(self, app, client):
        with app.app_context():
            resp = client.get("/api-docs/")
        assert resp.status_code == 200
        assert b"swagger-ui" in resp.data.lower()

    def test_redoc_renders(self, app, client):
        with app.app_context():
            resp = client.get("/api-docs/redoc")
        assert resp.status_code == 200
        assert b"redoc" in resp.data.lower()


class TestApiDocsProtection:
    """Production mode hides docs from anonymous users."""

    def test_protected_returns_404_for_anonymous(self, app, client):
        from werkzeug.exceptions import NotFound

        with patch("routes.api_docs._api_docs_public", return_value=False):
            with patch("routes.api_docs.current_user", MagicMock(is_authenticated=False)):
                with app.app_context():
                    try:
                        resp = client.get("/api-docs/openapi.json")
                    except NotFound:
                        pass
                    else:
                        assert resp.status_code == 404

    def test_protected_allows_authenticated_user(self, app, client):
        with patch("routes.api_docs._api_docs_public", return_value=False):
            with patch("routes.api_docs.current_user", MagicMock(is_authenticated=True)):
                with app.app_context():
                    resp = client.get("/api-docs/openapi.json")
        assert resp.status_code == 200

    def test_openapi_strips_servers_when_not_public(self, app, client):
        with patch("routes.api_docs._api_docs_public", return_value=False):
            with patch("routes.api_docs.current_user", MagicMock(is_authenticated=True)):
                with app.app_context():
                    resp = client.get("/api-docs/openapi.json")
        assert "servers" not in resp.get_json()
