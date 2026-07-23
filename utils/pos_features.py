"""POS Phase 4 — per-tenant POS sub-feature flags (SaaS feature flagging).

Each sub-feature maps to a nullable ``Tenant.enable_<feature>`` column:

- ``None``  → inherit the plan-level default (pro/enterprise tiers enable the
  advanced POS surface; the basic tier gets core checkout only).
- ``True``  → explicitly enabled (per-tenant override, e.g. add-on purchase).
- ``False`` → explicitly disabled (per-tenant override).

Stateless by design (GRIMOIRE utils layer) — the caller supplies the tenant.
"""

from __future__ import annotations

POS_SUBFEATURES = frozenset(
    {
        "pos_promotions",
        "pos_multi_tender",
        "pos_returns",
        "pos_shifts",
    }
)

# Minimum subscription tier that inherits each sub-feature when the per-tenant
# column is NULL. All Phase 1-4 advanced POS surfaces are pro+.
_POS_SUBFEATURE_MIN_PLAN = dict.fromkeys(POS_SUBFEATURES, "pro")

_PLAN_LEVELS = {"basic": 10, "pro": 20, "enterprise": 30}


def plan_meets(plan: str | None, minimum: str) -> bool:
    """True when ``plan`` is at least ``minimum`` in the tier hierarchy."""
    return _PLAN_LEVELS.get(plan or "basic", 0) >= _PLAN_LEVELS.get(minimum, 0)


def pos_feature_enabled(tenant, feature: str) -> bool:
    """Resolve a POS sub-feature for a tenant (column override → plan default)."""
    if feature not in POS_SUBFEATURES:
        raise ValueError(f"Unknown POS sub-feature: {feature}")
    value = getattr(tenant, f"enable_{feature}", None)
    if value is not None:
        return bool(value)
    return plan_meets(
        getattr(tenant, "subscription_plan", None),
        _POS_SUBFEATURE_MIN_PLAN[feature],
    )
