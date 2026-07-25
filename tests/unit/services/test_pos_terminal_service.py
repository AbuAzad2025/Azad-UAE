"""POS push-to-terminal gateway tests — pure unit, no DB.

Covers provider configuration detection, exact minor-unit conversion,
Stripe request shaping (auth header, form body, metadata), and safe error
mapping. All network calls are mocked at the requests boundary.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import requests

from services import pos_terminal_service as pts


def _capture_post(monkeypatch, payload: dict):
    calls = []

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    def fake_post(url, *, data, headers, timeout):
        calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return _Resp()

    monkeypatch.setattr(pts.requests, "post", fake_post)
    return calls


class TestConfiguration:
    def test_unconfigured_without_key(self, monkeypatch):
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        assert pts.is_configured() is False
        assert pts.terminal_status() == {"provider": "stripe_terminal", "configured": False}

    def test_configured_with_key(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
        assert pts.is_configured() is True
        assert pts.terminal_status()["configured"] is True

    def test_blank_key_is_unconfigured(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "   ")
        assert pts.is_configured() is False


class TestMinorUnits:
    def test_whole_amount(self):
        assert pts.amount_to_minor_units("10") == 1000

    def test_decimal_amount(self):
        assert pts.amount_to_minor_units("12.34") == 1234

    def test_half_up_rounding(self):
        assert pts.amount_to_minor_units("10.005") == 1001

    def test_accepts_decimal_and_float(self):
        assert pts.amount_to_minor_units(Decimal("7.50")) == 750
        assert pts.amount_to_minor_units(7.5) == 750

    def test_zero_and_negative_rejected(self):
        with pytest.raises(pts.PosTerminalError):
            pts.amount_to_minor_units("0")
        with pytest.raises(pts.PosTerminalError):
            pts.amount_to_minor_units("-5")

    def test_none_rejected(self):
        with pytest.raises(pts.PosTerminalError):
            pts.amount_to_minor_units(None)


class TestConnectionToken:
    def test_request_shape_and_secret(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        calls = _capture_post(monkeypatch, {"secret": "pst_secret_1"})
        secret = pts.create_connection_token()
        assert secret == "pst_secret_1"
        call = calls[0]
        assert call["url"] == "https://api.stripe.com/v1/terminal/connection_tokens"
        assert call["headers"]["Authorization"] == "Bearer sk_test_abc"
        assert call["timeout"] == 10

    def test_unconfigured_raises_safe_error(self, monkeypatch):
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        with pytest.raises(pts.PosTerminalError):
            pts.create_connection_token()

    def test_incomplete_payload_raises(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        _capture_post(monkeypatch, {})
        with pytest.raises(pts.PosTerminalError):
            pts.create_connection_token()


class TestPaymentIntent:
    def test_request_body_and_response(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        calls = _capture_post(
            monkeypatch,
            {"id": "pi_1", "client_secret": "pi_1_secret_x", "status": "requires_payment_method"},
        )
        intent = pts.create_terminal_payment_intent(
            "25.50", currency="AED", tenant_id=7, sale_reference="POS-2026-0001"
        )
        assert intent["id"] == "pi_1"
        assert intent["client_secret"] == "pi_1_secret_x"
        assert intent["amount_minor"] == 2550
        assert intent["currency"] == "aed"
        call = calls[0]
        assert call["url"] == "https://api.stripe.com/v1/payment_intents"
        data = call["data"]
        assert data["amount"] == "2550"
        assert data["currency"] == "aed"
        assert data["capture_method"] == "automatic"
        assert data["payment_method_types[]"] == "card_present"
        assert data["metadata[tenant_id]"] == "7"
        assert data["metadata[sale_reference]"] == "POS-2026-0001"

    def test_http_error_maps_to_safe_message(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")

        def fake_post(url, *, data, headers, timeout):
            response = requests.Response()
            response.status_code = 402
            raise requests.HTTPError(response=response)

        monkeypatch.setattr(pts.requests, "post", fake_post)
        with pytest.raises(pts.PosTerminalError) as excinfo:
            pts.create_terminal_payment_intent("10")
        assert "402" not in str(excinfo.value)

    def test_transport_error_maps_to_safe_message(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")

        def fake_post(url, *, data, headers, timeout):
            raise requests.ConnectionError("connection refused")

        monkeypatch.setattr(pts.requests, "post", fake_post)
        with pytest.raises(pts.PosTerminalError) as excinfo:
            pts.create_terminal_payment_intent("10")
        assert "refused" not in str(excinfo.value)

    def test_invalid_amount_rejected_before_network(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        calls = _capture_post(monkeypatch, {"id": "pi_1", "client_secret": "s"})
        with pytest.raises(pts.PosTerminalError):
            pts.create_terminal_payment_intent("0")
        assert calls == []
