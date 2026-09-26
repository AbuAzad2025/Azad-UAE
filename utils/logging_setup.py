import logging
import os
import sys

from flask import g, has_request_context

try:
    from colorama import Fore, Style
    from colorama import init as colorama_init

    colorama_init(autoreset=True)
except ImportError:
    colorama_init = None

    class _Fore:
        BLUE = ""
        CYAN = ""
        GREEN = ""
        YELLOW = ""
        RED = ""
        MAGENTA = ""
        WHITE = ""

    class _Style:
        BRIGHT = ""
        RESET_ALL = ""

    Fore, Style = _Fore(), _Style()


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if has_request_context():
            record.request_id = getattr(g, "request_id", "-")
        else:
            record.request_id = "-"
        return True


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": Fore.CYAN + Style.BRIGHT,
        "INFO": Fore.WHITE + Style.BRIGHT,
        "WARNING": Fore.YELLOW + Style.BRIGHT,
        "ERROR": Fore.RED + Style.BRIGHT,
        "CRITICAL": Fore.MAGENTA + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        use_colors = os.environ.get("FLASK_ENV", "development") == "development"
        if use_colors:
            color = self.COLORS.get(record.levelname, "")
            reset = Style.RESET_ALL
        else:
            color = ""
            reset = ""
        req_id = getattr(record, "request_id", "-")
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        message = f"[{timestamp}] {color}{record.levelname:8s}{reset} [{req_id}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        try:
            target_encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        except Exception:
            target_encoding = "utf-8"
        try:
            message = message.encode(target_encoding, errors="replace").decode(target_encoding, errors="replace")
        except Exception:
            message = message.encode("ascii", errors="replace").decode("ascii")
        return message


def _utf8_stream(stream):
    """Return a UTF-8 view of ``stream`` without mutating global state.

    The Windows console defaults to a legacy code page, so log records containing
    Arabic or box-drawing characters raise UnicodeEncodeError. The previous
    implementation fixed that by *reassigning* ``sys.stdout`` / ``sys.stderr`` to
    a new TextIOWrapper and latching a module-level "already wrapped" flag. That
    leaked into every library in the process: once the original buffered stream
    was closed (pytest capture teardown, redirect_stdout finalisers, interpreter
    shutdown) the wrapper kept receiving writes and raised
    "ValueError: I/O operation on closed file", which then broke unrelated tests
    in the same session. Wrapping the object we hand to the handler gets the same
    UTF-8 behaviour with no global mutation.
    """
    buffer = getattr(stream, "buffer", None)
    if buffer is None or getattr(stream, "encoding", "").lower().replace("-", "") == "utf8":
        return stream
    import io

    try:
        return io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        return stream


def setup_logging(app):
    level_name = app.config.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if sys.platform == "win32":
        stdout = _utf8_stream(sys.stdout)
        stderr = _utf8_stream(sys.stderr)
    else:
        stdout, stderr = sys.stdout, sys.stderr
    console_handler = logging.StreamHandler(stdout)
    console_handler.setLevel(level)
    console_handler.addFilter(RequestIdFilter())
    console_handler.setFormatter(ColorFormatter())
    error_handler = logging.StreamHandler(stderr)
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
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.handlers.clear()
    werkzeug_logger.propagate = True
    app.logger.info("[OK] Logging configured")
