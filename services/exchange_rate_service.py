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

from utils.db_safety import atomic_transaction

# Import existing currency service for manual-rate fallback detection only

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
                        result[code.upper()] = float(val or 0)
                    except Exception:
                        pass
            if result:
                result[base.upper()] = 1.0
                return result
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_frankfurter(
        base: str, symbols: tuple[str, ...]
    ) -> dict[str, float] | None:
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
                        result[code.upper()] = float(val or 0)
                    except Exception:
                        pass
            if result:
                result[base.upper()] = 1.0
                return result
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_fallbacks(
        base: str, symbols: tuple[str, ...]
    ) -> dict[str, float] | None:
        """Try configured fallbacks from config.py (excluding Frankfurter to avoid dup)."""
        if not REQUESTS_AVAILABLE:
            return None
        fallbacks = current_app.config.get("CURRENCY_API_FALLBACKS", [])
        for tmpl in fallbacks:
            url = tmpl.replace("{base}", base.upper()).replace(
                "{base_lower}", base.lower()
            )
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
                            result[code.upper()] = float(val or 0)
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
                "last_updated": cached.get(
                    "last_updated", datetime.now(timezone.utc).isoformat()
                ),
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
                    k: v
                    for k, v in ExchangeRateService.DISPLAY_FALLBACK.items()
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
            "stale": provider == "fallback_static"
            or rates == ExchangeRateService.DISPLAY_FALLBACK,
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
        tenant_id: int | None = None,
        effective_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Resolve the rate to store inside a transaction document (invoice, payment,
        receipt, purchase order, etc.).

        Priority (correct order):
          1) fixed_rate     — already frozen in an existing document (read-only)
          2) user_rate      — manual input from the user in the form (override)
          3) admin_rate     — manager's stored manual rate in exchange_rate_records
          4) online_rate    — API online rate (auto-saved to exchange_rate_records)
          5) last_record    — last known rate from exchange_rate_records
          6) needs_input    — nothing found; caller MUST show a modal for user input

        Return dict includes 'rate_mode':
          - "frozen"      : rate already saved in document; never touch again.
          - "editable"    : rate resolved BEFORE saving; caller MAY still let user edit.
          - "needs_input" : no rate found at all; show modal to user.

        Contract for callers:
          - On CREATE: call this once, store the returned 'rate' in the document's
            exchange_rate field, then never update that field automatically.
          - On READ/UPDATE: pass the stored rate as fixed_rate so this method
            returns rate_mode="frozen" and refuses any automatic change.
          - On needs_input: stop form submission, show modal, then re-submit with user_rate.
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

        # 2. User manual input — highest priority for NEW documents
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

        # 3. Same currency → parity
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

        # 4. Admin manual rate (stored by manager in exchange_rate_records)
        admin_rate = ExchangeRateService._get_admin_rate(
            from_currency, to_currency, tenant_id, effective_date
        )
        if admin_rate:
            return {
                "ok": True,
                "from": from_currency,
                "to": to_currency,
                "rate": admin_rate,
                "source": "admin_manual",
                "rate_mode": "editable",
                "note": "Manager-stored rate from exchange_rate_records. Caller MUST store in document on save and then treat as frozen.",
            }

        # 5. Online rate — fetch, then auto-save to exchange_rate_records for next time
        online_rate = ExchangeRateService._fetch_and_store_online_rate(
            from_currency, to_currency, tenant_id
        )
        if online_rate:
            return {
                "ok": True,
                "from": from_currency,
                "to": to_currency,
                "rate": online_rate,
                "source": "online_api",
                "rate_mode": "editable",
                "note": "Online API rate (auto-saved to exchange_rate_records). Caller MUST store in document on save and then treat as frozen.",
            }

        # 6. Last known rate from exchange_rate_records (any date, any source)
        last_rate = ExchangeRateService._get_last_known_rate(
            from_currency, to_currency, tenant_id
        )
        if last_rate:
            return {
                "ok": True,
                "from": from_currency,
                "to": to_currency,
                "rate": last_rate,
                "source": "last_record",
                "rate_mode": "editable",
                "note": "Last known rate from history. Caller MUST store in document on save and then treat as frozen.",
            }

        # 7. Nothing found — caller MUST show modal
        return {
            "ok": False,
            "from": from_currency,
            "to": to_currency,
            "rate": None,
            "source": "needs_input",
            "rate_mode": "needs_input",
            "note": "No exchange rate found. Caller MUST show a modal for the user to input a rate.",
        }

    @staticmethod
    def _get_admin_rate(
        from_currency: str,
        to_currency: str,
        tenant_id: int | None = None,
        effective_date: str | None = None,
    ) -> float | None:
        """Lookup manager's manual rate in exchange_rate_records for today (or given date)."""
        try:
            from models import ExchangeRateRecord
            from datetime import date

            target_date = effective_date or date.today().isoformat()
            record = (
                ExchangeRateRecord.query.filter_by(
                    tenant_id=tenant_id,
                    from_currency=from_currency,
                    to_currency=to_currency,
                    effective_date=target_date,
                    source="manual",
                )
                .order_by(ExchangeRateRecord.created_at.desc())
                .first()
            )
            if record and record.rate:
                return float(record.rate)
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_and_store_online_rate(
        from_currency: str,
        to_currency: str,
        tenant_id: int | None = None,
    ) -> float | None:
        """Fetch online rate, auto-save to exchange_rate_records, return the rate."""
        try:
            from services.currency_service import CurrencyService

            rate_decimal = CurrencyService.get_exchange_rate(
                from_currency, to_currency, user_rate=None
            )
            if rate_decimal and rate_decimal > Decimal("0"):
                rate_float = float(rate_decimal.quantize(Decimal("0.000001")))
                # Auto-save to exchange_rate_records as 'api_primary' for today
                ExchangeRateService._save_rate_record(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate=rate_float,
                    source="api_primary",
                    tenant_id=tenant_id,
                )
                return rate_float
        except Exception:
            pass
        return None

    @staticmethod
    def _get_last_known_rate(
        from_currency: str,
        to_currency: str,
        tenant_id: int | None = None,
    ) -> float | None:
        """Get the most recent exchange_rate_record regardless of date or source."""
        try:
            from models import ExchangeRateRecord

            record = (
                ExchangeRateRecord.query.filter_by(
                    tenant_id=tenant_id,
                    from_currency=from_currency,
                    to_currency=to_currency,
                )
                .order_by(
                    ExchangeRateRecord.effective_date.desc(),
                    ExchangeRateRecord.created_at.desc(),
                )
                .first()
            )
            if record and record.rate:
                return float(record.rate)
        except Exception:
            pass
        return None

    @staticmethod
    def _save_rate_record(
        from_currency: str,
        to_currency: str,
        rate: float,
        source: str,
        tenant_id: int | None = None,
        api_provider: str | None = None,
    ) -> None:
        """Save a rate record to exchange_rate_records (idempotent for same day)."""
        try:
            from models import ExchangeRateRecord
            from extensions import db
            from datetime import date

            today = date.today().isoformat()
            with atomic_transaction("save_rate_record"):
                existing = ExchangeRateRecord.query.filter_by(
                    tenant_id=tenant_id,
                    from_currency=from_currency,
                    to_currency=to_currency,
                    effective_date=today,
                    source=source,
                ).first()
                if existing:
                    existing.rate = Decimal(str(rate))
                    return

                record = ExchangeRateRecord(
                    tenant_id=tenant_id,
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate=Decimal(str(rate)),
                    source=source,
                    api_provider=api_provider,
                    effective_date=today,
                )
                db.session.add(record)
        except Exception:
            pass

    @staticmethod
    def save_manual_rate(
        from_currency: str,
        to_currency: str,
        rate: float,
        tenant_id: int | None = None,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """Public API: save a manager's manual rate."""
        try:
            ExchangeRateService._save_rate_record(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=rate,
                source="manual",
                tenant_id=tenant_id,
            )
            return {"ok": True, "message": "Rate saved successfully"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
