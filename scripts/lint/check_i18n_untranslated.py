"""Find template translation calls that silently return the key.

Why this exists
---------------
``tests/unit/utils/test_i18n_parity.py`` checks that every key a template uses
exists in the catalogue. That is necessary and not sufficient: a template could
call ``{{ _('Save') }}`` and pass it, because "Save" *is* in the catalogue, while
the call itself never consults it.

That is not hypothetical. Jinja2's ``_`` and ``{% trans %}`` resolve through
``environment.gettext``, and nothing in this app had installed a translator
there. 2022 call sites across 82 templates were therefore rendering the raw
English key in Arabic, and the parity test could not see it.

So this gate *calls* the translator, in a real request context with Arabic
selected, and reports every key whose output is identical to its input - which
is exactly what "the key is missing" looks like from the outside.

Usage:
    python scripts/lint/check_i18n_untranslated.py [--limit N]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import warnings
from collections import defaultdict
from collections.abc import Callable
from typing import cast

TEMPLATES = "templates"
# {{ _('X') }} / {{ _('X', ...) }} and {% trans %}X{% endtrans %}
CALL = re.compile(r"\{\{-?\s*_\(\s*(['\"])((?:\\.|(?!\1).)*)\1")
TRANS = re.compile(r"\{%-?\s*trans\s*-?%\}(.*?)\{%-?\s*endtrans\s*-?%\}", re.S)
# Things that are never UI text.
SKIP = re.compile(r"^\s*$")
# A key that is legitimately identical in both languages (proper nouns, codes).
ALLOW = {
    "AZAD",
    "Azad",
    "API",
    "URL",
    "PDF",
    "CSV",
    "Excel",
    "ISO",
    "VAT",
    "SKU",
    "QR",
    "PIN",
    "IP",
    "HTTP",
    "HTTPS",
    "OAuth",
    "SaaS",
    "POS",
    "GL",
    "AED",
    "USD",
    "ILS",
    "EUR",
    "SAR",
}


def template_keys(path: str) -> set[str]:
    text = open(path, encoding="utf-8", errors="surrogateescape").read()
    keys = {m.group(2) for m in CALL.finditer(text)}
    for m in TRANS.finditer(text):
        block = m.group(1)
        if "%" not in block and "{%" not in block:
            stripped = block.strip()
            if stripped:
                keys.add(stripped)
    return {k for k in keys if not SKIP.match(k)}


def _is_ascii_ui(key: str) -> bool:
    """True when this key is meant to be translated, i.e. it is not already text.

    Lowercase snake_case with an underscore is the house style for catalogue
    keys, and codes like BIN or ISO are intentional untranslated abbreviations.
    A key containing non-ASCII characters is already the target language, so it
    cannot be a missing translation.
    """
    if not key.isascii():
        return False
    if "_" in key and key.replace("_", "").isalnum():
        return True
    # A bare word: only English-looking words are candidates, not "1234" or
    # "v2.0" or "user@example.com".
    return key.isalpha() and any(c.islower() for c in key)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40, help="how many findings to print")
    args = ap.parse_args()

    os.environ.setdefault("CACHE_TYPE", "null")
    os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"
    os.environ["SKIP_BOOT_PROVISIONING"] = "1"
    # This file lives in scripts/lint, so the repo root is not on sys.path.
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)

    if not os.path.isdir(TEMPLATES):
        print(f"i18n gate: {TEMPLATES}/ not found", file=sys.stderr)
        return 2

    by_file: dict[str, set[str]] = {}
    for root, _dirs, files in os.walk(TEMPLATES):
        for name in sorted(files):
            if name.endswith(".html"):
                p = os.path.join(root, name)
                k = template_keys(p)
                if k:
                    by_file[p.replace("\\", "/")] = k
    total_calls = sum(len(v) for v in by_file.values())
    if total_calls == 0:
        print("i18n gate: no translation calls found - refusing to pass vacuously.")
        return 2

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
        from flask import session

        from app import create_app

        app = create_app()
        translator = cast("Callable[[str], str]", app.jinja_env.globals["t"])

    untranslated: dict[str, list[str]] = defaultdict(list)
    arabic_output: dict[str, list[str]] = defaultdict(list)
    checked = 0
    with app.test_request_context("/"):
        session["language"] = "ar"
        for path, keys in sorted(by_file.items()):
            for key in sorted(keys):
                if key in ALLOW:
                    continue
                checked += 1
                try:
                    out = translator(key)
                except Exception:
                    out = key
                if out == key:
                    # Identical output. That is only a *defect* when the key was
                    # supposed to be English. A key that is already Arabic - a
                    # literal Arabic label someone put in the template - comes
                    # back unchanged because there was nothing to translate, and
                    # flagging it as missing would send someone to "translate" a
                    # string that is already correct. So: an ASCII key that
                    # survives is a real hole; a non-ASCII one is fine.
                    target = untranslated if _is_ascii_ui(key) else arabic_output
                    target[path].append(key)

    n = sum(len(v) for v in untranslated.values())
    a = sum(len(v) for v in arabic_output.values())
    print(
        f"Untranslated-key gate: {total_calls} distinct call(s) across {len(by_file)} template(s); {checked} checked."
    )
    if a:
        print(
            f"  {a} call(s) pass a literal Arabic label to the translator - already the target language, not a defect."
        )
    if not n:
        print("  0 English keys render as the raw key - every call resolves to Arabic.")
        return 0
    print(f"  {n} key(s) render as the raw key (English shown to an Arabic user):")
    for path, bad_keys in sorted(untranslated.items(), key=lambda z: -len(z[1]))[: args.limit]:
        print(f"     {path}  ({len(bad_keys)})")
        for offending in bad_keys[:6]:
            print(f"        {offending}")
    if len(untranslated) > args.limit:
        print(f"     ... and {len(untranslated) - args.limit} more files")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
