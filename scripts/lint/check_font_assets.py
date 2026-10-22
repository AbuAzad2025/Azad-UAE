"""Font-asset coherence gate.

The pages of this application used to load their fonts from
``fonts.googleapis.com``: a render-blocking stylesheet, on a host the CI
runner does not control, on the critical path to the first paint. That was the
open finding in ``docs/LIGHTHOUSE_GATE.md`` and it cost the landing page
several Lighthouse performance points. Every family is now served from this
repository, under ``static/fonts/``, and this gate is what keeps it that way.

Everything it checks fails SILENTLY otherwise:

1. every ``src:`` of an ``@font-face`` in ``static/fonts/**.css`` resolves to
   a file that is in the repository. A font that is referenced but absent is
   invisible in the HTML - the page still renders, still passes every test -
   and shows up only as text that comes out in the wrong face;
2. every ``url_for('static', filename='fonts/...')`` in a template resolves to
   a file that exists;
3. every vendored ``.woff2`` is a real woff2: non-empty, with the ``wOF2``
   magic. A truncated download served as a 200 is still a broken font;
4. no stylesheet and no template pulls a font from a third-party host any
   more. The URL may still be *documented* - the vendored stylesheets say
   where they came from - so comments are stripped before the search.

It also enforces the rule that makes a missing font harmless: every font
stack has to contain a family the browser always has, so a font that cannot
be loaded degrades the type, never the text. Families that are named in a
stack but are neither vendored here nor a system font are reported, without
failing the build: they are a design decision, not a defect.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = ROOT / "static" / "fonts"
CSS_DIR = ROOT / "static" / "css"
TEMPLATES = ROOT / "templates"

# Vendor directories: their typography is not ours to police.
SKIP_CSS_DIRS = {"dist", "adminlte", "datatables", "vendor", "theme"}

# The hosts a font must never come from. The stylesheet is render-blocking,
# so its latency is charged to the page's first paint.
THIRD_PARTY_FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")

# The magic number of a woff2 file ("wOF2", big-endian ASCII).
WOFF2_MAGIC = b"wOF2"

# Families the browser always has, or that are near-universal system fonts.
# A stack that contains one of these can never leave the text unrendered.
GENERIC_FAMILIES = frozenset(
    {
        # CSS generic families
        "serif",
        "sans-serif",
        "monospace",
        "cursive",
        "fantasy",
        "system-ui",
        "ui-serif",
        "ui-sans-serif",
        "ui-monospace",
        "ui-rounded",
        "math",
        "emoji",
        "fangsong",
        # CSS-wide keywords
        "inherit",
        "initial",
        "unset",
        "revert",
        # System fonts that exist on every supported platform
        "-apple-system",
        "blinkmacsystemfont",
        "segoe ui",
        "roboto",
        "helvetica",
        "helvetica neue",
        "arial",
        "arial black",
        "tahoma",
        "verdana",
        "geneva",
        "times",
        "times new roman",
        "courier",
        "courier new",
        "georgia",
        "trebuchet ms",
        "palatino",
        "garamond",
        "book antiqua",
        "andale mono",
        "lucida console",
        "lucida grande",
        "monaco",
        "menlo",
        "consolas",
        "cascadia code",
        "cascadia mono",
        "noto color emoji",
        "segoe ui emoji",
        "apple color emoji",
    }
)

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.S)
_FONT_FACE_SRC = re.compile(r"""src\s*:\s*url\(\s*["']?([^"')]+)["']?\s*\)""", re.I)
_STATIC_FONT_REF = re.compile(r"""filename\s*=\s*["']([^"']+)["']""")
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;{}]+)", re.I)
_CUSTOM_PROPERTY = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+)")
_VAR = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*([^)]*))?\)")
# A CSP directive and the sources it allows, up to the end of the directive.
_CSP_DIRECTIVE = re.compile(r"(font-src|style-src)([^;]*)")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _strip_css_comments(text: str) -> str:
    return _CSS_COMMENT.sub(" ", text)


def _strip_comments(text: str) -> str:
    """Remove the comment forms a template can carry."""
    text = _JINJA_COMMENT.sub(" ", text)
    return _HTML_COMMENT.sub(" ", text)


def _font_stylesheets() -> list[Path]:
    if not FONT_DIR.is_dir():
        return []
    return sorted(FONT_DIR.rglob("*.css"))


def _project_stylesheets() -> list[Path]:
    if not CSS_DIR.is_dir():
        return []
    sheets = []
    for path in sorted(CSS_DIR.rglob("*.css")):
        parts = set(path.relative_to(CSS_DIR).parts)
        if parts & SKIP_CSS_DIRS:
            continue
        sheets.append(path)
    return sheets


def _template_files() -> list[Path]:
    if not TEMPLATES.is_dir():
        return []
    return sorted(TEMPLATES.rglob("*.html"))


def _split_stack(value: str) -> list[str]:
    return [part.strip().strip("\"'").strip() for part in value.split(",") if part.strip()]


def _resolve_vars(value: str, properties: dict[str, str]) -> str:
    """Substitute the custom properties a font stack refers to."""
    for _ in range(4):
        replaced = _VAR.sub(lambda m: properties.get(m.group(1), m.group(2) or ""), value)
        if replaced == value:
            break
        value = replaced
    return value


def _collect_properties(sheets: list[Path], templates: list[Path]) -> dict[str, str]:
    """Every custom property the project defines, for var() resolution."""
    properties: dict[str, str] = {}
    for path in [*sheets, *templates]:
        for name, value in _CUSTOM_PROPERTY.findall(_read(path)):
            properties.setdefault(name, value.strip())
    return properties


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    font_sheets = _font_stylesheets()
    project_sheets = _project_stylesheets()
    templates = _template_files()

    if not FONT_DIR.is_dir():
        print(f"FAIL: {FONT_DIR} does not exist - the vendored fonts are gone.")
        return 1

    # 1. Every @font-face src resolves to a file in the repository.
    declared_families: set[str] = set()
    for sheet in font_sheets:
        text = _read(sheet)
        for family in re.findall(r"font-family\s*:\s*([^;{}]+)", text, re.I):
            declared_families.add(family.strip().strip("\"'").lower())
        for source in _FONT_FACE_SRC.findall(text):
            if source.startswith(("http://", "https://", "data:")):
                failures.append(f"{sheet.relative_to(ROOT)}: @font-face src points at a third party ({source})")
                continue
            target = (sheet.parent / source).resolve()
            if not target.is_file():
                failures.append(f"{sheet.relative_to(ROOT)}: @font-face src -> {source} is not in the repository")
            elif target.stat().st_size == 0:
                failures.append(f"{sheet.relative_to(ROOT)}: @font-face src -> {source} is empty")

    # 2. Every font stylesheet a template names exists.
    for template in templates:
        text = _read(template)
        for filename in _STATIC_FONT_REF.findall(text):
            if not filename.startswith("fonts/"):
                continue
            if not (ROOT / "static" / filename).is_file():
                failures.append(
                    f"{template.relative_to(ROOT)}: url_for('static', filename={filename!r}) does not resolve to a file"
                )

    # 3. Every vendored font file is a real woff2.
    font_files = sorted(FONT_DIR.rglob("*.woff2"))
    if not font_files:
        failures.append(f"{FONT_DIR.relative_to(ROOT)}: no .woff2 file is vendored")
    for path in font_files:
        try:
            head = path.read_bytes()[:4]
        except OSError as exc:
            failures.append(f"{path.relative_to(ROOT)}: cannot be read ({exc})")
            continue
        if len(head) < 4 or head != WOFF2_MAGIC:
            failures.append(f"{path.relative_to(ROOT)}: not a woff2 file (magic {head!r})")

    # 4. No third-party font host anywhere in the stylesheets or the templates.
    for path in [*font_sheets, *project_sheets]:
        text = _strip_css_comments(_read(path))
        for host in THIRD_PARTY_FONT_HOSTS:
            if host in text:
                failures.append(
                    f"{path.relative_to(ROOT)}: references {host} - the font must be served from this repository"
                )
    for template in templates:
        text = _strip_comments(_read(template))
        for host in THIRD_PARTY_FONT_HOSTS:
            if host in text:
                failures.append(
                    f"{template.relative_to(ROOT)}: references {host} - the font must be served from this repository"
                )

    # 4b. The Content-Security-Policy must not allow a font host either. A
    # policy that still permits fonts.gstatic.com makes the rule advisory: the
    # browser would happily load a Google Fonts stylesheet again.
    for path in sorted((ROOT / "app").rglob("*.py")):
        text = _read(path)
        for directive, allowed in _CSP_DIRECTIVE.findall(text):
            for host in THIRD_PARTY_FONT_HOSTS:
                if host in allowed:
                    failures.append(
                        f"{path.relative_to(ROOT)}: the {directive} CSP directive allows {host} - "
                        "a font host the application does not use"
                    )

    # 5. Every font stack keeps a family the browser always has.
    properties = _collect_properties(project_sheets, templates)
    checked_stacks = 0
    for path in [*project_sheets, *templates]:
        text = _read(path)
        for value in _FONT_FAMILY.findall(text):
            value = value.replace("!important", "").strip()
            if not value:
                continue
            resolved = _resolve_vars(value, properties)
            stack = _split_stack(resolved)
            if not stack:
                continue
            checked_stacks += 1
            for family in stack:
                lowered = family.lower()
                if lowered in GENERIC_FAMILIES or lowered in declared_families:
                    continue
                warnings.append(f"{path.relative_to(ROOT)}: {family!r} is not vendored under static/fonts/")
            if any(family.lower() in GENERIC_FAMILIES for family in stack):
                continue
            failures.append(
                f"{path.relative_to(ROOT)}: font-family {value!r} has no generic fallback - "
                "a font that cannot be loaded would leave the text unrendered"
            )

    print("Font-asset coherence")
    print(f"  font stylesheets            : {len(font_sheets)}")
    print(f"  vendored font files         : {len(font_files)}")
    print(f"  families served locally     : {len(declared_families)}")
    print(f"  font stacks checked         : {checked_stacks}")

    if warnings:
        print("\n  families named in a stack that are neither vendored nor system fonts:")
        for item in sorted(set(warnings)):
            print(f"    - {item}")

    if failures:
        print("\nFAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nOK: every font reference resolves, every font file is a real woff2, no third-party font host.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
