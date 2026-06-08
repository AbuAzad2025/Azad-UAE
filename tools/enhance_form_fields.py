"""Enhance form inputs with validation attributes based on field name patterns."""
import os
import re

INPUT_RE = re.compile(
    r'<(input|select|textarea)\s+([^>]*?)>',
    re.IGNORECASE
)

RULES = [
    # (name_contains, attr_name, attr_value, condition)
    (['email', 'e_mail', 'user_email'], 'type', 'email', lambda a: 'type=' not in a.lower()),
    (['phone', 'mobile', 'tel', 'fax'], 'pattern', r'^\+?[0-9\s\-]{8,20}$', lambda a: 'pattern=' not in a.lower()),
    (['password', 'passwd'], 'minlength', '6', lambda a: 'minlength=' not in a.lower()),
    (['amount', 'price', 'cost', 'salary', 'total', 'discount'], 'min', '0', lambda a: 'min=' not in a.lower()),
    (['quantity', 'qty', 'stock_quantity'], 'min', '0', lambda a: 'min=' not in a.lower()),
    (['quantity', 'qty', 'stock_quantity'], 'type', 'number', lambda a: 'type=' not in a.lower()),
    (['name', 'full_name', 'company_name', 'contact_name'], 'minlength', '2', lambda a: 'minlength=' not in a.lower()),
    (['name', 'full_name', 'company_name', 'contact_name'], 'maxlength', '100', lambda a: 'maxlength=' not in a.lower()),
    (['description', 'notes', 'remark'], 'maxlength', '500', lambda a: 'maxlength=' not in a.lower()),
    (['address'], 'maxlength', '255', lambda a: 'maxlength=' not in a.lower()),
    (['tax_id', 'tax_number', 'vat_number'], 'maxlength', '20', lambda a: 'maxlength=' not in a.lower()),
    (['sku', 'barcode'], 'maxlength', '50', lambda a: 'maxlength=' not in a.lower()),
    (['iban', 'account_number', 'bank_account'], 'maxlength', '34', lambda a: 'maxlength=' not in a.lower()),
    (['share_percentage', 'commission_rate'], 'min', '0', lambda a: 'min=' not in a.lower()),
    (['share_percentage', 'commission_rate'], 'max', '100', lambda a: 'max=' not in a.lower()),
]


def _extract_name(attrs: str) -> str:
    m = re.search(r'name="([^"]*)"', attrs, re.IGNORECASE)
    return m.group(1).lower() if m else ''


def _enhance(m) -> str:
    tag = m.group(1).lower()
    attrs = m.group(2)
    if tag == 'select':
        # Selects: only add required if label has *
        return m.group(0)
    name = _extract_name(attrs)
    if not name:
        return m.group(0)
    modified = attrs
    for keywords, attr, val, cond in RULES:
        if any(k in name for k in keywords):
            if cond(modified):
                modified = modified + f' {attr}="{val}"'
    # Add required if label nearby has *
    if 'required' not in modified.lower():
        # We'll rely on user to add required manually or via another pass
        pass
    if modified == attrs:
        return m.group(0)
    return f'<{tag} {modified.strip()}>'


def process(path: str) -> bool:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'needs-validation' not in content:
        return False
    new_content = INPUT_RE.sub(_enhance, content)
    if new_content == content:
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'  enhanced: {os.path.relpath(path, "templates")}')
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
    print(f'Done. Checked {total} templates, enhanced {modified}.')


if __name__ == '__main__':
    main()
