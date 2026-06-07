import logging
import sys
import os
from datetime import datetime, timezone

from flask import g, has_request_context, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_babel import Babel
import pickle

# Monkey patch cachelib.serializers.BaseSerializer.dumps to fix UnboundLocalError
try:
    from cachelib.serializers import BaseSerializer
    
    def patched_dumps(self, value, protocol=pickle.HIGHEST_PROTOCOL):
        try:
            return pickle.dumps(value, protocol)
        except (pickle.PickleError, pickle.PicklingError) as e:
            self._warn(e)
            return None
            
    BaseSerializer.dumps = patched_dumps
except ImportError:
    pass

try:
    from flask_compress import Compress
    COMPRESS_AVAILABLE = True
except ImportError:
    COMPRESS_AVAILABLE = False
    logging.warning("Flask-Compress not available - install with: pip install Flask-Compress Brotli")


def get_locale():
    """تحديد اللغة الحالية"""
    if 'language' in session:
        return session.get('language', 'ar')
    return 'ar'

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except ImportError:
    class _Fore:
        BLUE = ""; GREEN = ""; YELLOW = ""; RED = ""
    class _Style:
        BRIGHT = ""; RESET_ALL = ""
    Fore, Style = _Fore(), _Style()


class RequestIdFilter(logging.Filter):
    """Add request ID to log records"""
    def filter(self, record):
        if has_request_context():
            record.request_id = getattr(g, "request_id", "-")
        else:
            record.request_id = "-"
        return True


class ColorFormatter(logging.Formatter):
    """Colored console logging with better PowerShell support"""
    
    COLORS = {
        "DEBUG":   Fore.CYAN + Style.BRIGHT,      # سماوي فاتح
        "INFO":    Fore.WHITE + Style.BRIGHT,     # أبيض فاتح
        "WARNING": Fore.YELLOW + Style.BRIGHT,    # أصفر فاتح
        "ERROR":   Fore.RED + Style.BRIGHT,       # أحمر فاتح
        "CRITICAL": Fore.MAGENTA + Style.BRIGHT,  # وردي فاتح
    }

    def format(self, record: logging.LogRecord) -> str:
        use_colors = os.environ.get('FLASK_ENV', 'development') == 'development'
        
        if use_colors:
            color = self.COLORS.get(record.levelname, "")
            reset = Style.RESET_ALL
        else:
            color = ""
            reset = ""
        
        req_id = getattr(record, "request_id", "-")
        
        timestamp = self.formatTime(record, '%Y-%m-%d %H:%M:%S')
        message = f"[{timestamp}] {color}{record.levelname:8s}{reset} [{req_id}] {record.name}: {record.getMessage()}"
        
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        try:
            target_encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        except Exception:
            target_encoding = "utf-8"

        try:
            message = message.encode(target_encoding, errors='replace').decode(target_encoding, errors='replace')
        except Exception:
            message = message.encode('ascii', 'replace').decode('ascii')
        
        return message


# ======================
# Setup Logging
# ======================
def setup_logging(app):
    """Configure application logging with UTF-8 support"""
    level_name = app.config.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    if sys.platform == 'win32':
        import io
        # Avoid re-wrapping stdio on repeated create_app() calls (QA tools),
        # which can close underlying streams when old wrappers are collected.
        if hasattr(sys.stdout, 'buffer') and not getattr(sys.stdout, '_azad_utf8_wrapped', False):
            wrapped_out = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            setattr(wrapped_out, '_azad_utf8_wrapped', True)
            sys.stdout = wrapped_out
        if hasattr(sys.stderr, 'buffer') and not getattr(sys.stderr, '_azad_utf8_wrapped', False):
            wrapped_err = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
            setattr(wrapped_err, '_azad_utf8_wrapped', True)
            sys.stderr = wrapped_err

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.addFilter(RequestIdFilter())
    console_handler.setFormatter(ColorFormatter())

    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(RequestIdFilter())
    error_handler.setFormatter(ColorFormatter())

    for logger in (app.logger, logging.getLogger()):
        logger.handlers.clear()
        logger.setLevel(level)
        logger.addHandler(console_handler)
        logger.addHandler(error_handler)
        logger.propagate = False

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # Show HTTP request logs once (avoid duplicate werkzeug handlers).
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.handlers.clear()
    werkzeug_logger.propagate = True

    app.logger.info("[OK] Logging configured")

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
    """Custom rate limit key (user or IP)"""
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

from sqlalchemy import event
from sqlalchemy.engine import Engine


def init_extensions(app):
    
    db.init_app(app)
    migrate.init_app(app, db)
    
    if app.config.get('SQLALCHEMY_ECHO'):
        from utils.performance_tracker import log_slow_queries
        log_slow_queries(app)
    
    login_manager.init_app(app)
    
    csrf.init_app(app)
    
    cache.init_app(app)
    
    limiter.init_app(app)
    limiter.storage_uri = app.config.get('RATELIMIT_STORAGE_URI', 'memory://')
    
    if compress:
        compress.init_app(app)
        logging.info("[OK] Compression enabled")
    else:
        logging.warning("⚠️ Compression disabled - install Flask-Compress for better performance")
    
    default_limit = app.config.get("RATELIMIT_DEFAULT")
    if default_limit:
        if isinstance(default_limit, str):
            limiter.default_limits = [l.strip() for l in default_limit.split(";") if l.strip()]
        else:
            limiter.default_limits = [default_limit]
    
    if app.config.get("MAIL_USERNAME"):
        mail.init_app(app)
    
    babel.init_app(app, locale_selector=get_locale)

    try:
        from utils.tenant_orm import register_tenant_orm_scoping
        register_tenant_orm_scoping(app)
    except Exception as exc:
        app.logger.error("[ERROR] Tenant ORM scoping failed: %s", exc)
    
    app.logger.info("[OK] Extensions initialized")

def get_or_create(session, model, defaults=None, **kwargs):
    """Get or create a database record"""
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    else:
        params = dict((k, v) for k, v in kwargs.items())
        if defaults:
            params.update(defaults)
        instance = model(**params)
        session.add(instance)
        return instance, True
