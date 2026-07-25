"""POS push-to-terminal gateway tests — pure unit, no DB.

Covers provider configuration detection, exact minor-unit conversion,
Stripe request shaping (auth header, form body, metadata), and safe error
mapping. All network calls are mocked at the urllib boundary.
"""

from __future__ import annotations

import io
import json
import urllib.error
from decimal import Decimal

import pytest

from services import pos_terminal_service as pts


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _capture_urlopen(monkeypatch, payload: dict):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append({"req": req, "timeout": timeout})
        return _FakeResponse(payload)

    monkeypatch.setattr(pts.urllib.request, "urlopen", fake_urlopen)
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
        calls = _capture_urlopen(monkeypatch, {"secret": "pst_secret_1"})
        secret = pts.create_connection_token()
        assert secret == "pst_secret_1"
        req = calls[0]["req"]
        assert req.full_url == "https://api.stripe.com/v1/terminal/connection_tokens"
        assert req.headers["Authorization"] == "Bearer sk_test_abc"
        assert calls[0]["timeout"] == 10

    def test_unconfigured_raises_safe_error(self, monkeypatch):
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        with pytest.raises(pts.PosTerminalError):
            pts.create_connection_token()

    def test_incomplete_payload_raises(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        _capture_urlopen(monkeypatch, {})
        with pytest.raises(pts.PosTerminalError):
            pts.create_connection_token()


class TestPaymentIntent:
    def test_request_body_and_response(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        calls = _capture_urlopen(
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
        req = calls[0]["req"]
        assert req.full_url == "https://api.stripe.com/v1/payment_intents"
        body = req.data.decode("utf-8")
        assert "amount=2550" in body
        assert "currency=aed" in body
        assert "capture_method=automatic" in body
        assert "card_present" in body
        assert "metadata%5Btenant_id%5D=7" in body
        assert "sale_reference" in body

    def test_http_error_maps_to_safe_message(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 402, "Payment Required", {}, io.BytesIO(b"{}"))

        monkeypatch.setattr(pts.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(pts.PosTerminalError) as excinfo:
            pts.create_terminal_payment_intent("10")
        assert "402" not in str(excinfo.value)

    def test_transport_error_maps_to_safe_message(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(pts.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(pts.PosTerminalError) as excinfo:
            pts.create_terminal_payment_intent("10")
        assert "refused" not in str(excinfo.value)

    def test_invalid_amount_rejected_before_network(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        calls = _capture_urlopen(monkeypatch, {"id": "pi_1", "client_secret": "s"})
        with pytest.raises(pts.PosTerminalError):
            pts.create_terminal_payment_intent("0")
        assert calls == []
