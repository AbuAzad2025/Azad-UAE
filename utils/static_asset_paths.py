"""
Canonical relative paths under static/ for branding and shared assets.

Layout (plain language):
  assets/brand/azad/     — Azad platform owner logos & icons (not a tenant)
  assets/tenants/{slug}/ — each company's branding (logo, favicon, headers…)
  assets/shared/         — defaults for everyone (e.g. "no product photo")
  uploads/tenants/{id}/  — runtime files per tenant (product photos, uploaded logos)
"""

from __future__ import annotations

# Platform owner — Azad Smart Systems
AZAD_LOGO = "assets/brand/azad/logos/logo.png"
AZAD_LOGO_DARK = "assets/brand/azad/logos/logo-dark.png"
AZAD_FAVICON = "assets/brand/azad/favicons/favicon.png"
AZAD_ICON_192 = "assets/brand/azad/icons/icon-192.png"
AZAD_ICON_512 = "assets/brand/azad/icons/icon-512.png"

DEFAULT_PRODUCT_IMAGE = "assets/shared/placeholders/no-product.png"

TENANT_ASSET_LAYOUT: dict[str, str] = {
    "logo_url": "logos/logo.png",
    "logo_dark_url": "logos/logo-dark.png",
    "favicon_url": "favicons/favicon.png",
    "og_image_url": "og/social-share.png",
    "icon_192": "icons/icon-192.png",
    "icon_512": "icons/icon-512.png",
}


def tenant_asset_base(folder: str) -> str:
    return f"assets/tenants/{folder}"


def tenant_asset_rel(folder: str, kind: str) -> str:
    rel = TENANT_ASSET_LAYOUT.get(kind)
    if not rel:
        raise KeyError(kind)
    return f"{tenant_asset_base(folder)}/{rel}"


def tenant_upload_dir(tenant_id: int, category: str) -> str:
    """Runtime upload path relative to static/ (e.g. uploads/tenants/1/products)."""
    if not tenant_id:
        raise ValueError("tenant_id required")
    safe = category.strip("/").replace("..", "").strip("/")
    return f"uploads/tenants/{int(tenant_id)}/{safe}"


def tenant_demo_products_dir(tenant_slug: str) -> str:
    """Sample product images shipped in git for a tenant storefront."""
    slug = (tenant_slug or "").strip().lower()
    return f"assets/tenants/{slug}/demo-products"
