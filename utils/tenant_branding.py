"""Tenant branding resolution for UI and print documents.

Tenant profile values are authoritative. ``file_hints`` may be supplied by an
explicit caller for uploaded assets such as a transient print snapshot, but are
not fetched from legacy settings here.
"""

from __future__ import annotations

import os
import re
from typing import Any

from utils.cache_decorators import cached_query
from utils.regional_defaults import (
    FALLBACK_CURRENCY,
    FALLBACK_TIMEZONE,
    FALLBACK_VAT_COUNTRY,
)
from utils.static_asset_paths import AZAD_FAVICON, AZAD_LOGO

_WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]")
_POWERED_BY = "Powered by AZAD Intelligent Systems"
_COPYRIGHT_AR = "شركة أزاد للأنظمة الذكية"
_COPYRIGHT_EN = "AZAD Intelligent Systems"


def normalize_static_rel(path: str | None) -> str:
    """Return a relative static path (no static/ prefix, no Windows absolute)."""
    p = (path or "").strip()
    if not p or _WINDOWS_ABS.match(p):
        return ""
    if "://" in p:
        return p
    if p.startswith("/static/"):
        p = p[len("/static/") :]
    elif p.startswith("static/"):
        p = p[len("static/") :]
    return p.replace("\\", "/")


def _static_exists(rel: str) -> bool:
    rel = normalize_static_rel(rel)
    if not rel or rel.startswith("http"):
        return bool(rel)
    root = str(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"))
    return os.path.isfile(os.path.join(root, rel.replace("/", os.sep)))


def _first_existing(*candidates: str | None) -> str:
    for c in candidates:
        p = normalize_static_rel(c)
        if not p:
            continue
        if p.startswith("http") or _static_exists(p):
            return p
    return ""


@cached_query(timeout=300, key_prefix="tenant_branding")
def resolve_tenant_branding(tenant_id: int | None = None, profile=None) -> dict[str, Any]:
    """Resolve branding from the pinned tenant profile and disk assets.

    ``profile`` is an explicit caller-selected snapshot (for a document) and is
    not accepted as a replacement tenant ID. Without it the tenant profile alone
    supplies company fields.
    """
    from extensions import db
    from models.tenant import Tenant

    tenant = db.session.get(Tenant, int(tenant_id)) if tenant_id else Tenant.get_current()
    if tenant is None:
        profile = None  # a print snapshot is pinned to one tenant; without it, it cannot resolve
    from utils.tenant_assets import branding_for_tenant_slug

    logo_path = getattr(profile, "logo_path", None) if profile is not None else None
    disk: dict[str, str] = {}
    slug = (tenant.slug or "").strip().lower() if tenant else ""
    if slug:
        disk = branding_for_tenant_slug(slug)

    logo = _first_existing(
        logo_path,
        tenant.logo_url if tenant else None,
        tenant.logo_dark_url if tenant else None,
        disk.get("logo_url"),
    )
    favicon = _first_existing(
        tenant.favicon_url if tenant else None,
        disk.get("favicon_url"),
        AZAD_FAVICON,
    )
    letterhead = _first_existing(
        disk.get("letterhead_url"),
        f"assets/tenants/{slug}/headers/invoice-letterhead.png" if slug else None,
    )

    company_name_ar = (tenant.name_ar if tenant else None) or ""
    company_name_en = (tenant.name_en if tenant else None) or (tenant.name if tenant else None) or "Company"
    address_ar = (tenant.address_ar if tenant else None) or ""
    address_en = (tenant.address_en if tenant else None) or ""

    return {
        "tenant_id": tenant.id if tenant else None,
        "tenant_slug": slug,
        "logo_url": logo,
        "logo_dark_url": _first_existing(
            tenant.logo_dark_url if tenant else None,
            disk.get("logo_dark_url"),
        ),
        "favicon_url": favicon,
        "letterhead_url": letterhead,
        "invoice_logo_url": logo,
        "company_name_ar": company_name_ar,
        "company_name_en": company_name_en,
        "address_ar": address_ar,
        "address_en": address_en,
        "phone": ((tenant.phone_1 if tenant else None) or (tenant.mobile if tenant else None) or ""),
        "email": (tenant.email if tenant else None) or "",
        "tax_number": (tenant.tax_number if tenant else None) or "",
        "vat_country": (tenant.vat_country if tenant else None) or FALLBACK_VAT_COUNTRY,
        "default_currency": (tenant.default_currency if tenant else None) or FALLBACK_CURRENCY,
        "timezone": (tenant.timezone if tenant else None) or FALLBACK_TIMEZONE,
        "city": (tenant.city if tenant else None) or "",
        "developer_logo_url": AZAD_LOGO,
        "powered_by_text": _POWERED_BY,
        "copyright_ar": _COPYRIGHT_AR,
        "copyright_en": _COPYRIGHT_EN,
    }


def document_logo_relative_path(
    settings=None,
    tenant_id: int | None = None,
) -> str:
    """Logo path for tenant invoices/receipts/reports (relative under static/)."""
    profile_path = getattr(settings, "logo_path", None) if settings is not None else None
    logo = _first_existing(profile_path)
    if logo:
        return logo
    branding = resolve_tenant_branding(tenant_id, profile=settings)
    return branding["logo_url"]


def get_print_header_context(tenant_id: int | None = None, profile=None) -> dict[str, Any]:
    """Context dict for print/PDF templates."""
    return resolve_tenant_branding(tenant_id, profile=profile)


def get_invoice_branding(tenant_id: int | None = None, profile=None) -> dict[str, Any]:
    return resolve_tenant_branding(tenant_id, profile=profile)


def branding_path_warnings(branding: dict[str, Any] | None) -> list[str]:
    """Display-only warnings for owner panel (does not change branding resolution)."""
    if not branding:
        return ["no branding resolved"]
    warns: list[str] = []
    for key in ("logo_url", "favicon_url", "letterhead_url"):
        raw = branding.get(key) or ""
        if _WINDOWS_ABS.match(raw):
            warns.append(f"{key}: absolute Windows path")
        elif raw and not raw.startswith("http"):
            rel = normalize_static_rel(raw)
            if rel and not _static_exists(rel):
                warns.append(f"{key}: file missing ({rel})")
    slug = (branding.get("tenant_slug") or "").strip()
    logo = normalize_static_rel(branding.get("logo_url") or "")
    if slug and logo and f"assets/tenants/{slug}" not in logo and "uploads/" not in logo:
        if "azad" in logo.lower() and slug not in ("azad",):
            warns.append("logo may be platform default, not tenant asset")
    return warns
