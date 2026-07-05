"""
Replace hardcoded Arabic strings in owner templates with t() translation calls.
Uses the TRANSLATIONS dict from utils/i18n.py for safe key lookup.
"""

import os
import re
import ast

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
PROJECT_ROOT = os.path.abspath(PROJECT_ROOT)
OWNER_DIR = os.path.join(PROJECT_ROOT, 'templates', 'owner')
I18N_PATH = os.path.join(PROJECT_ROOT, 'utils', 'i18n.py')


def extract_translations(path):
    """Parse TRANSLATIONS dict from i18n.py."""
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()

    # Find the TRANSLATIONS = { ... } block
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

    dict_text = source[start:end]
    try:
        translations = ast.literal_eval(dict_text)
    except Exception as e:
        print(f"  ERROR parsing TRANSLATIONS: {e}")
        return {}

    # Build reverse map: Arabic text -> best English key
    arabic_to_key = {}
    for key, langs in translations.items():
        ar_text = langs.get('ar', '')
        if ar_text:
            # Prefer shorter keys for common words
            existing = arabic_to_key.get(ar_text)
            if existing is None or len(key) < len(existing):
                arabic_to_key[ar_text] = key

    return arabic_to_key


def find_hardcoded_arabic(content):
    """Find hardcoded Arabic text that is not inside Jinja expressions or HTML attributes."""
    # Pattern: Arabic text between HTML tags or as plain text in templates
    # Avoid: {{ ... }}, {% ... %}, HTML attributes like value="..."
    results = []

    # Find all Arabic text runs
    for m in re.finditer(r'[\u0600-\u06FF][\u0600-\u06FF\s\d\(\)\[\]\{\}\/\-\\.,:;!?\'%]+', content):
        start, end = m.span()
        text = m.group().strip()
        if len(text) < 2:
            continue

        # Check context: is it inside Jinja or an HTML attribute?
        prefix = content[max(0, start-20):start]
        suffix = content[end:min(len(content), end+10)]

        # Skip if inside {{ ... }} or {% ... %}
        if re.search(r'\{\{\s*$', prefix) or re.search(r'^\s*\}\}', suffix):
            continue
        if re.search(r'\{%\s*$', prefix) or re.search(r'^\s*%\}', suffix):
            continue

        # Skip if inside an HTML tag attribute value
        if re.search(r'\w+\s*=\s*["\'][^"\']*$', prefix):
            continue

        # Skip if part of a URL or path
        if re.search(r'["/\\]', prefix[-5:]):
            continue

        # Skip if inside <script> or <style>
        before = content[:start]
        if '<script' in before and '</script>' not in before.split('<script')[-1]:
            continue
        if '<style' in before and '</style>' not in before.split('<style')[-1]:
            continue

        # Skip if inside HTML tag itself
        last_lt = before.rfind('<')
        last_gt = before.rfind('>')
        if last_lt > last_gt:
            continue

        results.append((start, end, text))

    return results


def replace_in_template(content, arabic_to_key):
    """Replace hardcoded Arabic with t() calls where safe."""
    replacements = []
    hardcoded = find_hardcoded_arabic(content)

    for start, end, text in hardcoded:
        # Try exact match first
        key = arabic_to_key.get(text)
        if key:
            replacements.append((start, end, text, key))
            continue

        # Try without trailing punctuation/spaces
        clean = text.rstrip(' .,;:!?()[]{}').strip()
        key = arabic_to_key.get(clean)
        if key:
            replacements.append((start, end, text, key))
            continue

        # Try common substrings for composite labels
        # e.g., "إدارة الجداول" -> might be split
        parts = clean.split()
        if len(parts) == 2:
            # Try each part as a key
            for part in parts:
                if part in arabic_to_key:
                    # Partial match - skip for now, too risky
                    pass

    if not replacements:
        return content, 0

    # Apply replacements from end to start to preserve positions
    new_content = content
    replaced = 0
    for start, end, old_text, key in sorted(replacements, key=lambda x: x[0], reverse=True):
        # Build replacement
        prefix_ws = ''
        suffix_ws = ''
        if old_text != old_text.lstrip():
            prefix_ws = old_text[:len(old_text) - len(old_text.lstrip())]
        if old_text != old_text.rstrip():
            suffix_ws = old_text[len(old_text.rstrip()):]

        replacement = f"{prefix_ws}{{ t('{key}') }}{suffix_ws}"
        new_content = new_content[:start] + replacement + new_content[end:]
        replaced += 1

    return new_content, replaced


def log(msg):
    import sys
    sys.stdout.buffer.write((msg + '\n').encode('utf-8'))

def process_all_templates():
    log("=" * 70)
    log("I18N OWNER TEMPLATES — Replace hardcoded Arabic with t()")
    log("=" * 70)

    arabic_to_key = extract_translations(I18N_PATH)
    log(f"  Loaded {len(arabic_to_key)} translation mappings")
    log("")

    total_replaced = 0
    files_modified = 0
    files_skipped = 0
    unmatched = {}

    for filename in sorted(os.listdir(OWNER_DIR)):
        if not filename.endswith('.html'):
            continue

        path = os.path.join(OWNER_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        new_content, replaced = replace_in_template(content, arabic_to_key)

        if replaced > 0:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            log(f"  {filename}: {replaced} replacements")
            total_replaced += replaced
            files_modified += 1
        else:
            files_skipped += 1

        # Collect unmatched for reporting
        hardcoded = find_hardcoded_arabic(content)
        for _, _, text in hardcoded:
            clean = text.strip()
            if clean not in arabic_to_key and len(clean) > 2:
                unmatched[clean] = unmatched.get(clean, 0) + 1

    log("")
    log("=" * 70)
    log("SUMMARY")
    log("=" * 70)
    log(f"  Files modified:     {files_modified}")
    log(f"  Files skipped:      {files_skipped}")
    log(f"  Total replacements: {total_replaced}")

    if unmatched:
        log("")
        log("  Top unmatched Arabic strings (need translation keys):")
        for text, count in sorted(unmatched.items(), key=lambda x: x[1], reverse=True)[:20]:
            try:
                log(f"    ({count}x) {text}")
            except Exception:
                log(f"    ({count}x) [Arabic text]")

    log("=" * 70)


if __name__ == '__main__':
    process_all_templates()
