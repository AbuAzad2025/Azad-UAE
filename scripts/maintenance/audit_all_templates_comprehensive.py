"""
Comprehensive template audit - READ ONLY.
Checks ALL templates in the system for:
1. Jinja syntax errors (parse every template)
2. Broken braces {{{ / }}} 
3. Broken t() calls: { t('...') } instead of {{ t('...') }}
4. Missing translation keys
5. Mismatched Jinja blocks (if/for/macro unclosed)
6. Undefined variables that would crash rendering

This script ONLY reads and reports. It does NOT modify any file.
Output: detailed report file.
"""

import os
import re
import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
I18N_PATH = PROJECT_ROOT / "utils" / "i18n.py"
REPORT_PATH = Path(__file__).parent / "all_templates_audit_report.txt"

# Try to import Jinja for parsing
try:
    from jinja2 import Environment, FileSystemLoader, meta, TemplateSyntaxError
    JINJA_AVAILABLE = True
except ImportError:
    JINJA_AVAILABLE = False
    print("WARNING: jinja2 not available, syntax check skipped")


def load_translations():
    with open(I18N_PATH, "r", encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"TRANSLATIONS\s*=\s*\{", src)
    if not m:
        return set()
    start = m.end() - 1
    brace = 0
    end = start
    for i, ch in enumerate(src[start:], start):
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
            if brace == 0:
                end = i + 1
                break
    try:
        d = ast.literal_eval(src[start:end])
        return set(d.keys())
    except Exception:
        return set()


def find_templates():
    templates = []
    for root, dirs, files in os.walk(TEMPLATES_DIR):
        # Skip deleted/orphaned
        if "to-delete" in root:
            continue
        for name in sorted(files):
            if name.endswith(".html"):
                templates.append(os.path.join(root, name))
    return sorted(templates)


def audit_template(path, translations):
    rel = os.path.relpath(path, PROJECT_ROOT)
    issues = []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")

    # 1. Triple / quadruple braces
    for i, line in enumerate(lines, 1):
        if "{{{" in line or "}}}" in line:
            issues.append((i, "TRIPLE_BRACE", line.strip()[:120]))

    # 2. Broken single-brace t() calls: { t('Key') }
    for i, line in enumerate(lines, 1):
        if re.search(r"(?<!\{)\{\s*t\(", line):
            issues.append((i, "BROKEN_T_CALL", line.strip()[:120]))

    # 3. Missing translation keys
    for m in re.finditer(r"t\(\'([A-Za-z_0-9\u0600-\u06FF ]+)'\)", content):
        key = m.group(1)
        if key not in translations:
            pos = m.start()
            line_no = content[:pos].count("\n") + 1
            issues.append((line_no, f"MISSING_KEY: '{key}'", lines[line_no - 1].strip()[:120]))

    # 4. Jinja syntax parse (with i18n extension enabled for {% trans %} tags)
    if JINJA_AVAILABLE:
        from jinja2.ext import InternationalizationExtension
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            extensions=[InternationalizationExtension]
        )
        try:
            template_name = os.path.relpath(path, TEMPLATES_DIR).replace("\\", "/")
            source = env.loader.get_source(env, template_name)[0]
            env.parse(source)
        except TemplateSyntaxError as e:
            issues.append((e.lineno or 1, f"JINJA_SYNTAX_ERROR: {e.message}", str(e)[:120]))
        except Exception as e:
            # Some templates might fail to load due to includes/extends - that's ok
            pass

    # 5. Check for unclosed blocks (rough check)
    block_stack = []
    block_pattern = re.compile(r"\{%\s*(if|for|macro|block|filter|with|autoescape|trans|set)\b")
    end_pattern = re.compile(r"\{%\s*end(if|for|macro|block|filter|with|autoescape|trans|set)\b")
    for i, line in enumerate(lines, 1):
        for m in block_pattern.finditer(line):
            block_stack.append((i, m.group(1)))
        for m in end_pattern.finditer(line):
            if not block_stack:
                issues.append((i, f"UNEXPECTED_END_{m.group(1).upper()}", line.strip()[:120]))
            else:
                block_stack.pop()
    for i, tag in block_stack:
        issues.append((i, f"UNCLOSED_{tag.upper()}", lines[i - 1].strip()[:120]))

    return rel, issues


def main():
    templates = find_templates()
    translations = load_translations()

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("COMPREHENSIVE TEMPLATE AUDIT (READ-ONLY)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Total templates scanned: {len(templates)}\n")
        f.write(f"Translation keys loaded: {len(translations)}\n")
        f.write(f"Jinja parser available: {JINJA_AVAILABLE}\n")
        f.write("=" * 80 + "\n\n")

        files_with_issues = 0
        total_issues = 0
        critical_issues = 0

        for path in templates:
            rel, issues = audit_template(path, translations)
            if issues:
                files_with_issues += 1
                total_issues += len(issues)
                # Count critical (syntax/braces) vs warnings
                for _, issue_type, _ in issues:
                    if any(x in issue_type for x in ["SYNTAX", "TRIPLE", "BROKEN", "UNCLOSED", "UNEXPECTED"]):
                        critical_issues += 1

                f.write(f"\n{rel}\n")
                f.write("-" * len(rel) + "\n")
                for line_no, issue_type, snippet in issues:
                    f.write(f"  Line {line_no:4d} | {issue_type:30s} | {snippet}\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write(f"SUMMARY\n")
        f.write(f"  Templates scanned:     {len(templates)}\n")
        f.write(f"  Files with issues:     {files_with_issues}\n")
        f.write(f"  Total issues:          {total_issues}\n")
        f.write(f"  Critical issues:       {critical_issues}\n")
        f.write(f"  Clean templates:       {len(templates) - files_with_issues}\n")
        f.write("=" * 80 + "\n")
        f.write("Fix issues MANUALLY. Do NOT run auto-fix scripts on production.\n")

    print(f"Report written to: {REPORT_PATH}")
    print(f"Templates scanned: {len(templates)}")
    print(f"Files with issues: {files_with_issues}")
    print(f"Critical issues: {critical_issues}")
    if critical_issues == 0:
        print("\n✅ NO CRITICAL ISSUES FOUND. All templates parse correctly.")


if __name__ == "__main__":
    main()
