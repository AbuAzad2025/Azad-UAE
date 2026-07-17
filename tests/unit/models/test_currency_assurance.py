"""Currency and ExchangeRate models — display, validity, serialization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal


def _currency_stub(**kwargs):
    from models.currency import Currency

    class Stub:
        id = kwargs.get("id", 1)
        code = kwargs.get("code", "AED")
        name = kwargs.get("name", "UAE Dirham")
        name_ar = kwargs.get("name_ar", "درهم")
        symbol = kwargs.get("symbol", "د.إ")
        is_base = kwargs.get("is_base", False)

        get_display_name = Currency.get_display_name
        to_dict = Currency.to_dict
        __repr__ = Currency.__repr__

    return Stub()


def _rate_stub(**kwargs):
    from models.currency import ExchangeRate

    class Stub:
        id = kwargs.get("id", 1)
        rate = kwargs.get("rate", Decimal("3.67"))
        source = kwargs.get("source", "manual")
        is_manual = kwargs.get("is_manual", True)
        valid_from = kwargs.get(
            "valid_from",
            datetime.now(timezone.utc) - timedelta(days=1),
        )
        valid_until = kwargs.get("valid_until")
        currency = kwargs.get("currency", _currency_stub())

        is_valid = ExchangeRate.is_valid
        to_dict = ExchangeRate.to_dict
        __repr__ = ExchangeRate.__repr__

    return Stub()


class TestCurrency:
    def test_repr(self):
        assert "AED" in repr(_currency_stub())

    def test_get_display_name_ar(self):
        assert _currency_stub().get_display_name() == "درهم"

    def test_get_display_name_en_fallback(self):
        c = _currency_stub(name_ar=None)
        assert c.get_display_name() == "UAE Dirham"

    def test_to_dict(self):
        data = _currency_stub(is_base=True).to_dict()
        assert data["code"] == "AED"
        assert data["is_base"] is True


class TestExchangeRate:
    def test_repr_with_currency(self):
        assert "AED" in repr(_rate_stub())

    def test_repr_without_currency(self):
        r = _rate_stub(currency=None)
        assert "?" in repr(r)

    def test_is_valid_open_ended(self):
        r = _rate_stub(valid_until=None)
        assert r.is_valid() is True

    def test_is_valid_within_window(self):
        now = datetime.now(timezone.utc)
        r = _rate_stub(
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=1),
        )
        assert r.is_valid() is True

    def test_is_valid_expired(self):
        now = datetime.now(timezone.utc)
        r = _rate_stub(
            valid_from=now - timedelta(days=2),
            valid_until=now - timedelta(days=1),
        )
        assert r.is_valid() is False

    def test_to_dict(self):
        data = _rate_stub().to_dict()
        assert data["currency_code"] == "AED"
        assert data["rate"] == 3.67
        assert "is_valid" in data
