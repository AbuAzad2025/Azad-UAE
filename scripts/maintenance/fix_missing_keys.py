import re

path = r'D:\Data\karaj\UAE\Azad-UAE\utils\i18n.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the last entry before the closing brace
old = "    'View_All': {'ar': 'عرض الكل', 'en': 'View_All'},\n}"
new = """    'View_All': {'ar': 'عرض الكل', 'en': 'View_All'},

    'Table': {'ar': 'الجدول', 'en': 'Table'},
    'City': {'ar': 'المدينة', 'en': 'City'},
    'Country': {'ar': 'الدولة', 'en': 'Country'},
    'Other': {'ar': 'أخرى', 'en': 'Other'},
    'System Settings': {'ar': 'إعدادات النظام', 'en': 'System Settings'},
    'Full Name': {'ar': 'الاسم الكامل', 'en': 'Full Name'},
    'Not Specified': {'ar': 'غير محدد', 'en': 'Not Specified'},
}"""

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added missing keys')
else:
    print('Pattern not found, trying alternative')
    # Try with just the closing brace
    old2 = "    'View_All': {'ar': 'عرض الكل', 'en': 'View_All'},\n}\n\n\n\n\ndef t(key, **kwargs):"
    new2 = """    'View_All': {'ar': 'عرض الكل', 'en': 'View_All'},

    'Table': {'ar': 'الجدول', 'en': 'Table'},
    'City': {'ar': 'المدينة', 'en': 'City'},
    'Country': {'ar': 'الدولة', 'en': 'Country'},
    'Other': {'ar': 'أخرى', 'en': 'Other'},
    'System Settings': {'ar': 'إعدادات النظام', 'en': 'System Settings'},
    'Full Name': {'ar': 'الاسم الكامل', 'en': 'Full Name'},
    'Not Specified': {'ar': 'غير محدد', 'en': 'Not Specified'},
}




def t(key, **kwargs):"""
    if old2 in content:
        content = content.replace(old2, new2)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('Added missing keys (alt)')
    else:
        print('Still not found')
        # Print last 10 chars of line 2344 and first 10 chars of line 2345
        lines = content.split('\n')
        print(f"Line 2344 end: [{lines[2343][-30:]}]")
        print(f"Line 2345 start: [{lines[2344][:30]}]")
