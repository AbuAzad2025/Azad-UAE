"""Encrypted carrier/SMS configuration: all providers, fallbacks and guards."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

SECRETS = "services.tenant_secrets_service.TenantSecretsService"


def _get(values):
    return patch(f"{SECRETS}.get", side_effect=lambda tid, name: values.get(name, ""))


class TestCarrierConfig:
    def test_dhl_from_secret(self):
        from services.shipping_config_service import ShippingConfigService

        with _get({"dhl_api_key": "KEY"}):
            cfg = ShippingConfigService.get_carrier_config("DHL", 1)
            assert ShippingConfigService.is_carrier_configured("dhl", 1) is True
        assert cfg["api_key"] == "KEY"

    def test_dhl_env_fallback(self, monkeypatch):
        from services.shipping_config_service import ShippingConfigService

        monkeypatch.setenv("DHL_API_KEY", "ENVKEY")
        with _get({}):
            cfg = ShippingConfigService.get_carrier_config("dhl", 1)
        assert cfg["api_key"] == "ENVKEY"

    def test_fedex_all_fields(self):
        from services.shipping_config_service import ShippingConfigService

        values = {"fedex_client_id": "id", "fedex_client_secret": "secret"}
        with _get(values):
            cfg = ShippingConfigService.get_carrier_config("fedex", 1)
            assert ShippingConfigService.is_carrier_configured("fedex", 1) is True
        assert cfg == {"client_id": "id", "client_secret": "secret"}

    def test_fedex_env_fallback(self, monkeypatch):
        from services.shipping_config_service import ShippingConfigService

        monkeypatch.setenv("FEDEX_CLIENT_ID", "env-id")
        monkeypatch.setenv("FEDEX_CLIENT_SECRET", "env-secret")
        with _get({}):
            cfg = ShippingConfigService.get_carrier_config("fedex")
        assert cfg == {"client_id": "env-id", "client_secret": "env-secret"}

    def test_aramex_all_fields(self):
        from services.shipping_config_service import ShippingConfigService

        values = {
            "aramex_username": "u",
            "aramex_password": "p",
            "aramex_account_number": "a",
            "aramex_pin": "pin",
        }
        with _get(values):
            cfg = ShippingConfigService.get_carrier_config("aramex", 1)
            assert ShippingConfigService.is_carrier_configured("aramex", 1) is True
        assert cfg == {"username": "u", "password": "p", "account_number": "a", "pin": "pin"}

    def test_aramex_env_fallback(self, monkeypatch):
        from services.shipping_config_service import ShippingConfigService

        for key, value in (
            ("ARAMEX_USERNAME", "u"),
            ("ARAMEX_PASSWORD", "p"),
            ("ARAMEX_ACCOUNT_NUMBER", "a"),
            ("ARAMEX_PIN", "pin"),
        ):
            monkeypatch.setenv(key, value)
        with _get({}):
            cfg = ShippingConfigService.get_carrier_config("aramex")
        assert cfg == {"username": "u", "password": "p", "account_number": "a", "pin": "pin"}

    def test_unknown_carrier_is_unconfigured(self):
        from services.shipping_config_service import ShippingConfigService

        with _get({}):
            assert ShippingConfigService.get_carrier_config("unknown", 1) == {}
        assert ShippingConfigService.is_carrier_configured("unknown", 1) is False

    def test_secret_backend_error_is_best_effort(self):
        from services.shipping_config_service import ShippingConfigService

        with patch(f"{SECRETS}.get", side_effect=RuntimeError("vault down")):
            cfg = ShippingConfigService.get_carrier_config("dhl", 1)
        assert cfg == {"api_key": ""}


class TestCarrierSecretWrites:
    def test_tenant_id_required(self):
        from services.shipping_config_service import ShippingConfigService

        with pytest.raises(ValueError, match="tenant_id is required"):
            ShippingConfigService.set_carrier_secret("dhl", "api_key", "k")
        with pytest.raises(ValueError, match="tenant_id is required"):
            ShippingConfigService.set_sms_secret("sms_auth_token", "t")

    def test_set_and_delete(self):
        from services.shipping_config_service import ShippingConfigService

        with patch(f"{SECRETS}.set") as set_secret, patch(f"{SECRETS}.delete") as delete:
            ShippingConfigService.set_carrier_secret("dhl", "api_key", "k", tenant_id=1, user_id=7)
            ShippingConfigService.set_carrier_secret("dhl", "api_key", "", tenant_id=1)
        set_secret.assert_called_once_with(1, "dhl_api_key", "k", user_id=7)
        delete.assert_called_once_with(1, "dhl_api_key")

    def test_delete_error_is_swallowed(self):
        from services.shipping_config_service import ShippingConfigService

        with patch(f"{SECRETS}.delete", side_effect=RuntimeError("vault down")):
            ShippingConfigService.set_carrier_secret("dhl", "api_key", "", tenant_id=1)
        with patch(f"{SECRETS}.delete", side_effect=RuntimeError("vault down")):
            ShippingConfigService.set_sms_secret("sms_auth_token", "", tenant_id=1)

    def test_is_secret_set_and_error_fallback(self):
        from services.shipping_config_service import ShippingConfigService

        with patch(f"{SECRETS}.is_set", return_value=True):
            assert ShippingConfigService.is_secret_set("dhl", "api_key", 1) is True
        with patch(f"{SECRETS}.is_set", side_effect=RuntimeError("vault down")):
            assert ShippingConfigService.is_secret_set("dhl", "api_key", 1) is False
        with patch(f"{SECRETS}.is_set", return_value=True):
            assert ShippingConfigService.is_sms_secret_set("sms_auth_token", 1) is True
        with patch(f"{SECRETS}.is_set", side_effect=RuntimeError("vault down")):
            assert ShippingConfigService.is_sms_secret_set("sms_auth_token", 1) is False


class TestSmsConfig:
    def test_from_secrets(self):
        from services.shipping_config_service import ShippingConfigService

        values = {"sms_account_sid": "sid", "sms_auth_token": "tok", "sms_from_number": "+9715"}
        with _get(values):
            cfg = ShippingConfigService.get_sms_config(1)
            assert ShippingConfigService.is_sms_configured(1) is True
        assert cfg["account_sid"] == "sid"
        assert cfg["auth_token"] == "tok"
        assert cfg["from_number"] == "+9715"

    def test_env_fallback_and_default_provider(self, monkeypatch):
        from services.shipping_config_service import ShippingConfigService

        for key, value in (
            ("TWILIO_ACCOUNT_SID", "sid"),
            ("TWILIO_AUTH_TOKEN", "tok"),
            ("TWILIO_FROM_NUMBER", "+9715"),
        ):
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("SMS_PROVIDER", raising=False)
        integration = MagicMock()
        integration.get_config.return_value = {}
        with (
            _get({}),
            patch(
                "models.integration_settings.IntegrationSettings.get_service_config",
                return_value=integration,
            ),
        ):
            cfg = ShippingConfigService.get_sms_config(1)
        assert cfg["provider"] == "twilio"

    def test_provider_from_integration_settings(self, monkeypatch):
        from services.shipping_config_service import ShippingConfigService

        integration = MagicMock()
        integration.get_config.return_value = {"provider": "custom"}
        with (
            _get({}),
            patch(
                "models.integration_settings.IntegrationSettings.get_service_config",
                return_value=integration,
            ),
        ):
            cfg = ShippingConfigService.get_sms_config(1)
        assert cfg["provider"] == "custom"

    def test_no_integration_row_uses_default(self, monkeypatch):
        from services.shipping_config_service import ShippingConfigService

        monkeypatch.setenv("SMS_PROVIDER", "custom-env")
        with (
            _get({}),
            patch("models.integration_settings.IntegrationSettings.get_service_config", return_value=None),
        ):
            cfg = ShippingConfigService.get_sms_config(1)
        assert cfg["provider"] == "custom-env"

    def test_integration_error_is_best_effort(self, monkeypatch):
        from services.shipping_config_service import ShippingConfigService

        monkeypatch.delenv("SMS_PROVIDER", raising=False)
        with (
            _get({}),
            patch(
                "models.integration_settings.IntegrationSettings.get_service_config",
                side_effect=RuntimeError("db down"),
            ),
        ):
            cfg = ShippingConfigService.get_sms_config(1)
        assert cfg["provider"] == "twilio"

    def test_secret_error_is_best_effort(self):
        from services.shipping_config_service import ShippingConfigService

        with patch(f"{SECRETS}.get", side_effect=RuntimeError("vault down")):
            cfg = ShippingConfigService.get_sms_config(1)
        assert cfg["account_sid"] == ""

    def test_set_and_delete_sms_secret(self):
        from services.shipping_config_service import ShippingConfigService

        with patch(f"{SECRETS}.set") as set_secret, patch(f"{SECRETS}.delete") as delete:
            ShippingConfigService.set_sms_secret("sms_auth_token", "tok", tenant_id=1, user_id=3)
            ShippingConfigService.set_sms_secret("sms_auth_token", "", tenant_id=1)
        set_secret.assert_called_once_with(1, "sms_auth_token", "tok", user_id=3)
        delete.assert_called_once_with(1, "sms_auth_token")
