#!/usr/bin/env python3
"""
Jinja template syntax gate for CI.

Parses EVERY ``templates/**/*.html`` file with a real Jinja2 environment
(i18n extension enabled, null translations installed) so that a template
with broken syntax fails the build before it ever reaches production.

The gate asserts that every discovered template was parsed — nothing in
``templates/`` may be skipped silently.

Exit code: 0 when all templates parse, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, TemplateSyntaxError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = PROJECT_ROOT / "templates"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    env = Environment(extensions=["jinja2.ext.i18n"], autoescape=True)
    env.install_null_translations()

    templates = sorted(TEMPLATES_DIR.rglob("*.html"))
    failures: list[tuple[str, int, str]] = []

    for path in templates:
        rel = path.relative_to(TEMPLATES_DIR).as_posix()
        try:
            env.parse(path.read_text(encoding="utf-8"))
        except TemplateSyntaxError as exc:
            failures.append((rel, exc.lineno or 0, exc.message))
        except OSError as exc:
            failures.append((rel, 0, f"unreadable file: {exc}"))

    print(
        f"Jinja template gate: parsed {len(templates)} template(s) "
        f"under templates/ — {len(failures)} failure(s)."
    )
    for rel, line, message in failures:
        # GitHub Actions annotation format
        print(
            f"::error file=templates/{rel},line={line}::Jinja syntax error: {message}"
        )

    if not templates:
        print("::error::No templates found — the gate itself must be misconfigured.")
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
