"""
Phase 1 i18n Batch Replacement Script
Replace Arabic strings that already have translation keys in utils/i18n.py
with {{ t('EnglishKey') }} calls.
"""
import os
import re
import sys
from datetime import datetime

PROJECT_ROOT = r'D:\Data\karaj\UAE\Azad-UAE'
OUTPUT_FILE = os.path.join(PROJECT_ROOT, 'scripts', 'i18n_phase1_report.txt')
EXCLUDE_SUBDIRS = {'shop', 'public', 'owner', 'auth'}
SKIP_VARS = {'tenant_currency_name_ar', 'company_name_ar', 'tenant_name_ar'}
LOG = []


def log(text=""):
    print(text)
    LOG.append(text)


def build_reverse_lookup():
    """Read TRANSLATIONS dict from utils/i18n.py and build Arabic -> English key mapping."""
    i18n_path = os.path.join(PROJECT_ROOT, 'utils', 'i18n.py')
    with open(i18n_path, 'r', encoding='utf-8') as f:
        content = f.read()

    arabic_to_key = {}
    pattern = r"'([^']+)'\s*:\s*\{[^}]*'ar'\s*:\s*'([^']+)'[^}]*'en'\s*:\s*'([^']+)'"
    matches = re.findall(pattern, content)

    for eng_key, ar_text, _ in matches:
        arabic_to_key[ar_text] = eng_key

    log(f"[INFO] Loaded {len(arabic_to_key)} existing translation keys")
    return arabic_to_key


def get_target_files():
    """Get all .html files under templates/, excluding specified subdirs."""
    templates_dir = os.path.join(PROJECT_ROOT, 'templates')
    files = []
    for root, dirs, fnames in os.walk(templates_dir):
        rel_root = os.path.relpath(root, templates_dir)
        parts = rel_root.split(os.sep)
        if parts and parts[0] in EXCLUDE_SUBDIRS:
            dirs[:] = []
            continue
        for f in fnames:
            if f.endswith('.html'):
                files.append(os.path.join(root, f))
    return sorted(files)


def has_template_syntax(line):
    """Check if line contains Jinja2 template syntax."""
    return bool(re.search(r'\{\{|\{%|\{#', line))


def has_skip_var(line):
    """Check if line contains any of the skip variables."""
    for var in SKIP_VARS:
        if var in line:
            return True
    return False


def process_file(filepath, arabic_to_key):
    """Replace Arabic strings in a file with t() calls. Returns (modified, count, warnings)."""
    relpath = os.path.relpath(filepath, PROJECT_ROOT)

    with open(filepath, 'r', encoding='utf-8') as f:
        original_lines = f.readlines()

    modified_lines = list(original_lines)
    total_replacements = 0
    file_modified = False
    warnings = []

    sorted_items = sorted(arabic_to_key.items(), key=lambda x: -len(x[0]))

    for line_idx, line in enumerate(original_lines):
        if not re.search(r'[\u0600-\u06FF]', line):
            continue

        stripped = line.rstrip('\n')

        if has_skip_var(stripped):
            continue

        if has_template_syntax(stripped):
            warnings.append(f"  SKIP line {line_idx+1}: mixed Arabic + template syntax in {relpath}")
            continue

        new_line = stripped
        line_replacement_count = 0

        for ar_text, eng_key in sorted_items:
            if ar_text not in new_line:
                continue

            # JS alert/confirm - single-quoted strings
            new_line, count = re.subn(
                r'(alert|confirm)\s*\(\s*\'' + re.escape(ar_text) + r'\'\s*\)',
                lambda m, k=eng_key: f"{m.group(1)}('{{{{ t('{k}') }}}}')",
                new_line
            )
            line_replacement_count += count

            if ar_text not in new_line:
                continue

            # HTML attribute - double-quoted
            new_line, count = re.subn(
                r'(\b[\w-]+)\s*=\s*"' + re.escape(ar_text) + r'"',
                lambda m, k=eng_key: f'{m.group(1)}="{{{{ t(\'{k}\') }}}}"',
                new_line
            )
            line_replacement_count += count

            if ar_text not in new_line:
                continue

            # HTML attribute - single-quoted
            new_line, count = re.subn(
                r"(\b[\w-]+)\s*=\s*'" + re.escape(ar_text) + r"'",
                lambda m, k=eng_key: f"{m.group(1)}='{{{{ t('{k}') }}}}'",
                new_line
            )
            line_replacement_count += count

            if ar_text not in new_line:
                continue

            # Text between tags - with trailing colon
            new_line, count = re.subn(
                r'>' + re.escape(ar_text) + r':<',
                lambda m, k=eng_key: f'>{{{{ t(\'{k}\') }}}}:<',
                new_line
            )
            line_replacement_count += count

            if ar_text not in new_line:
                continue

            # Text between tags - without colon
            new_line, count = re.subn(
                r'>' + re.escape(ar_text) + r'<',
                lambda m, k=eng_key: f'>{{{{ t(\'{k}\') }}}}<',
                new_line
            )
            line_replacement_count += count

        if line_replacement_count > 0:
            total_replacements += line_replacement_count
            file_modified = True
            modified_lines[line_idx] = new_line + '\n'

    if file_modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(modified_lines)

    return file_modified, total_replacements, warnings


def main():
    log("=" * 70)
    log("i18n PHASE 1 — Batch Replacements")
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)

    arabic_to_key = build_reverse_lookup()
    all_files = get_target_files()
    log(f"\n[INFO] Found {len(all_files)} target template files")

    total_modified = 0
    total_replacements = 0
    all_warnings = []

    for filepath in all_files:
        modified, count, warnings = process_file(filepath, arabic_to_key)
        all_warnings.extend(warnings)
        if modified:
            total_modified += 1
            total_replacements += count
            relpath = os.path.relpath(filepath, PROJECT_ROOT)
            log(f"  {relpath:<65s} {count:>3d} replacements")

    log(f"\n{'=' * 70}")
    log(f"SUMMARY")
    log(f"{'=' * 70}")
    log(f"  Files processed:  {len(all_files)}")
    log(f"  Files modified:   {total_modified}")
    log(f"  Replacements:     {total_replacements}")

    if all_warnings:
        log(f"\n{'=' * 70}")
        log("WARNINGS (lines skipped due to mixed Arabic + template syntax)")
        log(f"{'=' * 70}")
        for w in all_warnings:
            log(w)

    log(f"\n{'=' * 70}")
    log(f"[DONE] Report saved to: {OUTPUT_FILE}")
    log(f"{'=' * 70}")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(LOG))

    return total_modified, total_replacements


if __name__ == '__main__':
    main()
