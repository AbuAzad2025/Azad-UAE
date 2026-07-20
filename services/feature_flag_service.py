"""
Feature Flag Service — Phase 10
Per-tenant feature flag resolution with global defaults from config.

NOTE: The flags in FEATURE_FLAG_KEYS are *platform-level* capability toggles
(e.g. ENABLE_TREASURY, ENABLE_LANDED_COST).  They are resolved from the Flask
config; there is no per-tenant database column for them.
Per-tenant feature gating (e.g. enable_pos, enable_ai) uses the ``Tenant``
model's ``enable_*`` boolean columns directly (see utils/decorators.py).
"""

from flask import current_app

FEATURE_FLAG_KEYS = {
    "ENABLE_DYNAMIC_GL": "ENABLE_DYNAMIC_GL_MAPPING",
    "ENABLE_MWAC": "ENABLE_MWAC",
    "ENABLE_LANDED_COST": "ENABLE_LANDED_COST_CAPITALIZATION",
    "ENABLE_EXCHANGE_RATE_LOCK": "ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK",
    "ENABLE_RECONCILIATION": "ENABLE_ADVANCED_RECONCILIATION",
    "ENABLE_TREASURY": "ENABLE_TREASURY",
    "ENABLE_LOCALIZATION": "ENABLE_LOCALIZATION_FRAMEWORK",
    "ENABLE_LOAD_TESTING": "ENABLE_LOAD_TESTING",
    "ENABLE_FULL_REGRESSION": "ENABLE_FULL_REGRESSION",
}


class FeatureFlagService:
    """Platform-level feature flag resolution from global config."""

    @staticmethod
    def is_enabled(flag_key: str, tenant_id=None) -> bool:
        """
        Resolve feature flag from global Flask config.

        ``tenant_id`` is accepted for backward compatibility but is **not**
        used — per-tenant feature gating is handled by the ``enable_*``
        columns on the ``Tenant`` model, not by this service (see
        ``utils/decorators.require_subscription_feature``).
        """
        config_key = FEATURE_FLAG_KEYS.get(flag_key, flag_key)
        return bool(current_app.config.get(config_key, False))

    @staticmethod
    def get_all_flags(tenant_id=None) -> dict:
        """Return all flags resolved for a tenant."""
        return {k: FeatureFlagService.is_enabled(k, tenant_id) for k in FEATURE_FLAG_KEYS}

    @staticmethod
    def require_enabled(flag_key: str, tenant_id=None):
        """Raise if flag is not enabled."""
        if not FeatureFlagService.is_enabled(flag_key, tenant_id):
            raise RuntimeError(f"Feature flag '{flag_key}' is not enabled for tenant {tenant_id}")
