"""Unified storefront pricing — single source of truth for customer-facing prices.

Every storefront entry point (catalog, product page, cart, checkout, quick view,
search API) MUST resolve prices through this service so customers see one
consistent converted price everywhere (fixes audit issue D1).

Price pipeline: product.regular_price (tenant base currency)
    → converted to the store display currency (TenantStore.display_currency
      or tenant.default_currency) via the live/recorded exchange rate
    → quantized to 2 decimals for display.

Fallback policy (fixes audit issue D4 — no more silent rate=1):
    1. CurrencyService.get_exchange_rate_details (live providers + cache)
    2. ExchangeRateService.get_latest_rate (last stored tenant/system record)
    3. Give up: log a warning and return the UNCONVERTED base price so the
       merchant never shows a silently wrong conversion.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


class StorePricingService:
    @staticmethod
    def _as_currency_code(value) -> str:
        """Coerce to an ISO currency code string; anything non-string becomes ''."""
        if not isinstance(value, str):
            return ""
        return value.strip().upper()

    @staticmethod
    def resolve_display_currency(store, tenant) -> str:
        """Store display currency: explicit store setting, else tenant default, else tenant base."""
        explicit = StorePricingService._as_currency_code(getattr(store, "display_currency", None))
        if explicit:
            return explicit
        default = StorePricingService._as_currency_code(getattr(tenant, "default_currency", None))
        if default:
            return default
        return StorePricingService._base_currency(tenant)

    @staticmethod
    def _base_currency(tenant) -> str:
        if tenant is not None and hasattr(tenant, "get_base_currency"):
            getter = tenant.get_base_currency
            value = getter() if callable(getter) else getter
            code = StorePricingService._as_currency_code(value)
            if code:
                return code
        return StorePricingService._as_currency_code(
            getattr(tenant, "base_currency", None) or getattr(tenant, "default_currency", None)
        )

    @staticmethod
    def _resolve_rate(from_currency: str, to_currency: str) -> Decimal | None:
        """Live/recorded rate with logged, graceful degradation. None when unresolvable."""
        try:
            from services.currency_service import CurrencyService

            info = CurrencyService.get_exchange_rate_details(from_currency, to_currency)
            rate_raw = info.get("rate") or (info.get("rates") or {}).get(to_currency)
            if rate_raw and Decimal(str(rate_raw)) > 0:
                return Decimal(str(rate_raw))
        except Exception:
            logger.warning(
                "Storefront pricing: live rate %s -> %s unavailable, trying last stored record",
                from_currency,
                to_currency,
                exc_info=True,
            )
        try:
            from services.exchange_rate_service import ExchangeRateService

            stored = ExchangeRateService.get_latest_rate(from_currency, to_currency)
            if stored and Decimal(str(stored)) > 0:
                return Decimal(str(stored))
        except Exception:
            logger.warning(
                "Storefront pricing: stored rate %s -> %s unavailable",
                from_currency,
                to_currency,
                exc_info=True,
            )
        logger.warning(
            "Storefront pricing: NO rate for %s -> %s — displaying unconverted base price",
            from_currency,
            to_currency,
        )
        return None

    @staticmethod
    def convert_amount(amount, tenant, target_currency: str | None = None) -> Decimal:
        """Convert any base-currency amount to the target display currency (2 decimals)."""
        value = Decimal(str(amount or 0))
        base = StorePricingService._base_currency(tenant)
        target = StorePricingService._as_currency_code(target_currency) or base
        if not target or target == base:
            return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        rate = StorePricingService._resolve_rate(base, target)
        if rate is None:
            return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return (value * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    @staticmethod
    def resolve_display_price(product, tenant, target_currency: str | None = None) -> Decimal:
        """Convert product.regular_price (base currency) to the target display currency.

        Returns a 2-decimal Decimal. When no rate exists the unconverted base
        price is returned (never a fabricated rate=1 conversion).
        """
        price = Decimal(str(getattr(product, "regular_price", None) or 0))
        return StorePricingService.convert_amount(price, tenant, target_currency)

    @staticmethod
    def resolve_display_price_for_store(product, store, tenant) -> Decimal:
        """Convenience wrapper bound to the store's resolved display currency."""
        return StorePricingService.resolve_display_price(
            product,
            tenant,
            StorePricingService.resolve_display_currency(store, tenant),
        )
