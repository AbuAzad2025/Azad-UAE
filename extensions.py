import logging
import os
from typing import Any
from flask import session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_babel import Babel

try:
    from flask_compress import Compress

    COMPRESS_AVAILABLE = True
except ImportError:
    Compress = None  # type: ignore[misc,assignment]
    COMPRESS_AVAILABLE = False
    logging.warning("Flask-Compress not available - install with: pip install Flask-Compress Brotli")


def get_locale():
    if "language" in session:
        return session.get("language", "ar")
    return "ar"


db = SQLAlchemy(session_options={"expire_on_commit": False})

migrate = Migrate()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "الرجاء تسجيل الدخول للوصول لهذه الصفحة"
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"

csrf = CSRFProtect()


class TenantAwareCache:
    """Flask-Caching wrapper that prefixes every key with the active tenant id.

    Prevents cross-tenant cache poisoning when multiple tenants share the same
    cache backend (redis, simple, etc.).
    """

    def __init__(self, cache_instance):
        self._cache = cache_instance

    @staticmethod
    def _tenant_key(key):
        try:
            from flask import g, has_request_context

            if has_request_context():
                tid = getattr(g, "active_tenant_id", None) or getattr(g, "tenant_id", None)
                if tid is not None:
                    return f"t:{tid}:{key}"
        except Exception:
            pass
        return key

    def get(self, key):
        return self._cache.get(self._tenant_key(key))

    def set(self, key, value, timeout=None):
        return self._cache.set(self._tenant_key(key), value, timeout=timeout)

    def delete(self, key):
        return self._cache.delete(self._tenant_key(key))

    def delete_many(self, *keys):
        return self._cache.delete_many(*[self._tenant_key(k) for k in keys])

    def get_many(self, *keys):
        mapped = {self._tenant_key(k): k for k in keys}
        results = self._cache.get_many(*mapped.keys())
        return {mapped[k]: v for k, v in results.items()}

    def set_many(self, mapping, timeout=None):
        mapped = {self._tenant_key(k): v for k, v in mapping.items()}
        return self._cache.set_many(mapped, timeout=timeout)

    def init_app(self, app, config=None):
        cache_type = (config or app.config).get("CACHE_TYPE")
        if cache_type in (None, "", "null") and not app.config.get("APP_ENV", "").lower() == "production":
            app.config.setdefault("CACHE_NO_NULL_WARNING", True)
        return self._cache.init_app(app, config=config)

    def __getattr__(self, name):
        return getattr(self._cache, name)


cache = TenantAwareCache(Cache())

mail = Mail()


def _rate_limit_key():
    try:
        from flask_login import current_user

        if getattr(current_user, "is_authenticated", False):
            return f"user:{current_user.get_id()}"
    except Exception:
        import logging

        logging.getLogger(__name__).debug("Rate-limit key resolution: current_user not available, falling back to IP")
    return get_remote_address()


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)
babel = Babel()
compress: Any = Compress() if COMPRESS_AVAILABLE else None


def init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)
    if app.config.get("SQLALCHEMY_ECHO"):
        from services.logging_core import LoggingCore

        LoggingCore.register_slow_query_listener(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    limiter.storage_uri = app.config.get("RATELIMIT_STORAGE_URI", "memory://")
    if compress:
        compress.init_app(app)
        logging.info("[OK] Compression enabled")
    else:
        logging.warning("Compression disabled - install Flask-Compress for better performance")
    default_limit = app.config.get("RATELIMIT_DEFAULT")
    if default_limit:
        if isinstance(default_limit, str):
            limiter.default_limits = [part.strip() for part in default_limit.split(";") if part.strip()]
        else:
            limiter.default_limits = [default_limit]
    if app.config.get("MAIL_USERNAME"):
        mail.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    app.logger.info("[OK] Extensions initialized")


def get_or_create(db_session, model, defaults=None, **kwargs):
    instance = db_session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    params = dict((k, v) for k, v in kwargs.items())
    if defaults:
        params.update(defaults)
    instance = model(**params)
    db_session.add(instance)
    return instance, True
