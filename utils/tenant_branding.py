"""
Central tenant branding resolution for UI and print documents.

Priority for tenant document logo:
  invoice_settings.logo_path → invoice_settings.logo_url → tenant.logo_url
  → tenant.logo_dark_url → static/assets/tenants/{slug}/ (disk)
  → Azad platform logo (last resort)
"""
from __future__ import annotations

import os
import re
from typing import Any

from utils.static_asset_paths import AZAD_LOGO, AZAD_FAVICON, tenant_asset_rel

_WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]")
_POWERED_BY = "Powered by Azad Smart Systems"


def normalize_static_rel(path: str | None) -> str:
    """Return a relative static path (no static/ prefix, no Windows absolute)."""
    p = (path or "").strip()
    if not p or _WINDOWS_ABS.match(p):
        return ""
    if p.startswith("http://") or p.startswith("https://"):
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
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"
    )
    return os.path.isfile(os.path.join(root, rel.replace("/", os.sep)))


def _first_existing(*candidates: str | None) -> str:
    for c in candidates:
        p = normalize_static_rel(c)
        if not p:
            continue
        if p.startswith("http") or _static_exists(p):
            return p
    return ""


def resolve_tenant_branding(tenant_id: int | None = None) -> dict[str, Any]:
    from extensions import db
    from models.invoice_settings import InvoiceSettings
    from models.tenant import Tenant
    from utils.tenant_assets import branding_for_tenant_slug

    tenant = db.session.get(Tenant, int(tenant_id)) if tenant_id else Tenant.get_current()
    settings = (
        InvoiceSettings.get_active(tenant.id)
        if tenant
        else InvoiceSettings.get_active()
    )

    disk: dict[str, str] = {}
    slug = (tenant.slug or "").strip().lower() if tenant else ""
    if slug:
        disk = branding_for_tenant_slug(slug)

    logo = _first_existing(
        settings.logo_path if settings else None,
        settings.logo_url if settings else None,
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

    company_name_ar = (
        (settings.company_name_ar if settings else None)
        or (tenant.name_ar if tenant else None)
        or "نظام المحاسبة"
    )
    company_name_en = (
        (settings.company_name_en if settings else None)
        or (tenant.name_en if tenant else None)
        or (tenant.name if tenant else None)
        or "Company"
    )
    address_ar = (
        (settings.address_ar if settings else None)
        or (tenant.address_ar if tenant else None)
        or ""
    )
    address_en = (
        (settings.address_en if settings else None)
        or (tenant.address_en if tenant else None)
        or ""
    )

    return {
        "tenant_id": tenant.id if tenant else None,
        "tenant_slug": slug,
        "logo_url": logo or AZAD_LOGO,
        "logo_dark_url": _first_existing(
            tenant.logo_dark_url if tenant else None,
            disk.get("logo_dark_url"),
        ),
        "favicon_url": favicon,
        "letterhead_url": letterhead,
        "invoice_logo_url": logo or AZAD_LOGO,
        "company_name_ar": company_name_ar,
        "company_name_en": company_name_en,
        "address_ar": address_ar,
        "address_en": address_en,
        "phone": (
            (settings.phone_1 if settings else None)
            or (tenant.phone_1 if tenant else None)
            or (tenant.mobile if tenant else None)
            or ""
        ),
        "email": (
            (settings.email if settings else None)
            or (tenant.email if tenant else None)
            or ""
        ),
        "tax_number": (
            (settings.tax_number if settings else None)
            or (tenant.tax_number if tenant else None)
            or ""
        ),
        "vat_country": (tenant.vat_country if tenant else None) or "AE",
        "default_currency": (tenant.default_currency if tenant else None) or "AED",
        "timezone": (tenant.timezone if tenant else None) or "Asia/Dubai",
        "city": (tenant.city if tenant else None) or "",
        "developer_logo_url": AZAD_LOGO,
        "powered_by_text": _POWERED_BY,
    }


def document_logo_relative_path(
    settings=None,
    tenant_id: int | None = None,
) -> str:
    """Logo path for tenant invoices/receipts/reports (relative under static/)."""
    branding = resolve_tenant_branding(tenant_id)
    if settings is not None:
        explicit = _first_existing(
            getattr(settings, "logo_path", None),
            getattr(settings, "logo_url", None),
        )
        if explicit:
            return explicit
    return branding["logo_url"] or AZAD_LOGO


def get_print_header_context(tenant_id: int | None = None) -> dict[str, Any]:
    """Context dict for print/PDF templates."""
    return resolve_tenant_branding(tenant_id)


def get_invoice_branding(tenant_id: int | None = None) -> dict[str, Any]:
    return resolve_tenant_branding(tenant_id)
