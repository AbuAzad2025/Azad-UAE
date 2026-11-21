"""Coverage for service-layer branches absent from the existing suites.

Targets (see the combined coverage report):
  * ``services/store_whatsapp_service.py`` — ``build_message`` (39-96),
    ``whatsapp_url`` (109-115), ``generate_provisional_number`` (123-143)
    and ``send_message`` (161-208).
  * ``services/carrier_tracking_service.py`` — ``_track_dhl`` (77-120),
    ``_fedex_token`` (136-152), ``_track_fedex`` (165-217),
    ``_track_aramex`` (241-289) and the status mapping in ``sync_shipment``
    (310-326).

HTTP clients, the shipping-config service boundary and the DB session are
patched at the service boundary; no production code is touched.
"""

from __future__ import annotations

import re
import sys
from unittest.mock import MagicMock

import pytest

from services.carrier_tracking_service import CarrierTrackingService
from services.store_whatsapp_service import StoreWhatsAppService


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    """Keep host credentials from changing which provider branch is taken."""
    for key in (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_WHATSAPP_FROM",
        "WHATSAPP_API_URL",
        "WHATSAPP_API_TOKEN",
        "DHL_API_KEY",
        "FEDEX_CLIENT_ID",
        "FEDEX_CLIENT_SECRET",
        "ARAMEX_USERNAME",
        "ARAMEX_PASSWORD",
        "ARAMEX_ACCOUNT_NUMBER",
        "ARAMEX_PIN",
    ):
        monkeypatch.delenv(key, raising=False)


# ─────────────────────────── store_whatsapp_service ───────────────────────────


def _provisional(**over):
    p = MagicMock()
    p.provisional_number = "PRV-1-20260101-001"
    p.created_at.strftime.return_value = "2026-01-01 09:30"
    p.customer_name = "John"
    p.customer_phone = "+971501234567"
    p.customer_email = "john@example.com"
    p.cart_json = [
        {
            "product_id": 5,
            "product_name": "Widget",
            "quantity": 2,
            "unit_price": "10.00",
            "line_total": "20.00",
        },
        # no product_name — exercises the "منتج #id" fallback (line 60)
        {"product_id": 6, "quantity": 1, "unit_price": "5.00", "line_total": "5.00"},
    ]
    p.currency_code = "AED"
    p.subtotal_tx_ccy = "25.00"
    p.subtotal_aed = "92.50"  # differs from tx currency — emits the base-currency line
    for key, value in over.items():
        setattr(p, key, value)
    return p


def _tenant(base_currency="AED"):
    t = MagicMock()
    t.base_currency = base_currency
    return t


def _store(**over):
    s = MagicMock()
    s.title = "Demo Store"
    s.whatsapp = "+971555555555"
    s.phone = "+971544444444"
    for key, value in over.items():
        setattr(s, key, value)
    return s


class TestBuildMessage:
    def test_full_message_with_every_section(self):
        message = StoreWhatsAppService.build_message(_provisional(), _tenant(), _store())

        assert "طلب متجر إلكتروني جديد" in message
        assert "PRV-1-20260101-001" in message
        assert "2026-01-01 09:30" in message
        assert "John" in message
        assert "+971501234567" in message
        assert "john@example.com" in message
        # first item uses its explicit name, second falls back to "منتج #6"
        assert "1. Widget × 2 = 10.00 AED" in message
        assert "2. منتج #6 × 1 = 5.00 AED" in message
        assert "المجموع الفرعي: 25.00 AED" in message
        assert "المجموع بالعملة الأساسية: 92.50 AED" in message
        assert "من: Demo Store" in message
        assert "للتواصل: +971555555555" in message

    def test_phone_fallback_and_absent_optional_sections(self):
        provisional = _provisional(
            customer_name=None,
            customer_phone=None,
            customer_email=None,
            cart_json=None,
            subtotal_aed=None,
        )
        message = StoreWhatsAppService.build_message(provisional, _tenant(), _store(whatsapp=None))

        assert "للتواصل: +971544444444" in message
        assert "العميل:" not in message
        assert "الهاتف:" not in message
        assert "البريد الإلكتروني:" not in message
        assert "المجموع بالعملة الأساسية:" not in message

    def test_no_store_still_builds_message(self):
        message = StoreWhatsAppService.build_message(_provisional(), _tenant(), None)

        assert "طلب متجر إلكتروني جديد" in message
        assert "من:" not in message
        assert "للتواصل:" not in message


class TestWhatsappUrl:
    def test_strips_plus_and_non_digits_and_encodes_message(self):
        url = StoreWhatsAppService.whatsapp_url("+971 50-123 4567", "Hello world & مرحبا")

        assert url.startswith("https://wa.me/971501234567?text=")
        assert "Hello%20world%20%26" in url
        assert "%D9%85%D8%B1%D8%AD%D8%A8%D8%A7" in url


class TestGenerateProvisionalNumber:
    @staticmethod
    def _mock_session(mocker, last):
        session = mocker.patch("extensions.db.session")
        chain = session.query.return_value
        chain.filter_by.return_value.filter.return_value.order_by.return_value.first.return_value = last
        return session

    def test_first_order_of_the_day(self, mocker):
        self._mock_session(mocker, None)

        number = StoreWhatsAppService.generate_provisional_number(7)

        assert re.fullmatch(r"PRV-7-\d{8}-001", number)

    def test_increments_the_last_sequence(self, mocker):
        last = MagicMock()
        last.provisional_number = "PRV-7-20260101-005"
        self._mock_session(mocker, last)

        number = StoreWhatsAppService.generate_provisional_number(7)

        assert re.fullmatch(r"PRV-7-\d{8}-006", number)

    def test_malformed_last_sequence_resets_to_one(self, mocker):
        last = MagicMock()
        last.provisional_number = "PRV-7-20260101-xyz"
        self._mock_session(mocker, last)

        number = StoreWhatsAppService.generate_provisional_number(7)

        assert re.fullmatch(r"PRV-7-\d{8}-001", number)


@pytest.fixture
def twilio_rest(mocker):
    """Twilio is an optional dependency — inject a module when it is absent."""
    rest = sys.modules.get("twilio.rest")
    if rest is None:
        rest = MagicMock()
        mocker.patch.dict(sys.modules, {"twilio": MagicMock(rest=rest), "twilio.rest": rest})
    return rest


class TestSendMessage:
    def test_twilio_success(self, monkeypatch, twilio_rest):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
        client = MagicMock()
        twilio_rest.Client.return_value = client

        assert StoreWhatsAppService.send_message("+971501234567", "Hi") is True

        client.messages.create.assert_called_once_with(
            body="Hi",
            from_="whatsapp:+14155238886",
            to="whatsapp:971501234567",
        )

    def test_business_api_used_when_twilio_fails(self, monkeypatch, mocker, twilio_rest):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
        monkeypatch.setenv("WHATSAPP_API_URL", "https://wa.test/messages")
        monkeypatch.setenv("WHATSAPP_API_TOKEN", "wtoken")
        twilio_rest.Client.side_effect = RuntimeError("twilio down")
        # requests is imported inside send_message, so patch the shared module
        post = mocker.patch("requests.post")

        assert StoreWhatsAppService.send_message("+971 50 123 4567", "Hi") is True

        assert post.call_args.kwargs["json"]["to"] == "971501234567"
        assert post.call_args.kwargs["json"]["text"] == {"body": "Hi"}
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer wtoken"
        assert post.call_args.kwargs["timeout"] == 10

    def test_no_provider_configured(self):
        assert StoreWhatsAppService.send_message("+971501234567", "Hi") is False

    def test_both_providers_fail(self, monkeypatch, mocker, twilio_rest):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
        monkeypatch.setenv("WHATSAPP_API_URL", "https://wa.test/messages")
        monkeypatch.setenv("WHATSAPP_API_TOKEN", "wtoken")
        twilio_rest.Client.side_effect = RuntimeError("twilio down")
        mocker.patch("requests.post", side_effect=RuntimeError("http down"))

        assert StoreWhatsAppService.send_message("+971501234567", "Hi") is False


# ─────────────────────────── carrier_tracking_service ──────────────────────────


def _ok_response(payload):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return response


def _error_response(status_code):
    response = MagicMock()
    response.status_code = status_code
    return response


def _patch_carrier_config(mocker, value):
    return mocker.patch(
        "services.carrier_tracking_service.ShippingConfigService.get_carrier_config",
        return_value=value,
    )


def _dhl_payload(shipments=None):
    if shipments is None:
        shipments = [
            {
                "status": {"statusCode": "delivered"},
                "estimatedTimeOfDelivery": {"estimatedTimeOfDelivery": "2026-02-01T10:00:00Z"},
                "events": [
                    {
                        "timestamp": "2026-01-31T08:00:00Z",
                        "location": {"address": {"addressLocality": "Dubai"}},
                        "description": None,
                        "status": "delivered",
                    },
                    {
                        "timestamp": "2026-01-30T08:00:00Z",
                        "location": {},
                        "description": "In transit",
                        "status": "in_transit",
                    },
                ],
            }
        ]
    return {"shipments": shipments}


class TestDHLTracking:
    def test_success_normalizes_events(self, mocker):
        _patch_carrier_config(mocker, {"api_key": "key"})
        get = mocker.patch(
            "services.carrier_tracking_service.requests.get",
            return_value=_ok_response(_dhl_payload()),
        )

        result = CarrierTrackingService.track("DHL", " 123456 ")

        assert result["success"] is True
        assert result["status"] == "delivered"
        assert result["estimated_delivery"] == "2026-02-01T10:00:00Z"
        assert result["events"][0]["location"] == "Dubai"
        assert result["events"][0]["description"] == "delivered"  # falls back to status
        assert result["events"][1]["description"] == "In transit"
        assert get.call_args.kwargs["headers"] == {"DHL-API-Key": "key"}
        assert "trackingNumber=123456" in get.call_args.args[0]

    def test_http_error(self, mocker):
        _patch_carrier_config(mocker, {"api_key": "key"})
        mocker.patch(
            "services.carrier_tracking_service.requests.get",
            return_value=_error_response(503),
        )

        result = CarrierTrackingService.track("dhl", "123456")

        assert result["success"] is False
        assert result["error"] == "DHL HTTP 503"

    def test_no_shipment_data(self, mocker):
        _patch_carrier_config(mocker, {"api_key": "key"})
        mocker.patch(
            "services.carrier_tracking_service.requests.get",
            return_value=_ok_response({"shipments": []}),
        )

        result = CarrierTrackingService.track("dhl", "123456")

        assert result["success"] is False
        assert result["error"] == "no shipment data"

    def test_request_exception(self, mocker):
        _patch_carrier_config(mocker, {"api_key": "key"})
        mocker.patch(
            "services.carrier_tracking_service.requests.get",
            side_effect=RuntimeError("socket down"),
        )

        result = CarrierTrackingService.track("dhl", "123456")

        assert result["success"] is False
        assert result["error"] == "socket down"


class TestFedexToken:
    def _credentials(self, mocker):
        _patch_carrier_config(mocker, {"client_id": "cid", "client_secret": "secret"})

    def test_success(self, mocker):
        self._credentials(mocker)
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            return_value=_ok_response({"access_token": "token"}),
        )

        assert CarrierTrackingService._fedex_token() == "token"

    def test_non_200_returns_none(self, mocker):
        self._credentials(mocker)
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            return_value=_error_response(401),
        )

        assert CarrierTrackingService._fedex_token() is None

    def test_request_exception_returns_none(self, mocker):
        self._credentials(mocker)
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            side_effect=RuntimeError("boom"),
        )

        assert CarrierTrackingService._fedex_token() is None


class TestFedexTracking:
    def _token(self, mocker, token="token"):
        return mocker.patch(
            "services.carrier_tracking_service.CarrierTrackingService._fedex_token",
            return_value=token,
        )

    def test_success_normalizes_events(self, mocker):
        self._token(mocker)
        payload = {
            "output": {
                "completeTrackResults": [
                    {
                        "trackResults": [
                            {
                                "scanEvents": [
                                    {
                                        "date": "2026-01-30",
                                        "scanLocation": {"city": "Abu Dhabi"},
                                        "eventDescription": "Shipment in transit",
                                        "eventType": "IT",
                                    }
                                ],
                                "latestStatusDetail": {"description": "In transit"},
                                "estimatedDeliveryTimeWindow": {"window": {"ends": "2026-02-01"}},
                            }
                        ]
                    }
                ]
            }
        }
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            return_value=_ok_response(payload),
        )

        result = CarrierTrackingService.track("fedex", "123456")

        assert result["success"] is True
        assert result["status"] == "In transit"
        assert result["estimated_delivery"] == "2026-02-01"
        assert result["events"][0]["location"] == "Abu Dhabi"
        assert result["events"][0]["status"] == "IT"

    def test_http_error(self, mocker):
        self._token(mocker)
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            return_value=_error_response(500),
        )

        result = CarrierTrackingService.track("fedex", "123456")

        assert result["error"] == "FedEx HTTP 500"

    def test_no_tracking_data(self, mocker):
        self._token(mocker)
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            return_value=_ok_response({"output": {"completeTrackResults": []}}),
        )

        result = CarrierTrackingService.track("fedex", "123456")

        assert result["error"] == "no tracking data"

    def test_request_exception(self, mocker):
        self._token(mocker)
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            side_effect=RuntimeError("boom"),
        )

        result = CarrierTrackingService.track("fedex", "123456")

        assert result["success"] is False
        assert result["error"] == "boom"


class TestAramexTracking:
    def _credentials(self, mocker):
        _patch_carrier_config(
            mocker,
            {
                "username": "user",
                "password": "pass",
                "account_number": "acct",
                "pin": "1234",
            },
        )

    def test_success_uses_last_update_as_status(self, mocker):
        self._credentials(mocker)
        payload = {
            "TrackingResults": [
                {
                    "Key": "123456",
                    "Value": [
                        {
                            "UpdateDateTime": "2026-01-30",
                            "Location": "Amman",
                            "UpdateDescription": "Delivered",
                            "UpdateCode": "D",
                        }
                    ],
                }
            ]
        }
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            return_value=_ok_response(payload),
        )

        result = CarrierTrackingService.track("aramex", "123456")

        assert result["success"] is True
        assert result["status"] == "Delivered"
        assert result["estimated_delivery"] is None
        assert result["events"][0]["location"] == "Amman"
        assert result["events"][0]["status"] == "D"

    def test_result_without_key_keeps_unknown_status(self, mocker):
        self._credentials(mocker)
        payload = {
            "TrackingResults": [
                {
                    "Key": None,
                    "Value": [
                        {
                            "UpdateDateTime": "2026-01-30",
                            "Location": "Dubai",
                            "UpdateDescription": "Picked up",
                            "UpdateCode": "P",
                        }
                    ],
                }
            ]
        }
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            return_value=_ok_response(payload),
        )

        result = CarrierTrackingService.track("aramex", "123456")

        assert result["success"] is True
        assert result["status"] == "unknown"
        assert len(result["events"]) == 1

    def test_http_error(self, mocker):
        self._credentials(mocker)
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            return_value=_error_response(500),
        )

        result = CarrierTrackingService.track("aramex", "123456")

        assert result["error"] == "Aramex HTTP 500"

    def test_request_exception(self, mocker):
        self._credentials(mocker)
        mocker.patch(
            "services.carrier_tracking_service.requests.post",
            side_effect=RuntimeError("boom"),
        )

        result = CarrierTrackingService.track("aramex", "123456")

        assert result["success"] is False
        assert result["error"] == "boom"


class TestSyncShipmentStatusMapping:
    @staticmethod
    def _shipment(status="pending"):
        shipment = MagicMock()
        shipment.carrier_code = "dhl"
        shipment.tracking_number = "123456"
        shipment.status = status
        shipment.actual_delivery = None
        return shipment

    @staticmethod
    def _track_result(mocker, status):
        return mocker.patch(
            "services.carrier_tracking_service.CarrierTrackingService.track",
            return_value={"success": True, "status": status, "events": []},
        )

    def test_delivered_sets_actual_delivery(self, mocker):
        self._track_result(mocker, "Delivered")
        shipment = self._shipment()

        result = CarrierTrackingService.sync_shipment(shipment)

        assert result["success"] is True
        assert shipment.status == "delivered"
        assert shipment.actual_delivery is not None

    def test_out_for_delivery_maps_to_in_transit(self, mocker):
        self._track_result(mocker, "Out for delivery")
        shipment = self._shipment()

        CarrierTrackingService.sync_shipment(shipment)

        assert shipment.status == "in_transit"
        assert shipment.actual_delivery is None

    def test_already_mapped_status_is_not_rewritten(self, mocker):
        self._track_result(mocker, "Delivered")
        shipment = self._shipment(status="delivered")

        CarrierTrackingService.sync_shipment(shipment)

        assert shipment.status == "delivered"
        assert shipment.actual_delivery is None

    def test_unmapped_status_leaves_shipment_unchanged(self, mocker):
        self._track_result(mocker, "Exception")
        shipment = self._shipment()

        CarrierTrackingService.sync_shipment(shipment)

        assert shipment.status == "pending"
