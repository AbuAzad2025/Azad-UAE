#!/usr/bin/env python3
"""
First-run for PRODUCTION — clean, idempotent, no mess, no demo data.

Creates the production database, runs all Alembic migrations,
and seeds only the data required for a live tenant.

Usage:
    export SECRET_KEY="..."                # required, 32+ chars
    export DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/azad_prod"
    export OWNER_PASSWORD="Strong@123..."  # required in production
    export OWNER_USERNAME="owner"          # optional, default owner
    export OWNER_EMAIL="owner@company.com" # optional
    python scripts/ops/first_run_prod.py

Idempotent: safe to re-run. Will not delete existing tenant data;
only creates missing rows (permissions, roles, currencies, GL base). SaaS
packages are created by the platform owner from the Owner panel, not here.

For PostgreSQL and SQLite (SQLite file is created automatically).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _run(cmd: list[str], env: dict | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT), env=env)  # nosec B603


def _ensure_db(db_url: str) -> None:
    if db_url.startswith("sqlite"):
        return
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    # Derive admin URL from db_url (replace dbname with postgres)
    dbname = db_url.rsplit("/", 1)[-1].split("?")[0]
    admin_url = db_url.rsplit("/", 1)[0] + "/postgres"
    # Try common postgres superuser; fallback to postgres:123
    # Use the same host/user as db_url if possible, else default
    eng = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"connect_timeout": 3}
    )
    with eng.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": dbname}).scalar()
        if not exists:
            conn.execute(text(f"CREATE DATABASE \"{dbname}\" WITH ENCODING 'UTF8' TEMPLATE template0"))
            print(f"created database {dbname}")
        else:
            print(f"database {dbname} already exists — keeping data")
    eng.dispose()


def _which(cmd: str) -> str | None:
    """Resolve a binary on PATH; returns absolute path or None."""
    from shutil import which

    return which(cmd)


def _ensure_assets_build(env: dict) -> None:
    """Best-effort asset build for dist_url() cache-busted minified files.

    Safe to call in all environments:
    * If node+npm are missing AND dist/ is already populated → skip silently
      (dist_url falls back to originals, app still works).
    * If node+npm are missing AND dist/ is empty/missing → print a one-line
      warning so operators know the unminified originals are being served.
    * Otherwise: install deps (npm ci if package-lock exists) + run build:assets.
    """
    css_dist = PROJECT_ROOT / "static" / "css" / "dist"
    js_dist = PROJECT_ROOT / "static" / "js" / "dist"
    pkg_json = PROJECT_ROOT / "package.json"
    pkg_lock = PROJECT_ROOT / "package-lock.json"

    if not pkg_json.is_file():
        return

    dist_populated = (
        css_dist.is_dir()
        and any(css_dist.glob("*.css"))
        and js_dist.is_dir()
        and any(js_dist.rglob("*.js"))
    )

    npm_cmd = _which("npm")
    node_cmd = _which("node")
    can_build = bool(npm_cmd and node_cmd)

    if not can_build:
        if dist_populated:
            print("assets: dist/ already populated; skipping npm build (node/npm not on PATH)")
        else:
            print(
                "WARN: assets: dist/ is empty and node/npm were not found on PATH. "
                "The app still works via unminified originals (dist_url fallback). "
                "Install Node.js 22+ and re-run, or run manually:",
                file=sys.stderr,
            )
            print("      npm ci  &&  npm run build:assets\n", file=sys.stderr)
        return

    node_modules_dir = PROJECT_ROOT / "node_modules"
    if not node_modules_dir.is_dir() or not (node_modules_dir / ".package-lock.json").is_file():
        lock_exists = pkg_lock.is_file()
        install_args = [npm_cmd, "ci" if lock_exists else "install", "--no-audit", "--no-fund"]
        print(f"assets: installing node deps ({'npm ci' if lock_exists else 'npm install'})…")
        try:
            _run(install_args, env=env)
        except Exception as exc:  # pragma: no cover - operator feedback
            print(f"WARN: npm install failed ({exc}); continuing with unminified assets", file=sys.stderr)
            return

    print("assets: running npm run build:assets …")
    try:
        _run([npm_cmd, "run", "build:assets"], env=env)
    except Exception as exc:  # pragma: no cover - operator feedback
        print(f"WARN: build:assets failed ({exc}); continuing with unminified assets", file=sys.stderr)


def main() -> None:
    env = os.environ.copy()
    # Production sanity — these must be set, otherwise factory will abort
    for var in ("SECRET_KEY", "DATABASE_URL", "OWNER_PASSWORD"):
        if not env.get(var):
            print(f"ERROR: {var} must be set in production", file=sys.stderr)
            sys.exit(1)

    env.setdefault("APP_ENV", "production")
    env.setdefault("FLASK_ENV", "production")
    env.setdefault("OWNER_USERNAME", "owner")
    env.setdefault("OWNER_EMAIL", "owner@system.local")
    env.setdefault("CACHE_TYPE", "null")
    env.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    env.setdefault("CELERY_BROKER_URL", "memory://")
    env.setdefault("CELERY_RESULT_BACKEND", "memory://")

    # 0. Build minified CSS/JS dist/ (best-effort; safe no-op fallback if missing)
    _ensure_assets_build(env)

    # 1. Ensure DB exists (does not drop existing data in prod)
    _ensure_db(env["DATABASE_URL"])

    # 2. Run migrations
    _run([sys.executable, "-m", "flask", "db", "upgrade"], env=env)

    # 3. Trigger system_init (perms, roles, owner, currencies, industry fields, GL base)
    _run([sys.executable, "-c", "from app import create_app; app=create_app(); print('system_init done')"], env=env)

    # 4. No seed-packages: the platform owner creates SaaS packages from the
    # Owner panel (payment_vault/packages-management).

    # 5. Verify
    _run([sys.executable, "-m", "flask", "db", "current"], env=env)
    print("\n[OK] Prod first-run complete - DB ready at", env["DATABASE_URL"].split("@")[-1])
    print(f"   Owner: {env['OWNER_USERNAME']} / {env['OWNER_EMAIL']}")
    print("   No demo data created. Create tenants via Owner panel: /owner/tenants/new")
    css_dist = PROJECT_ROOT / "static" / "css" / "dist" / "landing.css"
    if css_dist.is_file():
        size_kb = round(css_dist.stat().st_size / 1024, 1)
        print(f"   Assets: dist/ built OK (landing.css minified ~{size_kb} KB + SHA-256 cache bust)")
    else:
        print("   Assets: serving originals (dist/ not built; install Node.js to enable minified bundles)")
    print("   Run: gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app")


if __name__ == "__main__":
    main()
