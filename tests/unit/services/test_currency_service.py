from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.currency_service import CurrencyService


@pytest.fixture(autouse=True)
def _clear_rates_cache():
    CurrencyService._rates_cache.clear()
    yield
    CurrencyService._rates_cache.clear()


class TestCurrencyMetadata:
    def test_get_supported_currencies(self, mocker):
        mocker.patch.object(
            CurrencyService,
            "get_all_rates",
            return_value={"AED": Decimal("1"), "USD": Decimal("0.27")},
        )
        codes = CurrencyService.get_supported_currencies()
        assert "AED" in codes
        assert "USD" in codes

    def test_get_currency_label_known(self):
        label = CurrencyService.get_currency_label("AED")
        assert "AED" in label
        assert "Dirham" in label

    def test_get_currency_label_unknown(self):
        label = CurrencyService.get_currency_label("ZZZ")
        assert label == "ZZZ - Currency"


class TestGetAllRates:
    def test_cache_hit(self):
        CurrencyService._rates_cache["AED"] = {
            "timestamp": __import__("time").time(),
            "rates": {"AED": Decimal("1"), "USD": Decimal("0.27")},
        }
        rates = CurrencyService.get_all_rates("AED")
        assert rates["USD"] == Decimal("0.27")

    def test_forex_python_path(self):
        import services.currency_service as cs

        instance = MagicMock()
        instance.get_rates.return_value = {"USD": 0.27, "EUR": 0.25, "AED": 1.0}
        old_forex = cs.FOREX_AVAILABLE
        old_rates_cls = getattr(cs, "CurrencyRates", None)
        cs.FOREX_AVAILABLE = True
        cs.CurrencyRates = MagicMock(return_value=instance)
        try:
            rates = CurrencyService.get_all_rates("AED")
            assert "USD" in rates
        finally:
            cs.FOREX_AVAILABLE = old_forex
            if old_rates_cls is None:
                delattr(cs, "CurrencyRates")
            else:
                cs.CurrencyRates = old_rates_cls

    def test_forex_failure_falls_back_http(self, mocker):
        import services.currency_service as cs

        old_forex = cs.FOREX_AVAILABLE
        old_rates_cls = getattr(cs, "CurrencyRates", None)
        cs.FOREX_AVAILABLE = True
        cs.CurrencyRates = MagicMock(side_effect=RuntimeError("api down"))
        try:
            mocker.patch.object(
                CurrencyService,
                "_fetch_open_er_api_rates",
                return_value={"AED": Decimal("1"), "USD": Decimal("0.27")},
            )
            rates = CurrencyService.get_all_rates("AED")
            assert rates["USD"] == Decimal("0.27")
        finally:
            cs.FOREX_AVAILABLE = old_forex
            if old_rates_cls is None:
                delattr(cs, "CurrencyRates")
            else:
                cs.CurrencyRates = old_rates_cls

    def test_http_open_er_api(self, mocker):
        mocker.patch("services.currency_service.FOREX_AVAILABLE", False)
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {
            "result": "success",
            "rates": {"AED": 1.0, "USD": 0.27},
        }
        mocker.patch("services.currency_service.requests.get", return_value=mock_res)
        rates = CurrencyService.get_all_rates("AED")
        assert rates["USD"] == Decimal("0.27")

    def test_static_fallback_cross_rate(self, mocker):
        mocker.patch("services.currency_service.FOREX_AVAILABLE", False)
        mocker.patch.object(
            CurrencyService, "_fetch_open_er_api_rates", return_value={}
        )
        rates = CurrencyService.get_all_rates("USD")
        assert rates["USD"] == Decimal("1.00")
        assert "AED" in rates

    def test_fetch_open_er_api_bad_status(self, mocker):
        mocker.patch("services.currency_service.REQUESTS_AVAILABLE", True)
        mock_res = MagicMock(status_code=500)
        mocker.patch("services.currency_service.requests.get", return_value=mock_res)
        assert CurrencyService._fetch_open_er_api_rates("AED") == {}


class TestExchangeRateDetails:
    def test_user_rate_priority(self):
        details = CurrencyService.get_exchange_rate_details(
            "USD", "AED", user_rate="3.67"
        )
        assert details["source"] == "user_input"
        assert details["rate"] == Decimal("3.670000")

    def test_invalid_user_rate_ignored(self):
        details = CurrencyService.get_exchange_rate_details(
            "USD", "AED", user_rate="bad"
        )
        assert details["source"] in (
            "parity",
            "open_er_api",
            "forex_python",
            "fallback_static",
            "cache",
        )

    def test_parity(self):
        details = CurrencyService.get_exchange_rate_details("AED", "AED")
        assert details["source"] == "parity"
        assert details["rate"] == Decimal("1.000000")

    def test_cache_path(self):
        CurrencyService._rates_cache["USD"] = {
            "timestamp": __import__("time").time(),
            "rates": {"AED": Decimal("3.67")},
        }
        details = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert details["source"] == "cache"
        assert details["cached"] is True

    def test_http_provider(self, mocker):
        mocker.patch.object(
            CurrencyService,
            "_fetch_open_er_api_rates",
            return_value={"USD": Decimal("1"), "AED": Decimal("3.67")},
        )
        details = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert details["source"] == "open_er_api"

    def test_forex_python_provider(self):
        import services.currency_service as cs

        instance = MagicMock()
        instance.get_rate.return_value = 3.67
        old_forex = cs.FOREX_AVAILABLE
        old_rates_cls = getattr(cs, "CurrencyRates", None)
        cs.FOREX_AVAILABLE = True
        cs.CurrencyRates = MagicMock(return_value=instance)
        try:
            mocker_patch = patch.object(
                CurrencyService, "_fetch_open_er_api_rates", return_value={}
            )
            with mocker_patch:
                details = CurrencyService.get_exchange_rate_details("USD", "AED")
            assert details["source"] == "forex_python"
        finally:
            cs.FOREX_AVAILABLE = old_forex
            if old_rates_cls is None:
                delattr(cs, "CurrencyRates")
            else:
                cs.CurrencyRates = old_rates_cls

    def test_fetch_open_er_api_non_success(self, mocker):
        mocker.patch("services.currency_service.REQUESTS_AVAILABLE", True)
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"result": "error"}
        mocker.patch("services.currency_service.requests.get", return_value=mock_res)
        assert CurrencyService._fetch_open_er_api_rates("AED") == {}

    def test_fetch_open_er_api_request_error(self, mocker):
        mocker.patch("services.currency_service.REQUESTS_AVAILABLE", True)
        mocker.patch(
            "services.currency_service.requests.get", side_effect=RuntimeError("net")
        )
        assert CurrencyService._fetch_open_er_api_rates("AED") == {}

    def test_fallback_static(self, mocker):
        mocker.patch("services.currency_service.FOREX_AVAILABLE", False)
        mocker.patch.object(
            CurrencyService, "_fetch_open_er_api_rates", return_value={}
        )
        details = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert details["source"] == "fallback_static"
        assert details["rate"] > Decimal("0")

    def test_get_exchange_rate_wrapper(self, mocker):
        mocker.patch.object(
            CurrencyService,
            "get_exchange_rate_details",
            return_value={"rate": Decimal("3.67")},
        )
        assert CurrencyService.get_exchange_rate("USD", "AED") == Decimal("3.67")

    def test_none_from_currency_defaults(self):
        details = CurrencyService.get_exchange_rate_details(None, None)
        assert details["source"] == "parity"
