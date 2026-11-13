"""SMS messaging service (Twilio). Configurable via IntegrationSettings or env vars."""

from __future__ import annotations

import os

import requests


class SMSService:
    @staticmethod
    def is_enabled(tenant_id: int | None = None) -> bool:
        from services.shipping_config_service import ShippingConfigService

        cfg = ShippingConfigService.get_sms_config(tenant_id)
        return bool(cfg.get("account_sid") and cfg.get("auth_token") and cfg.get("from_number"))

    @staticmethod
    def send(phone: str, message: str, tenant_id: int | None = None) -> dict:
        from services.shipping_config_service import ShippingConfigService

        cfg = ShippingConfigService.get_sms_config(tenant_id)
        account_sid = cfg.get("account_sid") or os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = cfg.get("auth_token") or os.environ.get("TWILIO_AUTH_TOKEN")
        from_number = cfg.get("from_number") or os.environ.get("TWILIO_FROM_NUMBER")

        if not all([account_sid, auth_token, from_number]):
            return {"success": False, "error": "SMS not configured"}
        if not phone:
            return {"success": False, "error": "phone required"}

        phone_clean = phone.replace(" ", "").replace("-", "")
        if not phone_clean.startswith("+"):
            phone_clean = "+" + phone_clean

        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            resp = requests.post(
                url,
                data={"From": from_number, "To": phone_clean, "Body": message},
                auth=(account_sid, auth_token),
                timeout=15,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {"success": True, "message_id": data.get("sid"), "phone": phone_clean}
            return {"success": False, "error": f"Twilio HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def send_shipment_status(phone: str, tracking_number: str, status: str, tenant_id: int | None = None) -> dict:
        status_labels = {
            "pending": "Pending",
            "draft": "Draft",
            "in_transit": "In Transit",
            "arrived": "Arrived",
            "selling": "Selling",
            "closed": "Closed",
            "cancelled": "Cancelled",
            "delivered": "Delivered",
        }
        label = status_labels.get(status, status)
        tracking_part = f" Tracking: {tracking_number}" if tracking_number else ""
        message = f"Shipment update: {label}.{tracking_part}"
        return SMSService.send(phone, message, tenant_id=tenant_id)
