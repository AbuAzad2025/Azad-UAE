with open(r'D:\Data\karaj\UAE\Azad-UAE\templates\invoices\modern.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '<div class="erp-modern-bank-box" style="border-right: 3px solid {{ settings.header_color if settings else \'#667eea\' }};">',
    '<div class="erp-modern-bank-box erp-invoice-accent-border">'
)
content = content.replace(
    '<p class="erp-invoice-bank-title" style="color: {{ settings.header_color if settings else \'#667eea\' }};">',
    '<p class="erp-invoice-bank-title erp-invoice-accent-color">'
)

with open(r'D:\Data\karaj\UAE\Azad-UAE\templates\invoices\modern.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
