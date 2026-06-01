"""canonical_static_asset_paths

Revision ID: canonical_static_asset_paths_001
Revises: prod_schema_hardening_001
Create Date: 2026-06-01 23:25:00.000000

Idempotent data migration: legacy img/static/img product and tenant asset paths
→ canonical assets/... and uploads/... relative paths.
"""
from alembic import op
import sqlalchemy as sa


revision = "canonical_static_asset_paths_001"
down_revision = "prod_schema_hardening_001"
branch_labels = None
depends_on = None

PLACEHOLDER = "assets/shared/placeholders/no-product.png"

# slug → (old path fragment → canonical relative path under static/)
TENANT_PATH_MAP: dict[str, dict[str, str]] = {
    "alhazem": {
        "img/tenants/alhazem/logo.png": "assets/tenants/alhazem/logos/logo.png",
        "static/img/tenants/alhazem/logo.png": "assets/tenants/alhazem/logos/logo.png",
        "img/tenants/alhazem/logo_dark.png": "assets/tenants/alhazem/logos/logo-dark.png",
        "static/img/tenants/alhazem/logo_dark.png": "assets/tenants/alhazem/logos/logo-dark.png",
        "img/tenants/alhazem/favicon.png": "assets/tenants/alhazem/favicons/favicon.png",
        "static/img/tenants/alhazem/favicon.png": "assets/tenants/alhazem/favicons/favicon.png",
        "img/alhazem/logos/primary.png": "assets/tenants/alhazem/logos/logo-full.png",
        "static/img/alhazem/logos/primary.png": "assets/tenants/alhazem/logos/logo-full.png",
        "img/alhazem/headers/banner.png": "assets/tenants/alhazem/headers/store-banner.png",
        "static/img/alhazem/headers/banner.png": "assets/tenants/alhazem/headers/store-banner.png",
        "img/alhazem/headers/letterhead.png": "assets/tenants/alhazem/headers/invoice-letterhead.png",
        "static/img/alhazem/headers/letterhead.png": "assets/tenants/alhazem/headers/invoice-letterhead.png",
        "img/tenants/alhazem/og-1200x630.png": "assets/tenants/alhazem/og/social-share.png",
        "static/img/tenants/alhazem/og-1200x630.png": "assets/tenants/alhazem/og/social-share.png",
    },
    "nasrallah": {
        "img/nasrallah/logos/primary.png": "assets/tenants/nasrallah/logos/logo-primary.png",
        "static/img/nasrallah/logos/primary.png": "assets/tenants/nasrallah/logos/logo-primary.png",
        "img/nasrallah/logos/emblem.png": "assets/tenants/nasrallah/logos/logo-emblem.png",
        "static/img/nasrallah/logos/emblem.png": "assets/tenants/nasrallah/logos/logo-emblem.png",
        "img/nasrallah/favicons/favicon.png": "assets/tenants/nasrallah/favicons/favicon.png",
        "static/img/nasrallah/favicons/favicon.png": "assets/tenants/nasrallah/favicons/favicon.png",
        "img/nasrallah/headers/banner.png": "assets/tenants/nasrallah/headers/store-banner.png",
        "static/img/nasrallah/headers/banner.png": "assets/tenants/nasrallah/headers/store-banner.png",
        "img/nasrallah/headers/letterhead.png": "assets/tenants/nasrallah/headers/invoice-letterhead.png",
        "static/img/nasrallah/headers/letterhead.png": "assets/tenants/nasrallah/headers/invoice-letterhead.png",
    },
}

TENANT_COLUMNS = ("logo_url", "logo_dark_url", "favicon_url")
INVOICE_LOGO_COLUMNS = ("logo_url", "logo_path")


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


def _tenant_slug_exists(conn, slug: str) -> bool:
    if not _table_exists(conn, "tenants"):
        return False
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM tenants WHERE slug = :slug LIMIT 1"),
            {"slug": slug},
        ).scalar()
    )


def _update_tenant_branding(conn) -> None:
    if not _table_exists(conn, "tenants"):
        return
    for slug, mapping in TENANT_PATH_MAP.items():
        if not _tenant_slug_exists(conn, slug):
            continue
        for col in TENANT_COLUMNS:
            for old, new in mapping.items():
                conn.execute(
                    sa.text(
                        f"UPDATE tenants SET {col} = :new "
                        f"WHERE slug = :slug AND TRIM(COALESCE({col}, '')) = :old"
                    ),
                    {"new": new, "slug": slug, "old": old},
                )


def _update_invoice_settings(conn) -> None:
    if not _table_exists(conn, "invoice_settings") or not _table_exists(conn, "tenants"):
        return
    for slug, mapping in TENANT_PATH_MAP.items():
        if not _tenant_slug_exists(conn, slug):
            continue
        tenant_id = conn.execute(
            sa.text("SELECT id FROM tenants WHERE slug = :slug LIMIT 1"),
            {"slug": slug},
        ).scalar()
        if not tenant_id:
            continue
        for col in INVOICE_LOGO_COLUMNS:
            for old, new in mapping.items():
                conn.execute(
                    sa.text(
                        f"UPDATE invoice_settings SET {col} = :new "
                        f"WHERE tenant_id = :tid AND TRIM(COALESCE({col}, '')) = :old"
                    ),
                    {"new": new, "tid": tenant_id, "old": old},
                )


def _update_products(conn) -> None:
    if not _table_exists(conn, "products"):
        return
    conn.execute(
        sa.text(
            "UPDATE products SET image_url = :ph "
            "WHERE image_url IS NOT NULL AND ("
            "image_url LIKE 'https://example.com%' "
            "OR image_url LIKE 'http://example.com%' "
            "OR image_url LIKE '%127.0.0.1%'"
            ")"
        ),
        {"ph": PLACEHOLDER},
    )
    conn.execute(
        sa.text(
            "UPDATE products SET image_url = SUBSTRING(image_url FROM 8) "
            "WHERE image_url LIKE 'static/assets/%' OR image_url LIKE 'static/uploads/%'"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE products SET image_url = :ph "
            "WHERE image_url IS NOT NULL AND ("
            "image_url LIKE 'D:%' OR image_url LIKE 'C:%' "
            "OR image_url LIKE 'D:\\\\%' OR image_url LIKE 'C:\\\\%'"
            ")"
        ),
        {"ph": PLACEHOLDER},
    )
    legacy_product_paths = {
        "static/products/default.png": PLACEHOLDER,
        "static/products/default2.png": "assets/shared/placeholders/no-product-alt.png",
        "products/default.png": PLACEHOLDER,
        "products/default2.png": "assets/shared/placeholders/no-product-alt.png",
    }
    for old, new in legacy_product_paths.items():
        conn.execute(
            sa.text(
                "UPDATE products SET image_url = :new "
                "WHERE TRIM(COALESCE(image_url, '')) = :old"
            ),
            {"new": new, "old": old},
        )
    for slug, mapping in TENANT_PATH_MAP.items():
        if not _tenant_slug_exists(conn, slug):
            continue
        for old, new in mapping.items():
            if "demo-products" in new or "headers/" in new:
                continue
            conn.execute(
                sa.text(
                    "UPDATE products SET image_url = :new "
                    "WHERE TRIM(COALESCE(image_url, '')) = :old"
                ),
                {"new": new, "old": old},
            )


def upgrade():
    conn = op.get_bind()
    _update_tenant_branding(conn)
    _update_invoice_settings(conn)
    _update_products(conn)


def downgrade():
    # Data migration — restore from backup if rollback required.
    pass
