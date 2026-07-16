"""System integrity check on startup."""
import os
import sys


def _is_migration_command():
    migration_commands = {
        "db", "migrate", "migration", "upgrade", "downgrade",
        "stamp", "history", "current", "heads", "branches",
        "revision", "merge",
    }
    argv = [str(a).lower() for a in sys.argv]
    return any(arg in migration_commands for arg in argv)


def run_system_integrity_check(app):
    """Ensure essential data exists even after a full DB wipe."""
    if os.environ.get("SKIP_SYSTEM_INTEGRITY") or _is_migration_command():
        return
    from utils.system_init import ensure_system_integrity
    try:
        ensure_system_integrity(app)
        app.logger.info("[OK] System integrity verified (Master Key & Core Data Active)")
    except Exception as e:
        app.logger.error(f"[ERROR] System integrity check failed: {e}")
        import traceback
        traceback.print_exc()
