import re
import os

BATCH2_FILES = [
    "templates/customers/index.html",
    "templates/customers/statement.html",
    "templates/customers/view.html",
    "templates/suppliers/index.html",
    "templates/suppliers/statement.html",
    "templates/suppliers/view.html",
    "templates/payments/archived.html",
    "templates/payments/create.html",
    "templates/payments/create_payment.html",
    "templates/payments/create_receipt.html",
    "templates/payments/index.html",
    "templates/payments/print.html",
    "templates/payments/print_payment.html",
    "templates/payments/receipts.html",
    "templates/payments/view_receipt.html",
]

BASE = "D:/Data/karaj/UAE/Azad-UAE"

def process_file(filepath):
    relpath = os.path.relpath(filepath, BASE)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    total = 0

    # P1: format(X) }} {{ something.currency [or Y] }}
    P1 = re.compile(
        r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}\s*\{\{\s*(\w+(?:\.\w+)*)\s*\.currency(?:\s+or\s+\S+)?\s*\}\}'
    )
    def r1(m):
        return '{{ format_currency(' + m.group(1).strip() + ', ' + m.group(2).strip() + '.currency) }}'
    content, n = P1.subn(r1, content)
    if n: print(f"  P1 (currency): {n}")
    total += n

    # P2: format(X) }} {{ tenant_currency_symbol }}
    P2 = re.compile(
        r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}\s*\{\{\s*tenant_currency_symbol\s*\}\}'
    )
    def r2(m):
        return '{{ format_currency(' + m.group(1).strip() + ') }}'
    content, n = P2.subn(r2, content)
    if n: print(f"  P2 (symbol): {n}")
    total += n

    # P3: format(X) }} AED
    P3 = re.compile(
        r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}\s*AED'
    )
    def r3(m):
        return "{{ format_currency(" + m.group(1).strip() + ", 'AED') }}"
    content, n = P3.subn(r3, content)
    if n: print(f"  P3 (AED): {n}")
    total += n

    # P4: format(X) }} {{ selected_currency }}
    P4 = re.compile(
        r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}\s*\{\{\s*selected_currency\s*\}\}'
    )
    def r4(m):
        return '{{ format_currency(' + m.group(1).strip() + ', selected_currency) }}'
    content, n = P4.subn(r4, content)
    if n: print(f"  P4 (selected_currency): {n}")
    total += n

    # P5: format(X) }} {{ Y.currency or tenant_currency_symbol }} (complex trailing)
    P5 = re.compile(
        r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}\s*\{\{([^}]+)\.currency(?:\s+or\s+tenant_currency_symbol)?\s*\}\}'
    )
    def r5(m):
        obj_match = re.match(r'\s*(\w+(?:\.\w+)*)', m.group(2).strip())
        obj = obj_match.group(1) if obj_match else ''
        return '{{ format_currency(' + m.group(1).strip() + ', ' + obj + '.currency) }}'
    content, n = P5.subn(r5, content)
    if n: print(f"  P5 (currency complex): {n}")
    total += n

    # P9: format(X) }} (no trailing) - must be LAST
    P9 = re.compile(
        r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}'
    )
    def r9(m):
        return '{{ format_currency(' + m.group(1).strip() + ') }}'
    content, n = P9.subn(r9, content)
    if n: print(f"  P9 (no trailing): {n}")
    total += n

    if total == 0:
        print(f"  No changes")
        return

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  TOTAL: {total} replacements")


if __name__ == '__main__':
    for fname in BATCH2_FILES:
        fpath = os.path.join(BASE, fname)
        print(f"\n--- {fname} ---")
        if not os.path.exists(fpath):
            print(f"  MISSING")
            continue
        process_file(fpath)
    print("\nDone.")
