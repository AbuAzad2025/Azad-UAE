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
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from jinja2 import Environment, TemplateSyntaxError, nodes

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = PROJECT_ROOT / "templates"


def _iter_nodes(node: nodes.Node) -> Iterator[nodes.Node]:
    """Depth-first walk over every node in a parsed template."""
    yield node
    for child in node.iter_child_nodes():
        yield from _iter_nodes(child)


def _declared_blocks(ast: nodes.Template) -> set[str]:
    """Block names a template defines (the ones a child may override)."""
    return {n.name for n in _iter_nodes(ast) if isinstance(n, nodes.Block)}


def _overridden_blocks(ast: nodes.Template) -> dict[str, int]:
    """Top-level block overrides: name -> line, excluding self-recursive refs."""
    return {n.name: n.lineno for n in ast.body if isinstance(n, nodes.Block)}


def _resolve_extends(ast: nodes.Template) -> str | None:
    """Return the template path this one extends, normalised to a posix relpath."""
    for node in _iter_nodes(ast):
        if isinstance(node, nodes.Extends) and isinstance(node.template, nodes.Const):
            value = node.template.value
            if isinstance(value, str):
                return PurePosixPath(value).as_posix()
    return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    env = Environment(extensions=["jinja2.ext.i18n"], autoescape=True)
    env.install_null_translations()  # type: ignore[attr-defined]

    templates = sorted(TEMPLATES_DIR.rglob("*.html"))
    failures: list[tuple[str, int, str]] = []
    asts: dict[str, nodes.Template] = {}

    for path in templates:
        rel = path.relative_to(TEMPLATES_DIR).as_posix()
        try:
            parsed = env.parse(path.read_text(encoding="utf-8"))
            asts[rel] = parsed
        except TemplateSyntaxError as exc:
            failures.append((rel, exc.lineno or 0, exc.message or ""))
        except OSError as exc:
            failures.append((rel, 0, f"unreadable file: {exc}"))

    # --- Template inheritance gate -------------------------------------------
    # A ``{% block name %}`` that no ancestor declares is silently discarded by
    # Jinja2: the markup renders nowhere, no warning is emitted, and a reviewer
    # reasonably assumes it is wired up. That is how 12 templates ended up with
    # dead ``{% block scripts %}`` (script/handler bodies that never ran) and
    # the POS layout lost its ``extra_head`` block, voiding every tenant's
    # POS configuration. Assert the resolution instead of trusting it.
    blocks_by_template = {rel: _declared_blocks(ast) for rel, ast in asts.items()}

    for rel, ast in asts.items():
        parent = _resolve_extends(ast)
        if parent is None:
            # Root layout: it defines the contract, overrides nothing.
            continue
        # Jinja resolves a block override against *any* ancestor, so the whole
        # extends chain has to be walked — not just the direct parent.
        inherited: set[str] = set()
        seen: set[str] = set()
        # Start at the PARENT: a block this template declares itself must not
        # satisfy its own override, or the check silently passes everything.
        current: str | None = parent
        while current and current in asts and current not in seen:
            seen.add(current)
            inherited |= blocks_by_template[current]
            current = _resolve_extends(asts[current])

        for name, lineno in _overridden_blocks(ast).items():
            if name not in inherited:
                failures.append(
                    (
                        rel,
                        lineno,
                        f"orphaned block '{name}': no template in the extends chain "
                        f"(starting at '{parent}') declares it",
                    )
                )

    print(f"Jinja template gate: parsed {len(templates)} template(s) under templates/ — {len(failures)} failure(s).")
    for rel, line, message in failures:
        # GitHub Actions annotation format
        print(f"::error file=templates/{rel},line={line}::{message}")

    if not templates:
        print("::error::No templates found — the gate itself must be misconfigured.")
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
