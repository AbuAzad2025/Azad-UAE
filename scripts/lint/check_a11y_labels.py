#!/usr/bin/env python
"""Accessibility gate: every form control must expose an accessible name.

Run by CI alongside the other ``scripts/lint`` gates. This exists because a11y
regressed quietly: 94 controls across 30 templates had a ``<label>`` that was
never linked to its control, so screen readers announced them as unlabelled
edit fields and clicking the label did nothing.

Three ways a control qualifies, in the order checked:

1. ``aria-label`` / ``aria-labelledby`` on the control.
2. An ``id`` on the control that a ``<label for=...>`` points at.
3. A ``<label>`` that *wraps* the control - implicit association, which is
   equally valid and is why the original scan that ignored it over-reported.

Controls whose type carries no name (``hidden``, ``submit``, ``button``,
``reset``, ``image``) are excluded, as are opt-outs marked ``sr-only``.

Allowlist: a small number of deliberately bare controls, each with a reason.
Add an entry only when the control genuinely has no visible label.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter

TEMPLATES = "templates"
LABEL_OPEN = re.compile(r"<label\b([^>]*)>", re.I)
LABEL_CLOSE = r"</label\s*>"
CONTROL = re.compile(r"<(input|select|textarea)\b([^>]*?)(/?)>", re.I)
FOR = re.compile(r'\bfor\s*=\s*["\']([^"\']+)')
ID = re.compile(r'\bid\s*=\s*["\']([^"\']+)')
HIDE = re.compile(r'\btype\s*=\s*["\'](hidden|submit|button|reset|image)["\']', re.I)

# path -> {line -> reason}
ALLOWLIST: dict[str, dict[int, str]] = {}


def _controls(t: str):
    """Yield (offset, line_no, tag, attrs) for every control worth labelling."""
    for m in CONTROL.finditer(t):
        attrs = m.group(2)
        if HIDE.search(attrs):
            continue
        yield m.start(), t[: m.start()].count("\n") + 1, m.group(1), attrs


def _named(t: str, offset: int, attrs: str) -> bool:
    """Does this control have an accessible name?"""
    if "aria-label" in attrs or "aria-labelledby" in attrs or "sr-only" in attrs:
        return True
    ident = ID.search(attrs)
    if ident and ident.group(1) in {f.group(1) for f in FOR.finditer(t)}:
        return True
    # Implicit association: the control sits inside an as-yet-unclosed <label>.
    depth = 0
    for m in re.finditer(r"<label\b[^>]*>|</label\s*>", t[:offset], re.I):
        depth = 0 if m.group(0).lower().startswith("</") else depth + 1
    return depth > 0


def main() -> int:
    if not os.path.isdir(TEMPLATES):
        print(f"accessibility gate: {TEMPLATES}/ not found", file=sys.stderr)
        return 2

    findings: list[tuple[str, int, str]] = []
    total = 0
    for root, _dirs, files in os.walk(TEMPLATES):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path).replace("\\", "/")
            t = open(path, encoding="utf-8", errors="surrogateescape").read()
            allowed = ALLOWLIST.get(rel, {})
            for offset, line, tag, attrs in _controls(t):
                total += 1
                if line in allowed:
                    continue
                if not _named(t, offset, attrs):
                    findings.append((rel, line, tag))

    print(f"Accessibility gate: {total} form control(s) under {TEMPLATES}/ - {len(findings)} unnamed.")
    if not findings:
        return 0
    for rel, line, tag in findings[:40]:
        print(f"  {rel}:{line}  <{tag}> has no accessible name")
    if len(findings) > 40:
        print(f"  ... and {len(findings) - 40} more")
    for rel, n in Counter(r for r, _l, _t in findings).most_common(10):
        print(f"    {n:3}  {rel}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
