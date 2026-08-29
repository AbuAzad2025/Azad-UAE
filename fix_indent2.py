with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Line 365 (index 364) - fix flash message
lines[364] = '        flash(gettext("\u062a\u0645 \u062d\u0641\u0638 \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0637\u0628\u0627\u0639\u0629"), "success")\n'

# Line 366 (index 365) - fix return redirect indentation
if not lines[365].startswith('        '):
    lines[365] = '        ' + lines[365].lstrip()

# Line 368 (index 367) - fix return render_template indentation
if len(lines) > 367 and not lines[367].startswith('    '):
    lines[367] = '    ' + lines[367].lstrip()

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done')