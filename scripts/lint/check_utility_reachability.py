"""Fail when a template uses a utility class whose stylesheet is not reachable.

A `.w-*` or `.d-*` class resolves to nothing unless something in the template's
extends-chain links the stylesheet that defines it. The page still renders, the
template still parses, every test still passes, and the element is simply
unstyled.

This is not hypothetical. layout-utilities.css and dashboard-utilities.css were
referenced by 30 templates and linked from no layout at all, so all of it was
inert. check_inline_assets.py cannot catch it: that check looks at p-*/u-* and
only at standalone templates that carry no <link> whatsoever, and these
templates inherit a head full of links from their parent layout.

So the check is here instead of there: resolve the extends-chain, collect every
stylesheet the chain links, and compare that against the classes the template
actually uses. Partials are skipped - a partial legitimately has no chain of its
own and resolves its classes in the including page.

This is a gate, not a report: it exits non-zero when a page uses a class it
cannot reach.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
CSS = ROOT / "static" / "css"

# Prefixes that live in the extracted utility sheets.
UTILITY_PREFIXES = ("p-", "u-", "w-", "h-", "d-panel", "d-fs", "d-bar", "d-stagger", "fin-")

_SHEET_REF = re.compile(r"""(?:static/)?css/([A-Za-z0-9_.-]+\.css)""")
_EXTENDS = re.compile(r"""\{%-?\s*extends\s+["']([^"']+)["']""")
_INCLUDE = re.compile(r"""\{%-?\s*include\s+["']([^"']+)["']""")
_CLASS_ATTR = re.compile(r"""class\s*=\s*["']([^"']*)["']""")


def _resolve(name: str) -> pathlib.Path | None:
    """Jinja template names are relative to templates/, without the extension."""
    candidate = TEMPLATES / (name if name.endswith(".html") else f"{name}.html")
    return candidate if candidate.is_file() else None


def _defined_classes(sheet: str) -> set[str]:
    path = CSS / sheet
    if not path.is_file():
        return set()
    return set(re.findall(r"\.([A-Za-z0-9_-]+)", path.read_text(encoding="utf-8", errors="replace")))


def _linked_sheets(text: str) -> set[str]:
    return set(_SHEET_REF.findall(text))


def _chain(path: pathlib.Path, seen: set[str] | None = None) -> list[pathlib.Path]:
    """The template, every layout it extends, and every partial it includes.

    Includes matter as much as extends here: templates/base.html pulls in
    partials/head.html, and that partial is where layout-utilities.css is
    actually linked. Following extends alone made the gate demand a second,
    duplicate <link> on every page that already had one.
    """
    seen = seen if seen is not None else set()
    if path.as_posix() in seen:
        return []
    seen.add(path.as_posix())
    chain = [path]
    text = path.read_text(encoding="utf-8", errors="replace")
    match = _EXTENDS.search(text)
    if match:
        parent = _resolve(match.group(1))
        if parent is not None:
            chain.extend(_chain(parent, seen))
    for inc in _INCLUDE.findall(text):
        partial = _resolve(inc)
        if partial is not None:
            chain.extend(_chain(partial, seen))
    return chain


def main() -> int:
    if not CSS.is_dir():
        print(f"FAIL: {CSS} not found", file=sys.stderr)
        return 1

    class_sheet: dict[str, str] = {}
    for sheet_path in CSS.glob("*.css"):
        for class_name in _defined_classes(sheet_path.name):
            class_sheet.setdefault(class_name, sheet_path.name)

    findings: list[str] = []
    checked = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        is_page = "<html" in text.lower() or "<!doctype" in text.lower()
        extends_layout = _EXTENDS.search(text) is not None
        if not (is_page or extends_layout):
            # A true partial or macro: it is included by pages that do carry a
            # head, so its classes resolve in the including page and there is no
            # chain of its own to walk.
            continue
        used: set[str] = set()
        for attr in _CLASS_ATTR.findall(text):
            used.update(attr.split())
        utility_used = {c for c in used if c.startswith(UTILITY_PREFIXES) and c in class_sheet}
        if not utility_used:
            continue

        chain = _chain(path)
        reachable: set[str] = set()
        for link in chain:
            reachable |= _linked_sheets(link.read_text(encoding="utf-8", errors="replace"))
        reachable_classes: set[str] = set()
        for sheet in reachable:
            reachable_classes |= _defined_classes(sheet)

        checked += 1
        rel = path.relative_to(ROOT).as_posix()
        for name in sorted(utility_used - reachable_classes):
            findings.append(f"{rel}: uses .{name} but {class_sheet[name]} is not linked by it or any layout it extends")

    print(f"Utility reachability: {checked} full page(s) checked, {len(findings)} unreachable class(es).")
    if findings:
        print("\nFAIL")
        for line in findings:
            print(f"  - {line}")
        return 1
    print("OK: every utility class used by a page is reachable through its extends-chain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
