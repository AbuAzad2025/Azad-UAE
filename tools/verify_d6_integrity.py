"""Verify D6 integrity: every .ic-N class has a matching rule; no empty style attrs."""
import os
import re

IC_CLASS_RE = re.compile(r'\bic-(\d+)\b')
IC_RULE_RE = re.compile(r'\.ic-(\d+)\s*\{')
STYLE_ATTR_RE = re.compile(r'style="\s*"')


def check(path: str) -> list:
    issues = []
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    used = set(IC_CLASS_RE.findall(content))
    defined = set(IC_RULE_RE.findall(content))
    missing = used - defined
    if missing:
        issues.append(f'orphan classes: ic-{chr(39)} , ic-{chr(39)}.join(sorted(missing, key=int))')
    if STYLE_ATTR_RE.search(content):
        issues.append('empty style found')
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
                print(f'FAIL {os.path.relpath(p, chr(39)+chr(39)+chr(39)+chr(39)+chr(39)+chr(39)+chr(39))}: {chr(39)}; {chr(39)}.join(issues)')
    print(f'Checked {total} templates. Issues in {bad} files.')
    return 1 if bad else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
