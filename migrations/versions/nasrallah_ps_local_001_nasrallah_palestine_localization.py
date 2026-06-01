"""nasrallah_palestine_localization

Revision ID: nasrallah_ps_local_001
Revises: nasrallah_tenant_001
Create Date: 2026-06-02 00:15:00.000000

Idempotent: localize tenant nasrallah for Palestine (Ramallah).
"""
from alembic import op
import sqlalchemy as sa


revision = "nasrallah_ps_local_001"
down_revision = "nasrallah_tenant_001"
branch_labels = None
depends_on = None

NASRALLAH_SLUG = "nasrallah"
TIMEZONE = "Asia/Hebron"
LOGO = "assets/tenants/nasrallah/logos/logo.png"


def _validate_timezone(tz: str) -> None:
    from zoneinfo import ZoneInfo

    ZoneInfo(tz)


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def _require_nasrallah_tenant(conn) -> int:
    row = conn.execute(
        sa.text("SELECT id FROM tenants WHERE slug = :slug LIMIT 1"),
        {"slug": NASRALLAH_SLUG},
    ).fetchone()
    if not row:
        raise RuntimeError(
            "tenant slug=nasrallah missing — run nasrallah_tenant_001 migration first"
        )
    return int(row[0])


def upgrade():
    _validate_timezone(TIMEZONE)
    conn = op.get_bind()
    tenant_id = _require_nasrallah_tenant(conn)

    conn.execute(
        sa.text(
            "UPDATE tenants SET "
            "country = 'PS', "
            "vat_country = 'PS', "
            "timezone = :tz, "
            "default_currency = 'ILS', "
            "city = 'Ramallah', "
            "address_en = COALESCE(NULLIF(TRIM(address_en), ''), 'Ramallah'), "
            "address_ar = COALESCE(NULLIF(TRIM(address_ar), ''), 'رام الله') "
            "WHERE id = :id AND slug = :slug"
        ),
        {"id": tenant_id, "slug": NASRALLAH_SLUG, "tz": TIMEZONE},
    )

    if _column_exists(conn, "invoice_settings", "tenant_id"):
        conn.execute(
            sa.text(
                "UPDATE invoice_settings SET "
                "company_name_en = 'Nasrallah', "
                "company_name_ar = 'نصرالله', "
                "logo_url = :logo, "
                "logo_path = :logo, "
                "address_en = COALESCE(NULLIF(TRIM(address_en), ''), 'Ramallah'), "
                "address_ar = COALESCE(NULLIF(TRIM(address_ar), ''), 'رام الله'), "
                "is_active = TRUE "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id, "logo": LOGO},
        )

    if _column_exists(conn, "branches", "tenant_id"):
        branch_sql = (
            "UPDATE branches SET "
            "name = 'Ramallah Main Branch', "
            "code = 'MAIN', "
            "is_main = TRUE, "
            "is_active = TRUE "
        )
        if _column_exists(conn, "branches", "city"):
            branch_sql += ", city = 'Ramallah' "
        if _column_exists(conn, "branches", "address"):
            branch_sql += ", address = 'Ramallah' "
        branch_sql += "WHERE tenant_id = :tid AND code = 'MAIN'"
        conn.execute(sa.text(branch_sql), {"tid": tenant_id})

    if _column_exists(conn, "warehouses", "tenant_id"):
        conn.execute(
            sa.text(
                "UPDATE warehouses SET "
                "name = 'Ramallah Main Warehouse', "
                "name_ar = 'مستودع رام الله الرئيسي', "
                "code = 'MAIN', "
                "is_active = TRUE, "
                "is_main = TRUE "
                "WHERE tenant_id = :tid AND code = 'MAIN'"
            ),
            {"tid": tenant_id},
        )


def downgrade():
    # Localization data — restore from backup if rollback required.
    pass
