#!/usr/bin/env python3
"""i18n_lint.py — permanent lint gate for utils/i18n.py

Detects:
- Duplicate TRANSLATIONS dict keys
- Mixed-script keys (Arabic + Latin in same token, excluding POS/QR/VAT/ERP/CRM/URL/API/ID/PDF/CSV/SMS/UAE)
- Values containing underscore+digits (corruption marker)

Exit code 0 = clean, 1 = violations found.
"""
import ast
import re
import sys

EXCLUDED_MIXED = {"POS", "QR", "VAT", "ERP", "CRM", "URL", "API", "ID", "PDF", "CSV", "SMS", "UAE", "TRN", "A4", "A5", "COD", "PG", "DB", "AI", "EBILAEAD", "JSON", "TXT", "SQL", "HTML", "CSS", "JS", "PWA", "IBAN", "SWIFT", "VAT"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    path = r"D:\Data\karaj\UAE\Azad-UAE\utils\i18n.py"
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    # 1. AST parse
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"SYNTAX ERROR: {e}")
        return 1
    print("AST parse: OK")

    # 2. Extract TRANSLATIONS keys (top-level only)
    keys = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TRANSLATIONS":
                    if isinstance(node.value, ast.Dict):
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                keys.append(k.value)
                        break

    print(f"Keys found: {len(keys)}")

    # 3. Duplicates
    from collections import Counter
    dups = [k for k, c in Counter(keys).items() if c > 1]
    if dups:
        print(f"FAIL: {len(dups)} duplicate keys:")
        for k in dups:
            print(f"  {k}")
        return 1
    print("Duplicates: None")

    # 4. Mixed-script keys
    arabic_re = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
    latin_re = re.compile(r"[A-Za-z]")
    mixed = []
    for k in keys:
        tokens = re.findall(r"[A-Za-z0-9_\u0600-\u06FF]+", k)
        for tok in tokens:
            if arabic_re.search(tok) and latin_re.search(tok):
                if tok.upper() not in EXCLUDED_MIXED and not any(tok.upper().startswith(x) for x in EXCLUDED_MIXED):
                    mixed.append(k)
                    break
    if mixed:
        print(f"FAIL: {len(mixed)} mixed-script keys:")
        for k in mixed:
            print(f"  {k}")
        return 1
    print("Mixed-script keys: None")

    # 5. Values with _digits (inside TRANSLATIONS values only)
    bad_values = []
    underscore_digit_re = re.compile(r"_[0-9]")
    translations_dict = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TRANSLATIONS":
                    if isinstance(node.value, ast.Dict):
                        translations_dict = node.value
                        break
    if translations_dict:
        for k, v in zip(translations_dict.keys, translations_dict.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                key = k.value
                if isinstance(v, ast.Dict):
                    for sk, sv in zip(v.keys, v.values):
                        if isinstance(sk, ast.Constant) and sk.value == "ar" and isinstance(sv, ast.Constant):
                            val = sv.value
                            if isinstance(val, str) and underscore_digit_re.search(val):
                                bad_values.append((key, val))
    if bad_values:
        print(f"FAIL: {len(bad_values)} values with _digits:")
        for k, v in bad_values[:20]:
            print(f"  {k} => {v}")
        return 1
    print("Values with _digits: None")

    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
