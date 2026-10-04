"""CI gate: docs/API_REFERENCE.md must match the live url_map.

The deleted API reference documented an outbound webhook subscribe route,
X-Webhook-Signature headers, per-plan rate limits and POST /api/sales - none of
which exist here. It survived because nothing compared the document to the code.

This gate closes that. It regenerates the document in memory and compares it byte
for byte against the committed file, so:

- a hand-edited endpoint that does not exist cannot pass - the generator does not
  know about it, so the file diverges;
- a new route added without regenerating fails the build, which is the intended
  nudge to run the generator;
- a route deleted without regenerating fails the build too, so the document can
  never advertise a route that is gone.

Exits non-zero with the first differing line, so the failure names itself instead
of just reporting a mismatch.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from generate_api_reference import DOC_PATH, ROOT, _collect, render  # noqa: E402


def main() -> int:
    if not DOC_PATH.is_file():
        print(f"FAIL: {DOC_PATH.relative_to(ROOT)} does not exist.")
        print("      Generate it: python scripts/lint/generate_api_reference.py")
        return 1

    rows, meta = _collect()
    expected = render(rows, meta)
    actual = DOC_PATH.read_text(encoding="utf-8", errors="replace")

    if actual == expected:
        print(f"OK: API reference matches {len(rows)} live endpoints.")
        return 0

    print("FAIL: docs/API_REFERENCE.md does not match the code.")
    exp_lines, act_lines = expected.splitlines(), actual.splitlines()
    shown = 0
    for i in range(max(len(exp_lines), len(act_lines))):
        a = act_lines[i] if i < len(act_lines) else "<missing>"
        b = exp_lines[i] if i < len(exp_lines) else "<missing>"
        if a != b:
            print(f"  line {i + 1}:")
            print(f"    committed: {a[:110]}")
            print(f"    actual   : {b[:110]}")
            shown += 1
            if shown == 3:
                break
    if len(act_lines) != len(exp_lines):
        print(f"  length: committed {len(act_lines)} lines, actual {len(exp_lines)}")
    print("  Regenerate: python scripts/lint/generate_api_reference.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
