"""Shipping & SMS configuration helper — reads from IntegrationSettings (DB) first,
then falls back to environment variables. This lets the owner/tenant manager
configure carrier API keys and SMS credentials through the UI instead of
editing .env files.
"""

from __future__ import annotations

import os
from typing import Any


class ShippingConfigService:
    """Read/write shipping carrier credentials from IntegrationSettings."""

    CARRIER_NAMES = ("dhl", "fedex", "aramex")

    @staticmethod
    def get_carrier_config(carrier: str, tenant_id: int | None = None) -> dict[str, Any]:
        """Return config dict for a carrier (keys depend on carrier)."""
        carrier = (carrier or "").lower()
        # Try DB first
        try:
            from models.integration_settings import IntegrationSettings

            integration = IntegrationSettings.get_service_config("shipping", tenant_id=tenant_id)
            cfg = integration.get_config() if integration else {}
            carrier_cfg = (cfg.get("carriers") or {}).get(carrier) or {}
            if carrier_cfg:
                return carrier_cfg
        except Exception:
            import logging

            logging.getLogger(__name__).debug("shipping config read failed", exc_info=True)
        # Fall back to env vars
        if carrier == "dhl":
            return {"api_key": os.environ.get("DHL_API_KEY", "")}
        if carrier == "fedex":
            return {
                "client_id": os.environ.get("FEDEX_CLIENT_ID", ""),
                "client_secret": os.environ.get("FEDEX_CLIENT_SECRET", ""),
            }
        if carrier == "aramex":
            return {
                "username": os.environ.get("ARAMEX_USERNAME", ""),
                "password": os.environ.get("ARAMEX_PASSWORD", ""),
                "account_number": os.environ.get("ARAMEX_ACCOUNT_NUMBER", ""),
                "pin": os.environ.get("ARAMEX_PIN", ""),
            }
        return {}

    @staticmethod
    def is_carrier_configured(carrier: str, tenant_id: int | None = None) -> bool:
        cfg = ShippingConfigService.get_carrier_config(carrier, tenant_id)
        carrier = (carrier or "").lower()
        if carrier == "dhl":
            return bool(cfg.get("api_key"))
        if carrier == "fedex":
            return bool(cfg.get("client_id") and cfg.get("client_secret"))
        if carrier == "aramex":
            return bool(cfg.get("username") and cfg.get("password") and cfg.get("account_number"))
        return False

    @staticmethod
    def get_sms_config(tenant_id: int | None = None) -> dict[str, Any]:
        try:
            from models.integration_settings import IntegrationSettings

            integration = IntegrationSettings.get_service_config("sms", tenant_id=tenant_id)
            cfg = integration.get_config() if integration else {}
            if cfg:
                return cfg
        except Exception:
            import logging

            logging.getLogger(__name__).debug("sms config read failed", exc_info=True)
        return {
            "provider": os.environ.get("SMS_PROVIDER", "twilio"),
            "account_sid": os.environ.get("TWILIO_ACCOUNT_SID", ""),
            "auth_token": os.environ.get("TWILIO_AUTH_TOKEN", ""),
            "from_number": os.environ.get("TWILIO_FROM_NUMBER", ""),
        }

    @staticmethod
    def is_sms_configured(tenant_id: int | None = None) -> bool:
        cfg = ShippingConfigService.get_sms_config(tenant_id)
        return bool(cfg.get("account_sid") and cfg.get("auth_token") and cfg.get("from_number"))

    @staticmethod
    def get_all_shipping_config(tenant_id: int | None = None) -> dict[str, Any]:
        """Return full shipping integration config (all carriers + sms)."""
        try:
            from models.integration_settings import IntegrationSettings

            integration = IntegrationSettings.get_service_config("shipping", tenant_id=tenant_id)
            cfg = integration.get_config() if integration else {}
            if cfg:
                return cfg
        except Exception:
            import logging

            logging.getLogger(__name__).debug("shipping config read failed", exc_info=True)
        return {}
