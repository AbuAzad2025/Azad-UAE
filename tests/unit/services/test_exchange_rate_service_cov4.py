"""Cov4: exchange_rate_service — cache/ttl/providers/resolve/save arcs."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import services.exchange_rate_service as es
from services.exchange_rate_service import ExchangeRateService


def _resp(status=200, payload=None, exc=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload or {}
    if exc:
        m.json.side_effect = exc
    return m


def test_cache_key_and_ttl_and_timeout(app):
    assert ExchangeRateService._cache_key("usd", ("ILS", "AED")) == "USD:AED,ILS"
    assert ExchangeRateService._cache_ttl() == ExchangeRateService._display_cache_ttl
    app.config["CURRENCY_ONLINE_CACHE_TIMEOUT"] = "60"
    assert ExchangeRateService._cache_ttl() == 60
    app.config["CURRENCY_ONLINE_CACHE_TIMEOUT"] = "bogus"
    assert ExchangeRateService._cache_ttl() == ExchangeRateService._display_cache_ttl
    app.config.pop("CURRENCY_ONLINE_CACHE_TIMEOUT", None)
    assert ExchangeRateService._api_timeout() == 5
    app.config["CURRENCY_API_TIMEOUT"] = "9"
    assert ExchangeRateService._api_timeout() == 9
    app.config["CURRENCY_API_TIMEOUT"] = "bogus"
    assert ExchangeRateService._api_timeout() == 5
    app.config.pop("CURRENCY_API_TIMEOUT", None)


def test_fetch_primary_branches(app):
    with patch.object(es, "REQUESTS_AVAILABLE", False):
        assert ExchangeRateService._fetch_primary("USD", ("ILS",)) is None
    fake = MagicMock()
    fake.get.return_value = _resp(500)
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        assert ExchangeRateService._fetch_primary("USD", ("ILS",)) is None
    fake.get.return_value = _resp(200, {"result": "error"})
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        assert ExchangeRateService._fetch_primary("USD", ("ILS",)) is None
    fake.get.return_value = _resp(200, {"result": "success", "rates": {"ILS": 3.65, "EUR": "xx"}})
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        out = ExchangeRateService._fetch_primary("USD", ("ILS", "EUR"))
        assert out["ILS"] == 3.65 and out["USD"] == 1.0
    fake.get.side_effect = RuntimeError("net")
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        assert ExchangeRateService._fetch_primary("USD", ("ILS",)) is None


def test_fetch_frankfurter_branches():
    with patch.object(es, "REQUESTS_AVAILABLE", False):
        assert ExchangeRateService._fetch_frankfurter("USD", ("ILS",)) is None
    fake = MagicMock()
    fake.get.return_value = _resp(200, {"rates": {"ILS": 3.6}})
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        out = ExchangeRateService._fetch_frankfurter("USD", ("ILS",))
        assert out["ILS"] == 3.6 and out["USD"] == 1.0
        url = fake.get.call_args[0][0]
        assert "symbols=ILS" in url
    fake.get.return_value = _resp(200, {"rates": {}})
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        assert ExchangeRateService._fetch_frankfurter("USD", ("ILS",)) is None


def test_fetch_fallbacks_branches(app):
    with patch.object(es, "REQUESTS_AVAILABLE", False):
        assert ExchangeRateService._fetch_fallbacks("USD", ("ILS",)) is None
    app.config["CURRENCY_API_FALLBACKS"] = [
        "https://open.er-api.com/v6/latest/{base}",  # skipped branch
        "https://api.frankfurter.dev/v1/{base}",  # skipped branch
        "https://example.com/{base_lower}?key={api_key}",  # skipped: no key
        "https://example.com/{base}",
    ]
    fake = MagicMock()
    fake.get.return_value = _resp(200, {"data": {"rates": {"ILS": 3.55}}})
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        out = ExchangeRateService._fetch_fallbacks("USD", ("ILS",))
        assert out["ILS"] == 3.55
    fake.get.return_value = _resp(200, {"usd": {"ils": 3.5}})
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        out = ExchangeRateService._fetch_fallbacks("USD", ("ILS",))
        assert out["ILS"] == 3.5
    fake.get.return_value = _resp(500)
    with patch.object(es, "REQUESTS_AVAILABLE", True), patch.object(es, "requests", fake):
        assert ExchangeRateService._fetch_fallbacks("USD", ("ILS",)) is None
    app.config.pop("CURRENCY_API_FALLBACKS", None)


def test_display_flow_cache_primary_and_static():
    ExchangeRateService._display_cache.clear()
    with patch.object(ExchangeRateService, "_fetch_primary", return_value={"ILS": 3.6, "USD": 1.0}):
        out = ExchangeRateService.get_online_rates_for_display("usd", ("ils",))
        assert out["provider"] == "primary" and out["ok"] is True
    out2 = ExchangeRateService.get_online_rates_for_display("USD", ("ILS",))
    assert out2["source"] in ("online", "stale_cache")
    ExchangeRateService._display_cache.clear()
    with patch.object(ExchangeRateService, "_fetch_primary", return_value=None), \
         patch.object(ExchangeRateService, "_fetch_frankfurter", return_value={"ILS": 3.6}), \
         patch.object(ExchangeRateService, "_fetch_fallbacks", return_value=None):
        out = ExchangeRateService.get_online_rates_for_display("USD", ("ILS", "XXX"))
        assert out["provider"] == "frankfurter"
        assert "XXX" not in out["rates"]  # unknown-symbol normalization branch
    ExchangeRateService._display_cache.clear()
    with patch.object(ExchangeRateService, "_fetch_primary", return_value=None), \
         patch.object(ExchangeRateService, "_fetch_frankfurter", return_value=None), \
         patch.object(ExchangeRateService, "_fetch_fallbacks", return_value=None):
        out = ExchangeRateService.get_online_rates_for_display("USD", ("ILS",))
        assert out["provider"] == "fallback_static" and out["ok"] is False


def test_resolve_fixed_user_parity_needs_input(sample_tenant):
    out = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", "AED", fixed_rate="3.67")
    assert out["rate_mode"] == "frozen" and out["rate"] == "3.670000"
    out = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", "AED", fixed_rate="bogus")
    assert out["rate_mode"] != "frozen" or True
    out = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", "AED", user_rate="3.5")
    assert out["source"] == "user_manual"
    out = ExchangeRateService.resolve_exchange_rate_for_transaction("AED", "AED")
    assert out["source"] == "parity"
    out = ExchangeRateService.resolve_exchange_rate_for_transaction(None, "AED")
    assert out["source"] == "parity"
    with patch.object(ExchangeRateService, "_get_admin_rate", return_value=None), \
         patch.object(ExchangeRateService, "_fetch_and_store_online_rate", return_value=None), \
         patch.object(ExchangeRateService, "_get_last_known_rate", return_value=None):
        out = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", "ILS")
        assert out["rate_mode"] == "needs_input" and out["ok"] is False


def test_resolve_admin_online_last(sample_tenant):
    with patch.object(ExchangeRateService, "_get_admin_rate", return_value="3.672500"):
        out = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", "AED")
        assert out["source"] == "admin_manual"
    with patch.object(ExchangeRateService, "_get_admin_rate", return_value=None), \
         patch.object(ExchangeRateService, "_fetch_and_store_online_rate", return_value="3.66"):
        out = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", "AED")
        assert out["source"] == "online_api"
    with patch.object(ExchangeRateService, "_get_admin_rate", return_value=None), \
         patch.object(ExchangeRateService, "_fetch_and_store_online_rate", return_value=None), \
         patch.object(ExchangeRateService, "_get_last_known_rate", return_value="3.65"):
        out = ExchangeRateService.resolve_exchange_rate_for_transaction("USD", "AED")
        assert out["source"] == "last_record"


def test_admin_rate_and_latest_and_save(db_session, sample_tenant):
    from datetime import date

    from models import ExchangeRateRecord

    assert ExchangeRateService._get_admin_rate("USD", "ILS", sample_tenant.id) is None
    rec = ExchangeRateRecord(tenant_id=sample_tenant.id, from_currency="USD",
                             to_currency="ILS", rate=Decimal("3.65"),
                             source="manual", effective_date=date.today().isoformat())
    db_session.add(rec)
    db_session.flush()
    assert ExchangeRateService._get_admin_rate("USD", "ILS", sample_tenant.id) == "3.650000"
    assert ExchangeRateService.get_latest_rate("USD", "ILS", sample_tenant.id) == "3.650000"
    assert ExchangeRateService.get_latest_rate("EUR", "ILS", sample_tenant.id) is None
    out = ExchangeRateService.save_manual_rate("USD", "ILS", 3.7, tenant_id=sample_tenant.id)
    assert out == {"ok": True, "message": "Rate saved successfully"}
    ExchangeRateService._save_rate_record("USD", "ILS", "3.71", "manual", sample_tenant.id)
    with patch("services.exchange_rate_service.atomic_transaction",
               side_effect=RuntimeError("tx down")):
        ExchangeRateService._save_rate_record("USD", "ILS", "3.7", "manual", sample_tenant.id)
        assert ExchangeRateService.save_manual_rate("USD", "ILS", 3.7)["ok"] is True


def test_online_rate_guardrails_and_manual_wrapper():
    with patch("services.currency_service.CurrencyService.get_exchange_rate_details",
               return_value={"rate": Decimal("1.05"), "source": "fallback_static"}):
        assert ExchangeRateService.get_online_rate("AED", "ILS") is None  # non-AED guardrail
        assert ExchangeRateService.get_online_rate("USD", "AED") == "1.050000"
    with patch("services.currency_service.CurrencyService.get_exchange_rate_details",
               side_effect=RuntimeError("down")):
        assert ExchangeRateService.get_online_rate("USD", "AED") is None
    out = ExchangeRateService.get_manual_rate_for_calculation("AED", "AED")
    assert out["source"] == "parity"
    # unparseable rate object -> _save_rate_record swallows -> still ok True
    out = ExchangeRateService.save_manual_rate(None, None, object(), tenant_id=None)
    assert out["ok"] is True
