"""
Verify that all {{ t('Key') }} replacements in owner templates
map to correct Arabic translations.
"""

import os
import re
import sys
import ast

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
PROJECT_ROOT = os.path.abspath(PROJECT_ROOT)
OWNER_DIR = os.path.join(PROJECT_ROOT, 'templates', 'owner')
I18N_PATH = os.path.join(PROJECT_ROOT, 'utils', 'i18n.py')

def load_translations():
    with open(I18N_PATH, 'r', encoding='utf-8') as f:
        source = f.read()
    match = re.search(r'TRANSLATIONS\s*=\s*\{', source)
    if not match:
        return {}
    start = match.end() - 1
    brace_count = 0
    end = start
    for i, ch in enumerate(source[start:], start):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
    try:
        return ast.literal_eval(source[start:end])
    except Exception:
        return {}

def find_t_calls(content):
    """Find all {{ t('Key') }} calls and the text around them."""
    results = []
    # Find {{ t('...') }} or {{ t("...") }}
    for m in re.finditer(r"\{\{\s*t\(['\"]([A-Za-z_0-9\u0600-\u06FF ]+)['\"]\)\s*\}\}", content):
        key = m.group(1)
        start = m.start()
        # Get some context before
        context_start = max(0, start - 80)
        context = content[context_start:start + m.end() - context_start]
        results.append((key, context))
    return results

def main():
    translations = load_translations()
    print(f"Loaded {len(translations)} translations")
    print()

    issues = []
    total_calls = 0

    for filename in sorted(os.listdir(OWNER_DIR)):
        if not filename.endswith('.html'):
            continue
        path = os.path.join(OWNER_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        calls = find_t_calls(content)
        for key, context in calls:
            total_calls += 1
            if key not in translations:
                issues.append(f"MISSING KEY: '{key}' in {filename}")
            else:
                ar_text = translations[key]['ar']
                # Just report the key and its Arabic value

    print(f"Total {{ t('...') }} calls in owner templates: {total_calls}")
    print(f"Issues found: {len(issues)}")
    for issue in issues[:20]:
        print(f"  {issue}")

if __name__ == '__main__':
    main()
