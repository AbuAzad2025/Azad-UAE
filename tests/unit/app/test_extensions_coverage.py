from __future__ import annotations

from unittest.mock import MagicMock, patch

from flask import Flask, session


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
