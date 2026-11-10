"""FX scenario matrix — rate sources, online fetch, manual entry, fallback math.

The resolver priority is user input → parity → cache → online provider →
forex-python → static fallback (AED base only) → needs_input. Every case
here pins one branch with an independently computed expectation.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.currency_service import CurrencyService
from utils.currency_utils import convert_and_quantize_aed


@contextmanager
def _no_forex(mocker):
    mocker.patch("services.currency_service.FOREX_AVAILABLE", False)
    yield


@pytest.fixture(autouse=True)
def _clean_cache(mocker):
    CurrencyService._rates_cache.clear()
    mocker.patch("services.currency_service.FOREX_AVAILABLE", False)
    yield
    CurrencyService._rates_cache.clear()


def _http_response(json_data, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = json_data
    return response


class TestUserInputPriority:
    @pytest.mark.parametrize(
        "rate,expected",
        [
            ("3.65", "3.650000"), ("0.27", "0.270000"), ("1", "1.000000"), ("4.5", "4.500000"),
            ("0.0027", "0.002700"), ("999.9999", "999.999900"), ("0.000001", "0.000001"),
            ("123.4567", "123.456700"), ("2.5", "2.500000"), ("7.77", "7.770000"),
        ],
    )
    def test_user_rate_wins(self, rate, expected):
        details = CurrencyService.get_exchange_rate_details("USD", "AED", user_rate=rate)
        assert details["rate"] == Decimal(expected)
        assert details["source"] == "user_input"

    @pytest.mark.parametrize("bad", ["0", "-1", "abc", "", None])
    def test_invalid_user_rate_ignored(self, bad):
        details = CurrencyService.get_exchange_rate_details("AED", "AED", user_rate=bad)
        assert details["source"] in ("parity", "fallback_static")

    @pytest.mark.parametrize("pair", [("AED", "AED"), ("USD", "USD"), ("ILS", "ILS"), ("EUR", "EUR")])
    def test_parity(self, pair):
        details = CurrencyService.get_exchange_rate_details(pair[0], pair[1])
        assert details["rate"] == Decimal("1.000000")
        assert details["source"] == "parity"


class TestOnlineFetch:
    @pytest.mark.parametrize(
        "base,target,provider_rate,expected",
        [
            ("AED", "USD", "0.2723", "0.272300"),
            ("USD", "AED", "3.6725", "3.672500"),
            ("EUR", "AED", "3.98", "3.980000"),
            ("SAR", "AED", "0.98", "0.980000"),
            ("GBP", "AED", "4.65", "4.650000"),
            ("KWD", "AED", "11.95", "11.950000"),
        ],
    )
    def test_online_success(self, mocker, base, target, provider_rate, expected):
        mocker.patch(
            "services.currency_service.requests.get",
            return_value=_http_response({"result": "success", "rates": {target: float(provider_rate), base: 1}}),
        )
        with _no_forex(mocker):
            details = CurrencyService.get_exchange_rate_details(base, target)
        assert details["rate"] == Decimal(expected)
        assert details["source"] == "open_er_api"

    @pytest.mark.parametrize(
        "scenario",
        ["http500", "badjson", "error_result", "timeout", "missing_rates"],
    )
    def test_online_failures_fall_back(self, mocker, scenario):
        if scenario == "http500":
            response = _http_response({}, status=500)
        elif scenario == "badjson":
            response = MagicMock(status_code=200)
            response.json.side_effect = ValueError("no json")
        elif scenario == "error_result":
            response = _http_response({"result": "error", "rates": {}})
        elif scenario == "timeout":
            import requests as _rq

            mocker.patch(
                "services.currency_service.requests.get", side_effect=_rq.Timeout("slow")
            )
            with _no_forex(mocker):
                details = CurrencyService.get_exchange_rate_details("USD", "AED")
            assert details["source"] == "fallback_static"
            return
        else:
            response = _http_response({"result": "success"})
        mocker.patch("services.currency_service.requests.get", return_value=response)
        with _no_forex(mocker):
            details = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert details["source"] == "fallback_static"

    def test_cache_avoids_second_fetch(self, mocker):
        get = mocker.patch(
            "services.currency_service.requests.get",
            return_value=_http_response({"result": "success", "rates": {"AED": 3.65, "USD": 1}}),
        )
        with _no_forex(mocker):
            first = CurrencyService.get_exchange_rate_details("USD", "AED")
            second = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert get.call_count == 1
        assert first["source"] == "open_er_api"
        assert second["source"] == "cache"
        assert second["cached"] is True

    def test_cache_tenant_isolated(self, mocker):
        get = mocker.patch(
            "services.currency_service.requests.get",
            return_value=_http_response({"result": "success", "rates": {"AED": 3.65, "USD": 1}}),
        )
        with _no_forex(mocker):
            CurrencyService.get_exchange_rate_details("USD", "AED", tenant_id=1)
            CurrencyService.get_exchange_rate_details("USD", "AED", tenant_id=2)
        assert get.call_count == 2


class TestFallbackMath:
    @pytest.mark.parametrize(
        "from_c,to_c,expected",
        [
            ("USD", "AED", "3.703704"),
            ("EUR", "AED", "4.000000"),
            ("SAR", "AED", "0.980392"),
            ("ILS", "AED", "0.952381"),
        ],
    )
    def test_cross_rates(self, mocker, from_c, to_c, expected):
        mocker.patch("services.currency_service.requests.get", return_value=_http_response({}, status=500))
        with _no_forex(mocker):
            details = CurrencyService.get_exchange_rate_details(from_c, to_c)
        assert details["source"] == "fallback_static"
        assert details["rate"] == Decimal(expected)

    @pytest.mark.parametrize("from_c,to_c", [("AED", "EUR"), ("AED", "ILS"), ("AED", "SAR"), ("AED", "USD")])
    def test_aed_out_needs_input(self, mocker, from_c, to_c):
        mocker.patch("services.currency_service.requests.get", return_value=_http_response({}, status=500))
        with _no_forex(mocker):
            details = CurrencyService.get_exchange_rate_details(from_c, to_c)
        assert details["source"] == "needs_input"
        assert details["rate"] is None

    @pytest.mark.parametrize("to_c", ["ILS", "USD", "EUR"])
    def test_non_aed_base_needs_input(self, mocker, to_c):
        mocker.patch("services.currency_service.requests.get", return_value=_http_response({}, status=500))
        with _no_forex(mocker):
            details = CurrencyService.get_exchange_rate_details("AED", to_c)
        assert details["source"] == "needs_input"
        assert details["rate"] is None


class TestAccountingConversion:
    @pytest.mark.parametrize(
        "amount,currency,rate,base,expected",
        [
            ("100", "USD", "3.65", "AED", "365.000"),
            ("100", "USD", "3.65", "ILS", "365.000"),
            ("50", "EUR", "4", "AED", "200.000"),
            ("1000", "SAR", "0.98", "AED", "980.000"),
            ("200", "GBP", "4.65", "AED", "930.000"),
            ("10", "KWD", "11.95", "AED", "119.500"),
        ],
    )
    def test_convert_bases(self, amount, currency, rate, base, expected):
        result = convert_and_quantize_aed(
            Decimal(amount), currency, Decimal(rate), base_currency=base
        )
        assert result == Decimal(expected)

    def test_wrapper_matches_details(self):
        assert CurrencyService.get_exchange_rate("USD", "AED", user_rate="3.65") == Decimal("3.650000")
