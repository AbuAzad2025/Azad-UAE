from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from extensions import db
from models import ExchangeRateRecord
from services.exchange_rate_service import ExchangeRateService


@pytest.fixture(autouse=True)
def _clear_display_cache():
    ExchangeRateService._display_cache.clear()
    yield
    ExchangeRateService._display_cache.clear()


class TestCacheHelpers:
    def test_cache_key(self):
        key = ExchangeRateService._cache_key('usd', ('EUR', 'AED'))
        assert key == 'USD:AED,EUR'

    def test_cache_ttl_from_config(self, app):
        app.config['CURRENCY_ONLINE_CACHE_TIMEOUT'] = '120'
        assert ExchangeRateService._cache_ttl() == 120

    def test_cache_ttl_invalid_config(self, app):
        app.config['CURRENCY_ONLINE_CACHE_TIMEOUT'] = 'bad'
        assert ExchangeRateService._cache_ttl() == ExchangeRateService._display_cache_ttl

    def test_api_timeout_from_config(self, app):
        app.config['CURRENCY_API_TIMEOUT'] = '9'
        assert ExchangeRateService._api_timeout() == 9


class TestFetchProviders:
    def test_fetch_primary_success(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {
            'result': 'success',
            'rates': {'USD': 1.0, 'AED': 3.67, 'EUR': 0.92},
        }
        mocker.patch('services.exchange_rate_service.requests.get', return_value=mock_res)
        rates = ExchangeRateService._fetch_primary('USD', ('AED', 'EUR'))
        assert rates is not None
        assert rates['AED'] == 3.67

    def test_fetch_primary_failure(self, mocker):
        mocker.patch('services.exchange_rate_service.requests.get', side_effect=RuntimeError('net'))
        assert ExchangeRateService._fetch_primary('USD', ('AED',)) is None

    def test_fetch_frankfurter_success(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {'rates': {'AED': 3.67}}
        mocker.patch('services.exchange_rate_service.requests.get', return_value=mock_res)
        rates = ExchangeRateService._fetch_frankfurter('USD', ('AED',))
        assert rates is not None

    def test_fetch_fallbacks_configured(self, app, mocker):
        app.config['CURRENCY_API_FALLBACKS'] = ['https://example.com/{base}']
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {'rates': {'AED': 3.67}}
        mocker.patch('services.exchange_rate_service.requests.get', return_value=mock_res)
        rates = ExchangeRateService._fetch_fallbacks('USD', ('AED',))
        assert rates is not None

    def test_fetch_fallbacks_skips_dup_urls(self, app, mocker):
        app.config['CURRENCY_API_FALLBACKS'] = [
            'https://open.er-api.com/v6/latest/{base}',
            'https://api.frankfurter.dev/v1/latest?base={base}',
        ]
        get = mocker.patch('services.exchange_rate_service.requests.get')
        assert ExchangeRateService._fetch_fallbacks('USD', ('AED',)) is None
        get.assert_not_called()


class TestDisplayRates:
    def test_cache_hit(self, mocker):
        ExchangeRateService._display_cache['USD:AED,EUR'] = {
            'timestamp': __import__('time').time(),
            'rates': {'USD': 1.0, 'AED': 3.67, 'EUR': 0.92},
            'provider': 'primary',
            'last_updated': '2026-01-01T00:00:00+00:00',
            'stale': False,
        }
        mocker.patch('services.exchange_rate_service.requests.get')
        result = ExchangeRateService.get_online_rates_for_display('USD', ('AED', 'EUR'))
        assert result['source'] == 'online'
        assert result['rates']['AED'] == 3.67

    def test_primary_provider(self, mocker):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {
            'result': 'success',
            'rates': {'USD': 1.0, 'AED': 3.67, 'EUR': 0.92, 'ILS': 3.65},
        }
        mocker.patch('services.exchange_rate_service.requests.get', return_value=mock_res)
        result = ExchangeRateService.get_online_rates_for_display('USD')
        assert result['ok'] is True
        assert result['provider'] == 'primary'

    def test_static_fallback(self, mocker):
        mocker.patch.object(ExchangeRateService, '_fetch_primary', return_value=None)
        mocker.patch.object(ExchangeRateService, '_fetch_frankfurter', return_value=None)
        mocker.patch.object(ExchangeRateService, '_fetch_fallbacks', return_value=None)
        result = ExchangeRateService.get_online_rates_for_display('USD', ('AED',))
        assert result['source'] == 'fallback_static'
        assert result['rates']['AED'] == ExchangeRateService.DISPLAY_FALLBACK['AED']

    def test_stale_cache_when_apis_fail(self, mocker):
        ExchangeRateService._display_cache['USD:AED'] = {
            'timestamp': 0,
            'rates': {'USD': 1.0, 'AED': 3.5},
            'provider': 'primary',
            'last_updated': 'old',
            'stale': False,
        }
        mocker.patch.object(ExchangeRateService, '_fetch_primary', return_value=None)
        mocker.patch.object(ExchangeRateService, '_fetch_frankfurter', return_value=None)
        mocker.patch.object(ExchangeRateService, '_fetch_fallbacks', return_value=None)
        result = ExchangeRateService.get_online_rates_for_display('USD', ('AED',))
        assert result['rates']['AED'] == 3.5


class TestResolveTransactionRate:
    def test_fixed_rate(self):
        result = ExchangeRateService.resolve_exchange_rate_for_transaction(
            'USD', 'AED', fixed_rate=Decimal('3.67'),
        )
        assert result['rate_mode'] == 'frozen'
        assert result['rate'] == 3.67

    def test_user_rate(self):
        result = ExchangeRateService.resolve_exchange_rate_for_transaction(
            'USD', 'AED', user_rate=3.68,
        )
        assert result['source'] == 'user_manual'
        assert result['rate'] == 3.68

    def test_parity(self):
        result = ExchangeRateService.resolve_exchange_rate_for_transaction('AED', 'AED')
        assert result['rate'] == 1.0
        assert result['source'] == 'parity'

    def test_admin_rate(self, db_session, sample_tenant):
        record = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency='USD',
            to_currency='AED',
            rate=Decimal('3.65'),
            source='manual',
            effective_date=date.today(),
        )
        db_session.add(record)
        db_session.flush()
        result = ExchangeRateService.resolve_exchange_rate_for_transaction(
            'USD', 'AED', tenant_id=sample_tenant.id,
        )
        assert result['source'] == 'admin_manual'
        assert result['rate'] == 3.65

    def test_online_rate(self, mocker, sample_tenant):
        mocker.patch(
            'services.currency_service.CurrencyService.get_exchange_rate',
            return_value=Decimal('3.67'),
        )
        result = ExchangeRateService.resolve_exchange_rate_for_transaction(
            'USD', 'AED', tenant_id=sample_tenant.id,
        )
        assert result['source'] == 'online_api'

    def test_last_known_rate(self, db_session, sample_tenant):
        record = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency='EUR',
            to_currency='AED',
            rate=Decimal('4.0'),
            source='api_primary',
            effective_date=date(2020, 1, 1),
        )
        db_session.add(record)
        db_session.flush()
        mocker_patch = patch.object(ExchangeRateService, '_fetch_and_store_online_rate', return_value=None)
        with mocker_patch:
            result = ExchangeRateService.resolve_exchange_rate_for_transaction(
                'EUR', 'AED', tenant_id=sample_tenant.id,
            )
        assert result['source'] == 'last_record'

    def test_needs_input(self, mocker):
        mocker.patch.object(ExchangeRateService, '_get_admin_rate', return_value=None)
        mocker.patch.object(ExchangeRateService, '_fetch_and_store_online_rate', return_value=None)
        mocker.patch.object(ExchangeRateService, '_get_last_known_rate', return_value=None)
        result = ExchangeRateService.resolve_exchange_rate_for_transaction('XYZ', 'AED')
        assert result['rate_mode'] == 'needs_input'
        assert result['ok'] is False

    def test_invalid_fixed_rate_falls_through(self, mocker):
        mocker.patch.object(ExchangeRateService, '_get_admin_rate', return_value=3.67)
        result = ExchangeRateService.resolve_exchange_rate_for_transaction(
            'USD', 'AED', fixed_rate='invalid',
        )
        assert result['source'] == 'admin_manual'


class TestSaveAndLegacy:
    def test_save_rate_record_new(self, db_session, sample_tenant):
        ExchangeRateService._save_rate_record('USD', 'AED', 3.67, 'api_primary', sample_tenant.id)
        rec = ExchangeRateRecord.query.filter_by(
            tenant_id=sample_tenant.id, from_currency='USD', to_currency='AED',
        ).first()
        assert rec is not None
        assert float(rec.rate) == 3.67

    def test_save_rate_record_update_existing(self, db_session, sample_tenant):
        existing = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency='USD',
            to_currency='AED',
            rate=Decimal('3.60'),
            source='api_primary',
            effective_date=date.today(),
        )
        db_session.add(existing)
        db_session.flush()
        ExchangeRateService._save_rate_record('USD', 'AED', 3.70, 'api_primary', sample_tenant.id)
        db_session.refresh(existing)
        assert float(existing.rate) == 3.70

    def test_save_manual_rate_public(self, mocker):
        mocker.patch.object(ExchangeRateService, '_save_rate_record')
        result = ExchangeRateService.save_manual_rate('USD', 'AED', 3.67, tenant_id=1)
        assert result['ok'] is True

    def test_save_manual_rate_error(self, mocker):
        mocker.patch.object(
            ExchangeRateService, '_save_rate_record', side_effect=RuntimeError('db'),
        )
        result = ExchangeRateService.save_manual_rate('USD', 'AED', 3.67)
        assert result['ok'] is False

    def test_legacy_wrapper(self, mocker):
        mocker.patch.object(
            ExchangeRateService,
            'resolve_exchange_rate_for_transaction',
            return_value={'rate': 3.67},
        )
        result = ExchangeRateService.get_manual_rate_for_calculation('USD', user_rate=3.67)
        assert result['rate'] == 3.67

    def test_fetch_primary_bad_status(self, mocker):
        mock_res = MagicMock(status_code=500)
        mocker.patch('services.exchange_rate_service.requests.get', return_value=mock_res)
        assert ExchangeRateService._fetch_primary('USD', ('AED',)) is None

    def test_frankfurter_bad_status(self, mocker):
        mock_res = MagicMock(status_code=500)
        mocker.patch('services.exchange_rate_service.requests.get', return_value=mock_res)
        assert ExchangeRateService._fetch_frankfurter('USD', ('AED',)) is None
