"""Report catalogue keys that exist in utils/i18n.py but are unreachable.

Different question from check_i18n_untranslated.py. That gate asks "does a
template call that renders untranslated?" and the answer is now zero. This asks
the complementary one: which catalogue entries are English-only, or carry an
English string on the Arabic side, i.e. a user would see English.

Categories reported:
  no_ar        key has no "ar" value at all -> falls back to the key
  ar_is_ascii  the "ar" value is still English (placeholder or untranslated)
  missing_en   the "ar" value exists but there is no "en" value
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# The keys and values are Arabic. On a Windows console with the default cp1252
# code page, printing one raises UnicodeEncodeError and the gate would exit
# non-zero for the wrong reason - reported as a catalogue failure when the
# catalogue is fine. Force UTF-8 on both streams so the gate reports the data,
# not the terminal.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# Entries whose Arabic side is deliberately not Arabic: acronyms that are spelled
# the same in both languages, locale tags, direction tokens, and the language
# switcher's own label (it names the *other* language, so it is a word on purpose).
INTENTIONALLY_ASCII = {
    "API",
    "BIN",
    "SKU",
    "AR",
    "ar",
    "en",
    "dir_ltr",
    "ltr",
    "og_locale",
    "ar_AE",
    "en_US",
    "lang_switch_btn",
    "lang_switch_code",
    "lang_switch_label",
    "meta_language",
    "Default_Sender_Email",
    "Paper_Letter",
    "IP Column",
    # Paper sizes and shared punctuation, identical in both languages.
    "Paper_A4",
    "Paper_A5",
    "...",
    "-",
    # A truncated source string kept in the catalogue. Not referenced by any
    # template or route, so it is never rendered; it is listed here rather than
    # deleted because pruning the catalogue is a separate change.
    "Hello, I would like to subscribe to the ",
    # The language switcher's label. Its key is the word "English" and its Arabic
    # value is "English" too - deliberately: the button names the language the
    # user would switch *to*, not the one they are reading. It is English on
    # purpose, so it is excluded from this check.
    "English",
    # The other half of the same switcher: Arabic "English" and English "العربية".
    # Both name the language the user would switch *to*, so each is written in
    # that language, not the current one.
    "العربية",
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Report translation-catalogue health. Exits non-zero when a key is "
        "unusable, so it can serve as a CI gate as well as a report."
    )
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--category", choices=["no_ar", "ar_is_ascii", "missing_en"])
    args = ap.parse_args()

    from utils.i18n import TRANSLATIONS

    buckets: dict[str, list[str]] = {"no_ar": [], "ar_is_ascii": [], "missing_en": []}
    for key, value in TRANSLATIONS.items():
        ar = (value.get("ar") or "").strip() if isinstance(value, dict) else ""
        en = (value.get("en") or "").strip() if isinstance(value, dict) else ""
        if not ar:
            buckets["no_ar"].append(key)
        elif key not in INTENTIONALLY_ASCII and ar.isascii() and re.search(r"[A-Za-z]{2,}", ar):
            buckets["ar_is_ascii"].append(key)
        if ar and not en:
            buckets["missing_en"].append(key)

    total = len(TRANSLATIONS)
    print(f"Catalogue: {total} entries in utils/i18n.py")
    for name, items in buckets.items():
        mark = "  <-- " if name == args.category else ""
        print(f"  {name:12} {len(items):5}{mark}")
    print()

    if args.category:
        items = buckets[args.category]
        print(f"{args.category}: {len(items)} key(s)")
        for k in sorted(items)[: args.limit]:
            v = TRANSLATIONS[k]
            print(f"   {k!r:44} ar={v.get('ar')!r}")
        if len(items) > args.limit:
            print(f"   ... and {len(items) - args.limit} more")
        return 0

    # Gate behaviour. A key with no Arabic value at all is unusable: t() returns
    # the key, so the user sees English. A key whose Arabic side is still English
    # is the same failure recorded in place rather than as a missing entry, and
    # INTENTIONALLY_ASCII holds the ones where that is deliberate.
    unusable = len(buckets["no_ar"]) + len(buckets["ar_is_ascii"])
    if unusable:
        print(f"  FAIL: {unusable} key(s) would render as English to an Arabic user.")
        for name in ("no_ar", "ar_is_ascii"):
            for k in sorted(buckets[name])[: args.limit]:
                print(f"     [{name}] {k!r} ar={TRANSLATIONS[k].get('ar')!r}")
        return 1

    print(f"  OK: every one of {total} keys resolves to Arabic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
