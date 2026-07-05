"""
Clean owner templates:
1. Remove excessive Jinja section comments ({# ──────── ... ──────── #})
2. Replace hardcoded Arabic strings with t() where appropriate
"""

import os
import re

OWNER_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'templates', 'owner')
OWNER_DIR = os.path.abspath(OWNER_DIR)

# Patterns to remove: excessive section divider comments
SECTION_COMMENT_RE = re.compile(
    r'\s*\{\#\s*[-═]+\s*.*?\s*[-═]+\s*\#\}\n',
    re.MULTILINE
)

# Simple inline section comment pattern
INLINE_SECTION_RE = re.compile(
    r'\n\s*\{\#\s*[-═]+\s*.*?\s*[-═]+\s*\#\}',
    re.MULTILINE
)

# Very short/empty comments
EMPTY_COMMENT_RE = re.compile(r'\n\s*\{\#\s*\#\}', re.MULTILINE)

def clean_template(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # Remove excessive section divider comments
    content = SECTION_COMMENT_RE.sub('\n', content)
    content = INLINE_SECTION_RE.sub('', content)

    # Clean up multiple consecutive blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)

    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    print("=" * 60)
    print("CLEANING OWNER TEMPLATES")
    print("=" * 60)

    cleaned = 0
    for filename in sorted(os.listdir(OWNER_DIR)):
        if not filename.endswith('.html'):
            continue
        path = os.path.join(OWNER_DIR, filename)
        if clean_template(path):
            cleaned += 1
            print(f"  Cleaned: {filename}")

    print(f"\n  Total templates cleaned: {cleaned}")
    print("=" * 60)

if __name__ == '__main__':
    main()
