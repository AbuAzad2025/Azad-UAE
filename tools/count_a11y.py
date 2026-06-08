"""Count remaining accessibility issues on disk (bypassing IDE cache)."""
import os
import re


def count_issues(templates_dir):
    inputs_no_label = 0
    selects_no_label = 0
    textareas_no_label = 0
    buttons_no_text = 0
    files_with_issues = set()

    input_pat = re.compile(r'<input\s+[^>]*?>', re.IGNORECASE)
    select_pat = re.compile(r'<select\s+[^>]*?>', re.IGNORECASE)
    textarea_pat = re.compile(r'<textarea\s+[^>]*?>', re.IGNORECASE)
    btn_pat = re.compile(r'<button\s+[^>]*?>\s*<i\s+class="[^"]*fa[^"]*"[^>]*>\s*</i>\s*</button>', re.IGNORECASE)

    for root, _, files in os.walk(templates_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            for m in input_pat.finditer(content):
                tag = m.group(0).lower()
                if 'type="hidden"' in tag:
                    continue
                if 'aria-label=' not in tag and 'title=' not in tag and 'placeholder=' not in tag and 'id=' not in tag:
                    inputs_no_label += 1
                    files_with_issues.add(fpath)
            for m in select_pat.finditer(content):
                tag = m.group(0).lower()
                if 'aria-label=' not in tag and 'title=' not in tag:
                    selects_no_label += 1
                    files_with_issues.add(fpath)
            for m in textarea_pat.finditer(content):
                tag = m.group(0).lower()
                if 'aria-label=' not in tag and 'title=' not in tag and 'placeholder=' not in tag:
                    textareas_no_label += 1
                    files_with_issues.add(fpath)
            for m in btn_pat.finditer(content):
                tag = m.group(0).lower()
                if 'title=' not in tag and 'aria-label=' not in tag:
                    buttons_no_text += 1
                    files_with_issues.add(fpath)

    print(f'Inputs without label:    {inputs_no_label}')
    print(f'Selects without label:   {selects_no_label}')
    print(f'Textareas without label: {textareas_no_label}')
    print(f'Icon buttons no text:    {buttons_no_text}')
    print(f'Total real a11y issues:  {inputs_no_label + selects_no_label + textareas_no_label + buttons_no_text}')
    print(f'Files affected:          {len(files_with_issues)}')
    for fp in sorted(files_with_issues):
        print('  - ' + fp)


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    count_issues(os.path.join(root, 'templates'))
