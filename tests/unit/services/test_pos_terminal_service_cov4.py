"""Coverage-4 for services.pos_terminal_service — fallback/else/except arcs.

Targets (real behavior paths, network mocked only at requests boundary):
- is_configured unknown provider -> False (line 47)
- terminal_status unknown provider passthrough (line 51)
- _stripe_post HTTPError with response None -> safe error (line 77 ternary)
- _stripe_post ValueError from resp.json -> transport safe error (lines 80-82)
- create_connection_token empty-string secret -> incomplete (line 89)
- create_terminal_payment_intent no tenant/sale_reference metadata (lines 109-112 false arcs)
- create_terminal_payment_intent currency None fallback to AED (line 105)
- create_terminal_payment_intent missing client_secret only -> incomplete (line 116)
- amount_to_minor_units invalid decimal string propagates (line 56)
- amount_to_minor_units tiny value rounds to zero -> rejected (lines 56-58)
"""

from __future__ import annotations

import pytest
import requests

from services import pos_terminal_service as pts


def _capture(monkeypatch, payload):
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


class TestUnknownProvider:
    def test_unknown_provider_not_configured(self):
        assert pts.is_configured("nope_provider") is False

    def test_terminal_status_passthrough_unknown(self):
        out = pts.terminal_status("nope_provider")
        assert out == {"provider": "nope_provider", "configured": False}


class TestStripePostFallbacks:
    def test_http_error_without_response_maps_safe(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

        def fake_post(url, *, data, headers, timeout):
            raise requests.HTTPError("boom")  # response is None

        monkeypatch.setattr(pts.requests, "post", fake_post)
        with pytest.raises(pts.PosTerminalError):
            pts.create_connection_token()

    def test_json_value_error_maps_to_transport_error(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

        class _BadJson:
            def raise_for_status(self):
                return None

            def json(self):
                raise ValueError("bad json")

        monkeypatch.setattr(pts.requests, "post", lambda url, *, data, headers, timeout: _BadJson())
        with pytest.raises(pts.PosTerminalError):
            pts.create_connection_token()

    def test_timeout_maps_to_transport_error(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

        def fake_post(url, *, data, headers, timeout):
            raise requests.Timeout("slow")

        monkeypatch.setattr(pts.requests, "post", fake_post)
        with pytest.raises(pts.PosTerminalError):
            pts.create_connection_token()


class TestConnectionTokenEdge:
    def test_empty_string_secret_rejected(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        _capture(monkeypatch, {"secret": ""})
        with pytest.raises(pts.PosTerminalError):
            pts.create_connection_token()


class TestPaymentIntentArcs:
    def test_no_optional_metadata_keys(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        calls = _capture(monkeypatch, {"id": "pi_9", "client_secret": "sec_9", "status": "ok"})
        out = pts.create_terminal_payment_intent("5.00")
        assert out["id"] == "pi_9"
        assert "metadata[tenant_id]" not in calls[0]["data"]
        assert "metadata[sale_reference]" not in calls[0]["data"]

    def test_none_currency_falls_back_to_aed(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        calls = _capture(monkeypatch, {"id": "pi_2", "client_secret": "sec_2"})
        out = pts.create_terminal_payment_intent("5.00", currency=None)
        assert out["currency"] == "aed"
        assert calls[0]["data"]["currency"] == "aed"

    def test_missing_client_secret_only_rejected(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        _capture(monkeypatch, {"id": "pi_3"})
        with pytest.raises(pts.PosTerminalError):
            pts.create_terminal_payment_intent("5.00")

    def test_missing_id_only_rejected(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        _capture(monkeypatch, {"client_secret": "sec_only"})
        with pytest.raises(pts.PosTerminalError):
            pts.create_terminal_payment_intent("5.00")

    def test_default_status_empty_string(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        _capture(monkeypatch, {"id": "pi_4", "client_secret": "sec_4"})
        out = pts.create_terminal_payment_intent("5.00")
        assert out["status"] == ""


class TestMinorUnitEdges:
    def test_invalid_string_propagates_decimal_error(self):
        with pytest.raises(Exception):
            pts.amount_to_minor_units("not-a-number")

    def test_sub_cent_rounds_to_zero_and_rejected(self):
        with pytest.raises(pts.PosTerminalError):
            pts.amount_to_minor_units("0.001")

    def test_sale_reference_truncated_to_200(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        calls = _capture(monkeypatch, {"id": "pi_5", "client_secret": "sec_5"})
        pts.create_terminal_payment_intent("5.00", sale_reference="R" * 500)
        assert len(calls[0]["data"]["metadata[sale_reference]"]) == 200
