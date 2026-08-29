import re

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The corrupted line has non-printable characters
# Find and replace the corrupted flash message
old_pattern = r'flash\(gettext\([^)]+\)\)'
new_text = 'flash(gettext("\u062a\u0645 \u062d\u0641\u0638 \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0637\u0628\u0627\u0639\u0629"), "success")'

# Use regex to find the corrupted flash line
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'flash(gettext' in line and ('O' in line or '\ufffd' in line):
        lines[i] = '        flash(gettext("\u062a\u0645 \u062d\u0641\u0638 \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0637\u0628\u0627\u0639\u0629"), "success")'
        print(f'Fixed line {i+1}')

content = '\n'.join(lines)

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('Done')