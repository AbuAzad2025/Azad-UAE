"""Carrier tracking integration (DHL, FedEx, Aramex).

Provides a unified interface to query external carrier APIs for shipment
tracking events and normalize them into a common structure. Falls back
gracefully when API credentials are not configured (returns
``{"success": False, "error": "..."}``).

Environment variables:
- DHL_API_KEY
- FEDEX_CLIENT_ID, FEDEX_CLIENT_SECRET
- ARAMEX_USERNAME, ARAMEX_PASSWORD, ARAMEX_ACCOUNT_NUMBER, ARAMEX_PIN
"""

from __future__ import annotations

import os
from datetime import UTC
from typing import Any

import requests

from services.shipping_config_service import ShippingConfigService


class CarrierTrackingService:
    """Unified carrier tracking adapter."""

    SUPPORTED_CARRIERS = ("dhl", "fedex", "aramex", "other")

    @staticmethod
    def is_configured(carrier: str, tenant_id: int | None = None) -> bool:
        return ShippingConfigService.is_carrier_configured(carrier, tenant_id)

    @staticmethod
    def track(carrier: str, tracking_number: str) -> dict[str, Any]:
        """Query the carrier API and return normalized tracking data.

        Returns a dict with keys: success, carrier, tracking_number,
        status, estimated_delivery, events (list of {timestamp, location,
        description, status}), error (on failure).
        """
        carrier = (carrier or "").lower().strip()
        tracking_number = (tracking_number or "").strip()
        if not tracking_number:
            return {"success": False, "error": "tracking_number required"}
        if carrier not in CarrierTrackingService.SUPPORTED_CARRIERS:
            return {"success": False, "error": f"unsupported carrier: {carrier}"}

        if carrier == "dhl":
            return CarrierTrackingService._track_dhl(tracking_number)
        if carrier == "fedex":
            return CarrierTrackingService._track_fedex(tracking_number)
        if carrier == "aramex":
            return CarrierTrackingService._track_aramex(tracking_number)
        return {
            "success": False,
            "error": "manual carrier — no API integration",
            "carrier": carrier,
            "tracking_number": tracking_number,
            "status": "unknown",
            "events": [],
        }

    # ── DHL ──────────────────────────────────────────────────────────────
    @staticmethod
    def _track_dhl(tracking_number: str) -> dict[str, Any]:
        cfg = ShippingConfigService.get_carrier_config("dhl")
        api_key = cfg.get("api_key") or os.environ.get("DHL_API_KEY")
        if not api_key:
            return {
                "success": False,
                "error": "DHL_API_KEY not configured",
                "carrier": "dhl",
                "tracking_number": tracking_number,
                "events": [],
            }
        try:
            url = f"https://api-eu.dhl.com/track/shipments?trackingNumber={tracking_number}"
            resp = requests.get(url, headers={"DHL-API-Key": api_key}, timeout=15)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"DHL HTTP {resp.status_code}",
                    "carrier": "dhl",
                    "tracking_number": tracking_number,
                    "events": [],
                }
            data = resp.json()
            shipments = data.get("shipments") or []
            if not shipments:
                return {
                    "success": False,
                    "error": "no shipment data",
                    "carrier": "dhl",
                    "tracking_number": tracking_number,
                    "events": [],
                }
            sh = shipments[0]
            events = []
            for ev in sh.get("events") or []:
                events.append(
                    {
                        "timestamp": ev.get("timestamp"),
                        "location": (ev.get("location") or {}).get("address", {}).get("addressLocality"),
                        "description": ev.get("description") or ev.get("status"),
                        "status": ev.get("status"),
                    }
                )
            status = (sh.get("status") or {}).get("statusCode") or "unknown"
            est = (sh.get("estimatedTimeOfDelivery") or {}).get("estimatedTimeOfDelivery")
            return {
                "success": True,
                "carrier": "dhl",
                "tracking_number": tracking_number,
                "status": status,
                "estimated_delivery": est,
                "events": events,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "carrier": "dhl",
                "tracking_number": tracking_number,
                "events": [],
            }

    # ── FedEx ─────────────────────────────────────────────────────────────
    @staticmethod
    def _fedex_token() -> str | None:
        cfg = ShippingConfigService.get_carrier_config("fedex")
        client_id = cfg.get("client_id") or os.environ.get("FEDEX_CLIENT_ID")
        client_secret = cfg.get("client_secret") or os.environ.get("FEDEX_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None
        try:
            resp = requests.post(
                "https://apis.fedex.com/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("access_token")
        except Exception:
            import logging

            logging.getLogger(__name__).debug("fedex token fetch failed", exc_info=True)
        return None

    @staticmethod
    def _track_fedex(tracking_number: str) -> dict[str, Any]:
        token = CarrierTrackingService._fedex_token()
        if not token:
            return {
                "success": False,
                "error": "FedEx credentials not configured or auth failed",
                "carrier": "fedex",
                "tracking_number": tracking_number,
                "events": [],
            }
        try:
            url = "https://apis.fedex.com/track/v1/trackingnumbers"
            payload = {
                "includeDetailedScans": True,
                "trackingInfo": [{"trackingNumberInfo": {"trackingNumber": tracking_number}}],
            }
            resp = requests.post(
                url,
                json=payload,  # type: ignore[arg-type]
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"FedEx HTTP {resp.status_code}",
                    "carrier": "fedex",
                    "tracking_number": tracking_number,
                    "events": [],
                }
            data = resp.json()
            results = (data.get("output") or {}).get("completeTrackResults") or []
            if not results:
                return {
                    "success": False,
                    "error": "no tracking data",
                    "carrier": "fedex",
                    "tracking_number": tracking_number,
                    "events": [],
                }
            track = (results[0].get("trackResults") or [{}])[0]
            events = []
            for ev in track.get("scanEvents") or []:
                events.append(
                    {
                        "timestamp": ev.get("date"),
                        "location": (ev.get("scanLocation") or {}).get("city"),
                        "description": ev.get("eventDescription"),
                        "status": ev.get("eventType"),
                    }
                )
            status = (track.get("latestStatusDetail") or {}).get("description") or "unknown"
            est = (track.get("estimatedDeliveryTimeWindow") or {}).get("window", {}).get("ends")
            return {
                "success": True,
                "carrier": "fedex",
                "tracking_number": tracking_number,
                "status": status,
                "estimated_delivery": est,
                "events": events,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "carrier": "fedex",
                "tracking_number": tracking_number,
                "events": [],
            }

    # ── Aramex ────────────────────────────────────────────────────────────
    @staticmethod
    def _track_aramex(tracking_number: str) -> dict[str, Any]:
        cfg = ShippingConfigService.get_carrier_config("aramex")
        username = cfg.get("username") or os.environ.get("ARAMEX_USERNAME")
        password = cfg.get("password") or os.environ.get("ARAMEX_PASSWORD")
        account = cfg.get("account_number") or os.environ.get("ARAMEX_ACCOUNT_NUMBER")
        pin = cfg.get("pin") or os.environ.get("ARAMEX_PIN")
        if not all([username, password, account]):
            return {
                "success": False,
                "error": "Aramex credentials not configured",
                "carrier": "aramex",
                "tracking_number": tracking_number,
                "events": [],
            }
        try:
            url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
            payload = {
                "ClientInfo": {
                    "UserName": username,
                    "Password": password,
                    "Version": "v1.0",
                    "AccountNumber": account,
                    "AccountPin": pin,
                    "AccountEntity": "AMM",
                    "AccountCountryCode": "JO",
                },
                "Shipments": [tracking_number],
            }
            resp = requests.post(url, json=payload, timeout=15)  # type: ignore[arg-type]
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Aramex HTTP {resp.status_code}",
                    "carrier": "aramex",
                    "tracking_number": tracking_number,
                    "events": [],
                }
            data = resp.json()
            results = data.get("TrackingResults") or []
            events = []
            status = "unknown"
            for r in results:
                for h in r.get("Value") or []:
                    events.append(
                        {
                            "timestamp": h.get("UpdateDateTime"),
                            "location": h.get("Location"),
                            "description": h.get("UpdateDescription"),
                            "status": h.get("UpdateCode"),
                        }
                    )
                if r.get("Key"):
                    status = (r.get("Value") or [{}])[-1].get("UpdateDescription", status) if r.get("Value") else status
            return {
                "success": True,
                "carrier": "aramex",
                "tracking_number": tracking_number,
                "status": status,
                "estimated_delivery": None,
                "events": events,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "carrier": "aramex",
                "tracking_number": tracking_number,
                "events": [],
            }

    @staticmethod
    def sync_shipment(shipment) -> dict[str, Any]:
        """Query the carrier for the shipment's tracking number and update status.

        Returns the carrier result dict. Does NOT commit — caller manages transaction.
        """
        carrier = getattr(shipment, "carrier_code", None) or "other"
        tn = getattr(shipment, "tracking_number", None)
        if not tn:
            return {"success": False, "error": "no tracking_number on shipment", "events": []}
        result = CarrierTrackingService.track(carrier, tn)
        if result.get("success"):
            # Map carrier status to internal status (best-effort)
            ext_status = (result.get("status") or "").lower()
            mapping = {
                "delivered": "delivered",
                "out for delivery": "in_transit",
                "in transit": "in_transit",
                "picked up": "in_transit",
                "arrived": "arrived",
            }
            for key, val in mapping.items():
                if key in ext_status:
                    if getattr(shipment, "status", None) != val:
                        shipment.status = val
                        if val == "delivered":
                            from datetime import datetime

                            shipment.actual_delivery = datetime.now(UTC)
                    break
        return result
