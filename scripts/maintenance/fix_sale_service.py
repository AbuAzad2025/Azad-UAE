import re

path = r'D:\Data\karaj\UAE\Azad-UAE\services\sale_service.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = """            rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
                currency,
                base_currency,
                user_rate=user_exchange_rate,
            )
            exchange_rate = Decimal(str(rate_info['rate']))"""

new = """            rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
                currency,
                base_currency,
                user_rate=user_exchange_rate,
                tenant_id=tenant_id,
            )
            if rate_info.get('rate_mode') == 'needs_input':
                raise ValueError(
                    '⚠️ سعر الصرف غير متوفر.\\n'
                    '💡 اذهب إلى إعدادات المالك ← أسعار الصرف ← أدخل سعر يدوي، '
                    'أو أدخل سعراً في حقل "سعر الصرف" بالفاتورة.'
                )
            exchange_rate = Decimal(str(rate_info['rate']))"""

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("sale_service updated")
else:
    print("Pattern not found in sale_service.py")
