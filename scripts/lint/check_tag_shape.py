"""Reject mangled HTML tags: <pclass= instead of <p class=.

A batch of inline-style conversions inserted ``class="..."`` at the offset where
the ``style`` attribute had matched. That match included the leading whitespace,
so on any element whose style attribute came first the insertion landed
immediately after the tag name and produced::

    <p style="font-size:9px;">      ->  <pclass="p-fs-9">
    <td style="width:70%">          ->  <tdclass="w-70">
    <ul style="display:none">       ->  <ulclass="d-none">

152 of these landed across 31 templates - including every ledger report table,
the dashboard, and the public landing page. They are not errors to any tool this
repository runs: the template gate parses Jinja, the a11y gate counts controls,
stylelint and biome only look at static assets, and cspell merely reported them
as unknown words. Nothing in the suite renders those pages, so nothing failed.
cspell's "Unknown word (tdclass)" was the only signal, and only by accident.

So this is a gate. It is deliberately narrow: a tag name immediately followed by
``class=`` with no space, which is never valid HTML.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"

MANGLED = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)class\s*=")


def main() -> int:
    findings: list[str] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.split("\n"), 1):
            for match in MANGLED.finditer(line):
                findings.append(
                    f"{path.relative_to(ROOT).as_posix()}:{lineno}: "
                    f"<{match.group(1)}class= is not valid HTML; expected "
                    f"<{match.group(1)} class="
                )

    if findings:
        print(f"FAIL: {len(findings)} mangled tag(s)")
        for line in findings[:40]:
            print(f"  - {line}")
        if len(findings) > 40:
            print(f"  ... and {len(findings) - 40} more")
        return 1

    print(f"Tag shape gate: OK - no <tagclass= in {len(list(TEMPLATES.rglob('*.html')))} templates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
