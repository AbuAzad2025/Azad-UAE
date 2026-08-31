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
only creates missing rows (permissions, roles, currencies, GL base, packages).

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

    # 1. Ensure DB exists (does not drop existing data in prod)
    _ensure_db(env["DATABASE_URL"])

    # 2. Run migrations
    _run([sys.executable, "-m", "flask", "db", "upgrade"], env=env)

    # 3. Trigger system_init (perms, roles, owner, currencies, industry fields, GL base)
    _run([sys.executable, "-c", "from app import create_app; app=create_app(); print('system_init done')"], env=env)

    # 4. Seed commercial packages (idempotent, no demo tenant)
    _run([sys.executable, "-m", "flask", "seed-packages"], env=env)

    # 5. Verify
    _run([sys.executable, "-m", "flask", "db", "current"], env=env)
    print("\n[OK] Prod first-run complete - DB ready at", env["DATABASE_URL"].split("@")[-1])
    print(f"   Owner: {env['OWNER_USERNAME']} / {env['OWNER_EMAIL']}")
    print("   No demo data created. Create tenants via Owner panel: /owner/tenants/new")
    print("   Run: gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app")


if __name__ == "__main__":
    main()
