#!/usr/bin/env python3
"""
First-run for DEVELOPMENT — clean, idempotent, no mess.

Creates a pristine dev database, runs all Alembic migrations,
and seeds only the data required for a usable dev environment.

Usage:
    python scripts/ops/first_run_dev.py              # uses .env or defaults
    python scripts/ops/first_run_dev.py --with-demo  # also seeds demo tenant + 12 products

Idempotent: safe to re-run. Existing DB is dropped and recreated.
Works for both PostgreSQL (postgres:123@localhost) and SQLite.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
DEFAULT_TEST_DB_URL = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae_test"


def _run(cmd: list[str], env: dict | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT), env=env)  # nosec B603


def _ensure_db(db_url: str) -> None:
    """Drop and create DB — works for postgres and sqlite."""
    if db_url.startswith("sqlite"):
        # sqlite file is created on first connect; remove old file if exists
        path = db_url.split("///")[-1].split("?")[0]
        if path and path != ":memory:":
            p = Path(path)
            if p.exists():
                p.unlink()
                print(f"removed sqlite {p}")
        return

    # postgres — use admin connection to drop/create
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    admin_url = "postgresql+psycopg2://postgres:123@localhost:5432/postgres"
    dbname = db_url.rsplit("/", 1)[-1].split("?")[0]
    eng = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"connect_timeout": 3}
    )
    with eng.connect() as conn:
        conn.execute(
            text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{dbname}' AND pid<>pg_backend_pid()"
            )
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
        conn.execute(text(f"CREATE DATABASE \"{dbname}\" WITH ENCODING 'UTF8' TEMPLATE template0"))
        print(f"created database {dbname}")
    eng.dispose()


def _which(cmd: str) -> str | None:
    """Resolve a binary on PATH; returns absolute path or None."""
    from shutil import which

    return which(cmd)


def _ensure_assets_build(env: dict) -> None:
    """Best-effort asset build for dist_url() cache-busted minified files.

    Mirrors the same helper used by first_run_prod.py — kept duplicated here
    so the single-file ops scripts remain zero-dependency and copy-safe.
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
    import argparse

    parser = argparse.ArgumentParser(description="First-run for development")
    parser.add_argument("--with-demo", action="store_true", help="also seed demo tenant (12 products, 3 sales, etc.)")
    parser.add_argument("--no-demo", dest="with_demo", action="store_false", help="skip demo data (default)")
    parser.set_defaults(with_demo=False)
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("APP_ENV", "development")
    env.setdefault("FLASK_ENV", "development")
    env.setdefault("SECRET_KEY", "dev-secret-key-not-for-production")
    env.setdefault("DATABASE_URL", DEFAULT_DB_URL)
    env.setdefault("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)
    env.setdefault("SKIP_SYSTEM_INTEGRITY", "0")
    env.setdefault("CACHE_TYPE", "null")
    env.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    env.setdefault("CELERY_BROKER_URL", "memory://")
    env.setdefault("CELERY_RESULT_BACKEND", "memory://")

    # 0. Build minified CSS/JS dist/ (best-effort; safe no-op fallback if missing)
    _ensure_assets_build(env)

    # 1. Drop and create DBs
    _ensure_db(env["DATABASE_URL"])
    _ensure_db(env["TEST_DATABASE_URL"])

    # 2. Run migrations (creates 162 tables, 32 revisions)
    _run([sys.executable, "-m", "flask", "db", "upgrade"], env=env)

    # 3. Trigger system_init via app boot (creates 37 perms, 8 roles, owner, 3 currencies, 76 industry fields, GL base)
    _run([sys.executable, "-c", "from app import create_app; app=create_app(); print('system_init done')"], env=env)

    # 4. No seed-packages: the platform owner creates SaaS packages from the
    # Owner panel (payment_vault/packages-management). Only first-run platform
    # essentials remain (permissions, roles, owner user, currencies, industry
    # fields, GL base) — all created idempotently by system_init app boot.

    # 5. Optional demo data
    if args.with_demo:
        _run([sys.executable, "-m", "flask", "seed-demo", "--force"], env=env)
        print("\nDemo tenant: slug=demo  user=demo_admin  pass=Demo@2026")
    else:
        print("\nSkipped demo data (use --with-demo to include)")

    # 6. Verify
    _run([sys.executable, "-m", "flask", "db", "current"], env=env)
    print("\n[OK] Dev first-run complete - clean DB ready at", env["DATABASE_URL"])
    print("   Owner: username=owner  password from OWNER_PASSWORD env or auto-generated (see instance/secret_key)")
    css_dist = PROJECT_ROOT / "static" / "css" / "dist" / "landing.css"
    if css_dist.is_file():
        size_kb = round(css_dist.stat().st_size / 1024, 1)
        print(f"   Assets: dist/ built OK (landing.css minified ~{size_kb} KB + SHA-256 cache bust)")
    else:
        print("   Assets: serving originals (dist/ not built; install Node.js to enable minified bundles)")
    print("   Run: python app.py  -> http://127.0.0.1:5000  (GET / -> 302 /auth/login)")


if __name__ == "__main__":
    main()
