"""Shipping & SMS configuration — credentials stored encrypted via TenantSecretsService.

Sensitive values (API keys, secrets, passwords, tokens) are Fernet-encrypted
at rest in the tenant_secrets table. Non-sensitive config (enabled flag,
provider choice) lives in IntegrationSettings.config_data as plain JSON.

Frontend shows *whether* a secret is set, never its value.
"""

from __future__ import annotations

import os
from typing import Any


class ShippingConfigService:
    """Read/write shipping carrier + SMS credentials (encrypted)."""

    # Secret names per carrier
    CARRIER_SECRETS = {
        "dhl": ["dhl_api_key"],
        "fedex": ["fedex_client_id", "fedex_client_secret"],
        "aramex": ["aramex_username", "aramex_password", "aramex_account_number", "aramex_pin"],
    }

    @staticmethod
    def _tenant_id(tenant_id: int | None) -> int:
        if tenant_id is not None:
            return int(tenant_id)
        # Read path: tenant_id=0 means "no tenant secret" — falls back to env vars.
        # Never write tenant_id=0 to the DB (FK violation + cross-tenant leak).
        return 0

    @staticmethod
    def get_carrier_config(carrier: str, tenant_id: int | None = None) -> dict[str, Any]:
        carrier = (carrier or "").lower()
        tid = ShippingConfigService._tenant_id(tenant_id)
        cfg: dict[str, Any] = {}
        try:
            from services.tenant_secrets_service import TenantSecretsService

            for secret_name in ShippingConfigService.CARRIER_SECRETS.get(carrier, []):
                val = TenantSecretsService.get(tid, secret_name)
                # Map secret name to config key
                # Special mappings
                if secret_name == "dhl_api_key":
                    cfg["api_key"] = val or ""
                elif secret_name == "fedex_client_id":
                    cfg["client_id"] = val or ""
                elif secret_name == "fedex_client_secret":
                    cfg["client_secret"] = val or ""
                elif secret_name == "aramex_username":
                    cfg["username"] = val or ""
                elif secret_name == "aramex_password":
                    cfg["password"] = val or ""
                elif secret_name == "aramex_account_number":
                    cfg["account_number"] = val or ""
                elif secret_name == "aramex_pin":
                    cfg["pin"] = val or ""
        except Exception:
            import logging

            logging.getLogger(__name__).debug("shipping config error", exc_info=True)

        # Fall back to env vars if not set in DB
        if carrier == "dhl" and not cfg.get("api_key"):
            cfg["api_key"] = os.environ.get("DHL_API_KEY", "")
        if carrier == "fedex":
            if not cfg.get("client_id"):
                cfg["client_id"] = os.environ.get("FEDEX_CLIENT_ID", "")
            if not cfg.get("client_secret"):
                cfg["client_secret"] = os.environ.get("FEDEX_CLIENT_SECRET", "")
        if carrier == "aramex":
            if not cfg.get("username"):
                cfg["username"] = os.environ.get("ARAMEX_USERNAME", "")
            if not cfg.get("password"):
                cfg["password"] = os.environ.get("ARAMEX_PASSWORD", "")
            if not cfg.get("account_number"):
                cfg["account_number"] = os.environ.get("ARAMEX_ACCOUNT_NUMBER", "")
            if not cfg.get("pin"):
                cfg["pin"] = os.environ.get("ARAMEX_PIN", "")
        return cfg

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
    def set_carrier_secret(
        carrier: str, key: str, value: str, tenant_id: int | None = None, user_id: int | None = None
    ) -> None:
        if tenant_id is None:
            raise ValueError(
                "tenant_id is required — encrypted secrets must be stored per-tenant, never platform-global"
            )
        tid = ShippingConfigService._tenant_id(tenant_id)
        secret_name = f"{carrier}_{key}"
        if value:
            from services.tenant_secrets_service import TenantSecretsService

            TenantSecretsService.set(tid, secret_name, value, user_id=user_id)
        else:
            try:
                from services.tenant_secrets_service import TenantSecretsService

                TenantSecretsService.delete(tid, secret_name)
            except Exception:
                import logging

                logging.getLogger(__name__).debug("shipping config error", exc_info=True)

    @staticmethod
    def is_secret_set(carrier: str, key: str, tenant_id: int | None = None) -> bool:
        tid = ShippingConfigService._tenant_id(tenant_id)
        secret_name = f"{carrier}_{key}"
        try:
            from services.tenant_secrets_service import TenantSecretsService

            return TenantSecretsService.is_set(tid, secret_name)
        except Exception:
            return False

    @staticmethod
    def get_sms_config(tenant_id: int | None = None) -> dict[str, Any]:
        tid = ShippingConfigService._tenant_id(tenant_id)
        cfg: dict[str, Any] = {}
        try:
            from services.tenant_secrets_service import TenantSecretsService

            for name, key in [
                ("sms_account_sid", "account_sid"),
                ("sms_auth_token", "auth_token"),
                ("sms_from_number", "from_number"),
            ]:
                val = TenantSecretsService.get(tid, name)
                if val:
                    cfg[key] = val
        except Exception:
            import logging

            logging.getLogger(__name__).debug("shipping config error", exc_info=True)
        # Fall back to env vars
        if not cfg.get("account_sid"):
            cfg["account_sid"] = os.environ.get("TWILIO_ACCOUNT_SID", "")
        if not cfg.get("auth_token"):
            cfg["auth_token"] = os.environ.get("TWILIO_AUTH_TOKEN", "")
        if not cfg.get("from_number"):
            cfg["from_number"] = os.environ.get("TWILIO_FROM_NUMBER", "")
        # provider from IntegrationSettings (non-sensitive)
        try:
            from models.integration_settings import IntegrationSettings

            integration = IntegrationSettings.get_service_config("sms", tenant_id=tenant_id)
            icfg = integration.get_config() if integration else {}
            if icfg.get("provider"):
                cfg["provider"] = icfg["provider"]
        except Exception:
            import logging

            logging.getLogger(__name__).debug("shipping config error", exc_info=True)
        if not cfg.get("provider"):
            cfg["provider"] = os.environ.get("SMS_PROVIDER", "twilio")
        return cfg

    @staticmethod
    def is_sms_configured(tenant_id: int | None = None) -> bool:
        cfg = ShippingConfigService.get_sms_config(tenant_id)
        return bool(cfg.get("account_sid") and cfg.get("auth_token") and cfg.get("from_number"))

    @staticmethod
    def set_sms_secret(name: str, value: str, tenant_id: int | None = None, user_id: int | None = None) -> None:
        if tenant_id is None:
            raise ValueError(
                "tenant_id is required — encrypted secrets must be stored per-tenant, never platform-global"
            )
        tid = ShippingConfigService._tenant_id(tenant_id)
        if value:
            from services.tenant_secrets_service import TenantSecretsService

            TenantSecretsService.set(tid, name, value, user_id=user_id)
        else:
            try:
                from services.tenant_secrets_service import TenantSecretsService

                TenantSecretsService.delete(tid, name)
            except Exception:
                import logging

                logging.getLogger(__name__).debug("shipping config error", exc_info=True)

    @staticmethod
    def is_sms_secret_set(name: str, tenant_id: int | None = None) -> bool:
        tid = ShippingConfigService._tenant_id(tenant_id)
        try:
            from services.tenant_secrets_service import TenantSecretsService

            return TenantSecretsService.is_set(tid, name)
        except Exception:
            return False
