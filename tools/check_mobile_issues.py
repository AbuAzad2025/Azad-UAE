"""Scan templates for common mobile responsiveness issues."""
import os
import re

TABLE_RE = re.compile(r'<table\b', re.IGNORECASE)
TABLE_RESP_RE = re.compile(r'table-responsive', re.IGNORECASE)
FIXED_WIDTH_RE = re.compile(r'style="[^"]*width:\s*\d+px', re.IGNORECASE)
SMALL_BTN_RE = re.compile(r'btn-(sm|xs)\b', re.IGNORECASE)
INPUT_GROUP_RE = re.compile(r'input-group', re.IGNORECASE)


def check(path: str) -> list:
    issues = []
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    tables = TABLE_RE.findall(content)
    has_resp = TABLE_RESP_RE.search(content)
    if tables and not has_resp:
        issues.append(f'table without table-responsive wrapper ({len(tables)} tables)')

    fw = FIXED_WIDTH_RE.findall(content)
    if fw:
        issues.append(f'fixed-width inline styles ({len(fw)})')

    small_btns = SMALL_BTN_RE.findall(content)
    if small_btns:
        issues.append(f'small buttons btn-sm/xs ({len(small_btns)})')

    return issues


def main():
    total = 0
    bad = 0
    for r, _, fs in os.walk('templates'):
        for f in fs:
            if not f.endswith('.html'):
                continue
            p = os.path.join(r, f)
            total += 1
            issues = check(p)
            if issues:
                bad += 1
                rel = os.path.relpath(p, 'templates')
                print(f'{rel}:')
                for i in issues:
                    print(f'  - {i}')
    print(f'Checked {total} templates. {bad} with mobile issues.')


if __name__ == '__main__':
    main()
