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

    # 1. Drop and create DBs
    _ensure_db(env["DATABASE_URL"])
    _ensure_db(env["TEST_DATABASE_URL"])

    # 2. Run migrations (creates 162 tables, 32 revisions)
    _run([sys.executable, "-m", "flask", "db", "upgrade"], env=env)

    # 3. Trigger system_init via app boot (creates 37 perms, 8 roles, owner, 3 currencies, 76 industry fields, GL base)
    _run([sys.executable, "-c", "from app import create_app; app=create_app(); print('system_init done')"], env=env)

    # 4. Seed commercial packages (3 tiers) — idempotent
    _run([sys.executable, "-m", "flask", "seed-packages"], env=env)

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
    print("   Run: python app.py  -> http://127.0.0.1:5000  (GET / -> 302 /auth/login)")


if __name__ == "__main__":
    main()
