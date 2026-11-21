"""Public tracking webhook and page branches absent from the public route suites."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def carrier_secret(app):
    app.config["CARRIER_WEBHOOK_SECRET"] = "shared-secret"
    return "shared-secret"


def _shipment_query(found):
    query = MagicMock()
    query.filter_by.return_value.first.return_value = found
    return query


class TestCarrierWebhook:
    def test_missing_secret_is_401(self, client, app):
        app.config["CARRIER_WEBHOOK_SECRET"] = ""
        resp = client.post("/webhooks/carrier/dhl", json={"tracking_number": "T1"})
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "unauthorized"

    def test_wrong_secret_is_401(self, client, carrier_secret):
        resp = client.post(
            "/webhooks/carrier/dhl",
            json={"tracking_number": "T1"},
            headers={"X-Webhook-Secret": "wrong"},
        )
        assert resp.status_code == 401

    def test_missing_tracking_number_is_400(self, client, carrier_secret):
        resp = client.post(
            "/webhooks/carrier/dhl",
            json={},
            headers={"X-Webhook-Secret": carrier_secret},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "no tracking number"

    def test_unknown_shipment_is_404(self, client, carrier_secret):
        with patch("models.shipment.Shipment.query", _shipment_query(None)):
            resp = client.post(
                "/webhooks/carrier/dhl",
                json={"trackingNumber": "T1"},
                headers={"X-Webhook-Secret": carrier_secret},
            )
        assert resp.status_code == 404

    def test_successful_sync(self, client, carrier_secret):
        shipment = MagicMock()
        shipment.tenant_id = 4
        shipment.status = "delivered"
        with (
            patch("models.shipment.Shipment.query", _shipment_query(shipment)),
            patch(
                "services.carrier_tracking_service.CarrierTrackingService.sync_shipment",
                return_value={"success": True},
            ),
            patch("extensions.db.session.flush"),
        ):
            resp = client.post(
                "/webhooks/carrier/dhl",
                json={"TrackingResults": [{"Key": "T1"}]},
                headers={"X-Webhook-Secret": carrier_secret},
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert resp.get_json()["status"] == "delivered"

    def test_sync_failure_is_500(self, client, carrier_secret):
        shipment = MagicMock()
        shipment.tenant_id = 4
        with (
            patch("models.shipment.Shipment.query", _shipment_query(shipment)),
            patch(
                "services.carrier_tracking_service.CarrierTrackingService.sync_shipment",
                side_effect=RuntimeError("carrier down"),
            ),
        ):
            resp = client.post(
                "/webhooks/carrier/dhl",
                json={"tracking_no": "T1"},
                headers={"X-Webhook-Secret": carrier_secret},
            )
        assert resp.status_code == 500
        assert "carrier down" not in resp.get_data(as_text=True)

    def test_nested_tracking_number(self, client, carrier_secret):
        shipment = MagicMock()
        shipment.tenant_id = 4
        shipment.status = "in_transit"
        with (
            patch("models.shipment.Shipment.query", _shipment_query(shipment)),
            patch(
                "services.carrier_tracking_service.CarrierTrackingService.sync_shipment",
                return_value={"success": True},
            ),
            patch("extensions.db.session.flush"),
        ):
            resp = client.post(
                "/webhooks/carrier/dhl",
                json={"shipment": {"trackingNumber": "T1"}},
                headers={"X-Webhook-Secret": carrier_secret},
            )
        assert resp.status_code == 200


class TestTrackShipmentPage:
    def test_blank_tracking_number_404(self, client):
        resp = client.get("/track/   ")
        assert resp.status_code == 404

    def test_unknown_shipment_404(self, client):
        with patch("models.shipment.Shipment.query", _shipment_query(None)):
            resp = client.get("/track/T-404")
        assert resp.status_code == 404

    def test_carrier_error_is_best_effort(self, client):
        shipment = MagicMock()
        shipment.tenant_id = 4
        with (
            patch("models.shipment.Shipment.query", _shipment_query(shipment)),
            patch(
                "services.carrier_tracking_service.CarrierTrackingService.sync_shipment",
                side_effect=RuntimeError("carrier down"),
            ),
            patch("routes.public.render_template", return_value="ok") as render,
        ):
            resp = client.get("/track/T-1")
        assert resp.status_code == 200
        assert render.call_args.kwargs["carrier_result"] is None

    def test_carrier_events_are_passed_to_template(self, client):
        shipment = MagicMock()
        shipment.tenant_id = 4
        events = [{"status": "delivered"}]
        with (
            patch("models.shipment.Shipment.query", _shipment_query(shipment)),
            patch(
                "services.carrier_tracking_service.CarrierTrackingService.sync_shipment",
                return_value={"success": True, "events": events},
            ),
            patch("routes.public.render_template", return_value="ok") as render,
        ):
            resp = client.get("/track/T-2")
        assert resp.status_code == 200
        assert render.call_args.kwargs["events"] == events
