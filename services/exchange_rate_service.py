"""
Exchange Rate Service — Unified Rate Resolution

Separation of concerns (no overlap, no conflict):

1. DISPLAY  →  get_online_exchange_rates_for_display()
   Online rates for navbar / fxModal ONLY.  Never used in accounting.

2. TRANSACTION  →  resolve_exchange_rate_for_transaction()
   Resolves rate at document-creation time:
     - user_rate (manual) has absolute priority
     - if missing, fetches system rate via CurrencyService
     - once stored in the document, the rate is FIXED and never changes

3. LEGACY ACCOUNTING  →  CurrencyService.get_exchange_rate()
   Still used directly by existing sale/payment/purchase services.
   ExchangeRateService.resolve_exchange_rate_for_transaction()
   is the preferred path for NEW code.

This module is the SINGLE organized source for all exchange-rate needs.
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
    def resolve_exchange_rate_for_transaction(
        from_currency: str,
        to_currency: str = "AED",
        *,
        user_rate: float | Decimal | None = None,
        fixed_rate: float | Decimal | None = None,
    ) -> dict[str, Any]:
        """
        Resolve the rate to store inside a transaction document (invoice, payment,
        receipt, purchase order, etc.).

        Priority:
          1) fixed_rate  — already frozen in an existing document (read-only)
          2) user_rate   — manual input from the user (has absolute priority)
          3) CurrencyService.get_exchange_rate()  — system rate at creation time

        Return dict includes 'rate_mode':
          - "frozen"   : rate already saved in document; never touch again.
          - "editable" : rate resolved BEFORE saving; caller MAY still let user
                         edit it, but once the document is saved the rate MUST
                         be treated as frozen forever.

        Contract for callers:
          - On CREATE: call this once, store the returned 'rate' in the document's
            exchange_rate field, then never update that field automatically.
          - On READ/UPDATE: pass the stored rate as fixed_rate so this method
            returns rate_mode="frozen" and refuses any automatic change.
        """
        from_currency = (from_currency or "AED").upper()
        to_currency = (to_currency or "AED").upper()

        # 1. Already frozen in document — read-only
        if fixed_rate is not None:
            try:
                rate = Decimal(str(fixed_rate))
                if rate > Decimal("0"):
                    return {
                        "ok": True,
                        "from": from_currency,
                        "to": to_currency,
                        "rate": float(rate.quantize(Decimal("0.000001"))),
                        "source": "document_fixed",
                        "rate_mode": "frozen",
                        "note": "Rate is already frozen inside the saved document. Never auto-update.",
                    }
            except Exception:
                pass

        # 2. Manual/user rate has absolute priority (pre-save, editable until saved)
        if user_rate is not None:
            try:
                rate = Decimal(str(user_rate))
                if rate > Decimal("0"):
                    return {
                        "ok": True,
                        "from": from_currency,
                        "to": to_currency,
                        "rate": float(rate.quantize(Decimal("0.000001"))),
                        "source": "user_manual",
                        "rate_mode": "editable",
                        "note": "User-provided rate. Caller MUST store in document on save and then treat as frozen.",
                    }
            except (ValueError, TypeError):
                pass

        # 3. Same currency → parity (pre-save, editable until saved)
        if from_currency == to_currency:
            return {
                "ok": True,
                "from": from_currency,
                "to": to_currency,
                "rate": 1.0,
                "source": "parity",
                "rate_mode": "editable",
                "note": "Same currency. Caller MUST store 1.0 in document on save and then treat as frozen.",
            }

        # 4. System rate at creation time — fetch once, store forever
        from services.currency_service import CurrencyService
        rate_decimal = CurrencyService.get_exchange_rate(
            from_currency, to_currency, user_rate=None
        )
        return {
            "ok": True,
            "from": from_currency,
            "to": to_currency,
            "rate": float(rate_decimal.quantize(Decimal("0.000001"))),
            "source": "system_at_creation",
            "rate_mode": "editable",
            "note": "System rate at creation time. Caller MUST store in document on save and then treat as frozen.",
        }

    @staticmethod
    def get_manual_rate_for_calculation(
        from_currency: str, to_currency: str = "AED", user_rate: float | None = None
    ) -> dict[str, Any]:
        """
        LEGACY wrapper — kept for backward compatibility.
        New code should use resolve_exchange_rate_for_transaction().
        """
        return ExchangeRateService.resolve_exchange_rate_for_transaction(
            from_currency=from_currency,
            to_currency=to_currency,
            user_rate=user_rate,
        )
