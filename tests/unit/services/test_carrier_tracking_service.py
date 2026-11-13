"""Tests for CarrierTrackingService."""

from services.carrier_tracking_service import CarrierTrackingService


class TestCarrierTrackingService:
    def test_supported_carriers(self):
        assert "dhl" in CarrierTrackingService.SUPPORTED_CARRIERS
        assert "fedex" in CarrierTrackingService.SUPPORTED_CARRIERS
        assert "aramex" in CarrierTrackingService.SUPPORTED_CARRIERS

    def test_is_configured_false_without_env(self, monkeypatch):
        for var in (
            "DHL_API_KEY",
            "FEDEX_CLIENT_ID",
            "FEDEX_CLIENT_SECRET",
            "ARAMEX_USERNAME",
            "ARAMEX_PASSWORD",
            "ARAMEX_ACCOUNT_NUMBER",
        ):
            monkeypatch.delenv(var, raising=False)
        assert CarrierTrackingService.is_configured("dhl") is False
        assert CarrierTrackingService.is_configured("fedex") is False
        assert CarrierTrackingService.is_configured("aramex") is False

    def test_track_requires_tracking_number(self):
        res = CarrierTrackingService.track("dhl", "")
        assert res["success"] is False
        assert "tracking_number required" in res["error"]

    def test_track_unsupported_carrier(self):
        res = CarrierTrackingService.track("ups", "123")
        assert res["success"] is False
        assert "unsupported carrier" in res["error"]

    def test_track_dhl_not_configured(self, monkeypatch):
        monkeypatch.delenv("DHL_API_KEY", raising=False)
        res = CarrierTrackingService.track("dhl", "123456")
        assert res["success"] is False
        assert "not configured" in res["error"]

    def test_track_fedex_not_configured(self, monkeypatch):
        monkeypatch.delenv("FEDEX_CLIENT_ID", raising=False)
        monkeypatch.delenv("FEDEX_CLIENT_SECRET", raising=False)
        res = CarrierTrackingService.track("fedex", "123456")
        assert res["success"] is False

    def test_track_aramex_not_configured(self, monkeypatch):
        monkeypatch.delenv("ARAMEX_USERNAME", raising=False)
        res = CarrierTrackingService.track("aramex", "123456")
        assert res["success"] is False

    def test_track_other_returns_manual(self):
        res = CarrierTrackingService.track("other", "ABC123")
        assert res["success"] is False
        assert res["carrier"] == "other"
        assert res["events"] == []

    def test_sync_shipment_no_tracking_number(self):
        class FakeShipment:
            carrier_code = "dhl"
            tracking_number = None
            status = "pending"
            recipient_phone = None

        res = CarrierTrackingService.sync_shipment(FakeShipment())
        assert res["success"] is False
        assert "no tracking_number" in res["error"]
