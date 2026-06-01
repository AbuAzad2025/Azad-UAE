"""
Static asset path audit — invoked from predeploy_check.py.

Returns (fail_messages, warn_messages).
"""
from __future__ import annotations

import json
import os
import re
from typing import Iterable

from sqlalchemy import create_engine, text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATIC = os.path.join(ROOT, "static")

CODE_SCAN_DIRS = ("templates", "routes", "utils", "static/js", "static/css")
CODE_SCAN_FILES = ("config.py", "app.py", "static/manifest.json", "static/sw.js")

SKIP_PATH_PARTS = (
    os.path.join("migrations", "versions"),
    "tools/organize_tenant_assets.py",
    "tools/_db_asset_probe.py",
    "tools/qa/static_asset_audit.py",
)

FAIL_CODE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("static/img/", re.compile(r"static/img/")),
    ("static/products/", re.compile(r"static/products/")),
    ("legacy img/tenants/alhazem", re.compile(r"(?<![\w/])img/tenants/alhazem")),
]

# Image/asset URL contexts only (avoid CORS defaults, email placeholders, form hints)
IMAGE_URL_FAIL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("example.com image URL", re.compile(r"(image_url|logo_url|logo_path|favicon|og:image|filename=)[^\n]{0,120}example\.com", re.I)),
    ("127.0.0.1 image URL", re.compile(r"(image_url|logo_url|logo_path|favicon|/static/)[^\n]{0,80}127\.0\.0\.1", re.I)),
    ("Windows path in asset ref", re.compile(r"(image_url|logo_url|logo_path|filename=)[^\n]{0,80}[\"'][A-Za-z]:\\\\")),
]

CANONICAL_CONFIG_PATHS = (
    "config.py:COMPANY_LOGO",
    "config.py:DEVELOPER_LOGO",
    "config.py:DEFAULT_PRODUCT_IMAGE",
)

MANIFEST_ICON_PATHS = (
    "assets/brand/azad/icons/icon-192.png",
    "assets/brand/azad/icons/icon-512.png",
)

SW_CACHED_PATHS = (
    "assets/brand/azad/logos/logo.png",
    "assets/brand/azad/logos/logo-dark.png",
)

NOTIFICATION_JS_PATHS = (
    "assets/brand/azad/logos/logo.png",
    "assets/brand/azad/favicons/favicon.png",
)


def _static_exists(rel: str) -> bool:
    rel = rel.lstrip("/").replace("\\", "/")
    if rel.startswith("static/"):
        rel = rel[7:]
    return os.path.isfile(os.path.join(STATIC, rel.replace("/", os.sep)))


def _iter_scan_files() -> Iterable[str]:
    for rel in CODE_SCAN_FILES:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        if os.path.isfile(path):
            yield path
    for sub in CODE_SCAN_DIRS:
        base = os.path.join(ROOT, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            for fn in filenames:
                if fn.endswith((".py", ".html", ".js", ".css", ".json")):
                    yield os.path.join(dirpath, fn)


def _should_skip(path: str) -> bool:
    norm = path.replace("\\", "/")
    return any(part.replace("\\", "/") in norm for part in SKIP_PATH_PARTS)


def scan_code_references() -> tuple[list[str], list[str]]:
    fails: list[str] = []
    for path in _iter_scan_files():
        if _should_skip(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for label, pattern in FAIL_CODE_PATTERNS:
            if pattern.search(content):
                fails.append(f"code ref {label} in {rel}")
                break
        else:
            for label, pattern in IMAGE_URL_FAIL_PATTERNS:
                if pattern.search(content):
                    fails.append(f"code ref {label} in {rel}")
                    break
    return fails, []


def scan_config_and_manifest() -> tuple[list[str], list[str]]:
    fails: list[str] = []
    try:
        from utils.static_asset_paths import (
            AZAD_FAVICON,
            AZAD_ICON_192,
            AZAD_ICON_512,
            AZAD_LOGO,
            AZAD_LOGO_DARK,
            DEFAULT_PRODUCT_IMAGE,
        )
        for label, rel in (
            ("AZAD_LOGO", AZAD_LOGO),
            ("AZAD_LOGO_DARK", AZAD_LOGO_DARK),
            ("AZAD_FAVICON", AZAD_FAVICON),
            ("AZAD_ICON_192", AZAD_ICON_192),
            ("AZAD_ICON_512", AZAD_ICON_512),
            ("DEFAULT_PRODUCT_IMAGE", DEFAULT_PRODUCT_IMAGE),
        ):
            if not _static_exists(rel):
                fails.append(f"missing static asset {label}: {rel}")
    except Exception as exc:
        fails.append(f"static_asset_paths import: {exc}")

    favicon_ico = os.path.join(STATIC, "favicon.ico")
    if not os.path.isfile(favicon_ico) or os.path.getsize(favicon_ico) < 32:
        fails.append("missing or empty static/favicon.ico root fallback")

    manifest_path = os.path.join(STATIC, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            data = json.loads(open(manifest_path, encoding="utf-8").read())
            for icon in data.get("icons") or []:
                src = (icon.get("src") or "").lstrip("/")
                if src.startswith("static/"):
                    src = src[7:]
                if src and not _static_exists(src):
                    fails.append(f"manifest icon missing: {src}")
        except Exception as exc:
            fails.append(f"manifest.json parse: {exc}")
    else:
        fails.append("missing static/manifest.json")

    for rel in SW_CACHED_PATHS:
        if not _static_exists(rel):
            fails.append(f"sw.js cached asset missing: {rel}")

    notif = os.path.join(STATIC, "js", "notification-system.js")
    if os.path.isfile(notif):
        body = open(notif, encoding="utf-8", errors="replace").read()
        for rel in NOTIFICATION_JS_PATHS:
            if rel not in body:
                fails.append(f"notification-system.js missing ref: {rel}")
            elif not _static_exists(rel):
                fails.append(f"notification-system.js asset missing: {rel}")

    return fails, []


def scan_db_asset_paths(database_url: str) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    if not database_url:
        fails.append("DATABASE_URL not set for static asset DB audit")
        return fails, warns

    engine = create_engine(database_url)
    with engine.connect() as conn:
        def scalar(sql: str) -> int:
            return int(conn.execute(text(sql)).scalar() or 0)

        if scalar(
            "SELECT COUNT(*) FROM tenants WHERE "
            "logo_url LIKE 'img/%' OR logo_url LIKE 'static/img/%' "
            "OR favicon_url LIKE 'img/%' OR favicon_url LIKE 'static/img/%' "
            "OR logo_dark_url LIKE 'img/%' OR logo_dark_url LIKE 'static/img/%'"
        ):
            fails.append("tenants table has legacy img/ logo or favicon paths")

        if scalar(
            "SELECT COUNT(*) FROM products WHERE image_url IS NOT NULL AND ("
            "image_url LIKE '%example.com%' OR image_url LIKE '%127.0.0.1%' "
            "OR image_url LIKE 'D:%' OR image_url LIKE 'C:%' "
            "OR image_url LIKE 'static/img%' OR image_url LIKE 'static/products%' "
            "OR image_url LIKE 'img/%'"
            ")"
        ):
            fails.append("products.image_url has legacy or invalid paths")

        if scalar(
            "SELECT COUNT(*) FROM invoice_settings WHERE "
            "logo_url LIKE 'img/%' OR logo_url LIKE 'static/img/%' "
            "OR logo_path LIKE 'img/%' OR logo_path LIKE 'static/img/%'"
        ):
            fails.append("invoice_settings has legacy logo paths")

        tenant_rows = conn.execute(
            text(
                "SELECT slug, logo_url, logo_dark_url, favicon_url FROM tenants "
                "WHERE logo_url IS NOT NULL OR logo_dark_url IS NOT NULL OR favicon_url IS NOT NULL"
            )
        ).fetchall()
        for slug, logo, dark, fav in tenant_rows:
            for label, val in (("logo_url", logo), ("logo_dark_url", dark), ("favicon_url", fav)):
                v = (val or "").strip()
                if not v or v.startswith("http"):
                    continue
                if v.startswith("static/"):
                    fails.append(f"tenant {slug} {label} must not use static/ prefix: {v}")
                    continue
                if not (v.startswith("assets/") or v.startswith("uploads/")):
                    fails.append(f"tenant {slug} {label} not relative assets/uploads: {v}")
                    continue
                if not _static_exists(v):
                    fails.append(f"tenant {slug} {label} file missing: {v}")

        product_rows = conn.execute(
            text(
                "SELECT id, tenant_id, image_url FROM products "
                "WHERE image_url IS NOT NULL AND TRIM(image_url) <> ''"
            )
        ).fetchall()
        for pid, tid, url in product_rows:
            u = (url or "").strip()
            if u.startswith("http"):
                if "example.com" in u or "127.0.0.1" in u:
                    fails.append(f"product {pid} bad URL: {u[:60]}")
                continue
            if u.startswith("static/"):
                fails.append(f"product {pid} uses static/ prefix: {u}")
                continue
            if not (u.startswith("assets/") or u.startswith("uploads/")):
                fails.append(f"product {pid} invalid relative path: {u}")
                continue
            if not _static_exists(u):
                if u.startswith("uploads/"):
                    warns.append(f"product {pid} upload not in git (expected): {u}")
                else:
                    fails.append(f"product {pid} asset missing: {u}")

        nasrallah_dir = os.path.join(STATIC, "assets", "tenants", "nasrallah")
        if os.path.isdir(nasrallah_dir):
            row = conn.execute(
                text(
                    "SELECT id, logo_url, favicon_url FROM tenants WHERE slug = 'nasrallah' LIMIT 1"
                )
            ).fetchone()
            if not row:
                fails.append("nasrallah assets on disk but tenant slug=nasrallah missing in DB")
            else:
                _tid, logo, fav = row
                for label, val in (("logo_url", logo), ("favicon_url", fav)):
                    v = (val or "").strip()
                    if not v:
                        fails.append(f"nasrallah tenant missing {label}")
                    elif v.startswith("img/") or v.startswith("static/img"):
                        fails.append(f"nasrallah tenant legacy {label}: {v}")
                    elif not _static_exists(v):
                        fails.append(f"nasrallah tenant {label} file missing: {v}")

    return fails, warns


def scan_git_uploads_staging() -> tuple[list[str], list[str]]:
    fails: list[str] = []
    import subprocess

    r = subprocess.run(  # nosec B603
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in (r.stdout or "").splitlines():
        p = line.strip().replace("\\", "/")
        if not p.startswith("static/uploads/tenants/"):
            continue
        if p.endswith(".gitkeep"):
            continue
        fails.append(f"runtime upload staged in git: {p}")

    r2 = subprocess.run(  # nosec B603
        ["git", "ls-files", "static/uploads/tenants/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in (r2.stdout or "").splitlines():
        p = line.strip().replace("\\", "/")
        if p.endswith(".gitkeep"):
            continue
        fails.append(f"runtime upload tracked in git: {p}")

    return fails, []


def run_static_asset_audit(database_url: str) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    for chunk in (
        scan_code_references(),
        scan_config_and_manifest(),
        scan_db_asset_paths(database_url),
        scan_git_uploads_staging(),
    ):
        f, w = chunk
        fails.extend(f)
        warns.extend(w)
    return fails, warns
