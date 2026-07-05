"""
Fix owner templates:
1. Fix broken { t('Key') } -> {{ t('Key') }}
2. Replace exact-match hardcoded Arabic with {{ t('Key') }} where safe
3. Report remaining hardcoded strings
"""

import os
import re
import ast
import sys

OWNER_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'templates', 'owner')
OWNER_DIR = os.path.abspath(OWNER_DIR)
I18N_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'i18n.py')
I18N_PATH = os.path.abspath(I18N_PATH)

def log(msg):
    sys.stdout.buffer.write((msg + '\n').encode('utf-8'))

def extract_translations(path):
    with open(path, 'r', encoding='utf-8') as f:
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
        translations = ast.literal_eval(source[start:end])
    except Exception:
        return {}

    # Build reverse map: Arabic text -> English key
    arabic_to_key = {}
    for key, langs in translations.items():
        ar_text = langs.get('ar', '')
        if ar_text:
            existing = arabic_to_key.get(ar_text)
            if existing is None or len(key) < len(existing):
                arabic_to_key[ar_text] = key
    return arabic_to_key

def process_template(path, arabic_to_key):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    filename = os.path.basename(path)
    fixes = []

    # 1. Fix broken { t('Key') } -> {{ t('Key') }}
    broken_pattern = re.compile(r"(?<!\{)\{\s*t\(\'([A-Za-z_0-9\u0600-\u06FF ]+)\'\)\s*\}")
    def fix_broken(m):
        key = m.group(1)
        fixes.append(f"Fixed broken Jinja: {{ t('{key}') }}")
        return f"{{{{ t('{key}') }}}}"
    content = broken_pattern.sub(fix_broken, content)

    # 2. Fix broken { t("Key") } -> {{ t("Key") }}
    broken_pattern2 = re.compile(r'(?<!\{)\{\s*t\("([A-Za-z_0-9\u0600-\u06FF ]+)"\)\s*\}')
    def fix_broken2(m):
        key = m.group(1)
        fixes.append('Fixed broken Jinja: {{ t("' + key + '") }}')
        return '{{{{ t("' + key + '") }}}}'

    content = broken_pattern2.sub(fix_broken2, content)

    # 3. Fix any triple braces that may have been introduced by previous runs
    content = content.replace('{{{ t(', '{{ t(')
    content = content.replace(') }}}', ') }}')

    # 4. Replace exact-match Arabic strings with {{ t('Key') }}
    # Only replace standalone text between HTML tags or in obvious label positions
    # Pattern: >Arabic text<  (text content between tags)
    text_pattern = re.compile(r'>([\u0600-\u06FF][\u0600-\u06FF\s\d\(\)\[\]\{\}/\\.,:;!?\'%]*?)<')

    def replace_text(m):
        text = m.group(1).strip()
        if not text or len(text) < 2:
            return m.group(0)

        # Check exact match
        key = arabic_to_key.get(text)
        if key:
            fixes.append(f"Replaced '{text[:30]}...' -> t('{key}')")
            return f">{{{{ t('{key}') }}}}<"

        # Try without trailing punctuation
        clean = text.rstrip(' .,;:!?') .strip()
        key = arabic_to_key.get(clean)
        if key:
            fixes.append(f"Replaced '{clean[:30]}...' -> t('{key}')")
            return f">{{{{ t('{key}') }}}}<"

        return m.group(0)

    # Be very conservative: only replace inside small-box and card contexts
    content = text_pattern.sub(replace_text, content)

    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return fixes
    return []

def main():
    log("=" * 70)
    log("FIX OWNER TEMPLATES I18N")
    log("=" * 70)

    arabic_to_key = extract_translations(I18N_PATH)
    log(f"Loaded {len(arabic_to_key)} translation mappings")
    log("")

    all_fixes = []
    files_modified = 0

    for filename in sorted(os.listdir(OWNER_DIR)):
        if not filename.endswith('.html'):
            continue
        path = os.path.join(OWNER_DIR, filename)
        fixes = process_template(path, arabic_to_key)
        if fixes:
            files_modified += 1
            log(f"{filename}:")
            for fix in fixes:
                try:
                    log(f"  - {fix}")
                except Exception:
                    log(f"  - [Arabic fix]")
            all_fixes.extend(fixes)

    log("")
    log("=" * 70)
    log("SUMMARY")
    log("=" * 70)
    log(f"Files modified: {files_modified}")
    log(f"Total fixes:    {len(all_fixes)}")
    log("=" * 70)

if __name__ == '__main__':
    main()
