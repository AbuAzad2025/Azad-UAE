"""Fail when one stylesheet defines the same bare class twice with different bodies.

`.ic-2 { display: grid }` and a later `.ic-2 { display: none }` are not two
rules; the second silently replaces the first for every consumer. That is how
shop-utilities.css came to define `.ic-2` seven times at top level, ending in
`display: none`, across roughly 45 templates including base.html and dashboard.

The check has to be @media-aware or it is worse than useless: a naive scan flags
41 classes in erp-theme-unified.css and 42 in landing.css, which are responsive
overrides behaving correctly. Same declaration under a different media query is
an override. Same declaration twice in the same context is not.

Selectors like `.a .b` are skipped: those are scoped, not global, and a class
appearing in two different parent contexts is not a collision.

Findings are reported, not auto-fixed: attributing each usage back to the
definition it was written against requires git history, not a regex.
"""

from __future__ import annotations

import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CSS = ROOT / "static" / "css"

# Known, diagnosed collisions in shop-utilities.css, where seven sections reused
# the same ic-* names in the global scope. Tracked rather than fixed: renaming
# needs to know which definition each of ~45 usages was written against, and
# nothing in the repo records that - see docs/shop_utilities_collision.md. The
# baseline is pinned by exact identity so a NEW collision anywhere, or an extra
# one in this file, still fails the build.
KNOWN_COLLISIONS = {
    ("static/css/shop-utilities.css", "ic-2"),
    ("static/css/shop-utilities.css", "ic-3"),
    ("static/css/shop-utilities.css", "ic-4"),
    ("static/css/shop-utilities.css", "ic-5"),
    ("static/css/shop-utilities.css", "ic-6"),
    ("static/css/shop-utilities.css", "ic-7"),
    ("static/css/shop-utilities.css", "ic-8"),
}

_AT_RULE = re.compile(r"@[A-Za-z-]+[^{]*\{")
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_BARE_CLASS = re.compile(r"^\.([A-Za-z0-9_-]+)$")


def _definitions(text: str) -> dict[tuple[str, str, str], list[int]]:
    """(class, @media context, body) -> line numbers.

    The context is part of the key on purpose. The same class legitimately
    appears once at top level and again inside a narrower @media query, and that
    is an override, not a collision. Only differing bodies *within the same
    context* are reported.
    """
    out: dict[tuple[str, str, str], list[int]] = collections.defaultdict(list)
    media: list[str] = []
    pos = 0
    while pos < len(text):
        at = _AT_RULE.search(text, pos)
        rule = _RULE.search(text, pos)
        if not rule:
            break
        if at and at.start() < rule.start():
            media.append(" ".join(at.group(0).split()))
            pos = at.end()
            continue
        selector = " ".join(rule.group(1).split())
        body = " ".join(rule.group(2).split())
        line = text.count("\n", 0, rule.start()) + 1
        match = _BARE_CLASS.match(selector)
        if match and body:
            out[(match.group(1), "|".join(media), body)].append(line)
        pos = rule.end()
    return out


def main() -> int:
    if not CSS.is_dir():
        print(f"FAIL: {CSS} not found", file=sys.stderr)
        return 1

    findings: list[tuple[str, str, str]] = []
    scanned = 0
    for path in sorted(CSS.glob("*.css")):
        text = path.read_text(encoding="utf-8", errors="replace")
        scanned += 1
        # group by class, then by @media context, then count distinct bodies
        by_class: dict[str, list[tuple[str, list[int]]]] = collections.defaultdict(list)
        for (name, context, body), lines in _definitions(text).items():
            by_class[name].append((context + "\x00" + body, lines))
        for name, variants in sorted(by_class.items()):
            if len(variants) < 2:
                continue
            # A differing body in a *different* @media context is an override.
            # Only disagreement inside one context is a collision.
            bodies: dict[str, list[int]] = {}
            for key, lines in variants:
                bodies.setdefault(key.split("\x00", 1)[1], []).extend(lines)
            contexts = {key.split("\x00", 1)[0] for key, _ in variants}
            if len(bodies) > 1 and len(contexts) == 1:
                detail = " | ".join(
                    f"L{lines[0]}: {body[:44]}" for body, lines in sorted(bodies.items(), key=lambda kv: kv[1][0])
                )
                findings.append((path.relative_to(ROOT).as_posix(), name, detail))

    print(f"CSS collision scan: {scanned} sheet(s), {len(findings)} globally-conflicting class(es).")
    known = {(rel, name) for rel, name, _ in findings}
    new = sorted(known - KNOWN_COLLISIONS)
    for rel, name in sorted(KNOWN_COLLISIONS - known):
        print(f"  NOTE: {rel} {name} no longer collides - drop it from KNOWN_COLLISIONS.")
    print(f"  {len(known & KNOWN_COLLISIONS)} known/documented, {len(new)} new.")
    if new:
        print("\nFAIL")
        for rel, name, detail in findings:
            if (rel, name) in new:
                print(f"  - {rel}: .{name} x{detail.count('|') + 1} -> {detail}")
        print(
            "\nEach of these is one class whose final top-level definition silently "
            "replaces the others. Namespace them per surface; do not merge bodies."
        )
        return 1
    print("OK: no undocumented bare class is defined twice with disagreeing bodies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
