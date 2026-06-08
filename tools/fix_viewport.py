"""Add viewport meta to standalone HTML templates missing it."""
import os
import re


def fix_viewport(templates_dir):
    fixed = []
    viewport_tag = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    for root, _, files in os.walk(templates_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            if '<!doctype' not in content.lower():
                continue
            if 'name="viewport"' in content.lower():
                continue
            charset_m = re.search(r'(<meta\s+charset=[^>]*>)', content, re.IGNORECASE)
            if charset_m:
                anchor = charset_m.group(1)
                new_content = content.replace(anchor, anchor + '\n  ' + viewport_tag, 1)
            else:
                head_m = re.search(r'(<head[^>]*>)', content, re.IGNORECASE)
                if not head_m:
                    continue
                anchor = head_m.group(1)
                new_content = content.replace(anchor, anchor + '\n  ' + viewport_tag, 1)
            if new_content != content:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                fixed.append(fpath)
    print(f'Added viewport to {len(fixed)} files')
    for fp in fixed:
        print('  - ' + fp)


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fix_viewport(os.path.join(root, 'templates'))
