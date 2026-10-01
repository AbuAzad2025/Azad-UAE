"""Lint gate for the inline-style / inline-script cleanup.

Reports, and optionally fails on, the three things the template cleanup is
reducing:

  1. static  ``style="..."``      - has a fixed value, so it belongs in a
                                     stylesheet
  2. dynamic ``style="..."``      - contains a Jinja expression, so it CANNOT
                                     move to a stylesheet as-is
  3. inline ``<script>`` blocks   - belong in /static/js

It is a reporting gate by default because categories 2 and 3 are not yet zero
and a red CI on an inventory nobody can move is noise. Pass --max-static (and
optionally --max-dynamic / --max-inline-scripts) to turn each into a budget
that only ratchets downward.

The dynamic count is tracked separately on purpose. "Zero inline styles" is not
achievable for it: a value computed per row - a stage colour, a progress
percentage, an animation delay from loop.index0 - has no stylesheet to live in.
The correct end state is a CSS custom property read from a data- attribute, which
still needs one style attribute. Counting it as the same class of problem as
``display:inline`` is how you end up deleting working templates.
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"

# style="..." anywhere, including single-quoted
_STYLE_ATTR = re.compile(r"""\sstyle\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""", re.S)
_SCRIPT_BLOCK = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>", re.I)
_OPEN_JINJA = re.compile(r"\{\{|\{%")


def _is_dynamic(value: str) -> bool:
    return bool(_OPEN_JINJA.search(value))


def scan() -> tuple[collections.Counter, list[tuple[str, str]], int, int]:
    static_values: collections.Counter = collections.Counter()
    dynamic: list[tuple[str, str]] = []
    static_total = 0
    script_blocks = 0
    script_files = 0

    for path in sorted(TEMPLATES.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(ROOT).as_posix()

        scripts = _script_ranges(text)
        for match in _STYLE_ATTR.finditer(text):
            if _in_ranges(scripts, match.start()):
                # JavaScript building a style string, not a template attribute.
                continue
            value = " ".join(match.group("val").split())
            if not value:
                continue
            if _is_dynamic(value):
                dynamic.append((rel, value))
            else:
                static_values[value] += 1
                static_total += 1

        blocks = len(_SCRIPT_BLOCK.findall(text))
        if blocks:
            script_blocks += blocks
            script_files += 1

    return static_values, dynamic, static_total, (script_blocks, script_files)


_SCRIPT_BODY = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.S | re.I)


def _script_ranges(text: str) -> list[tuple[int, int]]:
    """Byte ranges covered by inline <script> bodies.

    Without this the style regex matches JavaScript source, because JS assigns
    to element.style and builds style strings by concatenation. Two hits in
    partials/upgrade_banner.html were exactly that - "animation-delay:' + (...)"
    is a string being built, not an attribute - and they were being counted as
    inline styles and would have been "converted" by a mapper that treated them
    as real.
    """
    return [(m.start(1), m.end(1)) for m in _SCRIPT_BODY.finditer(text)]


def _in_ranges(ranges: list[tuple[int, int]], pos: int) -> bool:
    return any(start <= pos < end for start, end in ranges)


def _unlinked_utility_classes() -> list[tuple[str, str]]:
    """Utility classes used in a template that loads no stylesheet.

    A .p-* or .u-* class resolves to nothing if the page never links the
    stylesheet that defines it. This is not hypothetical: the print batch
    converted shop/order_invoice.html, which loads no <link> at all, so five
    elements silently lost their formatting. Nothing caught it - the template
    gate only parses, and no test renders that page, because it is rendered
    standalone for email / direct download / PDF.

    Only *full pages* are checked. A partial or a template that extends a layout
    legitimately has no <link> of its own - it inherits the head from its
    parent, so 77 of the templates that matched at first were false positives.
    The distinguishing feature is that a standalone document contains its own
    <html>, and that is also the case that breaks: shop/order_invoice.html is
    opened directly for email / download / PDF and nothing else supplies CSS.

    Self-contained is the right choice for those, so they must stay inline
    rather than adopt classes. This function is how that gets enforced instead
    of remembered.
    """
    findings: list[tuple[str, str]] = []
    utility = re.compile(r"""class\s*=\s*["'][^"']*\b([pu]-[a-z0-9-]+)""")
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "<link" in text or "stylesheet" in text:
            continue  # loads at least one stylesheet
        lowered = text.lower()
        if "<html" not in lowered and "<!doctype" not in lowered:
            continue  # a partial; inherits its parent's head
        for match in utility.finditer(text):
            findings.append((path.relative_to(ROOT).as_posix(), match.group(1)))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-static", type=int, default=None)
    parser.add_argument("--max-dynamic", type=int, default=None)
    parser.add_argument("--max-inline-scripts", type=int, default=None)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument(
        "--list",
        action="store_true",
        help="print every occurrence, not just the top values",
    )
    args = parser.parse_args()

    static_values, dynamic, static_total, (script_blocks, script_files) = scan()
    unlinked = _unlinked_utility_classes()

    print("Inline-style / inline-script inventory")
    print(f"  templates scanned          : {len(list(TEMPLATES.rglob('*.html')))}")
    print(f'  static  style="..."        : {static_total} occurrences, {len(static_values)} distinct')
    print(f'  dynamic style="...{{ }}"   : {len(dynamic)}')
    print(f"  inline <script> blocks     : {script_blocks} across {script_files} templates")
    print(f"  utility classes unlinked   : {len(unlinked)}  (standalone pages only)")

    if unlinked:
        print("\n  FAIL - these templates load no stylesheet, so these classes resolve to nothing:")
        for rel, cls in unlinked[:20]:
            print(f"    {rel}: .{cls}")

    if static_values:
        print("\n  most common static values:")
        for value, count in static_values.most_common(args.top):
            print(f"    x{count:<4}{value[:66]}")

    if dynamic:
        print("\n  dynamic values cannot move to a stylesheet as-is:")
        shown = dynamic if args.list else dynamic[: args.top]
        for rel, value in shown:
            print(f"    {rel}: {value[:60]}")
        if not args.list and len(dynamic) > args.top:
            print(f"    ... and {len(dynamic) - args.top} more")

    failures = []
    if unlinked:
        failures.append(f"{len(unlinked)} utility class(es) used in template(s) that load no stylesheet")
    if args.max_static is not None and static_total > args.max_static:
        failures.append(f"static inline styles: {static_total} > budget {args.max_static}")
    if args.max_dynamic is not None and len(dynamic) > args.max_dynamic:
        failures.append(f"dynamic inline styles: {len(dynamic)} > budget {args.max_dynamic}")
    if args.max_inline_scripts is not None and script_blocks > args.max_inline_scripts:
        failures.append(f"inline <script> blocks: {script_blocks} > budget {args.max_inline_scripts}")

    if failures:
        print("\nFAIL")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("\nOK: within budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
