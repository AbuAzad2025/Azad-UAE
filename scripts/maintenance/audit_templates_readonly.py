"""
Read-only template audit.
Checks for issues but NEVER modifies any file.
Outputs a report to stdout; fix issues manually after review.
"""

import os
import re
import sys
import ast

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
PROJECT_ROOT = os.path.abspath(PROJECT_ROOT)
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, 'templates')
I18N_PATH = os.path.join(PROJECT_ROOT, 'utils', 'i18n.py')


def load_translations():
    with open(I18N_PATH, 'r', encoding='utf-8') as f:
        src = f.read()
    m = re.search(r'TRANSLATIONS\s*=\s*\{', src)
    if not m:
        return set()
    start = m.end() - 1
    brace = 0
    end = start
    for i, ch in enumerate(src[start:], start):
        if ch == '{':
            brace += 1
        elif ch == '}':
            brace -= 1
            if brace == 0:
                end = i + 1
                break
    try:
        d = ast.literal_eval(src[start:end])
        return set(d.keys())
    except Exception:
        return set()


def audit_file(path, translations):
    issues = []
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')

    # 1. Triple / quadruple braces (from bad script runs)
    for i, line in enumerate(lines, 1):
        if '{{{' in line or '}}}' in line:
            issues.append((i, 'TRIPLE_BRACE', line.strip()))
        if '{{{{' in line or '}}}}' in line:
            issues.append((i, 'QUADRUPLE_BRACE', line.strip()))

    # 2. Broken Jinja t() calls: { t('Key') }  (single brace)
    for i, line in enumerate(lines, 1):
        if re.search(r'(?<!\{)\{\s*t\(', line):
            issues.append((i, 'BROKEN_T_CALL', line.strip()))

    # 3. Missing translation keys
    for m in re.finditer(r"t\(\'([A-Za-z_0-9\u0600-\u06FF ]+)'\)", content):
        key = m.group(1)
        if key not in translations:
            # find line
            pos = m.start()
            line_num = content[:pos].count('\n') + 1
            issues.append((line_num, f"MISSING_KEY: '{key}'", lines[line_num-1].strip()))

    # 4. Empty lang attribute
    for i, line in enumerate(lines, 1):
        if re.search(r'lang\s*=\s*""', line) or re.search(r"lang\s*=\s*''", line):
            issues.append((i, 'EMPTY_LANG', line.strip()))

    # 5. Empty aria-* attributes
    for i, line in enumerate(lines, 1):
        if re.search(r'aria-\w+\s*=\s*""', line) or re.search(r"aria-\w+\s*=\s*''", line):
            issues.append((i, 'EMPTY_ARIA', line.strip()))

    # 6. Inline style attributes
    for i, line in enumerate(lines, 1):
        if 'style=' in line.lower() and not line.strip().startswith('{%'):
            issues.append((i, 'INLINE_STYLE', line.strip()))

    # 7. Empty HTML comments
    for i, line in enumerate(lines, 1):
        if '<!-- -->' in line or '<!---->' in line:
            issues.append((i, 'EMPTY_HTML_COMMENT', line.strip()))

    # 8. Broken Jinja variable inside string (e.g., `'{{ t('Key') }}'` inside `{{ ... }}`)
    for i, line in enumerate(lines, 1):
        if "'{{" in line or '"{{' in line:
            if re.search(r"=\s*['\"].*\{\{.*\}\}.*['\"]", line):
                issues.append((i, 'JINJA_INSIDE_STRING', line.strip()))

    # 9. Unclosed Jinja blocks (basic check for mismatched if/for)
    stack = []
    for i, line in enumerate(lines, 1):
        for m in re.finditer(r'\{%\s*(if|for|macro|block)\b', line):
            stack.append((i, m.group(1)))
        for m in re.finditer(r'\{%\s*end(if|for|macro|block)\b', line):
            if not stack:
                issues.append((i, f'UNEXPECTED_END{m.group(1).upper()}', line.strip()))
            else:
                stack.pop()
    for i, tag in stack:
        issues.append((i, f'UNCLOSED_{tag.upper()}', lines[i-1].strip()))

    return issues


def safe_print(text, output_file):
    output_file.write(text + '\n')


def main():
    report_path = os.path.join(os.path.dirname(__file__), 'template_audit_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        safe_print("=" * 80, f)
        safe_print("TEMPLATE AUDIT (READ-ONLY)", f)
        safe_print("=" * 80, f)

        translations = load_translations()
        safe_print(f"Loaded {len(translations)} translation keys from utils/i18n.py\n", f)

        total_issues = 0
        files_with_issues = 0

        for root, dirs, files in os.walk(TEMPLATES_DIR):
            if 'to-delete' in root:
                continue
            for name in sorted(files):
                if not name.endswith('.html'):
                    continue
                path = os.path.join(root, name)
                rel = os.path.relpath(path, PROJECT_ROOT)
                issues = audit_file(path, translations)
                if issues:
                    files_with_issues += 1
                    total_issues += len(issues)
                    safe_print(f"\n{rel}", f)
                    safe_print("-" * len(rel), f)
                    for line_no, issue_type, snippet in issues:
                        snippet = snippet[:120]
                        safe_print(f"  Line {line_no:4d} | {issue_type:25s} | {snippet}", f)

        safe_print("\n" + "=" * 80, f)
        safe_print(f"SUMMARY: {files_with_issues} files with {total_issues} issue(s)", f)
        safe_print("=" * 80, f)
        safe_print("Fix issues MANUALLY. Do NOT run auto-fix scripts on production.", f)

    print(f"Report written to: {report_path}")


if __name__ == '__main__':
    main()
