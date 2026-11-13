"""Tests for WhatsAppService.send_shipment_status."""


class TestWhatsAppShipmentStatus:
    def test_disabled_returns_error(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_API_KEY", raising=False)
        from services.whatsapp_service import WhatsAppService

        res = WhatsAppService.send_shipment_status(
            phone="971501234567",
            tracking_number="TRK-1",
            status="in_transit",
            carrier_name="DHL",
        )
        assert res["success"] is False
        assert "not configured" in res["error"]

    def test_missing_phone_returns_error(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_API_KEY", "test-key")
        monkeypatch.setenv("WHATSAPP_INSTANCE_ID", "inst-1")
        from services.whatsapp_service import WhatsAppService

        res = WhatsAppService.send_shipment_status(
            phone="",
            tracking_number="TRK-1",
            status="in_transit",
        )
        assert res["success"] is False
        assert "phone required" in res["error"]
