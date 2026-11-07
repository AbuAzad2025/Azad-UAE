"""Explicit, tenant-scoped access to the unified document profile.

Every document render reads back one pinned tenant's snapshot. This module
adds no business logic of its own; it simply pins the tenant id and builds the
transient snapshot that document templates expect.
"""

from __future__ import annotations

from extensions import db
from models.tenant import Tenant
from utils.invoice_profile import apply_snapshot_to_tenant, build_invoice_settings_snapshot
from utils.tenanting import without_tenant_scope


def resolve_print_profile(tenant_id):
    """Resolve one tenant's print/profile snapshot without writing anything."""
    if tenant_id is None:
        return None
    return build_invoice_settings_snapshot_from_id(int(tenant_id))


def build_invoice_settings_snapshot_from_id(tenant_id):
    """Pinned tenant read for owner-selected tenants without tenant scoping."""
    with without_tenant_scope():
        tenant = db.session.get(Tenant, int(tenant_id))
    if tenant is None:
        return None
    return build_invoice_settings_snapshot(tenant)


def get_company_print_context(tenant_id=None, user=None):
    """Resolve the tenant, its profile snapshot and the company dict."""
    tid = tenant_id
    if tid is None and user is not None:
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
    if tid is None:
        return None, None, None
    tenant = db.session.get(Tenant, int(tid)) if tenant_id is not None else None
    if tenant is None:
        from utils.tenanting import without_tenant_scope

        with without_tenant_scope():
            tenant = db.session.get(Tenant, int(tid))
    if tenant is None:
        return None, None, None
    settings = build_invoice_settings_snapshot(tenant)
    company = {
        "name_ar": settings.company_name_ar,
        "name_en": settings.company_name_en,
        "address": settings.address_ar or settings.address_en,
        "phone": settings.phone_1,
        "email": settings.email,
        "tax_number": settings.tax_number,
        "logo_url": settings.logo_url,
    }
    return tenant, settings, company


def save_print_profile(tenant, data, *, allow_files=None):
    """Persist the unified invoice settings form against one pinned tenant."""
    return apply_snapshot_to_tenant(tenant, data, allow_files=allow_files)


def save_print_overlay(tenant, **values):
    """Persist print-only flags/values on the tenant profile."""
    return apply_snapshot_to_tenant(tenant, values)
