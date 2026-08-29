import re

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the corrupted Arabic flash message
old = 'flash(gettext("O\ufffdU. O-U?O, O\ufffdO1O_O\ufffdO1Oc O\u0015U,O\ufffdO"O\u0015O1Oc"), "success")'
new = 'flash(gettext("\u062a\u0645 \u062d\u0641\u0638 \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0637\u0628\u0627\u0639\u0629"), "success")'

if old in content:
    content = content.replace(old, new)
    print("Replaced corrupted flash message")
else:
    # Search for the pattern
    for i, line in enumerate(content.splitlines()):
        if 'flash(gettext' in line and 'O' in line and 'U. O-U' in line:
            print(f'Found at line {i+1}: {repr(line)}')

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')