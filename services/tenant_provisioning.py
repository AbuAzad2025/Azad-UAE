"""
Safe tenant industry provisioning layer.

Design goals (no destructive schema changes):
- Enforce `business_type` (and `industry`) at the APPLICATION level for new tenants.
- Provide a runtime compatibility fallback so legacy tenants with NULL
  `business_type`/`industry` resolve to sane defaults ('general' / 'retail').
- Trigger the specialized industry chart of accounts through
  `GLProvisioningService`, which is already idempotent (it skips any account
  code that already exists for the tenant).

No NOT NULL constraints are added at the database level.
"""
from __future__ import annotations

from typing import Optional

from services.industry_service import (
    VALID_BUSINESS_TYPES,
    get_pos_profile,
)


def validate_tenant_industry(business_type: Optional[str], industry: Optional[str] = None):
    """Application-level enforcement for new tenant creation.

    Raises ValueError if a mandatory field is missing. Unknown (legacy) codes
    are tolerated so existing seeds (e.g. 'multi_branch_retail') keep working.
    """
    bt = (business_type or '').strip()
    if not bt:
        raise ValueError("يجب تحديد نوع النشاط (business_type) عند إنشاء الشركة.")
    # Legacy/unknown codes are accepted; they simply map to neutral behaviour.
    ind = (industry or '').strip() or None
    return bt, ind


def resolve_tenant_industry(tenant) -> dict:
    """Compatibility layer: never return NULL for runtime consumers.

    Falls back to 'general' for business_type and 'retail' for industry so any
    code path (POS profile, GL extension, product fields) is always safe.
    """
    bt = (getattr(tenant, 'business_type', None) or '').strip() or 'general'
    ind = (getattr(tenant, 'industry', None) or '').strip() or 'retail'
    return {
        'business_type': bt,
        'industry': ind,
        'is_known': bt in VALID_BUSINESS_TYPES,
    }


def provision_tenant_gl(tenant_id: int) -> dict:
    """Idempotently seed the tenant's chart of accounts (base + industry extensions).

    `GLProvisioningService.provision_tenant` already guards every account write
    against pre-existing codes, so repeated calls are safe and duplicate-key
    failures cannot occur.
    """
    from services.gl_provisioning_service import GLProvisioningService
    result = GLProvisioningService.provision_tenant(tenant_id)
    return {
        'tenant_id': result.tenant_id,
        'created_accounts': result.created_accounts,
        'skipped_accounts': result.skipped_accounts,
        'created_mappings': result.created_mappings,
        'skipped_mappings': result.skipped_mappings,
        'errors': result.errors,
    }


def build_pos_profile(tenant) -> dict:
    """POS runtime profile with safe industry fallback applied."""
    resolved = resolve_tenant_industry(tenant)
    profile = get_pos_profile(tenant)
    profile['industry'] = resolved['industry']
    profile['is_known_business_type'] = resolved['is_known']
    return profile
