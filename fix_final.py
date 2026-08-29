with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Line 365 (index 364) - flash message: indent should be 12
lines[364] = '            flash(gettext("\u062a\u0645 \u062d\u0641\u0638 \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0637\u0628\u0627\u0639\u0629"), "success")\n'

# Line 366 - return redirect
lines[365] = '            return redirect(url_for("printing.print_settings"))\n'

# Line 367 (empty line) - index 366
lines[366] = '\n'

# Line 368 (index 367) - return render_template - already correct at 4 spaces
if not lines[367].startswith('    '):
    lines[367] = '    ' + lines[367].lstrip()

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done')