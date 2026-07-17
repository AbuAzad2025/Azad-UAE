from __future__ import annotations

import importlib
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from models import ExchangeRateRecord


def _ERS():
    """Current ExchangeRateService class (safe after importlib.reload in other tests)."""
    return importlib.import_module("services.exchange_rate_service").ExchangeRateService


@pytest.fixture(autouse=True)
def _clear_display_cache():
    _ERS()._display_cache.clear()
    yield
    _ERS()._display_cache.clear()


class TestCacheHelpers:
    def test_cache_key(self):
        key = _ERS()._cache_key("usd", ("EUR", "AED"))
        assert key == "USD:AED,EUR"

    def test_cache_ttl_from_config(self, app):
        app.config["CURRENCY_ONLINE_CACHE_TIMEOUT"] = "120"
        assert _ERS()._cache_ttl() == 120

    def test_cache_ttl_invalid_config(self, app):
        app.config["CURRENCY_ONLINE_CACHE_TIMEOUT"] = "bad"
        assert _ERS()._cache_ttl() == _ERS()._display_cache_ttl

    def test_api_timeout_from_config(self, app):
        app.config["CURRENCY_API_TIMEOUT"] = "9"
        assert _ERS()._api_timeout() == 9


class TestFetchProviders:
    def test_fetch_primary_success(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {
            "result": "success",
            "rates": {"USD": 1.0, "AED": 3.67, "EUR": 0.92},
        }
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        rates = _ERS()._fetch_primary("USD", ("AED", "EUR"))
        assert rates is not None
        assert rates["AED"] == 3.67

    def test_fetch_primary_failure(self, mocker):
        mocker.patch(
            "services.exchange_rate_service.requests.get",
            side_effect=RuntimeError("net"),
        )
        assert _ERS()._fetch_primary("USD", ("AED",)) is None

    def test_fetch_frankfurter_success(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"rates": {"AED": 3.67}}
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        rates = _ERS()._fetch_frankfurter("USD", ("AED",))
        assert rates is not None

    def test_fetch_fallbacks_configured(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = ["https://example.com/{base}"]
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"rates": {"AED": 3.67}}
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        rates = _ERS()._fetch_fallbacks("USD", ("AED",))
        assert rates is not None

    def test_fetch_fallbacks_skips_dup_urls(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = [
            "https://open.er-api.com/v6/latest/{base}",
            "https://api.frankfurter.dev/v1/latest?base={base}",
        ]
        get = mocker.patch("services.exchange_rate_service.requests.get")
        assert _ERS()._fetch_fallbacks("USD", ("AED",)) is None
        get.assert_not_called()


class TestDisplayRates:
    def test_cache_hit(self, mocker):
        _ERS()._display_cache["USD:AED,EUR"] = {
            "timestamp": __import__("time").time(),
            "rates": {"USD": 1.0, "AED": 3.67, "EUR": 0.92},
            "provider": "primary",
            "last_updated": "2026-01-01T00:00:00+00:00",
            "stale": False,
        }
        mocker.patch("services.exchange_rate_service.requests.get")
        result = _ERS().get_online_rates_for_display("USD", ("AED", "EUR"))
        assert result["source"] == "online"
        assert result["rates"]["AED"] == 3.67

    def test_primary_provider(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {
            "result": "success",
            "rates": {"USD": 1.0, "AED": 3.67, "EUR": 0.92, "ILS": 3.65},
        }
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        result = _ERS().get_online_rates_for_display("USD")
        assert result["ok"] is True
        assert result["provider"] == "primary"

    def test_static_fallback(self, mocker):
        mocker.patch.object(_ERS(), "_fetch_primary", return_value=None)
        mocker.patch.object(_ERS(), "_fetch_frankfurter", return_value=None)
        mocker.patch.object(_ERS(), "_fetch_fallbacks", return_value=None)
        result = _ERS().get_online_rates_for_display("USD", ("AED",))
        assert result["source"] == "fallback_static"
        assert result["rates"]["AED"] == _ERS().DISPLAY_FALLBACK["AED"]

    def test_stale_cache_when_apis_fail(self, mocker):
        _ERS()._display_cache["USD:AED"] = {
            "timestamp": 0,
            "rates": {"USD": 1.0, "AED": 3.5},
            "provider": "primary",
            "last_updated": "old",
            "stale": False,
        }
        mocker.patch.object(_ERS(), "_fetch_primary", return_value=None)
        mocker.patch.object(_ERS(), "_fetch_frankfurter", return_value=None)
        mocker.patch.object(_ERS(), "_fetch_fallbacks", return_value=None)
        result = _ERS().get_online_rates_for_display("USD", ("AED",))
        assert result["rates"]["AED"] == 3.5


class TestResolveTransactionRate:
    def test_fixed_rate(self):
        result = _ERS().resolve_exchange_rate_for_transaction(
            "USD",
            "AED",
            fixed_rate=Decimal("3.67"),
        )
        assert result["rate_mode"] == "frozen"
        assert result["rate"] == 3.67

    def test_user_rate(self):
        result = _ERS().resolve_exchange_rate_for_transaction(
            "USD",
            "AED",
            user_rate=3.68,
        )
        assert result["source"] == "user_manual"
        assert result["rate"] == 3.68

    def test_parity(self):
        result = _ERS().resolve_exchange_rate_for_transaction("AED", "AED")
        assert result["rate"] == 1.0
        assert result["source"] == "parity"

    def test_admin_rate(self, db_session, sample_tenant):
        record = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency="USD",
            to_currency="AED",
            rate=Decimal("3.65"),
            source="manual",
            effective_date=date.today(),
        )
        db_session.add(record)
        db_session.flush()
        result = _ERS().resolve_exchange_rate_for_transaction(
            "USD",
            "AED",
            tenant_id=sample_tenant.id,
        )
        assert result["source"] == "admin_manual"
        assert result["rate"] == 3.65

    def test_online_rate(self, mocker, sample_tenant):
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate",
            return_value=Decimal("3.67"),
        )
        result = _ERS().resolve_exchange_rate_for_transaction(
            "USD",
            "AED",
            tenant_id=sample_tenant.id,
        )
        assert result["source"] == "online_api"

    def test_last_known_rate(self, db_session, sample_tenant):
        record = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency="EUR",
            to_currency="AED",
            rate=Decimal("4.0"),
            source="api_primary",
            effective_date=date(2020, 1, 1),
        )
        db_session.add(record)
        db_session.flush()
        mocker_patch = patch.object(
            _ERS(), "_fetch_and_store_online_rate", return_value=None
        )
        with mocker_patch:
            result = _ERS().resolve_exchange_rate_for_transaction(
                "EUR",
                "AED",
                tenant_id=sample_tenant.id,
            )
        assert result["source"] == "last_record"

    def test_needs_input(self, mocker):
        mocker.patch.object(_ERS(), "_get_admin_rate", return_value=None)
        mocker.patch.object(_ERS(), "_fetch_and_store_online_rate", return_value=None)
        mocker.patch.object(_ERS(), "_get_last_known_rate", return_value=None)
        result = _ERS().resolve_exchange_rate_for_transaction("XYZ", "AED")
        assert result["rate_mode"] == "needs_input"
        assert result["ok"] is False

    def test_invalid_fixed_rate_falls_through(self, mocker):
        mocker.patch.object(_ERS(), "_get_admin_rate", return_value=3.67)
        result = _ERS().resolve_exchange_rate_for_transaction(
            "USD",
            "AED",
            fixed_rate="invalid",
        )
        assert result["source"] == "admin_manual"


class TestSaveAndLegacy:
    def test_save_rate_record_new(self, db_session, sample_tenant):
        _ERS()._save_rate_record("USD", "AED", 3.67, "api_primary", sample_tenant.id)
        rec = ExchangeRateRecord.query.filter_by(
            tenant_id=sample_tenant.id,
            from_currency="USD",
            to_currency="AED",
        ).first()
        assert rec is not None
        assert float(rec.rate) == 3.67

    def test_save_rate_record_update_existing(self, db_session, sample_tenant):
        existing = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency="USD",
            to_currency="AED",
            rate=Decimal("3.60"),
            source="api_primary",
            effective_date=date.today(),
        )
        db_session.add(existing)
        db_session.flush()
        _ERS()._save_rate_record("USD", "AED", 3.70, "api_primary", sample_tenant.id)
        db_session.refresh(existing)
        assert float(existing.rate) == 3.70

    def test_save_manual_rate_public(self, mocker):
        mocker.patch.object(_ERS(), "_save_rate_record")
        result = _ERS().save_manual_rate("USD", "AED", 3.67, tenant_id=1)
        assert result["ok"] is True

    def test_save_manual_rate_error(self, mocker):
        mocker.patch.object(
            _ERS(),
            "_save_rate_record",
            side_effect=RuntimeError("db"),
        )
        result = _ERS().save_manual_rate("USD", "AED", 3.67)
        assert result["ok"] is False

    def test_legacy_wrapper(self, mocker):
        mocker.patch.object(
            _ERS(),
            "resolve_exchange_rate_for_transaction",
            return_value={"rate": 3.67},
        )
        result = _ERS().get_manual_rate_for_calculation("USD", user_rate=3.67)
        assert result["rate"] == 3.67

    def test_fetch_primary_bad_status(self, mocker):
        mock_res = MagicMock(status_code=500)
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        assert _ERS()._fetch_primary("USD", ("AED",)) is None

    def test_frankfurter_bad_status(self, mocker):
        mock_res = MagicMock(status_code=500)
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        assert _ERS()._fetch_frankfurter("USD", ("AED",)) is None

    def test_requests_unavailable(self, mocker):
        mocker.patch("services.exchange_rate_service.REQUESTS_AVAILABLE", False)
        assert _ERS()._fetch_primary("USD", ("AED",)) is None
        assert _ERS()._fetch_frankfurter("USD", ("AED",)) is None
        assert _ERS()._fetch_fallbacks("USD", ("AED",)) is None

    def test_api_timeout_invalid_config(self, app):
        app.config["CURRENCY_API_TIMEOUT"] = "not-a-number"
        assert _ERS()._api_timeout() == 5

    def test_primary_non_success_result(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"result": "error", "rates": {}}
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        assert _ERS()._fetch_primary("USD", ("AED",)) is None

    def test_primary_invalid_rate_value_skipped(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {
            "result": "success",
            "rates": {"USD": 1.0, "AED": "bad"},
        }
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        assert _ERS()._fetch_primary("USD", ("AED",)) is None

    def test_frankfurter_provider_path(self, mocker):
        mocker.patch.object(_ERS(), "_fetch_primary", return_value=None)
        mocker.patch.object(
            _ERS(),
            "_fetch_frankfurter",
            return_value={"USD": 1.0, "AED": 3.67},
        )
        result = _ERS().get_online_rates_for_display("USD", ("AED",))
        assert result["provider"] == "frankfurter"

    def test_fallback_provider_path(self, mocker):
        mocker.patch.object(_ERS(), "_fetch_primary", return_value=None)
        mocker.patch.object(_ERS(), "_fetch_frankfurter", return_value=None)
        mocker.patch.object(
            _ERS(),
            "_fetch_fallbacks",
            return_value={"USD": 1.0, "AED": 3.67},
        )
        result = _ERS().get_online_rates_for_display("USD", ("AED",))
        assert result["provider"] == "fallback"

    def test_fallback_with_api_key(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = [
            "https://example.com/{base}?key={api_key}"
        ]
        app.config["CURRENCY_API_KEY"] = "secret"
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"rates": {"AED": 3.67}}
        get = mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        rates = _ERS()._fetch_fallbacks("USD", ("AED",))
        assert rates is not None
        assert "secret" in get.call_args.args[0]

    def test_fallback_skips_missing_api_key(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = [
            "https://example.com/{base}?key={api_key}"
        ]
        app.config["CURRENCY_API_KEY"] = ""
        get = mocker.patch("services.exchange_rate_service.requests.get")
        assert _ERS()._fetch_fallbacks("USD", ("AED",)) is None
        get.assert_not_called()

    def test_get_admin_rate_exception(self, mocker):
        chain = mocker.MagicMock()
        chain.filter_by.return_value.order_by.return_value.first.side_effect = (
            RuntimeError("db")
        )
        mocker.patch("models.ExchangeRateRecord.query", chain)
        assert _ERS()._get_admin_rate("USD", "AED", tenant_id=1) is None

    def test_fetch_and_store_online_rate_failure(self, mocker):
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate",
            side_effect=RuntimeError("api"),
        )
        assert _ERS()._fetch_and_store_online_rate("USD", "AED") is None

    def test_get_last_known_rate_exception(self, mocker):
        chain = mocker.MagicMock()
        chain.filter_by.return_value.order_by.return_value.first.side_effect = (
            RuntimeError("db")
        )
        mocker.patch("models.ExchangeRateRecord.query", chain)
        assert _ERS()._get_last_known_rate("USD", "AED") is None

    def test_save_rate_record_rollback_on_error(self, mocker, sample_tenant):
        chain = mocker.MagicMock()
        chain.filter_by.return_value.first.return_value = None
        mocker.patch("models.ExchangeRateRecord.query", chain)
        mocker.patch("extensions.db.session.commit", side_effect=RuntimeError("db"))
        mock_rollback = mocker.patch("extensions.db.session.rollback")
        _ERS()._save_rate_record("USD", "AED", 3.67, "api_primary", sample_tenant.id)
        mock_rollback.assert_called_once()

    def test_fetch_fallbacks_continues_on_url_error(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = [
            "https://bad.example/{base}",
            "https://good.example/{base}",
        ]
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"rates": {"AED": 3.67}}

        def _get(url, *args, **kwargs):
            if "bad.example" in url:
                raise RuntimeError("network")
            return mock_res

        mocker.patch("services.exchange_rate_service.requests.get", side_effect=_get)
        rates = _ERS()._fetch_fallbacks("USD", ("AED",))
        assert rates is not None
        assert rates["AED"] == 3.67

    def test_frankfurter_outer_exception(self, mocker):
        mocker.patch(
            "services.exchange_rate_service.requests.get",
            side_effect=RuntimeError("net"),
        )
        assert _ERS()._fetch_frankfurter("USD", ("AED",)) is None

    def test_frankfurter_invalid_float_skipped(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"rates": {"AED": "not-a-float", "EUR": 0.9}}
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        rates = _ERS()._fetch_frankfurter("USD", ("AED", "EUR"))
        assert rates is not None
        assert "EUR" in rates

    def test_fallback_non_200_status_continues(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = [
            "https://bad.example/{base}",
            "https://good.example/{base}",
        ]
        bad = MagicMock(status_code=500)
        good = MagicMock(status_code=200)
        good.json.return_value = {"rates": {"AED": 3.67}}
        mocker.patch(
            "services.exchange_rate_service.requests.get",
            side_effect=[bad, good],
        )
        rates = _ERS()._fetch_fallbacks("USD", ("AED",))
        assert rates is not None

    def test_fallback_base_currency_shape(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = ["https://example.com/{base}"]
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"USD": {"AED": 3.67}}
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        rates = _ERS()._fetch_fallbacks("USD", ("AED",))
        assert rates is not None

    def test_fallback_nested_jsdelivr_shape(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = ["https://example.com/{base}"]
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"usd": {"aed": 3.67}}
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        rates = _ERS()._fetch_fallbacks("USD", ("AED",))
        assert rates is not None

    def test_fallback_invalid_float_skipped(self, app, mocker):
        app.config["CURRENCY_API_FALLBACKS"] = ["https://example.com/{base}"]
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"rates": {"AED": "bad"}}
        mocker.patch(
            "services.exchange_rate_service.requests.get", return_value=mock_res
        )
        assert _ERS()._fetch_fallbacks("USD", ("AED",)) is None

    def test_user_rate_invalid_falls_through(self, mocker):
        mocker.patch.object(_ERS(), "_get_admin_rate", return_value=3.67)

        class _BadRate:
            def __str__(self):
                raise TypeError("bad user rate")

        result = _ERS().resolve_exchange_rate_for_transaction(
            "USD",
            "AED",
            user_rate=_BadRate(),
        )
        assert result["source"] == "admin_manual"

    def test_fixed_rate_invalid_string_falls_through(self, mocker):
        mocker.patch.object(_ERS(), "_get_admin_rate", return_value=3.67)
        result = _ERS().resolve_exchange_rate_for_transaction(
            "USD",
            "AED",
            fixed_rate={"bad": "object"},
        )
        assert result["source"] == "admin_manual"
