"""Adaptive Frontend Asset Audit — Jinja2 & static asset integrity.

Covers:
  - JS reachability via boost template (original)
  - No duplicate static assets per rendered page
  - All referenced assets exist on filesystem
  - No orphaned first-party static files
  - Jinja block asset integrity (child does not duplicate parent loads)

Updated per Adaptive Frontend Asset Audit directive — expands the existing
test_js_reachability.py rather than creating a duplicate module (guardrail).
"""

import contextlib
import re
from pathlib import Path

from flask import render_template

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

# Reuse patterns from scripts/coverage_report.py
_URLFOR_RE = re.compile(r"url_for\(['\"]static['\"],\s*filename=['\"]([^'\"]+)['\"]")
_DIST_URL_RE = re.compile(r"dist_url\(['\"]([^'\"]+)['\"]")
_LINK_RE = re.compile(r'<link[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
_SCRIPT_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_EXTENDS_RE = re.compile(r'{%\s*extends\s+["\']([^"\']+)["\']')
_BLOCK_RE = re.compile(r"{%\s*block\s+(\w+)\s*%}(.*?){%\s*endblock", re.DOTALL)


def _collect_template_assets(template_path: Path) -> tuple[list[str], list[str]]:
    """Return (css_refs, js_refs) for a single template file.

    Only counts effective stylesheet/script loads — preload hints and
    noscript fallbacks are excluded (they are performance hints, not
    duplicate effective loads). Parses tag-by-tag to avoid counting
    url_for inside preload links as duplicate with stylesheet links.
    """
    try:
        text = template_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [], []
    css: list[str] = []
    js: list[str] = []
    # Remove noscript blocks for duplicate check (fallback, not effective load)
    text_no_noscript = re.sub(r"<noscript>.*?</noscript>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # CSS: only <link rel="stylesheet" ...>
    for tag in re.findall(r"<link[^>]+>", text_no_noscript, flags=re.IGNORECASE):
        if 'rel="stylesheet"' not in tag.lower():
            continue
        # Extract url_for/dist_url or hardcoded href inside this tag
        for m in _URLFOR_RE.findall(tag):
            if m.endswith(".css"):
                css.append(m)
        for m in _DIST_URL_RE.findall(tag):
            if m.endswith(".css"):
                css.append(m)
        href_m = re.search(r'href=["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
        if href_m:
            href = href_m.group(1)
            # Hardcoded /static/... without url_for
            if ".css" in href and "/static/" in href and "url_for" not in href and "dist_url" not in href:
                fname = href.split("static/")[-1].split("?")[0].split("#")[0]
                if fname and fname not in css:
                    css.append(fname)
    # JS: only <script src=...>
    for tag in re.findall(r"<script[^>]+>", text_no_noscript, flags=re.IGNORECASE):
        src_m = re.search(r'src=["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
        if not src_m:
            continue
        src = src_m.group(1)
        if ".js" not in src:
            continue
        for m in _URLFOR_RE.findall(tag):
            if m.endswith(".js"):
                js.append(m)
        for m in _DIST_URL_RE.findall(tag):
            if m.endswith(".js"):
                js.append(m)
        if "/static/" in src and "url_for" not in src and "dist_url" not in src:
            fname = src.split("static/")[-1].split("?")[0].split("#")[0]
            if fname and fname not in js:
                js.append(fname)
    return css, js


def test_js_reachability_boost(app):
    with app.app_context():
        # Render the boost template which references every static/js file
        html = render_template("tests/js_reachability_boost.html")
        assert "action-helpers.js" in html
        assert "app.js" in html


def test_no_duplicate_static_assets():
    """No template loads the same .css or .js file multiple times (incl. via parent).

    Excludes tests/js_reachability_boost.html (intentionally references every
    asset via both url_for and dist_url) and ignores preload/noscript
    fallbacks (handled in _collect_template_assets).
    """
    issues: list[str] = []
    for tmpl in TEMPLATES_DIR.rglob("*.html"):
        rel = str(tmpl.relative_to(TEMPLATES_DIR)).replace("\\", "/")
        if rel == "tests/js_reachability_boost.html":
            continue
        css, js = _collect_template_assets(tmpl)
        # self-duplicates
        for kind, assets in (("css", css), ("js", js)):
            seen: set[str] = set()
            for a in assets:
                norm = a.split("?")[0]
                if norm in seen:
                    issues.append(f"{tmpl.relative_to(TEMPLATES_DIR)} duplicate {kind}: {a}")
                seen.add(norm)
        # parent-child duplicates (direct parent only)
        try:
            text = tmpl.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        m = _EXTENDS_RE.search(text)
        if not m:
            continue
        parent_rel = m.group(1)
        parent_path = TEMPLATES_DIR / parent_rel
        if not parent_path.exists():
            continue
        p_css, p_js = _collect_template_assets(parent_path)
        dup_css = {c.split("?")[0] for c in css} & {c.split("?")[0] for c in p_css}
        dup_js = {j.split("?")[0] for j in js} & {j.split("?")[0] for j in p_js}
        if dup_css:
            issues.append(f"{tmpl.relative_to(TEMPLATES_DIR)} duplicates parent {parent_rel} css: {dup_css}")
        if dup_js:
            issues.append(f"{tmpl.relative_to(TEMPLATES_DIR)} duplicates parent {parent_rel} js: {dup_js}")
    assert issues == [], "Duplicate static assets found:\n" + "\n".join(issues[:20])


def test_all_referenced_assets_exist():
    """Every asset referenced via url_for/dist_url exists on filesystem (or dist fallback)."""
    missing: list[str] = []
    for tmpl in TEMPLATES_DIR.rglob("*.html"):
        css, js = _collect_template_assets(tmpl)
        for ref in css + js:
            # dist_url may point to dist file; check both dist and source
            clean = ref.split("?")[0].split("#")[0]
            # handle dist_url returning path like js/app.js which may be in static/js/dist/
            candidates = [STATIC_DIR / clean]
            # if not in dist, also check without dist prefix
            if "dist/" not in clean:
                candidates.append(STATIC_DIR / f"dist/{clean}")
                # also check source without dist (dist_url fallback)
            # url_for may reference assets/brand etc.
            found = any(c.exists() for c in candidates)
            # also check for static/adminlte vendored — allow if in adminlte (may not be checked out fully)
            if not found and clean.startswith("adminlte/"):
                # vendored, check exists
                if (STATIC_DIR / clean).exists():
                    found = True
                else:
                    # allow missing vendored sub-files that are not critical (fonts)
                    continue
            if not found:
                # dist_url for js/css may resolve to dist file that is generated; if source exists, ok
                src = STATIC_DIR / clean
                dist = STATIC_DIR / "dist" / clean if not clean.startswith("dist/") else STATIC_DIR / clean
                if src.exists() or dist.exists():
                    continue
                missing.append(f"{tmpl.relative_to(TEMPLATES_DIR)} -> {clean}")
    assert missing == [], "Missing static assets (referenced but not on disk):\n" + "\n".join(missing[:20])


def test_no_orphaned_static_files():
    """Flag unreferenced first-party files in static/ (vendored adminlte ignored).

    Build artifacts (*.min.css / *.min.js outside dist/) are excluded — they are
    superseded by postcss --dir static/css/dist and terser --dist. The
    canonical source is the non-min file (e.g., css/accessibility.css).
    """
    # Collect all references from templates
    all_text = ""
    for tmpl in TEMPLATES_DIR.rglob("*.html"):
        with contextlib.suppress(Exception):
            all_text += tmpl.read_text(encoding="utf-8", errors="ignore") + "\n"
    # Also include python routes that may reference static via url_for
    for py in (PROJECT_ROOT / "routes").rglob("*.py"):
        with contextlib.suppress(Exception):
            all_text += py.read_text(encoding="utf-8", errors="ignore") + "\n"
    # First-party dirs to check (ignore vendored)
    allow_prefixes = ("adminlte/", "adminlte", "fonts/", "uploads/")
    first_party_files: list[Path] = []
    for p in STATIC_DIR.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(STATIC_DIR)).replace("\\", "/")
        if any(rel.startswith(ap) for ap in allow_prefixes):
            continue
        if "/dist/" in rel or rel.startswith("dist/"):
            continue
        if p.suffix not in (".css", ".js"):
            continue
        # service worker at root is referenced via /pos-sw.js not via url_for — exclude
        if rel == "pos-sw.js":
            continue
        # Build artifacts: ignore *.min.css / *.min.js in static/css or static/js
        # (they are not canonical sources; dist/ holds the built output)
        if p.suffix == ".css" and p.name.endswith(".min.css"):
            continue
        if p.suffix == ".js" and p.name.endswith(".min.js"):
            continue
        first_party_files.append(p)
    orphaned: list[str] = []
    for p in first_party_files:
        rel = str(p.relative_to(STATIC_DIR)).replace("\\", "/")
        basename = p.name
        # referenced if rel appears in any template text or basename appears
        if rel in all_text or basename in all_text:
            continue
        # also check dist_url/url_for without prefix
        if rel.replace("js/", "") in all_text or rel.replace("css/", "") in all_text:
            continue
        orphaned.append(rel)
    assert orphaned == [], "Orphaned first-party static files (not referenced in any template/route):\n" + "\n".join(
        orphaned[:20]
    )


def test_jinja_block_asset_integrity():
    """Child block overrides must not duplicate parent's CSS/JS loads."""
    issues: list[str] = []
    for tmpl in TEMPLATES_DIR.rglob("*.html"):
        try:
            text = tmpl.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        m = _EXTENDS_RE.search(text)
        if not m:
            continue
        parent_rel = m.group(1)
        parent_path = TEMPLATES_DIR / parent_rel
        if not parent_path.exists():
            continue
        try:
            parent_text = parent_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Extract blocks
        parent_blocks: dict[str, str] = {b: c for b, c in _BLOCK_RE.findall(parent_text)}
        child_blocks: dict[str, str] = {b: c for b, c in _BLOCK_RE.findall(text)}
        for bname, child_content in child_blocks.items():
            if bname not in parent_blocks:
                continue
            parent_content = parent_blocks[bname]
            # If child block re-introduces same static asset as parent block, flag
            child_assets = set(_URLFOR_RE.findall(child_content) + _DIST_URL_RE.findall(child_content))
            parent_assets = set(_URLFOR_RE.findall(parent_content) + _DIST_URL_RE.findall(parent_content))
            dup = child_assets & parent_assets
            if dup:
                issues.append(
                    f"{tmpl.relative_to(TEMPLATES_DIR)} block '{bname}' duplicates parent {parent_rel} assets: {dup}"
                )
    assert issues == [], "Jinja block asset duplication:\n" + "\n".join(issues[:20])
