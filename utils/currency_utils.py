from config import Config


def get_system_default_currency() -> str:
    return getattr(Config, 'DEFAULT_CURRENCY', None) or 'AED'


def resolve_default_currency(tenant=None) -> str:
    if tenant and hasattr(tenant, 'default_currency'):
        val = (tenant.default_currency or '').strip()
        if val:
            return val.upper()
    try:
        from models.system_settings import SystemSettings
        settings = SystemSettings.get_current()
        val = (getattr(settings, 'default_currency', None) or '').strip()
        if val:
            return val.upper()
    except Exception:
        pass
    return get_system_default_currency()


def get_currency_symbol(code):
    from utils.constants import CURRENCIES
    for c_code, data in CURRENCIES:
        if c_code == code:
            return data.get('symbol', code)
    return code


def get_currency_name_ar(code):
    from utils.constants import CURRENCIES
    for c_code, data in CURRENCIES:
        if c_code == code:
            return data.get('ar', code)
    return code
