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


def count_active_tenants() -> int:
    from models.tenant import Tenant

    return int(db.session.query(func.count(Tenant.id)).filter(Tenant.is_active.is_(True)).scalar() or 0)
