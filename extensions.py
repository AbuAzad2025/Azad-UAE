import logging
import os
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

csrf = CSRFProtect()

cache = Cache()

mail = Mail()

def _rate_limit_key():
    try:
        from flask_login import current_user
        if getattr(current_user, "is_authenticated", False):
            return f"user:{current_user.get_id()}"
    except Exception:
        pass
    return get_remote_address()
limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)
babel = Babel()
if COMPRESS_AVAILABLE:
    compress = Compress()
else:
    compress = None
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
