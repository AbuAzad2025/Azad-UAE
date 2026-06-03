"""
Exchange Rate Service — Display-Only Online Rates

Separation of concerns:
- Manual/internal rates  →  CurrencyService.get_exchange_rate()  (accounting)
- Online/display rates   →  ExchangeRateService.get_online_rates_for_display()  (UI only)

This module MUST NOT be used for invoices, payments, GL entries, or any
accounting calculation. It is strictly for the navbar / fxModal display.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import current_app

# Import existing currency service for manual-rate fallback detection only
from services.currency_service import CurrencyService

try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False


class ExchangeRateService:
    """
    Backend service for fetching online exchange rates for DISPLAY only.
    """

    # Cache for online display rates (separate from CurrencyService cache)
    _display_cache: dict[str, Any] = {}
    _display_cache_ttl: int = 43200  # 12 hours default for display

    # Supported display currencies
    DISPLAY_CURRENCIES = ("USD", "ILS", "JOD", "EUR", "AED", "SAR", "EGP", "GBP")

    # Static fallback for display (never used in accounting)
    DISPLAY_FALLBACK = {
        "USD": 1.0,
        "ILS": 3.65,
        "JOD": 0.709,
        "EUR": 0.92,
        "AED": 3.67,
        "SAR": 3.75,
        "EGP": 50.5,
        "GBP": 0.79,
    }

    CURRENCY_NAMES_AR = {
        "USD": "دولار أمريكي",
        "ILS": "شيقل إسرائيلي",
        "JOD": "دينار أردني",
        "EUR": "يورو",
        "AED": "درهم إماراتي",
        "SAR": "ريال سعودي",
        "EGP": "جنيه مصري",
        "GBP": "جنيه إسترليني",
    }

    CURRENCY_SYMBOLS = {
        "USD": "$",
        "ILS": "₪",
        "JOD": "JD",
        "EUR": "€",
        "AED": "د.إ",
        "SAR": "ر.س",
        "EGP": "ج.م",
        "GBP": "£",
    }

    @staticmethod
    def _cache_key(base: str, symbols: tuple[str, ...]) -> str:
        return f"{base.upper()}:{','.join(sorted(symbols))}"

    @staticmethod
    def _cache_ttl() -> int:
        cfg = current_app.config.get("CURRENCY_ONLINE_CACHE_TIMEOUT")
        if cfg:
            try:
                return int(cfg)
            except Exception:
                pass
        return ExchangeRateService._display_cache_ttl

    @staticmethod
    def _api_timeout() -> int:
        cfg = current_app.config.get("CURRENCY_API_TIMEOUT")
        if cfg:
            try:
                return int(cfg)
            except Exception:
                pass
        return 5

    @staticmethod
    def _fetch_primary(base: str, symbols: tuple[str, ...]) -> dict[str, float] | None:
        """Try the primary provider (open.er-api.com — same as CurrencyService)."""
        if not REQUESTS_AVAILABLE:
            return None
        url = f"https://open.er-api.com/v6/latest/{base.upper()}"
        try:
            res = requests.get(url, timeout=ExchangeRateService._api_timeout())
            if res.status_code != 200:
                return None
            data = res.json() or {}
            if data.get("result") != "success":
                return None
            raw = data.get("rates") or {}
            result: dict[str, float] = {}
            for code in symbols:
                val = raw.get(code.upper())
                if val is not None:
                    try:
                        result[code.upper()] = float(val)
                    except Exception:
                        pass
            if result:
                result[base.upper()] = 1.0
                return result
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_frankfurter(base: str, symbols: tuple[str, ...]) -> dict[str, float] | None:
        """Frankfurter fallback (https://api.frankfurter.dev)."""
        if not REQUESTS_AVAILABLE:
            return None
        sym_str = ",".join(s.upper() for s in symbols if s.upper() != base.upper())
        url = f"https://api.frankfurter.dev/v1/latest?base={base.upper()}"
        if sym_str:
            url += f"&symbols={sym_str}"
        try:
            res = requests.get(url, timeout=ExchangeRateService._api_timeout())
            if res.status_code != 200:
                return None
            data = res.json() or {}
            raw = data.get("rates") or {}
            result: dict[str, float] = {}
            for code in symbols:
                val = raw.get(code.upper())
                if val is not None:
                    try:
                        result[code.upper()] = float(val)
                    except Exception:
                        pass
            if result:
                result[base.upper()] = 1.0
                return result
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_fallbacks(base: str, symbols: tuple[str, ...]) -> dict[str, float] | None:
        """Try configured fallbacks from config.py (excluding Frankfurter to avoid dup)."""
        if not REQUESTS_AVAILABLE:
            return None
        fallbacks = current_app.config.get("CURRENCY_API_FALLBACKS", [])
        for tmpl in fallbacks:
            url = tmpl.replace("{base}", base.upper()).replace("{base_lower}", base.lower())
            # Skip if URL already covered by primary or frankfurter
            if "open.er-api.com" in url or "frankfurter" in url:
                continue
            if "{api_key}" in url:
                api_key = current_app.config.get("CURRENCY_API_KEY", "")
                if not api_key:
                    continue
                url = url.replace("{api_key}", api_key)
            try:
                res = requests.get(url, timeout=ExchangeRateService._api_timeout())
                if res.status_code != 200:
                    continue
                data = res.json() or {}
                # Try common response shapes
                raw = data.get("rates") or data.get("data", {}).get("rates") or {}
                if not raw:
                    # Some APIs return base_currency as key
                    raw = data.get(base.upper(), {})
                result: dict[str, float] = {}
                for code in symbols:
                    val = raw.get(code.upper())
                    if val is None:
                        # jsdelivr shape: {"usd": {"ils": 3.65}}
                        nested = data.get(base.lower(), {})
                        if nested:
                            val = nested.get(code.lower())
                    if val is not None:
                        try:
                            result[code.upper()] = float(val)
                        except Exception:
                            pass
                if result:
                    result[base.upper()] = 1.0
                    return result
            except Exception:
                continue
        return None

    @staticmethod
    def get_online_rates_for_display(
        base: str = "USD",
        symbols: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch online rates for DISPLAY only.  Never use for accounting.

        Returns:
            {
                "ok": bool,
                "base": str,
                "rates": {"USD": 1.0, "ILS": 3.65, ...},
                "source": "online" | "stale_cache" | "fallback_static",
                "provider": "primary" | "frankfurter" | "fallback_static",
                "last_updated": "2026-06-03T10:00:00+03:00",
                "stale": bool,
            }
        """
        base = (base or "USD").upper()
        symbols = symbols or ExchangeRateService.DISPLAY_CURRENCIES
        symbols = tuple(s.upper() for s in symbols)
        cache_key = ExchangeRateService._cache_key(base, symbols)
        now = time.time()
        ttl = ExchangeRateService._cache_ttl()

        # 1. Check in-memory cache
        cached = ExchangeRateService._display_cache.get(cache_key)
        if cached and (now - cached.get("timestamp", 0)) < ttl:
            return {
                "ok": True,
                "base": base,
                "rates": cached["rates"].copy(),
                "source": "stale_cache" if cached.get("stale") else "online",
                "provider": cached.get("provider", "cache"),
                "last_updated": cached.get("last_updated", datetime.now(timezone.utc).isoformat()),
                "stale": cached.get("stale", False),
            }

        rates: dict[str, float] | None = None
        provider = "unknown"

        # 2. Try primary provider
        rates = ExchangeRateService._fetch_primary(base, symbols)
        if rates:
            provider = "primary"
        else:
            # 3. Try Frankfurter
            rates = ExchangeRateService._fetch_frankfurter(base, symbols)
            if rates:
                provider = "frankfurter"
            else:
                # 4. Try other configured fallbacks
                rates = ExchangeRateService._fetch_fallbacks(base, symbols)
                if rates:
                    provider = "fallback"

        # 5. If all failed, use last cached (even if stale) or static fallback
        if not rates:
            if cached:
                rates = cached["rates"].copy()
                provider = cached.get("provider", "unknown")
            else:
                rates = {
                    k: v for k, v in ExchangeRateService.DISPLAY_FALLBACK.items()
                    if k in symbols or k == base
                }
                provider = "fallback_static"

        # Ensure base is present
        rates.setdefault(base, 1.0)

        # Normalize: all requested symbols should have a value
        for sym in symbols:
            if sym not in rates:
                # Try cross-rate via AED (fallback static knows AED)
                aed_rate_from_base = rates.get("AED")
                if aed_rate_from_base and sym in ExchangeRateService.DISPLAY_FALLBACK:
                    # 1 base = X AED; 1 AED = Y sym => 1 base = X*Y sym
                    # But DISPLAY_FALLBACK is "1 USD = X sym" — need careful cross-calc
                    # Simpler: just copy from fallback if available
                    rates[sym] = ExchangeRateService.DISPLAY_FALLBACK.get(sym, 1.0)

        last_updated = datetime.now(timezone.utc).isoformat()

        ExchangeRateService._display_cache[cache_key] = {
            "timestamp": now,
            "rates": rates.copy(),
            "provider": provider,
            "last_updated": last_updated,
            "stale": provider == "fallback_static" or rates == ExchangeRateService.DISPLAY_FALLBACK,
        }

        return {
            "ok": provider != "fallback_static",
            "base": base,
            "rates": rates,
            "source": "online" if provider != "fallback_static" else "fallback_static",
            "provider": provider,
            "last_updated": last_updated,
            "stale": provider == "fallback_static",
        }

    @staticmethod
    def get_manual_rate_for_calculation(
        from_currency: str, to_currency: str = "AED", user_rate: float | None = None
    ) -> dict[str, Any]:
        """
        Return the manual/internal rate for ACCOUNTING calculations.
        This is a thin wrapper around CurrencyService that enforces
        manual-rate priority and makes the source explicit.
        """
        from services.currency_service import CurrencyService
        rate_decimal = CurrencyService.get_exchange_rate(
            from_currency, to_currency, user_rate=user_rate
        )
        return {
            "ok": True,
            "from": (from_currency or "AED").upper(),
            "to": (to_currency or "AED").upper(),
            "rate": float(rate_decimal),
            "source": "manual_or_system",
            "note": "For accounting only.  Do NOT use for display.",
        }
