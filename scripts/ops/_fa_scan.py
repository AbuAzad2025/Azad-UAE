"""Scan the codebase for FontAwesome icon classes actually in use.

Outputs a JSON report: scripts/ops/_fa_used.json
"""
import json
import os
import re
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FA_DIR = os.path.join(ROOT, "static", "adminlte", "plugins", "fontawesome")
CSS_PATH = os.path.join(FA_DIR, "_original", "css", "all.min.css")

# Non-icon utility classes to exclude
EXCLUDE_EXACT = {
    "fa", "fas", "far", "fal", "fad", "fab", "fa-brands", "fa-regular",
    "fa-solid", "fa-light", "fa-duotone", "fa-thin", "fa-sharp", "fa-classic",
    "fa-fw", "fa-ul", "fa-li", "fa-border", "fa-spin", "fa-pulse",
    "fa-inverse", "fa-sr-only", "fa-stack", "fa-stack-1x", "fa-stack-2x",
    "fa-pull-left", "fa-pull-right", "fa-rotate-90", "fa-rotate-180",
    "fa-rotate-270", "fa-rotate-by", "fa-flip-horizontal", "fa-flip-vertical",
    "fa-flip-both", "fa-beat", "fa-fade", "fa-beat-fade", "fa-bounce",
    "fa-flip", "fa-shake", "fa-spin-pulse", "fa-spin-reverse", "fa-swap-opacity",
}
EXCLUDE_RE = re.compile(
    r"^fa-(\d+x|xs|sm|lg|xl|2xl|pull-|rotate-|flip-|stack|border|spin|pulse|"
    r"beat|fade|bounce|shake|swap-opacity|inverse|sr-only|fw|ul|li|layers)"
)

CANDIDATE_RE = re.compile(r"\bfa-[a-z0-9][a-z0-9-]*")

# Files/dirs to scan (relative to ROOT)
SCAN_GLOBS = [
    ("templates", (".html",)),
    ("static/js", (".js",)),
    ("static/css", (".css",)),
    ("routes", (".py",)),
    ("services", (".py",)),
    ("utils", (".py",)),
    ("models", (".py",)),
    ("forms", (".py",)),
    ("migrations", (".py",)),
    ("static/adminlte", (".css", ".js")),
]

SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git", "_original",
             "webfonts", "fonts", ".pytest_cache", "coverage-frontend",
             "fontawesome", "fontawesome-free", "bootstrap-icons"}


def parse_defined_icons(css_text):
    """Map icon class -> codepoint from the FA css."""
    icons = {}
    # rules look like: .fa-a:before,\n.fa-b:before {\n\tcontent: "\f232";\n}
    for m in re.finditer(
        r"((?:\.fa-[a-z0-9-]+:before\s*,?\s*)+)\{\s*content:\s*\"\\([0-9a-f]{2,4})\"",
        css_text,
    ):
        for sel in m.group(1).split(","):
            cm = re.match(r"\.(fa-[a-z0-9-]+)", sel.strip())
            if cm:
                icons[cm.group(1)] = m.group(2)
    return icons


def iter_files():
    for base, exts in SCAN_GLOBS:
        base_path = os.path.join(ROOT, base)
        if not os.path.isdir(base_path):
            continue
        for dirpath, dirnames, filenames in os.walk(base_path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if fn.endswith(exts):
                    yield os.path.join(dirpath, fn)


def main():
    with open(CSS_PATH, encoding="utf-8") as f:
        css_text = f.read()
    defined = parse_defined_icons(css_text)
    print(f"defined icons in css: {len(defined)}")

    used = defaultdict(set)  # icon -> set of files
    raw_excluded = defaultdict(int)
    for path in iter_files():
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        rel = os.path.relpath(path, ROOT)
        for m in CANDIDATE_RE.finditer(text):
            name = m.group(0).rstrip("-")
            if name in defined:
                used[name].add(rel)
            else:
                raw_excluded[name] += 1  # utility class or non-icon

    # Also catch direct content:"\fXXX" usages in our css/js (icon by codepoint)
    direct_codepoints = set()
    for path in iter_files():
        if not (path.endswith(".css") or path.endswith(".js")):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        for m in re.finditer(r'content:\s*["\']\\(f[0-9a-f]{2,4})["\']', text):
            direct_codepoints.add(m.group(1))

    report = {
        "used_icons": {k: sorted(v) for k, v in sorted(used.items())},
        "excluded_candidates": dict(sorted(raw_excluded.items())),
        "direct_codepoints": sorted(direct_codepoints),
        "defined_count": len(defined),
    }
    out = os.path.join(ROOT, "scripts", "ops", "_fa_used.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(f"used icons: {len(used)}")
    print(f"direct codepoints: {sorted(direct_codepoints)}")
    print("excluded/unknown candidates:", dict(sorted(raw_excluded.items())))


if __name__ == "__main__":
    main()
