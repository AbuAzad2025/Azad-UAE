"""Add required attribute to inputs whose label contains * (mandatory indicator)."""
import os
import re

# Pattern: label with * followed by input/select/textarea
LABEL_INPUT_RE = re.compile(
    r'(<label[^>]*>[^<]*\*[^<]*</label>\s*)'
    r'(<(input|select|textarea)\s+)([^>]*?)(/?>)',
    re.IGNORECASE | re.DOTALL
)


def _repl(m):
    label = m.group(1)
    tag_open = m.group(2)
    tag = m.group(3)
    attrs = m.group(4)
    end = m.group(5)
    if 'required' in attrs.lower():
        return m.group(0)
    # Skip hidden, submit, button, checkbox, radio (handled differently)
    low = attrs.lower()
    if 'type="hidden"' in low or 'type="submit"' in low or 'type="button"' in low:
        return m.group(0)
    if 'type="checkbox"' in low or 'type="radio"' in low:
        return m.group(0)
    # Skip if it already has aria-label or is a search/filter field
    if 'search' in low or 'filter' in low:
        return m.group(0)
    return label + tag_open + attrs + ' required' + end


def process(path: str) -> bool:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'needs-validation' not in content:
        return False
    new_content = LABEL_INPUT_RE.sub(_repl, content)
    if new_content == content:
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'  +required: {os.path.relpath(path, "templates")}')
    return True


def main():
    total = 0
    modified = 0
    for r, _, fs in os.walk('templates'):
        for f in fs:
            if not f.endswith('.html'):
                continue
            p = os.path.join(r, f)
            total += 1
            if process(p):
                modified += 1
    print(f'Done. Checked {total} templates, modified {modified}.')


if __name__ == '__main__':
    main()
