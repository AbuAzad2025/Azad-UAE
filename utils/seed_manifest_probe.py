"""Row-count probes referenced by ``utils/seed_manifest.py``.

Kept separate from the manifest so the manifest stays pure data: it declares
``verify="utils.seed_manifest_probe.count_roles"`` and this module supplies the
callable. Every probe is a single cheap COUNT and none of them creates or repairs
anything - these are read-only assertions that the documented state is the real
state.

Each probe returns an int. They assume an application context, and they raise on
a broken schema so the caller can decide how loudly to complain.
"""

from __future__ import annotations

from sqlalchemy import func

from extensions import db
from models.gl_account_registry import GL_MODULE_DEFINITIONS


def count_permissions() -> int:
    from models.user import Permission

    return int(db.session.query(func.count(Permission.id)).scalar() or 0)


def count_roles() -> int:
    from models.user import Role

    return int(db.session.query(func.count(Role.id)).scalar() or 0)


def count_currencies() -> int:
    from models.currency import Currency

    return int(db.session.query(func.count(Currency.id)).scalar() or 0)


def count_industry_fields() -> int:
    from models.industry_field_definition import IndustryFieldDefinition

    return int(db.session.query(func.count(IndustryFieldDefinition.id)).scalar() or 0)


def count_system_settings() -> int:
    from models.system_settings import SystemSettings

    return int(db.session.query(func.count(SystemSettings.id)).scalar() or 0)


def count_activation_alerts() -> int:
    """Server-activation records.

    The literal below is the one ``utils/system_init._record_server_activation``
    writes; it is repeated here rather than imported because the seeder builds it
    inline and exposes no constant.
    """
    from models.security_alert import SecurityAlert

    return int(
        db.session.query(func.count(SecurityAlert.id)).filter(SecurityAlert.alert_type == "system_activation").scalar()
        or 0
    )


def count_pos_order_types() -> int:
    from models.pos_order_type import PosOrderType

    return int(db.session.query(func.count(PosOrderType.id)).scalar() or 0)


def count_store_payment_methods() -> int:
    from models.store_payment_method import StorePaymentMethod

    return int(db.session.query(func.count(StorePaymentMethod.id)).scalar() or 0)


def count_gl_mappings() -> int:
    from models.gl import GLAccountMapping

    return int(db.session.query(func.count(GLAccountMapping.id)).scalar() or 0)


def min_gl_accounts_for_active_tenant() -> int:
    """Smallest chart of accounts across active tenants.

    The chart is per tenant, so the meaningful health signal is the *minimum*:
    the tenant with the fewest accounts is the one most likely to be under-seeded.
    Returns 0 when there are no active tenants, because an empty platform has
    nothing to seed yet.

    The manifest asserts ``>= 98`` against this, which is the count of
    ``BASE_ACCOUNTS``. That floor is unconditional: ``GLTreeBuilder.build`` calls
    ``_get_core_account_tree()`` for every tenant regardless of its
    ``business_type``, and the industry tree on top of it is additive, so a
    tenant below 98 is genuinely broken rather than merely minimal.
    """
    from models.gl import GLAccount
    from models.tenant import Tenant

    tids = [row[0] for row in db.session.query(Tenant.id).filter(Tenant.is_active.is_(True)).all()]
    if not tids:
        return 0
    counts = [
        int(db.session.query(func.count(GLAccount.id)).filter(GLAccount.tenant_id == tid).scalar() or 0) for tid in tids
    ]
    return min(counts)


def count_tenants_missing_required_gl_mappings() -> int:
    """How many active tenants are short of their required GL mappings. Must be 0.

    Expressed as a violation count rather than a row count on purpose.
    ``GLService.ensure_gl_mappings`` returns early with zero created when
    dynamic GL mapping is disabled, so on such an install the correct number of
    mapping rows is legitimately 0. Asserting ">= 16" would fire a false
    VIOLATED on every install that has the feature switched off, and asserting
    ">= 0" would be vacuous. Counting the tenants that are actually short
    sidesteps both: the check is meaningful and never false-alarms.
    """
    from models.gl import GLAccountMapping
    from models.tenant import Tenant
    from services.gl_service import is_dynamic_gl_mapping_enabled

    if not is_dynamic_gl_mapping_enabled():
        return 0  # nothing is required of this install

    required = len(GL_MODULE_DEFINITIONS)
    tids = [row[0] for row in db.session.query(Tenant.id).filter(Tenant.is_active.is_(True)).all()]
    short = 0
    for tid in tids:
        actual = int(
            db.session.query(func.count(GLAccountMapping.id)).filter(GLAccountMapping.tenant_id == tid).scalar() or 0
        )
        if actual < required:
            short += 1
    return short


def count_active_tenants() -> int:
    from models.tenant import Tenant

    return int(db.session.query(func.count(Tenant.id)).filter(Tenant.is_active.is_(True)).scalar() or 0)


# ── Integrity probes for lazy data ──────────────────────────────────────────
#
# A lazy set is created on first read, so asserting a row *count* against it
# produces false alarms: a tenant that has never opened the invoices page
# legitimately has zero invoice settings. What must always hold is the
# structural invariant - never more than one per tenant - which is what these
# probe, paired with ``check="at_most"`` in the manifest.


def _active_tenant_ids() -> list[int]:
    from models.tenant import Tenant

    return [row[0] for row in db.session.query(Tenant.id).filter(Tenant.is_active.is_(True)).all()]


def max_tenant_stores_per_active_tenant() -> int:
    """Highest number of storefronts any single active tenant has. Must be <= 1."""
    from models.tenant_store import TenantStore

    counts = [
        int(db.session.query(func.count(TenantStore.id)).filter(TenantStore.tenant_id == tid).scalar() or 0)
        for tid in _active_tenant_ids()
    ]
    return max(counts) if counts else 0


def max_invoice_settings_per_active_tenant() -> int:
    """Highest number of invoice-settings rows any single active tenant has. Must be <= 1."""
    from models.invoice_settings import InvoiceSettings

    counts = [
        int(db.session.query(func.count(InvoiceSettings.id)).filter(InvoiceSettings.tenant_id == tid).scalar() or 0)
        for tid in _active_tenant_ids()
    ]
    return max(counts) if counts else 0


def max_integration_settings_per_active_tenant() -> int:
    """Highest number of integration-settings rows any single active tenant has. Must be <= 1."""
    from models.integration_settings import IntegrationSettings

    counts = [
        int(
            db.session.query(func.count(IntegrationSettings.id)).filter(IntegrationSettings.tenant_id == tid).scalar()
            or 0
        )
        for tid in _active_tenant_ids()
    ]
    return max(counts) if counts else 0


def max_document_sequences_per_document_type() -> int:
    """Highest number of sequences for one (tenant, document_type) pair. Must be <= 1.

    Two sequences for the same document type in one tenant means two independent
    counters, so concurrent documents can be issued the same number. That is a
    numbering integrity failure regardless of whether either tenant has ever
    opened the page - which is why a count-based assertion was the wrong shape.
    """
    from models.document_sequence import DocumentSequence

    counts = [
        int(
            db.session.query(func.count(DocumentSequence.id))
            .filter(DocumentSequence.tenant_id == tid)
            .group_by(DocumentSequence.document_type)
            .scalar()
            or 0
        )
        for tid in _active_tenant_ids()
    ]
    return max(counts) if counts else 0


def min_pos_order_types_for_active_tenant() -> int:
    """Fewest POS order types any single active tenant has."""
    from models.pos_order_type import PosOrderType

    counts = [
        int(db.session.query(func.count(PosOrderType.id)).filter(PosOrderType.tenant_id == tid).scalar() or 0)
        for tid in _active_tenant_ids()
    ]
    return min(counts) if counts else 0


def min_store_payment_methods_for_active_tenant() -> int:
    """Fewest storefront payment methods any single active tenant has."""
    from models.store_payment_method import StorePaymentMethod

    counts = [
        int(
            db.session.query(func.count(StorePaymentMethod.id)).filter(StorePaymentMethod.tenant_id == tid).scalar()
            or 0
        )
        for tid in _active_tenant_ids()
    ]
    return min(counts) if counts else 0


def min_branches_for_active_tenant() -> int:
    """Fewest active branches any single active tenant has.

    A tenant with zero branches cannot record a sale, so this is a real
    liveness invariant rather than an arbitrary count. It is deliberately
    checked even though branches are operator-created: the manifest used to
    mark this set ``seeder=None``, which made ``verify_seed_manifest`` skip it
    entirely (``if seed_set.seeder is None: continue``), leaving the one tenant
    set that must never be empty with no check at all.
    """
    from models.branch import Branch

    counts = [
        int(
            db.session.query(func.count(Branch.id)).filter(Branch.tenant_id == tid, Branch.is_active.is_(True)).scalar()
            or 0
        )
        for tid in _active_tenant_ids()
    ]
    return min(counts) if counts else 0
