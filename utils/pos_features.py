"""POS Phase 4 — per-tenant POS sub-feature flags (SaaS feature flagging).

Each sub-feature maps to a nullable ``Tenant.enable_<feature>`` column:

- ``None``  → inherit the plan-level default (pro/enterprise tiers enable the
  advanced POS surface; the basic tier gets core checkout only).
- ``True``  → explicitly enabled (per-tenant override, e.g. add-on purchase).
- ``False`` → explicitly disabled (per-tenant override).

Plan hierarchy is resolved from the DB ``packages`` table (``tier_level``
column, seeded by ``seed_packages()``) — the Package model is the single
source of truth. ``_FALLBACK_TIER_LEVELS`` only applies when the DB is
unreachable or the slug has no matching package (e.g. isolated unit tests).

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

# Used only when the packages table cannot be consulted (no app context,
# no matching row, or DB error). Mirrors the seeded DEFAULT_PACKAGES tiers.
_FALLBACK_TIER_LEVELS = {"basic": 10, "pro": 20, "enterprise": 30}


def _db_tier_level(plan_slug: str) -> int | None:
    """Resolve a plan slug's tier level from the packages table; None if unknown."""
    try:
        from models.package import Package

        pkg = Package.query.filter_by(slug=plan_slug, is_active=True).first()
        if pkg is not None and isinstance(pkg.tier_level, int) and not isinstance(pkg.tier_level, bool):
            return pkg.tier_level
    except Exception:
        # No app context / no DB / table missing — fall through to fallback.
        pass
    return None


def _tier_level(plan: str | None) -> int:
    slug = plan or "basic"
    return _db_tier_level(slug) or _FALLBACK_TIER_LEVELS.get(slug, 0)


def plan_meets(plan: str | None, minimum: str) -> bool:
    """True when ``plan`` is at least ``minimum`` in the tier hierarchy."""
    return _tier_level(plan) >= _tier_level(minimum)


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
