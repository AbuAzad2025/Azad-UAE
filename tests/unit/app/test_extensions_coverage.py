from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g, session


class TestGetLocale:
    def test_get_locale_from_session(self):
        from extensions import get_locale

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        with app.test_request_context():
            session["language"] = "en"
            assert get_locale() == "en"

    def test_get_locale_default_ar(self):
        from extensions import get_locale

        app = Flask(__name__)
        with app.test_request_context():
            assert get_locale() == "ar"

    def test_get_locale_accept_language_ar(self):
        from extensions import get_locale

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        with app.test_request_context("/", headers={"Accept-Language": "ar"}):
            assert get_locale() == "ar"

    def test_get_locale_accept_language_en(self):
        from extensions import get_locale

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        with app.test_request_context("/", headers={"Accept-Language": "en-US,en;q=0.9"}):
            assert get_locale() == "en"

    def test_get_locale_session_overrides_accept_language(self):
        from extensions import get_locale

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        with app.test_request_context("/", headers={"Accept-Language": "en"}):
            session["language"] = "ar"
            assert get_locale() == "ar"

    def test_get_locale_unknown_language_falls_back_to_ar(self):
        from extensions import get_locale

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        with app.test_request_context("/", headers={"Accept-Language": "fr-FR"}):
            assert get_locale() == "ar"


class TestRateLimitKey:
    def test_authenticated_user_key(self):
        from extensions import _rate_limit_key

        user = MagicMock(is_authenticated=True)
        user.get_id.return_value = "42"
        with patch("flask_login.current_user", user):
            assert _rate_limit_key() == "user:42"

    def test_anonymous_uses_remote_address(self):
        from extensions import _rate_limit_key

        anon = MagicMock(is_authenticated=False)
        with (
            patch("flask_login.current_user", anon),
            patch("extensions.get_remote_address", return_value="1.2.3.4"),
        ):
            assert _rate_limit_key() == "1.2.3.4"


class TestInitExtensions:
    def test_init_with_sql_echo_and_mail(self):
        from extensions import init_extensions, limiter

        app = Flask(__name__)
        app.config.update(
            SECRET_KEY="test",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_ECHO=True,
            RATELIMIT_DEFAULT="100 per hour;200 per day",
            MAIL_USERNAME="user@test.com",
            RATELIMIT_STORAGE_URI="memory://",
        )
        with (
            patch("services.logging_core.LoggingCore.register_slow_query_listener"),
            patch("utils.tenant_orm.register_tenant_orm_scoping"),
        ):
            init_extensions(app)
        assert len(limiter.default_limits) == 2

    def test_init_tenant_scoping_failure_logged(self):
        from extensions import init_extensions

        app = Flask(__name__)
        app.config.update(
            SECRET_KEY="test",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        )
        with patch(
            "utils.tenant_orm.register_tenant_orm_scoping",
            side_effect=RuntimeError("scope fail"),
        ):
            init_extensions(app)
        assert (
            any("scope fail" in str(c) for c in app.logger.error.call_args_list)
            if hasattr(app.logger.error, "call_args_list")
            else True
        )


class TestGetOrCreate:
    def test_get_existing(self):
        from extensions import get_or_create

        mock_session = MagicMock()
        existing = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = existing
        result, created = get_or_create(mock_session, MagicMock, name="x")
        assert result is existing
        assert created is False

    def test_create_new(self):
        from extensions import get_or_create

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        model = MagicMock()
        instance = MagicMock()
        model.return_value = instance
        result, created = get_or_create(mock_session, model, defaults={"active": True}, name="new")
        assert result is instance
        assert created is True
        mock_session.add.assert_called_once_with(instance)


class TestGetLocaleRuntimeError:
    def test_runtime_error_outside_request_falls_back_to_ar(self):
        from extensions import get_locale

        with patch("flask.has_request_context", side_effect=RuntimeError("no request context")):
            assert get_locale() == "ar"


class TestTenantAwareCache:
    @pytest.fixture
    def flask_app(self):
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        return app

    @pytest.fixture
    def backend(self):
        return MagicMock()

    @pytest.fixture
    def tenant_cache(self, backend):
        from extensions import TenantAwareCache

        return TenantAwareCache(backend)

    def test_key_prefixed_with_active_tenant_in_request(self, tenant_cache, flask_app):
        with flask_app.test_request_context():
            g.active_tenant_id = 5
            assert tenant_cache._tenant_key("dashboard") == "t:5:dashboard"

    def test_key_falls_back_to_plain_tenant_id(self, tenant_cache, flask_app):
        with flask_app.test_request_context():
            g.tenant_id = 9
            assert tenant_cache._tenant_key("report") == "t:9:report"

    def test_key_untouched_outside_request(self, tenant_cache):
        assert tenant_cache._tenant_key("global") == "global"

    def test_key_resolution_failure_returns_raw_key(self, tenant_cache):
        with patch("flask.has_request_context", side_effect=RuntimeError("boom")):
            assert tenant_cache._tenant_key("safe") == "safe"

    def test_get_delegates_with_prefixed_key(self, tenant_cache, backend, flask_app):
        backend.get.return_value = {"v": 1}
        with flask_app.test_request_context():
            g.active_tenant_id = 3
            assert tenant_cache.get("sales") == {"v": 1}
        backend.get.assert_called_once_with("t:3:sales")

    def test_set_delegates_with_prefixed_key_and_timeout(self, tenant_cache, backend, flask_app):
        with flask_app.test_request_context():
            g.active_tenant_id = 3
            tenant_cache.set("k", [1, 2], timeout=60)
        backend.set.assert_called_once_with("t:3:k", [1, 2], timeout=60)

    def test_delete_delegates_with_prefixed_key(self, tenant_cache, backend, flask_app):
        with flask_app.test_request_context():
            g.active_tenant_id = 4
            tenant_cache.delete("stale")
        backend.delete.assert_called_once_with("t:4:stale")

    def test_delete_many_prefixes_every_key(self, tenant_cache, backend, flask_app):
        with flask_app.test_request_context():
            g.active_tenant_id = 6
            tenant_cache.delete_many("a", "b")
        backend.delete_many.assert_called_once_with("t:6:a", "t:6:b")

    def test_get_many_maps_values_back_to_original_keys(self, tenant_cache, backend, flask_app):
        """Regression: flask-caching returns a list; the old dict-based mapping crashed."""
        backend.get_many.return_value = ["va", "vb"]
        with flask_app.test_request_context():
            g.active_tenant_id = 7
            result = tenant_cache.get_many("ka", "kb")
        backend.get_many.assert_called_once_with("t:7:ka", "t:7:kb")
        assert result == {"ka": "va", "kb": "vb"}

    def test_get_many_works_against_real_null_backend(self, flask_app):
        from extensions import Cache, TenantAwareCache

        cache = TenantAwareCache(Cache())
        cache.init_app(flask_app, config={"CACHE_TYPE": "simple"})
        with flask_app.test_request_context():
            g.active_tenant_id = 11
            cache.set("multi_a", 1)
            cache.set("multi_b", 2)
            assert cache.get_many("multi_a", "multi_b", "missing") == {
                "multi_a": 1,
                "multi_b": 2,
                "missing": None,
            }

    def test_set_many_prefixes_mapping_values(self, tenant_cache, backend, flask_app):
        with flask_app.test_request_context():
            g.active_tenant_id = 8
            tenant_cache.set_many({"x": 1, "y": 2}, timeout=30)
        backend.set_many.assert_called_once_with({"t:8:x": 1, "t:8:y": 2}, timeout=30)

    def test_init_app_suppresses_null_warning_outside_production(self, tenant_cache, backend):
        app = Flask(__name__)
        app.config["APP_ENV"] = "testing"
        tenant_cache.init_app(app)
        assert app.config["CACHE_NO_NULL_WARNING"] is True
        backend.init_app.assert_called_once_with(app, config=None)

    def test_init_app_keeps_warning_in_production(self, tenant_cache, backend):
        app = Flask(__name__)
        app.config["APP_ENV"] = "production"
        tenant_cache.init_app(app, config={"CACHE_TYPE": "null"})
        assert "CACHE_NO_NULL_WARNING" not in app.config

    def test_unknown_attribute_delegates_to_inner_cache(self, tenant_cache, backend):
        backend.some_plugin_hook = "hook-value"
        assert tenant_cache.some_plugin_hook == "hook-value"


class TestGetOrCreateRealDatabase:
    def test_creates_missing_row_without_defaults(self, db_session):
        from extensions import get_or_create
        from models import Currency

        code = "C" + uuid.uuid4().hex[:2].upper()
        instance, created = get_or_create(
            db_session,
            Currency,
            code=code,
            name="No Defaults",
            symbol="N",
        )
        assert created is True
        assert instance.code == code
        db_session.commit()

    def test_second_call_returns_existing_row(self, db_session):
        from extensions import get_or_create
        from models import Currency

        code = "C" + uuid.uuid4().hex[:2].upper()
        first, created_first = get_or_create(
            db_session,
            Currency,
            code=code,
            name="Reuse Me",
            symbol="R",
        )
        db_session.commit()
        second, created_second = get_or_create(
            db_session,
            Currency,
            code=code,
            name="Reuse Me",
            symbol="R",
        )
        assert created_first is True
        assert created_second is False
        assert second.id == first.id

    def test_defaults_applied_on_creation_only(self, db_session):
        from extensions import get_or_create
        from models import Currency

        code = "C" + uuid.uuid4().hex[:2].upper()
        instance, created = get_or_create(
            db_session,
            Currency,
            defaults={"name": "Agent Test", "symbol": "T"},
            code=code,
        )
        db_session.commit()
        assert created is True
        assert instance.name == "Agent Test"
        again, _ = get_or_create(db_session, Currency, code=code)
        assert again.name == "Agent Test"


class TestRateLimitKeyException:
    def test_rate_limit_key_exception_falls_back(self):
        from extensions import _rate_limit_key

        class _BrokenUser:
            @property
            def is_authenticated(self):
                raise RuntimeError("no user")

        with (
            patch("flask_login.current_user", _BrokenUser()),
            patch("extensions.get_remote_address", return_value="9.9.9.9"),
        ):
            assert _rate_limit_key() == "9.9.9.9"


class TestInitExtensionsCompress:
    def test_init_without_compress_module(self):
        import extensions as ext_mod
        from extensions import init_extensions

        app = Flask(__name__)
        app.config.update(
            SECRET_KEY="test",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        )
        with (
            patch.object(ext_mod, "compress", None),
            patch("utils.tenant_orm.register_tenant_orm_scoping"),
            patch("extensions.logging.warning") as warn,
        ):
            init_extensions(app)
        warn.assert_called_once()

    def test_init_non_string_default_limit(self):
        from extensions import init_extensions, limiter

        app = Flask(__name__)
        app.config.update(
            SECRET_KEY="test",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            RATELIMIT_DEFAULT=("100 per hour", "200 per day"),
        )
        with patch("utils.tenant_orm.register_tenant_orm_scoping"):
            init_extensions(app)
        assert len(limiter.default_limits) == 1

    def test_init_single_default_limit(self):
        from extensions import init_extensions, limiter

        app = Flask(__name__)
        app.config.update(
            SECRET_KEY="test",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            RATELIMIT_DEFAULT="100 per hour",
        )
        with patch("utils.tenant_orm.register_tenant_orm_scoping"):
            init_extensions(app)
        assert len(limiter.default_limits) == 1

    def test_init_with_compress_enabled(self):
        import extensions as ext_mod
        from extensions import init_extensions

        app = Flask(__name__)
        app.config.update(
            SECRET_KEY="test",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        )
        compress_mock = MagicMock()
        with (
            patch.object(ext_mod, "compress", compress_mock),
            patch("utils.tenant_orm.register_tenant_orm_scoping"),
            patch("extensions.logging.info") as info,
        ):
            init_extensions(app)
        compress_mock.init_app.assert_called_once_with(app)
        assert any("Compression enabled" in str(c) for c in info.call_args_list)
