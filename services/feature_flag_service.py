"""
Feature Flag Service — Phase 10
Per-tenant feature flag resolution with global defaults from config.
"""

from flask import current_app


FEATURE_FLAG_KEYS = {
    'ENABLE_DYNAMIC_GL': 'ENABLE_DYNAMIC_GL_MAPPING',
    'ENABLE_MWAC': 'ENABLE_MWAC',
    'ENABLE_LANDED_COST': 'ENABLE_LANDED_COST_CAPITALIZATION',
    'ENABLE_EXCHANGE_RATE_LOCK': 'ENABLE_ONLINE_EXCHANGE_RATE_FALLBACK',
    'ENABLE_RECONCILIATION': 'ENABLE_ADVANCED_RECONCILIATION',
    'ENABLE_TREASURY': 'ENABLE_TREASURY',
    'ENABLE_LOCALIZATION': 'ENABLE_LOCALIZATION_FRAMEWORK',
    'ENABLE_LOAD_TESTING': 'ENABLE_LOAD_TESTING',
    'ENABLE_FULL_REGRESSION': 'ENABLE_FULL_REGRESSION',
}


class FeatureFlagService:
    """خدمة إدارة مفاتيح الميزات per-tenant"""

    @staticmethod
    def is_enabled(flag_key: str, tenant_id=None) -> bool:
        """
        Resolve feature flag: tenant override → config default → False.
        """
        config_key = FEATURE_FLAG_KEYS.get(flag_key, flag_key)

        # 1. Tenant override (if tenant.settings has the flag)
        if tenant_id is not None:
            from models import Tenant
            from extensions import db
            tenant = db.session.get(Tenant, tenant_id)
            if tenant and hasattr(tenant, 'settings') and tenant.settings:
                settings = tenant.settings if isinstance(tenant.settings, dict) else {}
                if flag_key in settings:
                    return bool(settings[flag_key])

        # 2. Global config default (Flask config is a dict — use .get, not getattr)
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
