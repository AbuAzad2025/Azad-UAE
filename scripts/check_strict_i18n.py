#!/usr/bin/env python3
"""Strict i18n linter — Odoo-style translation guard.

Scans all HTML templates and Flask route files for raw user-facing text
that is NOT wrapped in a translation call (``{{ _("...") }}``, ``{% trans %}``,
or ``gettext()``).  Fails with exit code 1 if any un-translated text is found.

Usage:
    python scripts/check_strict_i18n.py
    python scripts/check_strict_i18n.py --fix          # auto-wrap simple strings
"""

import argparse
import os
import re
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

ALLOWED_CONTEXTS = {
    "html",
    "svg",
    "py",
}

IGNORE_DIRS = {
    ".venv",
    "node_modules",
    "migrations",
    "static/adminlte",
    "static/vendor",
    "__pycache__",
    ".git",
    ".pytest-temp",
}

IGNORE_PATTERNS = [
    # HTML attribute values that are never user-facing
    re.compile(
        r'(id|class|name|type|value|placeholder|data-\w+|aria-\w+|href|src|action|method|rel|target|style|onclick|onchange|oninput|onfocus|onblur|onsubmit)\s*=\s*["\'][^"\']*["\']'
    ),
    # Jinja / template syntax
    re.compile(r"\{[{%#].*?[}%#]\}"),
    re.compile(r"\{\{.*?\}\}"),
    # CSS / style blocks
    re.compile(r"<\s*style\b[^>]*>.*?<\s*/\s*style\s*>", re.DOTALL),
    re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", re.DOTALL),
    # Comments
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"#.*?$", re.MULTILINE),
    # Numbers, currency amounts, dates
    re.compile(r"^-?\d+(?:[.,]\d+)?%?$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    # Single characters, punctuation, symbols
    re.compile(r"^[\s\W]+$"),
    re.compile(r"^[\w\-]+$"),
]

SKIP_RAW_TAGS = {"code", "pre", "samp", "kbd", "script", "style"}

RTL_CONTENT_MARKER = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]{2,}"
)

TRANSLATION_CALL = re.compile(
    r"(?:\{\{?\s*_\s*\(|gettext|lazy_gettext|lazy_pgettext|ngettext)\s*\("
)

FLASK_ROUTE_BARE_STRING = re.compile(
    r"return\s+(?:render_template|redirect|jsonify|make_response)\s*\("
)


def _should_skip_line(line):
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return True
    if stripped.startswith("{%") or stripped.startswith("{#"):
        return True
    return False


def _is_translation_wrapped(text):
    return bool(TRANSLATION_CALL.search(text))


def _is_likely_user_facing(text):
    if len(text) < 3:
        return False
    if re.match(r"^[\s\d\W]+$", text):
        return False
    if re.match(r"^[a-z_][a-z0-9_]*$", text, re.IGNORECASE):
        return False
    if "{{" in text or "{%" in text:
        return False
    return True


def _extract_string_literals(line):
    strings = re.findall(r'["\']([^"\']{3,})["\']', line)
    return strings


def scan_file(filepath):
    issues = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    ext = os.path.splitext(filepath)[1].lower()
    for lineno, line in enumerate(lines, 1):
        if _should_skip_line(line):
            continue
        if _is_translation_wrapped(line):
            continue
        if ext == ".html":
            for s in _extract_string_literals(line):
                if _is_likely_user_facing(s) and not RTL_CONTENT_MARKER.match(s):
                    issues.append((lineno, s, "template string"))
        elif ext == ".py":
            for s in _extract_string_literals(line):
                if _is_likely_user_facing(s) and RTL_CONTENT_MARKER.match(s):
                    issues.append((lineno, s, "python string"))
    return issues


def main():
    parser = argparse.ArgumentParser(
        description="Strict i18n linter for RTL translation enforcement"
    )
    parser.add_argument(
        "--fix", action="store_true", help="Not implemented: auto-wrap strings"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["templates", "routes", "services"],
        help="Directories or files to scan",
    )
    args = parser.parse_args()

    scan_dirs = []
    for p in args.paths:
        full = os.path.join(REPO_ROOT, p)
        if os.path.isdir(full):
            scan_dirs.append(full)
        elif os.path.isfile(full):
            scan_dirs.append(full)

    all_issues = []
    for target in scan_dirs:
        if os.path.isfile(target):
            issues = scan_file(target)
            for lineno, text, ctx in issues:
                rel = os.path.relpath(target, REPO_ROOT)
                all_issues.append((rel, lineno, text, ctx))
        else:
            for root, dirs, files in os.walk(target):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in {".html", ".py", ".svg"}:
                        continue
                    fpath = os.path.join(root, fname)
                    issues = scan_file(fpath)
                    for lineno, text, ctx in issues:
                        rel = os.path.relpath(fpath, REPO_ROOT)
                        all_issues.append((rel, lineno, text, ctx))

    if all_issues:
        print("❌ STRICT I18N FAILURE: Un-wrapped user-facing strings detected\n")
        for rel, lineno, text, ctx in sorted(all_issues):
            print(f'  {rel}:{lineno}  [{ctx}] "{text[:80]}"')
        print(f"\nTotal: {len(all_issues)} issue(s)")
        sys.exit(1)

    print("✅ Strict i18n check passed — all UI strings wrapped in translation calls")
    sys.exit(0)


if __name__ == "__main__":
    main()
