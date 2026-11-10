"""FX scenario matrix B — large grids: manual entry, online, fallback, parity.

Every case pins one resolver branch with an independently computed value.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import MagicMock

import pytest

from services.currency_service import CurrencyService
from utils.currency_utils import convert_and_quantize_aed

FALLBACK = {
    "AED": Decimal("1.00"), "USD": Decimal("0.27"), "EUR": Decimal("0.25"), "GBP": Decimal("0.22"),
    "SAR": Decimal("1.02"), "KWD": Decimal("0.08"), "BHD": Decimal("0.10"), "OMR": Decimal("0.10"),
    "QAR": Decimal("0.99"), "ILS": Decimal("1.05"),
}
COMMON = ["AED", "USD", "EUR", "GBP", "SAR", "QAR", "KWD", "BHD", "OMR", "ILS", "JPY", "CNY", "INR", "TRY", "EGP", "JOD"]


@pytest.fixture(autouse=True)
def _clean(mocker):
    CurrencyService._rates_cache.clear()
    mocker.patch("services.currency_service.FOREX_AVAILABLE", False)
    yield
    CurrencyService._rates_cache.clear()


@contextmanager
def _fail_http(mocker):
    response = MagicMock(status_code=500)
    response.json.return_value = {}
    mocker.patch("services.currency_service.requests.get", return_value=response)
    yield


class TestManualEntryGrid:
    @pytest.mark.parametrize(
        "rate",
        [str(v) for v in (0.5, 1, 2, 3.65, 4.5, 0.27, 11.95, 0.98, 1.05, 99.99, 0.0001, 123.456789, 7, 8.88, 0.1234, 456.789, 1000, 0.001, 5.5, 9.99)],
    )
    def test_user_rates(self, rate):
        details = CurrencyService.get_exchange_rate_details("USD", "AED", user_rate=rate)
        expected = Decimal(rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        assert details["rate"] == expected
        assert details["source"] == "user_input"

    @pytest.mark.parametrize("currency", COMMON)
    def test_parity_all(self, currency):
        details = CurrencyService.get_exchange_rate_details(currency, currency)
        assert details["rate"] == Decimal("1.000000")
        assert details["source"] == "parity"


class TestOnlineGrid:
    @pytest.mark.parametrize(
        "base,target,rate",
        [
            (b, t, "3.65") for b in ("USD", "EUR", "GBP") for t in ("AED",)
        ]
        + [
            (b, t, "0.27") for b in ("AED",) for t in ("USD", "EUR", "GBP")
        ]
        + [("SAR", "AED", "0.98"), ("KWD", "AED", "11.95"), ("ILS", "AED", "0.95"), ("QAR", "AED", "1.01")],
    )
    def test_provider_rates(self, mocker, base, target, rate):
        response = MagicMock(status_code=200)
        response.json.return_value = {"result": "success", "rates": {target: float(rate), base: 1}}
        mocker.patch("services.currency_service.requests.get", return_value=response)
        details = CurrencyService.get_exchange_rate_details(base, target)
        assert details["rate"] == Decimal(rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        assert details["source"] == "open_er_api"


class TestFallbackGrid:
    @pytest.mark.parametrize("currency", ["USD", "EUR", "GBP", "SAR", "KWD", "BHD", "OMR", "QAR", "ILS"])
    def test_into_aed(self, mocker, currency):
        with _fail_http(mocker):
            details = CurrencyService.get_exchange_rate_details(currency, "AED")
        expected = (Decimal("1") / FALLBACK[currency]).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        assert details["source"] == "fallback_static"
        assert details["rate"] == expected

    @pytest.mark.parametrize("currency", ["USD", "EUR", "GBP", "SAR", "KWD", "BHD", "OMR", "QAR", "ILS"])
    def test_out_of_aed_needs_input(self, mocker, currency):
        with _fail_http(mocker):
            details = CurrencyService.get_exchange_rate_details("AED", currency)
        assert details["source"] == "needs_input"

    @pytest.mark.parametrize("amount,rate", [(str(a), str(r)) for a in (5, 50, 500, 5000) for r in ("0.27", "3.65", "1.05", "0.98")])
    def test_convert_grid(self, amount, rate):
        assert convert_and_quantize_aed(Decimal(amount), "USD", Decimal(rate), base_currency="AED") == (
            Decimal(amount) * Decimal(rate)
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
