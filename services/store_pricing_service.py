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
        """Display a product at the price checkout actually charges (audit #1).

        This used to convert ``product.regular_price`` through ``convert_amount``
        independently of the checkout resolver, so the basket could show one
        number while the sale booked another (and explicit per-currency
        ``StoreProductPrice`` overrides were ignored on display). It now goes
        through the same ``resolve_store_price`` resolver the checkout uses,
        quantised to the 2 decimals the storefront templates render.
        """
        price = StorePricingService.resolve_store_price(product, tenant, target_currency)
        return (price if price is not None else Decimal("0")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    @staticmethod
    def resolve_display_price_for_store(product, store, tenant) -> Decimal:
        """Convenience wrapper bound to the store's resolved display currency."""
        return StorePricingService.resolve_display_price(
            product,
            tenant,
            StorePricingService.resolve_display_currency(store, tenant),
        )

    @staticmethod
    def resolve_store_price(product, tenant, currency_code: str | None = None) -> Decimal | None:
        """Resolve the storefront price for a product in a given currency.

        Priority:
        1. Explicit StoreProductPrice for (tenant, product, currency) if active
        2. Fallback: product.regular_price (tenant base currency) converted via
           the live/stored exchange rate to currency_code

        Returns a 3-decimal Decimal (store pricing precision), or None when no
        price can be resolved.
        """
        currency_code = StorePricingService._as_currency_code(currency_code)
        if not currency_code:
            currency_code = StorePricingService._base_currency(tenant)

        # 1. Explicit per-currency store price
        try:
            from models.store_product_price import StoreProductPrice

            price_row = (
                StoreProductPrice.query.filter_by(
                    tenant_id=int(tenant.id),
                    product_id=int(product.id),
                    currency_code=currency_code,
                    is_active=True,
                )
                .order_by(StoreProductPrice.is_default.desc(), StoreProductPrice.updated_at.desc())
                .first()
            )
            if price_row:
                return Decimal(str(price_row.price)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        except Exception:
            logger.warning(
                "StoreProductPrice lookup failed for product %s ccy %s",
                getattr(product, "id", None),
                currency_code,
                exc_info=True,
            )

        # 2. Fallback: convert base-currency regular_price
        base_price = Decimal(str(getattr(product, "regular_price", None) or 0))
        return StorePricingService.convert_amount(base_price, tenant, currency_code).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )

    @staticmethod
    def resolve_store_currency_rate(tenant, currency_code: str | None = None) -> Decimal:
        """Transaction-currency → base rate that matches ``resolve_store_price``.

        ``resolve_store_price`` converts a base-currency price into
        ``currency_code`` with the base→target rate from ``_resolve_rate`` (the
        same rate, live then stored, that ``convert_amount`` uses). A sale
        created in ``currency_code`` must therefore store the reciprocal so
        ``Sale.calculate_totals`` converts the charged amount back to the
        tenant base exactly once — no double conversion (audit finding #1).

        When the currency is the base (or no rate can be resolved) the pricing
        resolver falls back to the unconverted base price, so parity is the
        matching rate in that case too.
        """
        currency_code = StorePricingService._as_currency_code(currency_code)
        base = StorePricingService._base_currency(tenant)
        if not currency_code or not base or currency_code == base:
            return Decimal("1")
        base_to_target = StorePricingService._resolve_rate(base, currency_code)
        if base_to_target is None:
            return Decimal("1")
        return (Decimal("1") / base_to_target).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
