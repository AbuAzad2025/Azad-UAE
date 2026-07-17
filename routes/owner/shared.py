"""Shared helper functions for the owner blueprint."""

from routes.owner import (
    current_app,
    current_user,
    db,
    SystemSettings,
)
from services.logging_core import LoggingCore
from sqlalchemy import inspect
import logging
import re

logger = logging.getLogger(__name__)

_TABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$", re.IGNORECASE)

_TRUNCATE_BLOCKED_TABLES = frozenset(
    {
        "users",
        "roles",
        "permissions",
        "tenants",
        "alembic_version",
        "payment_vault",
        "card_vault",
        "api_keys",
    }
)

_STATS_BLOCKED_TABLES = _TRUNCATE_BLOCKED_TABLES

_FORBIDDEN_SQL_KEYWORDS = (
    "DROP ",
    "TRUNCATE ",
    "DELETE ",
    "UPDATE ",
    "INSERT ",
    "ALTER ",
    "CREATE ",
    "GRANT ",
    "REVOKE ",
    "COPY ",
    "EXEC ",
    "EXECUTE ",
    "CALL ",
    "INTO OUTFILE",
    "INTO DUMPFILE",
    "LOAD_FILE",
    "SELECT INTO",
    "OUTFILE",
    "DUMPFILE",
)

_CONVERT_BLOCKED_TABLES = _TRUNCATE_BLOCKED_TABLES

_EXPORT_FORMATS = frozenset({"sql", "json"})

_EXPORT_EXCEL_ENTITIES = frozenset({"customers", "products", "sales", "expenses"})


def _owner_branch_scope():
    from utils.decorators import branch_scope_id

    return branch_scope_id()


def _invalidate_owner_changes():
    """Clear cache after owner panel mutations so changes apply immediately system-wide."""
    try:
        from extensions import cache

        cache.clear()
    except Exception as exc:
        logger.debug("owner cache clear: %s", exc)


def _owner_backup_filename(filename: str):
    from services.backup_service import BackupService

    return BackupService.sanitize_filename(filename)


def _backup_created_by_payload():
    role = None
    if getattr(current_user, "role", None):
        role = getattr(current_user.role, "slug", None)
    return {
        "user_id": getattr(current_user, "id", None),
        "role": role,
        "username": getattr(current_user, "username", None),
    }


def _is_sensitive_stats_table(table_name: str) -> bool:
    return (table_name or "").strip().lower() in _STATS_BLOCKED_TABLES


def _resolve_browsable_table(table_name: str) -> str | None:
    """Known table safe to browse/edit in owner DB tools (excludes sensitive tables)."""
    safe_table = _resolve_known_table(table_name)
    if not safe_table or _is_sensitive_stats_table(safe_table):
        return None
    return safe_table


def _known_tables_map() -> dict[str, str]:
    return {name.lower(): name for name in inspect(db.engine).get_table_names()}


def _resolve_known_table(table_name: str) -> str | None:
    """Return canonical DB table name from inspector whitelist, else None."""
    if not table_name:
        return None
    normalized = table_name.strip().lower()
    if not _TABLE_NAME_RE.match(normalized):
        return None
    return _known_tables_map().get(normalized)


def _resolve_truncatable_table(table_name: str) -> str | None:
    """Return canonical DB table name if safe to truncate, else None."""
    safe_table = _resolve_known_table(table_name)
    if not safe_table or safe_table.lower() in _TRUNCATE_BLOCKED_TABLES:
        return None
    return safe_table


def _validate_select_only_sql(sql_query: str) -> tuple[bool, str | None]:
    """Allow a single SELECT statement; block stacked queries and mutations."""
    if not sql_query or not sql_query.strip():
        return False, "❌ استعلام فارغ."
    stripped = sql_query.strip()
    if ";" in stripped.rstrip(";"):
        return False, "❌ مسموح باستعلام واحد فقط (بدون ;)."
    sql_upper = stripped.upper()
    if not sql_upper.startswith("SELECT"):
        return False, "❌ مسموح باستعلامات SELECT للقراءة فقط."
    if any(kw in sql_upper for kw in _FORBIDDEN_SQL_KEYWORDS):
        return False, "❌ استعلام غير مسموح — قراءة فقط (SELECT)."
    return True, None


def _mask_api_key(key: str) -> str:
    if not key:
        return "****"
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


def _mask_db_uri(uri: str) -> str:
    if not uri:
        return ""
    try:
        if "://" not in uri or "@" not in uri:
            return uri.split("@")[-1][:80]
        scheme, rest = uri.split("://", 1)
        creds, tail = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{tail[:80]}"
    except Exception:
        return "[redacted]"


def _validate_postgresql_uri(uri: str) -> bool:
    if not uri or not uri.strip():
        return False
    uri = uri.strip()
    if ";" in uri or "\n" in uri or "\r" in uri:
        return False
    return bool(re.match(r"^postgresql(\+psycopg2)?://", uri, re.IGNORECASE))


def _inspector_column_names(table_name: str) -> set[str]:
    safe_table = _resolve_known_table(table_name) or table_name
    if safe_table.lower() not in _known_tables_map():
        return set()
    return {col["name"] for col in inspect(db.engine).get_columns(safe_table)}


def _audit_owner_db_action(action: str, details: dict | None = None):
    LoggingCore.log_audit(action, "database", 0, details or {})


def _get_developer_from_settings():
    """قيم الشركة المطورة من النظام (custom_settings) أو من config."""
    cfg = current_app.config
    settings = SystemSettings.get_current()
    return {
        "developer_name_ar": settings.get_custom_setting("developer_name_ar")
        or cfg.get("DEVELOPER_NAME_AR", ""),
        "developer_name": settings.get_custom_setting("developer_name")
        or cfg.get("DEVELOPER_NAME", ""),
        "developer_credit": settings.get_custom_setting("developer_credit")
        or cfg.get("DEVELOPER_CREDIT", ""),
        "developer_phone": settings.get_custom_setting("developer_phone")
        or cfg.get("DEVELOPER_PHONE", ""),
        "developer_email": settings.get_custom_setting("developer_email")
        or cfg.get("DEVELOPER_EMAIL", ""),
        "developer_website": settings.get_custom_setting("developer_website")
        or cfg.get("DEVELOPER_WEBSITE", ""),
        "developer_whatsapp": settings.get_custom_setting("developer_whatsapp")
        or cfg.get("DEVELOPER_WHATSAPP", ""),
        "developer_logo": settings.get_custom_setting("developer_logo")
        or cfg.get("DEVELOPER_LOGO", ""),
    }
