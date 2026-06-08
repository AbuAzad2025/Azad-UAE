"""Apply D3 client-side form validation: add needs-validation class to forms with inputs."""
import os
import re

FORM_RE = re.compile(r'<form\b', re.IGNORECASE)
NEEDS_VAL_RE = re.compile(r'class="[^"]*needs-validation[^"]*"', re.IGNORECASE)


def process(path: str) -> bool:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if NEEDS_VAL_RE.search(content):
        return False  # already has validation
    if not FORM_RE.search(content):
        return False  # no form
    # Skip print templates and error pages
    if '/invoices/' in path or '/receipts/' in path or '/errors/' in path:
        return False
    # Add needs-validation to first <form> tag
    def _repl(m):
        tag = m.group(0)
        if 'class=' in tag:
            return re.sub(r'class="([^"]*)"', lambda cm: f'class="{cm.group(1)} needs-validation"', tag, count=1)
        else:
            return tag + ' class="needs-validation"'
    new_content = FORM_RE.sub(_repl, content, count=1)
    if new_content == content:
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'  +needs-validation: {os.path.relpath(path, "templates")}')
    return True


def main():
    total = 0
    modified = 0
    for r, _, fs in os.walk('templates'):
        for f in fs:
            if not f.endswith('.html'):
                continue
            p = os.path.join(r, f)
            total += 1
            if process(p):
                modified += 1
    print(f'Done. Checked {total} templates, modified {modified}.')


if __name__ == '__main__':
    main()
