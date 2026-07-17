"""AZADEXA ERP — thin entrypoint.

All application logic lives in app/factory.py and supporting modules:
  - app/factory.py    : create_app() + extension init
  - app/handlers.py   : error handlers
  - app/context.py    : context processors
  - app/integrity.py  : startup integrity checks
"""

import os

from config import _init_env
from app.factory import create_app

_init_env()

app = create_app()

print("Starting Application...")

if __name__ == "__main__":
    try:
        from services.backup_service import BackupService

        print("Before BackupService.initialize")
        print("Before BackupService.initialize")
        BackupService.initialize()
        print("After BackupService.initialize")
        print("After BackupService.initialize")

        try:
            from services.auto_approval_service import schedule_auto_approval

            schedule_auto_approval(app)
            app.logger.info("Auto-approval service scheduler started")
        except Exception as e:
            app.logger.warning("Auto-approval service failed: %s", e)

        port = int(os.environ.get("PORT", 5000))
        host = os.environ.get("HOST", "0.0.0.0")  # nosec B104
        debug_mode = bool(app.config.get("DEBUG", False))

        def _mask_db_uri(uri: str) -> str:
            if not uri:
                return uri
            try:
                if "://" not in uri or "@" not in uri:
                    return uri
                scheme, rest = uri.split("://", 1)
                creds, tail = rest.split("@", 1)
                if ":" not in creds:
                    return uri
                user = creds.split(":", 1)[0]
                return f"{scheme}://{user}:***@{tail}"
            except Exception as exc:
                try:
                    from services.logging_core import LoggingCore

                    LoggingCore.log_error(
                        message=str(exc) or "Failed to mask DB URI",
                        category="SYSTEM_INIT",
                        level="WARNING",
                        source="app._mask_db_uri",
                        exception=exc,
                    )
                except Exception:
                    pass
                return uri

        app.logger.info("Starting UAE-Sale System")
        app.logger.info("Host: %s", host)
        app.logger.info("Port: %s", port)
        app.logger.info("Debug: %s", debug_mode)
        app.logger.info(
            "Database: %s", _mask_db_uri(app.config.get("SQLALCHEMY_DATABASE_URI"))
        )
        app.logger.info("Starting server on https://%s:%s", host, port)

        app.run(host=host, port=port, debug=debug_mode, use_reloader=False)
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception("Failed to start app: %s", e)
        raise
