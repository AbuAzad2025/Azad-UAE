import logging
import os
import sys
from flask import g, has_request_context

try:
    from colorama import init as colorama_init, Fore, Style

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
            message = message.encode(target_encoding, errors="replace").decode(
                target_encoding, errors="replace"
            )
        except Exception:
            message = message.encode("ascii", errors="replace").decode("ascii")
        return message


def setup_logging(app):
    level_name = app.config.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if sys.platform == "win32":
        import io

        if hasattr(sys.stdout, "buffer") and not getattr(
            sys.stdout, "_azad_utf8_wrapped", False
        ):
            wrapped_out = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            setattr(wrapped_out, "_azad_utf8_wrapped", True)
            sys.stdout = wrapped_out
        if hasattr(sys.stderr, "buffer") and not getattr(
            sys.stderr, "_azad_utf8_wrapped", False
        ):
            wrapped_err = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )
            setattr(wrapped_err, "_azad_utf8_wrapped", True)
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
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.handlers.clear()
    werkzeug_logger.propagate = True
    app.logger.info("[OK] Logging configured")
