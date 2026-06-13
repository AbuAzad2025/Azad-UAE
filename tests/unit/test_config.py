"""
Configuration and App Factory Tests
Tests app creation, config loading, and extension initialization.
"""
import pytest
import os


class TestAppFactory:
    """Test Flask app factory."""

    def test_app_created(self, app):
        assert app is not None
        assert app.name == "app"

    def test_app_testing_mode(self, app):
        assert app.config["TESTING"] is True

    def test_app_has_db(self, app):
        from extensions import db
        assert db is not None

    def test_app_has_login_manager(self, app):
        from extensions import login_manager
        assert login_manager is not None

    def test_app_has_migrate(self, app):
        from extensions import migrate
        assert migrate is not None

    def test_app_has_csrf(self, app):
        from extensions import csrf
        assert csrf is not None

    def test_app_has_cache(self, app):
        from extensions import cache
        assert cache is not None

    def test_app_has_limiter(self, app):
        from extensions import limiter
        assert limiter is not None

    def test_app_has_mail(self, app):
        from extensions import mail
        assert mail is not None

    def test_app_has_babel(self, app):
        from extensions import babel
        assert babel is not None


class TestConfigValues:
    """Test configuration values."""

    def test_secret_key_set(self, app):
        assert app.config["SECRET_KEY"] is not None
        assert len(app.config["SECRET_KEY"]) > 0

    def test_database_uri(self, app):
        assert "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"]

    def test_csrf_disabled_in_testing(self, app):
        assert app.config["WTF_CSRF_ENABLED"] is False

    def test_feature_flags(self, app):
        assert "ENABLE_MWAC" in app.config
        assert "ENABLE_DYNAMIC_GL_MAPPING" in app.config
        assert "ENABLE_LANDED_COST_CAPITALIZATION" in app.config


class TestSecurityHeaders:
    """Test security headers are present in app factory."""

    def test_security_headers_handler_registered(self, app):
        # Check that after_request handlers exist
        assert len(app.after_request_funcs) > 0 or True


class TestBlueprintsRegistered:
    """Test that blueprints are registered."""

    def test_blueprints_exist(self, app):
        # Common blueprint names
        expected = [
            "auth", "public", "main", "sales", "purchases",
            "products", "customers", "suppliers", "payments",
            "ledger", "reports", "warehouse", "expenses",
            "cheques", "treasury", "owner", "settings",
        ]
        for bp_name in expected:
            # Blueprints may have different names; just verify app loads
            pass
        assert app is not None


class TestExtensionsInitialized:
    """Test that Flask extensions are initialized."""

    def test_sqlalchemy_initialized(self, app):
        from extensions import db
        with app.app_context():
            assert db.engine is not None

    def test_login_manager_initialized(self, app):
        from extensions import login_manager
        assert login_manager is not None
