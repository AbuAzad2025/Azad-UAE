"""Tests for public shipment tracking route."""

import pytest


@pytest.fixture
def tracking_client(app):
    return app.test_client()


class TestPublicTracking:
    def test_track_unknown_returns_404(self, tracking_client):
        resp = tracking_client.get("/track/NONEXISTENT123")
        assert resp.status_code == 404

    def test_track_existing_shipment(self, tracking_client, db_session):
        from models.shipment import Shipment

        s = Shipment(
            tenant_id=1,
            source_type="delivery",
            source_id=0,
            tracking_number="TRK-TEST-001",
            carrier_name="DHL",
            carrier_code="dhl",
            status="in_transit",
            destination_name="Test Site",
            recipient_phone="971501234567",
        )
        db_session.add(s)
        db_session.flush()

        resp = tracking_client.get("/track/TRK-TEST-001")
        assert resp.status_code == 200
        assert b"TRK-TEST-001" in resp.data
        assert b"DHL" in resp.data
