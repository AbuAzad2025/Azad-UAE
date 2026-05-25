from decimal import Decimal, ROUND_HALF_UP
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

class CurrencyService:
    
    CACHE_TTL_SECONDS = 300  # 5 دقائق
    _rates_cache = {}
    
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
        'ILS': Decimal('0.98')  # 1 AED = 0.98 ILS (approx 1 ILS = 1.02 AED)
    }

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
    def get_all_rates(base='AED'):
        base = (base or 'AED').upper()
        
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
    def get_exchange_rate(from_currency, to_currency='AED', user_rate=None):
        """
        Get exchange rate between two currencies.
        Prioritises user-supplied rate, then checks CACHE, then live Forex,
        and finally uses static fallback rates.
        """
        if not from_currency: from_currency = 'AED'
        if not to_currency: to_currency = 'AED'

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        # 1. Smart Handling for User Rate (Priority #1)
        # Only use user_rate if it is explicitly provided, valid, and positive.
        # If it's None, 0, empty string, or invalid, we fall back to system rates.
        if user_rate is not None:
            try:
                rate = Decimal(str(user_rate))
                if rate > Decimal('0'):
                    return rate.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
            except (ValueError, TypeError):
                # Invalid user input (e.g. "abc"), ignore it and proceed to system rate
                pass

        if from_currency == to_currency:
            return Decimal('1')

        # 2. Online / Fallback (Priority #2)
        # Skip cache logic as requested. Fetch fresh or use fallback immediately.
        # This ensures we either get the LATEST live rate or the RELIABLE fallback.
        
        # Try fetching live rates
        if FOREX_AVAILABLE:
            try:
                c = CurrencyRates()
                # Attempt to get direct rate
                rate = c.get_rate(from_currency, to_currency)
                return Decimal(str(rate)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
            except Exception as e:
                # Log error if possible
                pass

        http_rates = CurrencyService._fetch_open_er_api_rates(from_currency)
        if http_rates:
            rate = http_rates.get(to_currency)
            if rate and rate > Decimal("0"):
                CurrencyService._rates_cache[from_currency] = {'timestamp': time.time(), 'rates': http_rates}
                return Decimal(str(rate)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        
        # Fallback to static rates
        def get_aed_value(target):
            if target == 'AED': return Decimal('1')
            return CurrencyService.FALLBACK_RATES.get(target, Decimal('1'))

        val_target = get_aed_value(to_currency)
        val_base = get_aed_value(from_currency)
        
        # Cross rate: Base -> Target
        return (val_target / val_base).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
