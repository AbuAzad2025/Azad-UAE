import re

# Fix purchase_service.py
path1 = r'D:\Data\karaj\UAE\Azad-UAE\services\purchase_service.py'
with open(path1, 'r', encoding='utf-8') as f:
    content1 = f.read()

old1 = """        rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
            currency,
            base_currency,
            user_rate=user_exchange_rate,
        )
        exchange_rate = Decimal(str(rate_info['rate']))"""

new1 = """        rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
            currency,
            base_currency,
            user_rate=user_exchange_rate,
            tenant_id=tenant_id,
        )
        if rate_info.get('rate_mode') == 'needs_input':
            raise ValueError(
                '⚠️ سعر الصرف غير متوفر.\\n'
                '💡 اذهب إلى إعدادات المالك ← أسعار الصرف ← أدخل سعر يدوي، '
                'أو أدخل سعراً في حقل "سعر الصرف".'
            )
        exchange_rate = Decimal(str(rate_info['rate']))"""

if old1 in content1:
    content1 = content1.replace(old1, new1)
    with open(path1, 'w', encoding='utf-8') as f:
        f.write(content1)
    print("purchase_service updated")
else:
    print("Pattern not found in purchase_service.py")

# Fix payment_service.py
path2 = r'D:\Data\karaj\UAE\Azad-UAE\services\payment_service.py'
with open(path2, 'r', encoding='utf-8') as f:
    content2 = f.read()

old2 = """    def _resolve_transaction_rate(currency, user_exchange_rate=None):
        from utils.currency_utils import get_system_default_currency
        rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
            currency,
            get_system_default_currency(),
            user_rate=user_exchange_rate,
        )
        return Decimal(str(rate_info['rate']))"""

new2 = """    def _resolve_transaction_rate(currency, user_exchange_rate=None, tenant_id=None):
        from utils.currency_utils import get_system_default_currency
        rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
            currency,
            get_system_default_currency(),
            user_rate=user_exchange_rate,
            tenant_id=tenant_id,
        )
        if rate_info.get('rate_mode') == 'needs_input':
            raise ValueError(
                '⚠️ سعر الصرف غير متوفر.\\n'
                '💡 اذهب إلى إعدادات المالك ← أسعار الصرف ← أدخل سعر يدوي، '
                'أو أدخل سعراً في حقل "سعر الصرف".'
            )
        return Decimal(str(rate_info['rate']))"""

if old2 in content2:
    content2 = content2.replace(old2, new2)
    with open(path2, 'w', encoding='utf-8') as f:
        f.write(content2)
    print("payment_service updated")
else:
    print("Pattern not found in payment_service.py")
