"""Externalize STATIC inline style="..." attributes into per-file <style> classes (D6).

Safe by design:
  - Only processes files passed explicitly as CLI args (controlled batch scope).
  - Skips any style value containing Jinja2 ({{ }} or {% %}) -> dynamic, left intact.
  - Skips elements that look JS-toggled (style is exactly display:none / display:block /
    display:inline[-block]) so JavaScript show/hide keeps working via inline override.
  - Generates deterministic class names (ic-<n>) and injects rules before </style>.
  - Merges with existing class="..." attributes instead of overwriting.

Usage:
  python tools/externalize_inline_css.py templates/invoices/simple.html [more files...]
"""
import re
import sys

TAG_STYLE_RE = re.compile(
    r'<(?P<tag>[a-zA-Z][\w-]*)(?P<pre>[^>]*?)\sstyle="(?P<style>[^"]*)"(?P<post>[^>]*?)(?P<end>/?)>'
)
JINJA_RE = re.compile(r'\{\{|\{%')
CLASS_RE = re.compile(r'\sclass="([^"]*)"')

# Pure display toggles that JS commonly flips at runtime -> keep inline.
JS_TOGGLE_VALUES = {
    'display:none', 'display: none',
    'display:block', 'display: block',
    'display:inline', 'display: inline',
    'display:inline-block', 'display: inline-block',
    'display:flex', 'display: flex',
}


def _normalize(style: str) -> str:
    parts = [s.strip() for s in style.rstrip(';').split(';') if s.strip()]
    return '; '.join(parts)


def process_file(path: str) -> int:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    if '</style>' not in content:
        print(f'  SKIP (no <style> block): {path}')
        return 0

    style_to_class = {}
    counter = [0]

    def _repl(m):
        style_val = m.group('style')
        if JINJA_RE.search(style_val):
            return m.group(0)
        if style_val.strip() in JS_TOGGLE_VALUES:
            return m.group(0)
        norm = _normalize(style_val)
        if not norm:
            return m.group(0)
        if norm not in style_to_class:
            counter[0] += 1
            style_to_class[norm] = f'ic-{counter[0]}'
        cls = style_to_class[norm]

        pre = m.group('pre')
        post = m.group('post')
        tag = m.group('tag')
        end = m.group('end')
        combined = pre + post
        cm = CLASS_RE.search(combined)
        if cm:
            existing = cm.group(1)
            new_class_attr = f' class="{existing} {cls}"'
            combined = CLASS_RE.sub(new_class_attr, combined, count=1)
        else:
            combined = combined + f' class="{cls}"'
        combined = re.sub(r'\s+', ' ', combined).strip()
        space = ' ' if combined else ''
        return f'<{tag}{space}{combined}{end}>'

    new_content = TAG_STYLE_RE.sub(_repl, content)

    if not style_to_class:
        print(f'  no static styles to externalize: {path}')
        return 0

    rules = ['', '    /* D6: externalized inline styles */']
    for norm, cls in style_to_class.items():
        rules.append(f'    .{cls} {{ {norm}; }}')
    rules_block = '\n'.join(rules) + '\n  '
    new_content = new_content.replace('</style>', rules_block + '</style>', 1)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'  externalized {len(style_to_class)} unique styles ({counter[0]} classes): {path}')
    return len(style_to_class)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python tools/externalize_inline_css.py <file1.html> [file2.html ...]')
        sys.exit(1)
    total = 0
    for p in sys.argv[1:]:
        total += process_file(p)
    print(f'Done. {total} unique style declarations externalized across {len(sys.argv) - 1} files.')
