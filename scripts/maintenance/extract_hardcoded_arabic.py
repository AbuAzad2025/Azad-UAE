"""
Extract remaining hardcoded Arabic strings from owner templates.
Output: list of unique strings with file occurrences.
"""

import os
import re
import sys

OWNER_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'templates', 'owner')
OWNER_DIR = os.path.abspath(OWNER_DIR)

def log(msg):
    sys.stdout.buffer.write((msg + '\n').encode('utf-8'))

def find_hardcoded_arabic(content):
    """Find Arabic text not inside Jinja expressions or HTML attributes."""
    results = []
    # Find Arabic text runs
    for m in re.finditer(r'[\u0600-\u06FF][\u0600-\u06FF\s\d\(\)\[\]\{\}/\\.,:;!?\'%]*', content):
        start, end = m.span()
        text = m.group().strip()
        if len(text) < 2:
            continue

        prefix = content[max(0, start-30):start]
        suffix = content[end:min(len(content), end+10)]

        # Skip if inside {{ ... }} or {% ... %}
        if re.search(r'\{\{\s*$', prefix) or re.search(r'^\s*\}\}', suffix):
            continue
        if re.search(r'\{%\s*$', prefix) or re.search(r'^\s*%\}', suffix):
            continue

        # Skip if inside HTML attribute value
        if re.search(r'\w+\s*=\s*["\'][^"\']*$', prefix):
            continue

        # Skip if part of URL/path
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

        # Skip if already inside t() call
        if re.search(r"t\(\s*['\"]", prefix[-15:]):
            continue

        results.append(text)
    return results

def main():
    log("=" * 70)
    log("EXTRACTING HARDCODED ARABIC FROM OWNER TEMPLATES")
    log("=" * 70)

    all_strings = {}  # text -> set of files

    for filename in sorted(os.listdir(OWNER_DIR)):
        if not filename.endswith('.html'):
            continue
        path = os.path.join(OWNER_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        texts = find_hardcoded_arabic(content)
        for text in texts:
            all_strings.setdefault(text, set()).add(filename)

    # Sort by frequency (most common first)
    sorted_items = sorted(all_strings.items(), key=lambda x: (-len(x[1]), x[0]))

    log(f"\nTotal unique Arabic strings: {len(sorted_items)}\n")

    # Show top 50 by frequency
    log("Top strings by frequency:")
    for text, files in sorted_items[:50]:
        try:
            log(f"  ({len(files):2d}x) {text}")
        except Exception:
            log(f"  ({len(files):2d}x) [Arabic text]")

    # Show all strings (grouped)
    log("\n" + "=" * 70)
    log("ALL STRINGS")
    log("=" * 70)
    for text, files in sorted_items:
        try:
            log(f"{text}  |  {', '.join(sorted(files))}")
        except Exception:
            log(f"[Arabic text]  |  {', '.join(sorted(files))}")

if __name__ == '__main__':
    main()
