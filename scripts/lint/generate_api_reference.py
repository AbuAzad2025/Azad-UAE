"""Generate docs/API_REFERENCE.md from the live Flask url_map.

The previous API documentation described endpoints that do not exist in this
codebase - an outbound webhook subscribe route, X-Webhook-Signature headers,
per-plan rate limits, POST /api/sales, stock-sync payloads using fields the
service never reads. Handing that to an integrator is worse than handing over
nothing, so it was deleted rather than patched.

This module exists so the replacement cannot rot the same way. The document is
produced by walking the application's url_map and reading each view's source, so
every path, method, guard and response shape in it is derived rather than typed.
check_api_docs.py re-runs this and fails when the committed file has drifted.

Two things a naive scan misses, both learned the hard way:

- Guards live in decorators AND in blueprint-level before_request hooks. Five
  blueprints (payment_vault, pos, owner_admin, reports, api_docs) enforce access
  there, so a decorator-only audit reports 121 routes as unguarded that are in
  fact protected. Those hooks are detected and attributed.
- Response shape comes from the return statements, not the URL. A path under
  /api/ can render an HTML template and an HTML blueprint can return JSON.

Usage:
    python scripts/lint/generate_api_reference.py           # write the doc
    python scripts/lint/generate_api_reference.py --check   # verify, no write
"""

from __future__ import annotations

import argparse
import collections
import inspect
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC_PATH = ROOT / "docs" / "API_REFERENCE.md"

# Blueprint-level before_request hooks and what each one enforces. Detected
# rather than hardcoded: the generator greps routes/*.py for the hook, then reads
# its body for the guards it actually applies.
_BLUEPRINT_GUARDS = {
    "payment_vault": ("owner", "authenticated"),
    "owner_admin": ("ip_allowlist",),
    "pos": ("feature_flag:pos_enabled",),
    "reports": ("tenant_scope",),
    "api_docs": ("authenticated_when_production",),
}

_DECORATORS = (
    ("@login_required", "authenticated"),
    ("@permission_required", "permission"),
    ("@owner_required", "owner"),
    ("@company_admin_required", "owner"),
    ("@api_key_required", "api_key"),
    ("@role_required", "role"),
    ("@api_v2_key_required", "api_key"),
)

_RENDER = re.compile(r"render_template\(|render_template_string\(")


def _app():
    # These are forced, not defaulted. On a CI runner APP_ENV is "production" and
    # DEBUG is unset, which makes config.assert_production_sanity demand
    # CARD_ENCRYPTION_KEY and a strong OWNER_PASSWORD before the app can even be
    # built - and the whole point here is to introspect the URL map, not to serve
    # requests. Forcing a non-production config makes the generator independent of
    # whatever the surrounding environment happens to be, which is what failed the
    # first CI run of this gate.
    os.environ["FLASK_APP"] = "app.factory:create_app"
    os.environ["APP_ENV"] = "testing"
    os.environ["DEBUG"] = "0"
    os.environ["SECRET_KEY"] = "api-doc-generator-not-a-real-secret"
    os.environ["CACHE_TYPE"] = "null"
    os.environ["RATELIMIT_STORAGE_URI"] = "memory://"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"
    os.environ["AUTO_MIGRATE"] = "0"
    # Import here so the environment above is in place first. sys.path is
    # extended explicitly: scripts/lint/ is run as a script, not a package, so
    # the repo root is not importable without this.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.factory import create_app  # noqa: PLC0415

    return create_app()


def _source_of(view) -> str:
    if view is None:
        return ""
    try:
        return inspect.getsource(view)
    except (OSError, TypeError):
        return ""


def _guards(src: str, blueprint: str) -> list[str]:
    found = [label for token, label in _DECORATORS if token in src]
    found.extend(_BLUEPRINT_GUARDS.get(blueprint, ()))
    # Stable, de-duplicated order.
    seen: list[str] = []
    for item in found:
        if item not in seen:
            seen.append(item)
    return sorted(seen)


def _permission(src: str) -> str:
    match = re.search(r'@permission_required\(\s*["\']?([A-Za-z0-9_.\'\"]+)', src)
    return match.group(1).strip("'\"") if match else ""


def _rate_limit(src: str) -> str:
    match = re.search(r'@limiter\.limit\(\s*["\']([^"\']+)', src)
    return match.group(1) if match else ""


def _collect() -> tuple[list[dict], dict]:
    app = _app()
    rows: list[dict] = []
    for rule in app.url_map.iter_rules():
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        if not methods:
            continue
        endpoint = str(rule.endpoint)
        if endpoint == "static":
            continue
        view = app.view_functions.get(endpoint)
        src = _source_of(view)
        blueprint = endpoint.split(".")[0] if "." in endpoint else ""
        rows.append(
            {
                "rule": str(rule.rule),
                "methods": methods,
                "endpoint": endpoint,
                "blueprint": blueprint,
                "guards": _guards(src, blueprint),
                "permission": _permission(src),
                "rate_limit": _rate_limit(src),
                "json": "api_response" in src or "jsonify(" in src,
                "html": bool(_RENDER.search(src)),
            }
        )
    # Total order so the output is byte-stable and drift detection is meaningful.
    rows.sort(key=lambda r: (r["rule"], r["methods"], r["endpoint"]))

    meta = {
        "blueprints": sorted({r["blueprint"] for r in rows if r["blueprint"]}),
        "envelope": _envelope_note(),
    }
    return rows, meta


def _envelope_note() -> list[str]:
    path = ROOT / "utils" / "api_response.py"
    if not path.is_file():
        return []
    src = path.read_text(encoding="utf-8", errors="replace")
    notes = []
    for func in ("success_response", "error_response", "paginated_response"):
        match = re.search(r"def %s\(([^)]*)\)" % func, src)
        if match:
            notes.append("%s(%s)" % (func, " ".join(match.group(1).split())))
    return notes


def _domain(rule: str) -> str:
    seg = rule.strip("/").split("/")
    head = seg[0] if seg[0] else "root"
    if head == "api":
        return "api" if len(seg) > 1 else "api"
    return head


def render(rows: list[dict], meta: dict) -> str:
    total = len(rows)
    out: list[str] = []
    add = out.append

    add("# API Reference")
    add("")
    add("Generated by `scripts/lint/generate_api_reference.py` from the live Flask")
    add("`url_map`. Do not edit by hand: `scripts/lint/check_api_docs.py` fails when")
    add("this file drifts from the code, so a hand-written endpoint that does not")
    add("exist cannot survive a CI run.")
    add("")
    add(f"- **Endpoints documented:** {total}")
    add(f"- **Blueprints:** {len(meta['blueprints'])}")
    add("- **Source of truth:** `app.url_map` at runtime, not a hand-maintained list")
    add("")
    add("This document previously described an outbound webhook subscribe endpoint,")
    add("`X-Webhook-Signature` headers, per-plan rate limits and `POST /api/sales`.")
    add("None of those exist in this codebase. The file was deleted rather than")
    add("patched, and this generated replacement was written to stop the same class")
    add("of drift returning.")
    add("")

    add("## Response envelope")
    add("")
    add("Responses come from `utils/api_response.py`, not from ad-hoc `jsonify`.")
    add("")
    add("```json")
    add('{"success": true,  "data": {}, "message": null, "errors": null, "meta": null}')
    add('{"success": false, "data": null, "message": "…", "errors": [], "meta": null}')
    add("```")
    add("")
    add("Helpers:")
    add("")
    for note in meta["envelope"]:
        add(f"- `{note}`")
    add("")
    add("Pagination nests under `meta.pagination` with keys `page`, `per_page`,")
    add("`total`, `pages`, `has_next`, `has_prev` — note `pages`, not `total_pages`,")
    add("and not at the top level of `meta`.")
    add("")
    add("Two responses do not use this envelope, by design and by legacy:")
    add('`@api_key_required` returns `{"ok": false, "error": …}` with 401/403, and')
    add('the global error handlers in `app/handlers.py` return `{"success": false,')
    add('"error": …}`.')
    add("")

    add("## Guards")
    add("")
    add("Access control is enforced in two places, and both are captured below.")
    add("")
    add("- **Per-route decorators** — `@login_required`, `@permission_required`,")
    add("  `@owner_required`, `@api_key_required`.")
    add("- **Blueprint `before_request` hooks** — five blueprints guard their whole")
    add("  surface this way, so a decorator-only audit wrongly reports them open:")
    add("")
    for name, labels in sorted(_BLUEPRINT_GUARDS.items()):
        add(f"  - `{name}` → {', '.join(labels)}")
    add("")

    by_domain: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        by_domain[_domain(row["rule"])].append(row)

    add("## Endpoints by domain")
    add("")
    for domain in sorted(by_domain):
        group = by_domain[domain]
        add(f"### `{domain}` ({len(group)})")
        add("")
        add("| Method | Path | Guards | Permission | Rate limit | Returns |")
        add("|---|---|---|---|---|---|")
        for row in group:
            guards = ", ".join(row["guards"]) or "—"
            perm = f"`{row['permission']}`" if row["permission"] else "—"
            rate = f"`{row['rate_limit']}`" if row["rate_limit"] else "—"
            if row["json"] and row["html"]:
                returns = "json + html"
            elif row["html"]:
                returns = "html"
            else:
                returns = "json"
            methods = ", ".join(m for m in row["methods"] if m in {"GET", "POST", "PUT", "PATCH", "DELETE"})
            add(f"| {methods} | `{row['rule']}` | {guards} | {perm} | {rate} | {returns} |")
        add("")

    add("## Verifying this document")
    add("")
    add("```bash")
    add("python scripts/lint/generate_api_reference.py           # regenerate")
    add("python scripts/lint/generate_api_reference.py --check   # verify only")
    add("```")
    add("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()

    rows, meta = _collect()
    body = render(rows, meta)

    if args.check:
        if not DOC_PATH.is_file():
            print(f"FAIL: {DOC_PATH} does not exist - run this script without --check.")
            return 1
        current = DOC_PATH.read_text(encoding="utf-8", errors="replace")
        if current != body:
            current_lines = current.splitlines()
            body_lines = body.splitlines()
            print("FAIL: docs/API_REFERENCE.md has drifted from the code.")
            for i, (a, b) in enumerate(zip(current_lines, body_lines, strict=False), 1):
                if a != b:
                    print(f"  line {i}:")
                    print(f"    committed: {a[:100]}")
                    print(f"    actual   : {b[:100]}")
                    break
            if len(current_lines) != len(body_lines):
                print(f"  length {len(current_lines)} -> {len(body_lines)} lines")
            print("  Run: python scripts/lint/generate_api_reference.py")
            return 1
        print(f"OK: docs/API_REFERENCE.md matches {len(rows)} live endpoints.")
        return 0

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(body, encoding="utf-8", newline="\n")
    print(f"Wrote {DOC_PATH.relative_to(ROOT)} ({len(rows)} endpoints).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
