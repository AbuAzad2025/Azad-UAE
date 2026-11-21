"""SMS service branches: configuration, normalization, HTTP and status labels."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

CONFIG = {"account_sid": "AC1", "auth_token": "tok", "from_number": "+97150000000"}


def _config(value):
    return patch("services.shipping_config_service.ShippingConfigService.get_sms_config", return_value=value)


def _post(status=201, body=None, side_effect=None):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "server said no"
    resp.json.return_value = body if body is not None else {"sid": "SM1"}
    if side_effect:
        return patch("services.sms_service.requests.post", side_effect=side_effect)
    return patch("services.sms_service.requests.post", return_value=resp)


class TestSMSService:
    def test_is_enabled_requires_all_credentials(self):
        from services.sms_service import SMSService

        with _config(CONFIG):
            assert SMSService.is_enabled(1) is True
        with _config({"account_sid": "AC1"}):
            assert SMSService.is_enabled(1) is False

    def test_missing_config_is_refused(self):
        from services.sms_service import SMSService

        with _config({}):
            assert SMSService.send("+971501234567", "hi", tenant_id=1) == {
                "success": False,
                "error": "SMS not configured",
            }

    def test_missing_phone_is_refused(self):
        from services.sms_service import SMSService

        with _config(CONFIG):
            assert SMSService.send("", "hi", tenant_id=1) == {"success": False, "error": "phone required"}

    @pytest.mark.parametrize("phone,normalized", [("050 123-4567", "+0501234567"), ("+971501234567", "+971501234567")])
    def test_phone_is_normalized(self, phone, normalized):
        from services.sms_service import SMSService

        with _config(CONFIG), _post() as post:
            result = SMSService.send(phone, "hi", tenant_id=1)
        assert result["success"] is True
        assert result["phone"] == normalized
        assert result["message_id"] == "SM1"
        assert post.call_args.kwargs["data"]["To"] == normalized

    def test_http_error_is_reported(self):
        from services.sms_service import SMSService

        with _config(CONFIG), _post(status=422):
            result = SMSService.send("+971501234567", "hi", tenant_id=1)
        assert result["success"] is False
        assert "422" in result["error"]
        assert "server said no" in result["error"]

    def test_network_error_is_reported(self):
        from services.sms_service import SMSService

        with _config(CONFIG), _post(side_effect=RuntimeError("offline")):
            result = SMSService.send("+971501234567", "hi", tenant_id=1)
        assert result == {"success": False, "error": "offline"}

    def test_env_fallback_when_config_is_partial(self, monkeypatch):
        from services.sms_service import SMSService

        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACENV")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
        monkeypatch.setenv("TWILIO_FROM_NUMBER", "+97150000000")
        with _config({}), _post() as post:
            result = SMSService.send("+971501234567", "hi", tenant_id=1)
        assert result["success"] is True
        assert "ACENV" in post.call_args.args[0]

    @pytest.mark.parametrize(
        "status,label",
        [
            ("pending", "Pending"),
            ("draft", "Draft"),
            ("in_transit", "In Transit"),
            ("arrived", "Arrived"),
            ("selling", "Selling"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
            ("delivered", "Delivered"),
            ("custom", "custom"),
        ],
    )
    def test_shipment_status_message(self, status, label):
        from services.sms_service import SMSService

        with patch.object(SMSService, "send", return_value={"success": True}) as send:
            result = SMSService.send_shipment_status("+971501234567", "TRK-1", status, tenant_id=1)
        assert result == {"success": True}
        assert send.call_args.args[1] == f"Shipment update: {label}. Tracking: TRK-1"

    def test_shipment_status_without_tracking_number(self):
        from services.sms_service import SMSService

        with patch.object(SMSService, "send", return_value={"success": True}) as send:
            SMSService.send_shipment_status("+971501234567", "", "delivered", tenant_id=1)
        assert send.call_args.args[1] == "Shipment update: Delivered."
