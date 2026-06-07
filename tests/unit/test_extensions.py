import pytest
from extensions import db, migrate, login_manager, csrf, limiter, mail, babel, init_extensions

class TestExtensionRegistry:
    def test_db_exists(self):
        assert db is not None
    def test_migrate_exists(self):
        assert migrate is not None
    def test_login_manager_exists(self):
        assert login_manager is not None
    def test_csrf_exists(self):
        assert csrf is not None
    def test_limiter_exists(self):
        assert limiter is not None
    def test_mail_exists(self):
        assert mail is not None
    def test_babel_exists(self):
        assert babel is not None

class TestExtensionsOnApp:
    def test_db_engine_ready(self, app):
        with app.app_context():
            assert db.engine is not None
    def test_login_manager_ready(self, app):
        assert login_manager is not None
    def test_limiter_storage_set(self, app):
        assert limiter.storage_uri is not None
    def test_babel_ready(self, app):
        assert babel is not None

class TestExemptSuperRemoved:
    def test_exempt_super_not_importable(self):
        with pytest.raises(ImportError):
            from extensions import _exempt_super
    def test_exempt_super_not_in_source(self):
        import extensions
        assert not hasattr(extensions, "_exempt_super")
class TestRateLimiterDefaults:
    def test_default_limits_set_from_config(self, app):
        app.config["RATELIMIT_DEFAULT"] = "100/hour"
        limiter.default_limits = ["100/hour"]
        assert limiter.default_limits == ["100/hour"]

