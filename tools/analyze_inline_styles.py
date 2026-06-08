"""Analyze inline style="..." usage to plan CSS externalization (D6).

Categorizes each occurrence into:
  - dynamic: contains Jinja2 {{ }} / {% %} -> cannot externalize as static class
  - static: fixed value -> candidate for utility class
Reports frequency of each unique static style declaration so we can map the
most common ones to reusable classes.
"""
import os
import re
from collections import Counter

STYLE_RE = re.compile(r'style="([^"]*)"', re.IGNORECASE)
JINJA_RE = re.compile(r'\{\{|\{%')


def analyze(templates_dir):
    static_counter = Counter()
    dynamic_count = 0
    static_count = 0
    per_file = Counter()

    for root, _, files in os.walk(templates_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            for m in STYLE_RE.finditer(content):
                val = m.group(1).strip()
                rel = os.path.relpath(fpath, templates_dir)
                per_file[rel] += 1
                if JINJA_RE.search(val):
                    dynamic_count += 1
                else:
                    static_count += 1
                    normalized = ';'.join(
                        s.strip() for s in val.rstrip(';').split(';') if s.strip()
                    )
                    static_counter[normalized] += 1

    print('=== INLINE STYLE ANALYSIS (D6) ===')
    print(f'Total static (externalizable):  {static_count}')
    print(f'Total dynamic (Jinja2, keep):   {dynamic_count}')
    print(f'Unique static declarations:     {len(static_counter)}')
    print()
    print('--- Top 40 most frequent static declarations ---')
    for decl, n in static_counter.most_common(40):
        print(f'  {n:4d}  {decl}')
    print()
    print('--- Top 20 files by inline-style count ---')
    for fp, n in per_file.most_common(20):
        print(f'  {n:4d}  {fp}')


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    analyze(os.path.join(root, 'templates'))
