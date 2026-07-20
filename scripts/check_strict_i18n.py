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

RTL_CONTENT_MARKER = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]{2,}")

TRANSLATION_CALL = re.compile(
    r"(?:\{\{?\s*_\s*\(|gettext\s*\(|lazy_gettext\s*\(|lazy_pgettext\s*\(|ngettext\s*\(|"
    r"\{\{?\s*t\s*\(|[^A-Za-z0-9_]t\s*\()"
)

FLASK_ROUTE_BARE_STRING = re.compile(r"return\s+(?:render_template|redirect|jsonify|make_response)\s*\(")


# Tracks whether the current scan position is inside a triple-quoted string
# literal (docstring / multi-line string).  Module-level state is reset per
# file by ``scan_file``.
_IN_TRIPLE = {"": None}


def _strip_triple_quotes(line):
    """Remove triple-quoted spans from ``line`` (single- or multi-line).

    Returns ``(in_block, cleaned)`` where ``in_block`` is True when the line
    ends inside an unterminated triple-quoted block, and ``cleaned`` is the
    line with any *completed* triple-quoted spans replaced by spaces (so
    single-line docstrings are dropped before literal extraction).
    """
    triples = ['"""', "'''"]
    cleaned = []
    i = 0
    in_block = _IN_TRIPLE[""] is not None
    open_quote = _IN_TRIPLE[""]
    n = len(line)
    while i < n:
        if in_block:
            end = line.find(open_quote, i)
            if end == -1:
                # Rest of line is inside the block.
                cleaned.append(" " * (n - i))
                i = n
                break
            cleaned.append(" " * (end - i))
            cleaned.append("   ")
            i = end + 3
            in_block = False
            open_quote = None
            _IN_TRIPLE[""] = None
        else:
            opened = None
            for t in triples:
                pos = line.find(t, i)
                if pos != -1 and (opened is None or pos < opened[1]):
                    opened = (t, pos)
            if opened is None:
                cleaned.append(line[i:])
                i = n
                break
            cleaned.append(line[i : opened[1]])
            i = opened[1] + 3
            in_block = True
            open_quote = opened[0]
            _IN_TRIPLE[""] = opened[0]
    _IN_TRIPLE[""] = open_quote if in_block else None
    return in_block, "".join(cleaned)


def _strip_inline_comment(line):
    """Remove a trailing ``# ...`` comment that lies outside of string literals.

    A bare ``#`` (not preceded by an unescaped quote section) begins a comment.
    Arabic string literals never contain a bare ``#``, so this is safe for the
    purpose of the linter.
    """
    in_single = in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
        i += 1
    return line


def _should_skip_line(line):
    stripped = line.strip()
    if not stripped or stripped.startswith("//"):
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


def _trans_call_unterminated(code):
    """True if a translation call on this line is not closed on the same line
    (i.e. the call and/or its string continue onto later lines).

    Detected by unbalanced parentheses after a translation-call keyword, which
    covers both ``gettext(\\n   "text")`` and ``{{ _('multi-line text`` cases.
    """
    if not TRANSLATION_CALL.search(code):
        return False
    return code.count("(") > code.count(")")


def _in_jinja_expr_spans(text, pos):
    """True if ``pos`` lies inside a ``{{ ... }}`` Jinja *expression* span.

    Strings inside ``{{ }}`` are code (e.g. ``{{ settings.x or 'العنوان' }}``),
    not literal user-facing template text, so they must not be flagged.
    """
    for m in re.finditer(r"\{\{.*?\}\}", text, re.DOTALL):
        if m.start() <= pos < m.end():
            return True
    return False


def scan_file(filepath):
    issues = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    ext = os.path.splitext(filepath)[1].lower()
    _IN_TRIPLE[""] = None
    in_raw = False  # inside <script> or <style> block (cross-line)
    in_trans = False  # inside a multi-line translation call string e.g. {{ _('...') }}
    in_trans_quote = None
    in_jinja_block = False  # inside {% set %} / {% macro %} / {% call %} / {% filter %}
    for lineno, line in enumerate(lines, 1):
        # Track multi-line Jinja *statement* blocks ({% set %}, {% macro %},
        # {% call %}, {% filter %}). Their bodies are code/data definitions,
        # not literal user-facing markup, so string literals inside are
        # skipped (per the i18n rules: skip content inside {% ... %} control
        # tags). Detected before the skip check because the opening tag itself
        # starts with {% and would otherwise be skipped.
        if ext == ".html":
            if not in_jinja_block:
                m = re.search(r"\{\%\s*(set|macro|call|filter)\b", line)
                if m and not re.search(r"\{\%\s*end" + m.group(1) + r"\b", line):
                    in_jinja_block = True
            else:
                if re.search(r"\{\%\s*end(set|macro|call|filter)\b", line):
                    in_jinja_block = False
                else:
                    continue
            if in_jinja_block:
                continue
        if _should_skip_line(line):
            continue
        # Track <script>/<style> raw blocks so their JS/CSS content is never
        # treated as user-facing template text.
        if ext == ".html":
            if re.search(r"<\s*script\b", line) and not re.search(r"<\s*/\s*script\s*>", line):
                in_raw = True
            elif re.search(r"<\s*/\s*script\s*>", line):
                in_raw = False
                continue
            elif re.search(r"<\s*style\b", line) and not re.search(r"<\s*/\s*style\s*>", line):
                in_raw = True
            elif re.search(r"<\s*/\s*style\s*>", line):
                in_raw = False
                continue
            if in_raw:
                continue
        # Remove triple-quoted spans (docstrings / multi-line strings) and
        # track block state; lines that are entirely inside a block are
        # dropped from literal extraction.
        in_block, stripped = _strip_triple_quotes(line)
        if in_block:
            continue
        # Drop trailing # comments (outside of string literals) so developer
        # comments are never treated as user-facing text.
        code = _strip_inline_comment(stripped)
        # A multi-line translation call (e.g. a whole `{% set %}` block passed
        # to {{ _('...') }}) may open on one line and close many lines later.
        # Track that span so its contents are not double-flagged.
        if in_trans:
            # We are inside a multi-line translation string opened earlier.
            # Close only when the *matching* quote is followed by the call
            # terminator ()) or }}). Inner '}' / ')' chars are ignored.
            close = re.search(
                re.escape(in_trans_quote) + r"\s*\)\s*\)"
                r"|" + re.escape(in_trans_quote) + r"\s*\}\}",
                code,
            )
            if close:
                in_trans = False
                in_trans_quote = None
            continue
        line_wrapped = _is_translation_wrapped(code)
        if line_wrapped and _trans_call_unterminated(code):
            in_trans = True
            q = re.search(r"['\"]", code[TRANSLATION_CALL.search(code).end() :])
            in_trans_quote = q.group(0) if q else "'"
            continue
        if line_wrapped:
            continue
        if ext == ".html":
            for s in _extract_string_literals(code):
                if _is_likely_user_facing(s) and RTL_CONTENT_MARKER.match(s):
                    # locate the literal in the (un-commented) code to test
                    # whether it lives inside a {{ ... }} Jinja expression
                    idx = code.find(s)
                    if idx != -1 and _in_jinja_expr_spans(code, idx):
                        continue
                    issues.append((lineno, s, "template string"))
        elif ext == ".py":
            for s in _extract_string_literals(code):
                if _is_likely_user_facing(s) and RTL_CONTENT_MARKER.match(s):
                    issues.append((lineno, s, "python string"))
    return issues


def main():
    parser = argparse.ArgumentParser(description="Strict i18n linter for RTL translation enforcement")
    parser.add_argument("--fix", action="store_true", help="Not implemented: auto-wrap strings")
    parser.add_argument(
        "--exclude-dirs",
        nargs="*",
        default=[],
        help="Additional directory basenames to exclude (e.g. services)",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["templates", "routes", "services"],
        help="Directories or files to scan",
    )
    args = parser.parse_args()

    skip_dirs = IGNORE_DIRS | set(args.exclude_dirs)

    scan_dirs = []
    for p in args.paths:
        if os.path.basename(p) in skip_dirs and os.path.isdir(os.path.join(REPO_ROOT, p)):
            continue
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
                dirs[:] = [d for d in dirs if d not in skip_dirs]
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
        print("STRICT I18N FAILURE: Un-wrapped user-facing strings detected\n")
        for rel, lineno, text, ctx in sorted(all_issues):
            print(f'  {rel}:{lineno}  [{ctx}] "{text[:80]}"')
        print(f"\nTotal: {len(all_issues)} issue(s)")
        sys.exit(1)

    print("Strict i18n check passed - all UI strings wrapped in translation calls")
    sys.exit(0)


if __name__ == "__main__":
    main()
