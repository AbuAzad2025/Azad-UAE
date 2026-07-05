with open(r'D:\Data\karaj\UAE\Azad-UAE\templates\owner\dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("{{{ t('Table') }}}", "{{ t('Table') }}")
content = content.replace("{{{ t('Date') }}}", "{{ t('Date') }}")

with open(r'D:\Data\karaj\UAE\Azad-UAE\templates\owner\dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed remaining triple braces')
