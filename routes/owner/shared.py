"""Shared helper functions for the owner blueprint."""

import logging
import re

from flask_babel import gettext
from sqlalchemy import inspect

from services.logging_core import LoggingCore

from .common import (
    SystemSettings,
    current_app,
    current_user,
    db,
)

logger = logging.getLogger(__name__)

_TABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$", re.IGNORECASE)
_SQL_TOKEN_RE = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)

# Tables the platform owner may NEVER read, browse, export, convert, or
# truncate through the database console / maintenance tools. This covers both
# system/security tables and every tenant operational / transactional table so
# the platform plane cannot reach tenant business data.
_TENANT_BUSINESS_TABLES = frozenset(
    {
        # Tenant operational / transactional data
        "sale",
        "sale_line",
        "customer",
        "product",
        "purchase",
        "ledger_entry",
        "gl_journal_entry",
        "expense",
        "receipt",
        "donation",
        "payment",
        "branch",
        "warehouse",
        "audit_log",
        "cheque",
        "product_warehouse_cost",
        "stock_movement",
        "product_return",
        "supplier",
        "pos_session",
        "pos_kds_order",
        "card_vault",
        # Platform / security tables
        "users",
        "roles",
        "permissions",
        "tenants",
        "tenant_stores",
        "tenant_store",
        "alembic_version",
        "payment_vault",
        "api_keys",
        "api_key",
        "login_history",
        "security_alert",
        "system_settings",
        "integration_settings",
        "archived_record",
    }
)

# Aliases some tools use by entity name rather than raw table name.
_TENANT_BUSINESS_ENTITIES = frozenset(
    {
        "customers",
        "products",
        "sales",
        "expenses",
        "purchases",
        "receipts",
        "donations",
        "payments",
        "branches",
        "warehouses",
        "ledger",
        "cheques",
        "suppliers",
    }
)

_BLOCKED_SQL_TABLES = _TENANT_BUSINESS_TABLES | _TENANT_BUSINESS_ENTITIES

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
    "UNION ",
    "UNION ALL ",
)

# PostgreSQL system relations and server-side file functions.
#
# _BLOCKED_SQL_TABLES is built from db.metadata, which contains no PostgreSQL
# system relation, so without this list the console could read anything the
# server can see. See _references_system_relation for the full reasoning.
#
# information_schema is deliberately NOT here: the schema browser and every
# "list the tables" helper reads it, and it exposes no row data.
_FORBIDDEN_SYSTEM_SQL = (
    "PG_AUTHID",
    "PG_SHADOW",
    "PG_USER",
    "PG_AUTHID ",
    "PG_ROLES",
    "PG_STAT_ACTIVITY",
    "PG_STAT_STATEMENTS",
    "PG_STAT_USER_TABLES",
    "PG_CATALOG.",
    "PG_TOAST.",
    "PG_READ_FILE",
    "PG_READ_BINARY_FILE",
    "PG_LS_DIR",
    "PG_STAT_FILE",
    "LO_IMPORT",
    "LO_EXPORT",
    "PG_FILE_READ",
    "PG_FILE_WRITE",
    "PG_SLEEP",
    "SET_CONFIG",
    "PG_READ_FILE(",
)

_EXPORT_FORMATS = frozenset({"sql", "json"})


def _is_blocked_table(identifier: str) -> bool:
    name = (identifier or "").strip().lower()
    if name in _BLOCKED_SQL_TABLES:
        return True
    # Schema-derived block set. The hand-written list above is an *additional*
    # guard, never the primary one: it silently fails when a model's
    # __tablename__ is plural where the list holds a singular token (that is
    # exactly how ``gl_journal_lines``, ``sale_lines``, ``card_payments``,
    # ``employees``, ``pos_sessions`` and ``shop_customer_accounts`` came to be
    # readable from the platform plane). Deriving from SQLAlchemy metadata means
    # a newly added tenant-scoped model is covered the moment it is declared.
    return name in _schema_blocked_tables()


_SCHEMA_BLOCKED_CACHE: frozenset[str] | None = None

# Column-name fragments that mark a table as carrying credentials/secrets and
# therefore off-limits to the platform plane even if it has no tenant_id.
_CREDENTIAL_COLUMN_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "salt",
    "hash",
)


def _schema_blocked_tables() -> frozenset[str]:
    """Every model table that is tenant-owned or carries credentials.

    Built from SQLAlchemy metadata rather than ``inspect(db.engine)`` so it needs
    no live database round-trip, is deterministic in tests and CI, and cannot
    drift from the ORM definitions.
    """
    global _SCHEMA_BLOCKED_CACHE
    if _SCHEMA_BLOCKED_CACHE is not None:
        return _SCHEMA_BLOCKED_CACHE

    # Metadata only holds tables whose module has been imported. Importing the
    # package registers every model, so the derived set is complete no matter
    # which blueprint triggered this first.
    import models  # noqa: F401  (import-for-side-effect: registers all tables)

    blocked: set[str] = {"alembic_version"}

    # Tables that carry a tenant_id column of their own.
    tenant_scoped = {name for name, table in db.metadata.tables.items() if "tenant_id" in table.columns}

    for table in db.metadata.tables.values():
        columns = {c.name.lower() for c in table.columns}
        has_credential_column = any(marker in column for marker in _CREDENTIAL_COLUMN_MARKERS for column in columns)
        if "tenant_id" in columns or has_credential_column:
            blocked.add(table.name.lower())
            continue
        # Tenant-owned by inheritance: a child table with no tenant_id of its own
        # that hangs off a tenant-scoped parent. ``shipment_lines`` is the case in
        # point - it reaches tenancy only through shipment_id -> shipments, so a
        # tenant_id-only test let the platform console read every tenant's
        # shipment lines, which is exactly what the module's own contract
        # ("the platform plane cannot reach tenant business data") forbids.
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name in tenant_scoped:
                    blocked.add(table.name.lower())
                    break
            else:
                continue
            break

    _SCHEMA_BLOCKED_CACHE = frozenset(blocked)
    return _SCHEMA_BLOCKED_CACHE


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
    return _is_blocked_table(table_name)


def _resolve_browsable_table(table_name: str) -> str | None:
    """Known table safe to browse/edit in owner DB tools (excludes blocked tables)."""
    safe_table = _resolve_known_table(table_name)
    if not safe_table or _is_blocked_table(safe_table):
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
    if not safe_table or _is_blocked_table(safe_table):
        return None
    return safe_table


def _sql_references_blocked_table(sql_query: str) -> str | None:
    """Return the first blocked table identifier referenced in the query, else None."""
    if not sql_query:
        return None
    lowered = sql_query.lower()
    blocked = _BLOCKED_SQL_TABLES | _schema_blocked_tables()
    for token in _SQL_TOKEN_RE.findall(lowered):
        if token in blocked:
            return token
    return None


def _references_system_relation(sql_upper: str) -> bool:
    """Block PostgreSQL system catalogs and server-side file functions.

    The tenant-table blocklist is derived from db.metadata plus a hand-written
    list, and db.metadata contains no PostgreSQL system relation. So while the
    module's own comment claims "the platform plane cannot reach tenant business
    data", the console would happily run:

        SELECT usename, passwd FROM pg_authid            -- every password hash
        SELECT query FROM pg_stat_activity              -- other tenants' live SQL
        SELECT pg_read_file('/etc/passwd')              -- server filesystem
        SELECT lo_import('/etc/shadow')                 -- a write, from a
                                                          -- "read-only" console

    None of those are tenant business tables, so none were blocked. The comment
    at :24-26 and the one at routes/owner/core.py:146 are both stated as
    invariants; this is what makes them true.

    Matched on the name as it appears in the statement, after upper-casing, so
    pg_catalog.pg_authid and a bare pg_authid are both caught. The
    information_schema schema is allowed through deliberately - the console's
    own schema browser and every "show me the tables" helper need it, and it
    exposes no row data.
    """
    return any(needle in sql_upper for needle in _FORBIDDEN_SYSTEM_SQL)


def _validate_select_only_sql(sql_query: str) -> tuple[bool, str | None]:
    """Allow a single read-only SELECT that references no blocked tenant table."""
    if not sql_query or not sql_query.strip():
        return False, gettext("❌ استعلام فارغ.")
    stripped = sql_query.strip()
    if ";" in stripped.rstrip(";"):
        return False, gettext("❌ مسموح باستعلام واحد فقط (بدون ;).")
    sql_upper = stripped.upper()
    if not sql_upper.startswith("SELECT"):
        return False, gettext("❌ مسموح باستعلامات SELECT للقراءة فقط.")
    if any(kw in sql_upper for kw in _FORBIDDEN_SQL_KEYWORDS):
        return False, gettext("❌ استعلام غير مسموح — قراءة فقط (SELECT).")
    if _references_system_relation(sql_upper):
        return False, gettext("❌ استعلام محظور — لا يمكن الوصول إلى كتالوج النظام أو relations الخاصة بـ PostgreSQL.")
    blocked = _sql_references_blocked_table(sql_query)
    if blocked:
        return (
            False,
            gettext("❌ الوصول محظور لجداول بيانات المستأجرين (tenant business tables)."),
        )
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
        "developer_name_ar": settings.get_custom_setting("developer_name_ar") or cfg.get("DEVELOPER_NAME_AR", ""),
        "developer_name": settings.get_custom_setting("developer_name") or cfg.get("DEVELOPER_NAME", ""),
        "developer_credit": settings.get_custom_setting("developer_credit") or cfg.get("DEVELOPER_CREDIT", ""),
        "developer_phone": settings.get_custom_setting("developer_phone") or cfg.get("DEVELOPER_PHONE", ""),
        "developer_email": settings.get_custom_setting("developer_email") or cfg.get("DEVELOPER_EMAIL", ""),
        "developer_website": settings.get_custom_setting("developer_website") or cfg.get("DEVELOPER_WEBSITE", ""),
        "developer_whatsapp": settings.get_custom_setting("developer_whatsapp") or cfg.get("DEVELOPER_WHATSAPP", ""),
        "developer_logo": settings.get_custom_setting("developer_logo") or cfg.get("DEVELOPER_LOGO", ""),
    }
