"""Cov4: currency_service — stub/cache/live/fallback/user/parity arcs."""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import services.currency_service as cs
from services.currency_service import CurrencyService


def _clear():
    CurrencyService._rates_cache.clear()


def test_stub_raises():
    stub = cs._CurrencyRatesStub()
    try:
        stub.get_rates("AED")
        raise AssertionError("should raise")
    except RuntimeError:
        pass
    try:
        stub.get_rate("AED", "USD")
        raise AssertionError("should raise")
    except RuntimeError:
        pass


def test_labels_and_supported(app):
    assert CurrencyService.get_currency_label("usd") == "USD - US Dollar"
    assert CurrencyService.get_currency_label("zzz") == "ZZZ - Currency"
    assert CurrencyService.get_currency_label(None) == " - Currency"
    _clear()
    with patch.object(CurrencyService, "get_all_rates", return_value={"JPY": Decimal("1")}):
        codes = CurrencyService.get_supported_currencies()
    assert "AED" in codes and "JPY" in codes
    assert all(len(c) == 3 for c in codes)


def test_fetch_open_er_branches():
    with patch.object(cs, "REQUESTS_AVAILABLE", False):
        assert CurrencyService._fetch_open_er_api_rates("AED") == {}
    fake_requests = MagicMock()
    resp = MagicMock(status_code=500)
    fake_requests.get.return_value = resp
    with patch.object(cs, "REQUESTS_AVAILABLE", True), patch.object(cs, "requests", fake_requests):
        assert CurrencyService._fetch_open_er_api_rates("AED") == {}
    resp.status_code = 200
    resp.json.return_value = {"result": "error", "rates": {}}
    with patch.object(cs, "REQUESTS_AVAILABLE", True), patch.object(cs, "requests", fake_requests):
        assert CurrencyService._fetch_open_er_api_rates("AED") == {}
    resp.json.return_value = {"result": "success",
                              "rates": {"USD": 0.27, "BAD!": object()}}
    with patch.object(cs, "REQUESTS_AVAILABLE", True), patch.object(cs, "requests", fake_requests):
        out = CurrencyService._fetch_open_er_api_rates("aed")
        assert out["USD"] == Decimal("0.27")
        assert out["AED"] == Decimal("1.00")
    fake_requests.get.side_effect = RuntimeError("net down")
    with patch.object(cs, "REQUESTS_AVAILABLE", True), patch.object(cs, "requests", fake_requests):
        assert CurrencyService._fetch_open_er_api_rates("AED") == {}


def test_get_all_rates_cache_and_fallback():
    _clear()
    CurrencyService._rates_cache["AED"] = {"timestamp": time.time(), "rates": {"USD": Decimal("0.5")}}
    assert CurrencyService.get_all_rates("AED") == {"USD": Decimal("0.5")}
    _clear()
    with patch.object(cs, "FOREX_AVAILABLE", False), patch.object(
        CurrencyService, "_fetch_open_er_api_rates", return_value={}):
        rates = CurrencyService.get_all_rates("USD")
        assert rates["USD"] == Decimal("1.00")
        assert rates["AED"] > 0


def test_get_all_rates_forex_and_http():
    _clear()
    fake_cls = MagicMock()
    fake_cls.return_value.get_rates.return_value = {"EUR": 0.9}
    with patch.object(cs, "FOREX_AVAILABLE", True), patch.object(cs, "CurrencyRates", fake_cls):
        rates = CurrencyService.get_all_rates("USD")
        assert rates["EUR"] == Decimal("0.9")
        assert rates["USD"] == Decimal("1.00")
    _clear()
    fake_cls.return_value.get_rates.side_effect = RuntimeError("forex down")
    with patch.object(cs, "FOREX_AVAILABLE", True), patch.object(cs, "CurrencyRates", fake_cls), \
         patch.object(CurrencyService, "_fetch_open_er_api_rates",
                      return_value={"USD": Decimal("1"), "EUR": Decimal("0.9")}):
        rates = CurrencyService.get_all_rates("USD")
        assert rates["EUR"] == Decimal("0.9")


def test_details_user_parity_cache_http_forex_fallback():
    _clear()
    out = CurrencyService.get_exchange_rate_details("USD", "AED", user_rate="3.67")
    assert out["source"] == "user_input"
    out = CurrencyService.get_exchange_rate_details("USD", "AED", user_rate="bogus!!!")
    assert out["source"] != "user_input"
    out = CurrencyService.get_exchange_rate_details("USD", "AED", user_rate="-5")
    assert out["source"] != "user_input"
    assert CurrencyService.get_exchange_rate_details("AED", "AED")["source"] == "parity"
    CurrencyService._rates_cache["USD"] = {"timestamp": time.time(),
                                           "rates": {"AED": Decimal("3.6725")}}
    out = CurrencyService.get_exchange_rate_details("USD", "AED")
    assert out["source"] == "cache" and out["cached"] is True
    _clear()
    with patch.object(CurrencyService, "_fetch_open_er_api_rates",
                      return_value={"AED": Decimal("3.67")}):
        out = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert out["source"] == "open_er_api"
    _clear()
    with patch.object(CurrencyService, "_fetch_open_er_api_rates", return_value={}), \
         patch.object(cs, "FOREX_AVAILABLE", True), patch.object(
             cs, "CurrencyRates",
             return_value=MagicMock(get_rate=MagicMock(return_value=3.6))):
        out = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert out["source"] == "forex_python"
    _clear()
    with patch.object(CurrencyService, "_fetch_open_er_api_rates", return_value={}), \
         patch.object(cs, "FOREX_AVAILABLE", False):
        out = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert out["source"] == "fallback_static"
        assert out["rate"] > 0
    assert CurrencyService.get_exchange_rate("USD", "AED") > 0
    _clear()


def test_details_defaults_and_stale_cache(app):
    _clear()
    out = CurrencyService.get_exchange_rate_details(None, None)
    assert out["source"] == "parity"
    CurrencyService._rates_cache["USD"] = {"timestamp": time.time() - 9999,
                                           "rates": {"AED": Decimal("3.6")}}
    with patch.object(CurrencyService, "_fetch_open_er_api_rates", return_value={}), \
         patch.object(cs, "FOREX_AVAILABLE", False):
        out = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert out["source"] == "fallback_static"
    _clear()
