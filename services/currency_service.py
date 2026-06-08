"""
CurrencyService — LEGACY INTERNAL PROVIDER

This module fetches system exchange rates for ACCOUNTING calculations.
It is NOT the public API for exchange-rate resolution.

For NEW code, use:
  - ExchangeRateService.resolve_exchange_rate_for_transaction()  (for invoices/payments)
  - ExchangeRateService.get_online_exchange_rates_for_display()  (for navbar only)

CurrencyService remains as the low-level provider that those methods call
when a system rate is needed. Do NOT call it directly from routes/forms.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import time

try:
    from forex_python.converter import CurrencyRates
    FOREX_AVAILABLE = True
except ImportError:
    FOREX_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False

from utils.currency_utils import get_system_default_currency


class CurrencyService:
    
    CACHE_TTL_SECONDS = 300  # 5 دقائق
    _rates_cache = {}
    
    # Fallback rates: value of 1 AED in target currency
    # Updated ILS: 1 AED ≈ 1.05 ILS (was 0.98, which implied 1 ILS = 1.02 AED — incorrect)
    FALLBACK_RATES = {
        'AED': Decimal('1.00'),
        'USD': Decimal('0.27'),
        'EUR': Decimal('0.25'),
        'GBP': Decimal('0.22'),
        'SAR': Decimal('1.02'),
        'KWD': Decimal('0.08'),
        'BHD': Decimal('0.10'),
        'OMR': Decimal('0.10'),
        'QAR': Decimal('0.99'),
        'ILS': Decimal('1.05'),  # 1 AED ≈ 1.05 ILS (approx 1 ILS = 0.952 AED)
    }
    COMMON_CURRENCIES = (
        'AED', 'USD', 'EUR', 'GBP', 'SAR', 'QAR', 'KWD', 'BHD', 'OMR', 'ILS',
        'JPY', 'CNY', 'INR', 'TRY', 'EGP', 'JOD',
    )
    CURRENCY_NAMES = {
        'AED': 'UAE Dirham',
        'USD': 'US Dollar',
        'EUR': 'Euro',
        'GBP': 'British Pound',
        'SAR': 'Saudi Riyal',
        'QAR': 'Qatari Riyal',
        'KWD': 'Kuwaiti Dinar',
        'BHD': 'Bahraini Dinar',
        'OMR': 'Omani Rial',
        'ILS': 'Israeli Shekel',
        'JPY': 'Japanese Yen',
        'CNY': 'Chinese Yuan',
        'INR': 'Indian Rupee',
        'TRY': 'Turkish Lira',
        'EGP': 'Egyptian Pound',
        'JOD': 'Jordanian Dinar',
    }

    @staticmethod
    def get_supported_currencies() -> list[str]:
        codes = set(CurrencyService.FALLBACK_RATES.keys())
        for base in ('USD', 'AED', 'EUR'):
            rates = CurrencyService.get_all_rates(base)
            codes.update(str(k).upper() for k in (rates or {}).keys())
        codes.update(CurrencyService.COMMON_CURRENCIES)
        return sorted(c for c in codes if len(c) == 3 and c.isalpha())

    @staticmethod
    def get_currency_label(code: str) -> str:
        code = str(code or '').upper()
        return f"{code} - {CurrencyService.CURRENCY_NAMES.get(code, 'Currency')}"

    @staticmethod
    def _fetch_open_er_api_rates(base: str) -> dict:
        if not REQUESTS_AVAILABLE:
            return {}
        base = (base or "AED").upper()
        url = f"https://open.er-api.com/v6/latest/{base}"
        try:
            res = requests.get(url, timeout=4)
            if res.status_code != 200:
                return {}
            data = res.json() or {}
            if data.get("result") != "success":
                return {}
            raw_rates = data.get("rates") or {}
            rates: dict[str, Decimal] = {}
            for code, rate in raw_rates.items():
                try:
                    rates[str(code).upper()] = Decimal(str(rate))
                except Exception:
                    continue
            rates[base] = Decimal("1.00")
            return rates
        except Exception:
            return {}
    
    @staticmethod
    def get_all_rates(base=None):
        base = (base or get_system_default_currency()).upper()
        
        # Check cache first
        cache_entry = CurrencyService._rates_cache.get(base)
        if cache_entry and (time.time() - cache_entry['timestamp']) < CurrencyService.CACHE_TTL_SECONDS:
            return cache_entry['rates'].copy()
        
        rates = {}
        
        # Try fetching live rates
        if FOREX_AVAILABLE:
            try:
                c = CurrencyRates()
                # get_rates returns a dict of rates for the base currency
                # This is a SINGLE API call, much faster than a loop
                fetched_rates = c.get_rates(base)
                
                # Convert to Decimal
                for curr, rate in fetched_rates.items():
                    rates[curr] = Decimal(str(rate))
                
                # Ensure base currency is 1.0
                rates[base] = Decimal('1.00')
                
                # Cache the result
                CurrencyService._rates_cache[base] = {'timestamp': time.time(), 'rates': rates}
                return rates.copy()
            except Exception as e:
                # Log error if possible, or just continue to fallback
                print(f"Forex API failed: {e}")

        http_rates = CurrencyService._fetch_open_er_api_rates(base)
        if http_rates:
            CurrencyService._rates_cache[base] = {'timestamp': time.time(), 'rates': http_rates}
            return http_rates.copy()
        
        # Fallback if API fails or not available
        # Recalculate fallback rates based on the requested base
        # Our static FALLBACK_RATES are "Value of 1 AED in X Currency"
        
        # Helper to get value of 1 AED in Target Currency
        def get_aed_value(target):
            if target == 'AED': return Decimal('1')
            return CurrencyService.FALLBACK_RATES.get(target, Decimal('1'))

        base_aed_val = get_aed_value(base) # How many Target units for 1 AED
        
        # We want: How many Target units for 1 Base unit?
        # Rate = (1 AED in Target) / (1 AED in Base)
        # Wait, if FALLBACK is "1 AED = X Target"
        # Then "1 Base = (1 AED in Base) units"
        # 1 Base = (1/Base_AED_Val) AED
        # Value in Target = (1/Base_AED_Val) * (Target_AED_Val)
        
        target_currencies = ['USD', 'EUR', 'GBP', 'SAR', 'KWD', 'BHD', 'OMR', 'QAR', 'AED']
        
        for curr in target_currencies:
            if curr == base:
                rates[curr] = Decimal('1.00')
            else:
                # Calculate Cross Rate from Fallback
                val_target = get_aed_value(curr)
                val_base = get_aed_value(base)
                
                # Cross rate: Base -> Target
                # 1 Base = (val_target / val_base) Target
                rates[curr] = (val_target / val_base).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)

        CurrencyService._rates_cache[base] = {'timestamp': time.time(), 'rates': rates}
        return rates

    @staticmethod
    def get_exchange_rate_details(from_currency, to_currency='AED', user_rate=None):
        """
        Detailed exchange-rate resolver with source metadata.
        Source priority:
          1) user input
          2) parity for same currency
          3) fresh in-memory cache
          4) live HTTP provider (open.er-api.com)
          5) forex-python provider
          6) static fallback table
        """
        if not from_currency:
            from_currency = 'AED'
        if not to_currency:
            to_currency = 'AED'

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        now_ts = time.time()

        if user_rate is not None:
            try:
                rate = Decimal(str(user_rate))
                if rate > Decimal('0'):
                    return {
                        'rate': rate.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP),
                        'source': 'user_input',
                        'cached': False,
                        'age_seconds': 0,
                    }
            except (ValueError, TypeError, InvalidOperation):
                pass

        if from_currency == to_currency:
            return {
                'rate': Decimal('1.000000'),
                'source': 'parity',
                'cached': False,
                'age_seconds': 0,
            }

        cache_entry = CurrencyService._rates_cache.get(from_currency)
        if cache_entry:
            age = max(0, int(now_ts - float(cache_entry.get('timestamp', 0))))
            cached_rates = cache_entry.get('rates') or {}
            cached_rate = cached_rates.get(to_currency)
            if cached_rate and age < CurrencyService.CACHE_TTL_SECONDS:
                return {
                    'rate': Decimal(str(cached_rate)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP),
                    'source': 'cache',
                    'cached': True,
                    'age_seconds': age,
                }

        http_rates = CurrencyService._fetch_open_er_api_rates(from_currency)
        if http_rates:
            CurrencyService._rates_cache[from_currency] = {'timestamp': now_ts, 'rates': http_rates}
            rate = http_rates.get(to_currency)
            if rate and rate > Decimal("0"):
                return {
                    'rate': Decimal(str(rate)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP),
                    'source': 'open_er_api',
                    'cached': False,
                    'age_seconds': 0,
                }

        if FOREX_AVAILABLE:
            try:
                c = CurrencyRates()
                rate = c.get_rate(from_currency, to_currency)
                rate = Decimal(str(rate)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
                CurrencyService._rates_cache[from_currency] = {
                    'timestamp': now_ts,
                    'rates': {from_currency: Decimal('1.000000'), to_currency: rate},
                }
                return {
                    'rate': rate,
                    'source': 'forex_python',
                    'cached': False,
                    'age_seconds': 0,
                }
            except Exception:
                pass

        def get_aed_value(target):
            if target == 'AED':
                return Decimal('1')
            return CurrencyService.FALLBACK_RATES.get(target, Decimal('1'))

        val_target = get_aed_value(to_currency)
        val_base = get_aed_value(from_currency)
        fallback_rate = (val_target / val_base).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        return {
            'rate': fallback_rate,
            'source': 'fallback_static',
            'cached': False,
            'age_seconds': 0,
        }

    @staticmethod
    def get_exchange_rate(from_currency, to_currency='AED', user_rate=None):
        details = CurrencyService.get_exchange_rate_details(from_currency, to_currency, user_rate=user_rate)
        return details['rate']
