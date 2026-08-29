with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'flash(gettext' in line and 'تم حفظ' in line:
        lines[i] = '        flash(gettext("\u062a\u0645 \u062d\u0641\u0638 \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0637\u0628\u0627\u0639\u0629"), "success")\n'
        print(f'Fixed flash at line {i+1}')
    if 'return render_template("printing/settings.html"' in line:
        if not line.startswith('    '):
            lines[i] = '    ' + line.lstrip()
            print(f'Fixed indent at line {i+1}')

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done')