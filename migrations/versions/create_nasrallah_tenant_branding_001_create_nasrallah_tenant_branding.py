"""create_nasrallah_tenant_branding

Revision ID: nasrallah_tenant_001
Revises: canonical_static_asset_paths_001
Create Date: 2026-06-01 23:50:00.000000

Idempotent: create Nasrallah tenant, invoice settings, main branch/warehouse,
and core GL accounts via GLService.
"""
from alembic import op
import sqlalchemy as sa


revision = "nasrallah_tenant_001"
down_revision = "canonical_static_asset_paths_001"
branch_labels = None
depends_on = None

NASRALLAH_SLUG = "nasrallah"
LOGO = "assets/tenants/nasrallah/logos/logo.png"
FAVICON = "assets/tenants/nasrallah/favicons/favicon.png"


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t"
            ),
            {"t": table},
        ).scalar()
    )


def _get_tenant_id(conn) -> int | None:
    row = conn.execute(
        sa.text("SELECT id FROM tenants WHERE slug = :slug LIMIT 1"),
        {"slug": NASRALLAH_SLUG},
    ).fetchone()
    return int(row[0]) if row else None


def _ensure_tenant(conn) -> int:
    tid = _get_tenant_id(conn)
    if tid:
        conn.execute(
            sa.text(
                "UPDATE tenants SET "
                "logo_url = COALESCE(NULLIF(TRIM(logo_url), ''), :logo), "
                "favicon_url = COALESCE(NULLIF(TRIM(favicon_url), ''), :fav), "
                "name = COALESCE(NULLIF(TRIM(name), ''), 'Nasrallah'), "
                "name_ar = COALESCE(NULLIF(TRIM(name_ar), ''), 'نصرالله'), "
                "is_active = TRUE "
                "WHERE id = :id AND slug = :slug"
            ),
            {"id": tid, "slug": NASRALLAH_SLUG, "logo": LOGO, "fav": FAVICON},
        )
        return tid

    conn.execute(
        sa.text(
            "INSERT INTO tenants ("
            "name, name_ar, name_en, slug, business_type, country, "
            "default_currency, default_language, timezone, vat_country, "
            "logo_url, favicon_url, is_active, created_at"
            ") VALUES ("
            ":name, :name_ar, :name_en, :slug, :business_type, :country, "
            ":default_currency, :default_language, :timezone, :vat_country, "
            ":logo, :fav, TRUE, CURRENT_TIMESTAMP"
            ")"
        ),
        {
            "name": "Nasrallah",
            "name_ar": "نصرالله",
            "name_en": "Nasrallah",
            "slug": NASRALLAH_SLUG,
            "business_type": "general",
            "country": "IL",
            "default_currency": "ILS",
            "default_language": "ar",
            "timezone": "Asia/Jerusalem",
            "vat_country": "IL",
            "logo": LOGO,
            "fav": FAVICON,
        },
    )
    return _get_tenant_id(conn)


def _ensure_invoice_settings(conn, tenant_id: int) -> None:
    if not _table_exists(conn, "invoice_settings"):
        return
    row = conn.execute(
        sa.text("SELECT id FROM invoice_settings WHERE tenant_id = :tid LIMIT 1"),
        {"tid": tenant_id},
    ).fetchone()
    if row:
        conn.execute(
            sa.text(
                "UPDATE invoice_settings SET "
                "company_name_en = COALESCE(NULLIF(TRIM(company_name_en), ''), 'Nasrallah'), "
                "company_name_ar = COALESCE(NULLIF(TRIM(company_name_ar), ''), 'نصرالله'), "
                "logo_url = COALESCE(NULLIF(TRIM(logo_url), ''), :logo), "
                "logo_path = COALESCE(NULLIF(TRIM(logo_path), ''), :logo), "
                "is_active = TRUE "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id, "logo": LOGO},
        )
        return
    conn.execute(
        sa.text(
            "INSERT INTO invoice_settings ("
            "tenant_id, company_name_en, company_name_ar, logo_url, logo_path, is_active, created_at"
            ") VALUES ("
            ":tid, 'Nasrallah', 'نصرالله', :logo, :logo, TRUE, CURRENT_TIMESTAMP"
            ")"
        ),
        {"tid": tenant_id, "logo": LOGO},
    )


def _ensure_main_branch(conn, tenant_id: int) -> int | None:
    if not _table_exists(conn, "branches"):
        return None
    row = conn.execute(
        sa.text(
            "SELECT id FROM branches WHERE tenant_id = :tid AND code = 'MAIN' LIMIT 1"
        ),
        {"tid": tenant_id},
    ).fetchone()
    if row:
        return int(row[0])
    row2 = conn.execute(
        sa.text(
            "INSERT INTO branches (tenant_id, name, code, is_active, is_main, created_at) "
            "VALUES (:tid, 'Main Branch', 'MAIN', TRUE, TRUE, CURRENT_TIMESTAMP) "
            "RETURNING id"
        ),
        {"tid": tenant_id},
    ).fetchone()
    return int(row2[0]) if row2 else None


def _ensure_main_warehouse(conn, tenant_id: int, branch_id: int | None) -> None:
    if not _table_exists(conn, "warehouses"):
        return
    row = conn.execute(
        sa.text(
            "SELECT id FROM warehouses WHERE tenant_id = :tid AND code = 'MAIN' LIMIT 1"
        ),
        {"tid": tenant_id},
    ).fetchone()
    if row:
        if branch_id:
            conn.execute(
                sa.text(
                    "UPDATE warehouses SET branch_id = COALESCE(branch_id, :bid), is_main = TRUE "
                    "WHERE id = :id"
                ),
                {"id": int(row[0]), "bid": branch_id},
            )
        return
    conn.execute(
        sa.text(
            "INSERT INTO warehouses ("
            "tenant_id, name, name_ar, code, branch_id, warehouse_type, is_active, is_main, created_at"
            ") VALUES ("
            ":tid, 'Main Warehouse', 'المستودع الرئيسي', 'MAIN', :bid, 'physical', TRUE, TRUE, CURRENT_TIMESTAMP"
            ")"
        ),
        {"tid": tenant_id, "bid": branch_id},
    )


def _ensure_gl_accounts(conn, tenant_id: int) -> None:
    import os

    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    from sqlalchemy.orm import scoped_session, sessionmaker

    from app import create_app
    from extensions import db
    from services.gl_service import GLService

    app = create_app()
    with app.app_context():
        Session = scoped_session(sessionmaker(bind=conn))
        db.session = Session
        GLService.ensure_core_accounts(tenant_id=tenant_id)
        Session.flush()


def upgrade():
    conn = op.get_bind()
    tenant_id = _ensure_tenant(conn)
    if not tenant_id:
        raise RuntimeError("Failed to create or resolve nasrallah tenant")
    _ensure_invoice_settings(conn, tenant_id)
    branch_id = _ensure_main_branch(conn, tenant_id)
    _ensure_main_warehouse(conn, tenant_id, branch_id)
    _ensure_gl_accounts(conn, tenant_id)


def downgrade():
    # Tenant provisioning — restore from backup if rollback required.
    pass
