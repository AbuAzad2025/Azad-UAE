"""Batch fix common mobile responsiveness issues in templates."""
import os
import re

TABLE_RE = re.compile(r'(<table\b[^>]*>)(.*?)(</table>)', re.IGNORECASE | re.DOTALL)
TABLE_RESP_RE = re.compile(r'table-responsive', re.IGNORECASE)
BTN_SM_RE = re.compile(r'\bbtn-sm\b')
BTN_XS_RE = re.compile(r'\bbtn-xs\b')


def process(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    changes = {'btn_sm': 0, 'btn_xs': 0, 'table_resp': 0}

    # Replace btn-sm in class attributes only
    changes['btn_sm'] = len(BTN_SM_RE.findall(content))
    content = BTN_SM_RE.sub('', content)
    # Clean up "class=\"btn  other\"" → "class=\"btn other\""
    content = re.sub(r'class="([^"]*)\s+\s+([^"]*)"', r'class="\1 \2"', content)
    content = re.sub(r'class="\s+([^"]*)"', r'class="\1"', content)
    content = re.sub(r'class="([^"]*)\s+"', r'class="\1"', content)

    # Replace btn-xs (deprecated in BS4 anyway)
    changes['btn_xs'] = len(BTN_XS_RE.findall(content))
    content = BTN_XS_RE.sub('', content)
    content = re.sub(r'class="([^"]*)\s+\s+([^"]*)"', r'class="\1 \2"', content)
    content = re.sub(r'class="\s+([^"]*)"', r'class="\1"', content)
    content = re.sub(r'class="([^"]*)\s+"', r'class="\1"', content)

    # Add table-responsive wrapper to tables without it
    # Only if the file has tables and no table-responsive
    if TABLE_RE.search(content) and not TABLE_RESP_RE.search(content):
        # Simple: wrap each <table...>...</table> in <div class="table-responsive">
        def _wrap_table(m):
            return f'<div class="table-responsive">{m.group(0)}</div>'
        content = TABLE_RE.sub(_wrap_table, content)
        changes['table_resp'] = len(TABLE_RE.findall(original))

    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return changes
    return None


def main():
    total = 0
    modified = 0
    totals = {'btn_sm': 0, 'btn_xs': 0, 'table_resp': 0}
    for r, _, fs in os.walk('templates'):
        for f in fs:
            if not f.endswith('.html'):
                continue
            p = os.path.join(r, f)
            total += 1
            changes = process(p)
            if changes:
                modified += 1
                rel = os.path.relpath(p, 'templates')
                parts = []
                if changes['btn_sm']: parts.append(f"-btn_sm:{changes['btn_sm']}")
                if changes['btn_xs']: parts.append(f"-btn_xs:{changes['btn_xs']}")
                if changes['table_resp']: parts.append(f"+table_resp:{changes['table_resp']}")
                print(f'  {rel} {" ".join(parts)}')
                for k in totals:
                    totals[k] += changes[k]
    print(f'Done. Checked {total} templates, modified {modified}.')
    print(f'Totals: btn_sm removed={totals["btn_sm"]}, btn_xs removed={totals["btn_xs"]}, tables wrapped={totals["table_resp"]}')


if __name__ == '__main__':
    main()
