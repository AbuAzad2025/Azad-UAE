import re
import os

BATCH1_FILES = [
    "templates/invoices/classic.html",
    "templates/invoices/gulf.html",
    "templates/invoices/minimal.html",
    "templates/invoices/modern.html",
    "templates/invoices/simple.html",
    "templates/receipts/classic.html",
    "templates/receipts/gulf.html",
    "templates/receipts/minimal.html",
    "templates/receipts/modern.html",
    "templates/receipts/simple.html",
    "templates/sales/view.html",
    "templates/sales/print.html",
    "templates/sales/index.html",
    "templates/sales/archived.html",
    "templates/returns/view.html",
    "templates/returns/index.html",
]

BASE = "D:/Data/karaj/UAE/Azad-UAE"

# Match format(X) }} {{ expr.currency }}
# Captures: the format() argument, and the full currency variable (e.g. "sale.currency or tenant_currency_symbol")
P_CURRENCY = re.compile(
    r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}\s*\{\{\s*([^}]+?)\.currency\s*\}\}'
)

# Match format(X) }} {{ tenant_currency_symbol }}
P_SYMBOL = re.compile(
    r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}\s*\{\{\s*tenant_currency_symbol\s*\}\}'
)

# Match format(X) }} AED
P_AED = re.compile(
    r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}\s*AED'
)

# Match format(X) }} (no trailing currency)
P_NONE = re.compile(
    r'\{\{\s*["\']\{:,.2f\}["\']\.format\(([^)]+)\)\s*\}\}'
)

def process_file(filepath):
    relpath = os.path.relpath(filepath, BASE)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    total = 0

    # Pass 1: trailing {{ something.currency }}
    def r1(m):
        expr = m.group(1).strip()
        obj = m.group(2).strip()
        return '{{ format_currency(' + expr + ', ' + obj + '.currency) }}'
    content, n = P_CURRENCY.subn(r1, content)
    if n:
        print(f"  P1 (currency trailing): {n}")
    total += n

    # Pass 2: trailing {{ tenant_currency_symbol }}
    def r2(m):
        expr = m.group(1).strip()
        return '{{ format_currency(' + expr + ') }}'
    content, n = P_SYMBOL.subn(r2, content)
    if n:
        print(f"  P2 (symbol trailing): {n}")
    total += n

    # Pass 3: trailing AED
    def r3(m):
        expr = m.group(1).strip()
        return "{{ format_currency(" + expr + ", 'AED') }}"
    content, n = P_AED.subn(r3, content)
    if n:
        print(f"  P3 (AED trailing): {n}")
    total += n

    # Pass 4: no trailing (only if no previous pass consumed it)
    def r4(m):
        expr = m.group(1).strip()
        return '{{ format_currency(' + expr + ') }}'
    content, n = P_NONE.subn(r4, content)
    if n:
        print(f"  P4 (no trailing): {n}")
    total += n

    if total == 0:
        print(f"  No changes")
        return

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  TOTAL: {total} replacements")


if __name__ == '__main__':
    for fname in BATCH1_FILES:
        fpath = os.path.join(BASE, fname)
        print(f"\n--- {fname} ---")
        if not os.path.exists(fpath):
            print(f"  MISSING")
            continue
        process_file(fpath)
    print("\nDone.")
