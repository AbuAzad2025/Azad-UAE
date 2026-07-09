"""
Maintenance script: fix / reconcile the DEFAULT tenant before a scoped restore.

Why this exists
---------------
The default demo tenant (slug='default') was first backed up before several
NOT NULL columns were added to the schema (e.g. tenants.prices_include_vat).
When such a *stale* scoped backup is later restored, the raw INSERT omits the
new column and Postgres raises:

    NotNullViolation: null value in column "prices_include_vat"
    of relation "tenants" violates not-null constraint

(Conversely, a column that existed in the backup but was later removed from the
schema causes a ProgrammingError on an unknown column.)

This script makes the default tenant *restore-safe*:

  (a) PATCHES the live default-tenant row: any NOT NULL column that has no DB
      default and is currently NULL gets a typed default written to it, so the
      live row is internally consistent.

  (b) REGENERATES a fresh, drift-free scoped backup of the default tenant,
      overwriting the stale archive, so future live/dry_run restores succeed.

It is idempotent and read-only with respect to business data: it only fills in
missing NOT NULL metadata and refreshes the export.

Usage:
    python scripts/fix_default_tenant.py            # patch + regenerate backup
    python scripts/fix_default_tenant.py --check     # report only, no writes
    python scripts/fix_default_tenant.py --no-backup # patch live row only
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from extensions import db
from sqlalchemy import create_engine, text
from services.backup_scope_config import normalize_row_to_target


def _default_for_type(data_type: str):
    dt = (data_type or "").lower()
    if "boolean" in dt:
        return False
    if any(k in dt for k in ("int", "numeric", "decimal", "money", "real", "double", "float")):
        return 0
    if "json" in dt:
        return "{}"
    if any(k in dt for k in ("timestamp", "date", "time")):
        return "now()"
    if "uuid" in dt:
        import uuid

        return str(uuid.uuid4())
    return ""


def find_default_tenant(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, slug FROM tenants WHERE slug = 'default' LIMIT 1")
        ).fetchone()
        return (int(row[0]), row[1]) if row else (None, None)


def conflicting_demo_rows(engine, tenant_id: int) -> list:
    """Detect duplicate/conflicting demo records for the default tenant."""
    issues = []
    with engine.connect() as conn:
        dup_slug = conn.execute(
            text(
                "SELECT count(*) FROM tenants WHERE slug = 'default' "
                "AND id <> :tid"
            ),
            {"tid": tenant_id},
        ).scalar()
        if dup_slug:
            issues.append(f"{dup_slug} other tenant(s) also use slug 'default'")
    return issues


def patch_default_tenant_metadata(engine, tenant_id: int, dry_run: bool) -> list:
    """Fill NOT NULL columns (no DB default) that are NULL on the default row."""
    fixed = []
    with engine.begin() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name, data_type, column_default FROM "
                "information_schema.columns WHERE table_schema='public' "
                "AND table_name='tenants' AND is_nullable='NO'"
            )
        ).fetchall()
        for name, dtype, default in cols:
            if default is not None and str(default).upper() != "NULL":
                continue  # DB will supply the default on insert/update
            cur = conn.execute(
                text(f'SELECT "{name}" FROM tenants WHERE id = :tid'),
                {"tid": tenant_id},
            ).scalar()
            if cur is None:
                val = _default_for_type(dtype)
                fixed.append(f"tenants.{name} <- {val!r} ({dtype})")
                if not dry_run:
                    if isinstance(val, str) and val == "now()":
                        conn.execute(
                            text(f"UPDATE tenants SET {name} = now() WHERE id = :tid"),
                            {"tid": tenant_id},
                        )
                    else:
                        conn.execute(
                            text(f'UPDATE tenants SET "{name}" = :v WHERE id = :tid'),
                            {"v": val, "tid": tenant_id},
                        )
    return fixed


def regenerate_default_backup(engine_url: str, tenant_id: int, dry_run: bool) -> str:
    """Create a fresh, schema-current scoped backup of the default tenant."""
    from app import create_app
    from services.backup_service import BackupService

    app = create_app()
    with app.app_context():
        BackupService.initialize()
        if dry_run:
            return "(skipped: --check mode)"
        result = BackupService.create_backup(scope="tenant", tenant_id=tenant_id, manual=True)
    if isinstance(result, dict):
        return result.get("filename") or result.get("manifest", {}).get("backup_scope") or str(result)
    return str(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix the default tenant for safe scoped restore")
    parser.add_argument("--check", action="store_true", help="report only, no writes")
    parser.add_argument("--no-backup", action="store_true", help="do not regenerate the backup")
    parser.add_argument("--bootstrap", action="store_true",
                        help="if no live default tenant exists, create one from the default backup archive")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL") or "postgresql+psycopg2://postgres@localhost:5432/azad_uae"
    # psycopg2 needs a plain postgresql:// DSN for raw connections
    raw_url = database_url.replace("postgresql+psycopg2", "postgresql")

    return _run_maintenance(database_url, raw_url, dry_run=args.check, no_backup=args.no_backup, bootstrap=args.bootstrap)


def _run_maintenance(database_url: str, raw_url: str, dry_run: bool, no_backup: bool, bootstrap: bool) -> int:
    """Core maintenance logic extracted for programmatic use."""
    print(f"[fix_default_tenant] DATABASE_URL={database_url}")
    engine = create_engine(raw_url)

    tid, slug = find_default_tenant(engine)
    if tid is None:
        # The conflict lives only in backup archives (the live DB has no
        # 'default' tenant). The restore engine now normalizes every row to
        # the target schema (normalize_row_to_target), so a restore of the
        # default backup succeeds. A dry-run restore validates this.
        print("[fix_default_tenant] No live tenant with slug='default' found.")
        print("[fix_default_tenant] The default-tenant conflict is backup-archive only; "
              "the restore engine normalizes rows to the target schema, so restore now "
              "succeeds. Run a dry-run restore to validate.")
        if bootstrap:
            created = bootstrap_default_tenant_from_backup(engine, database_url, dry_run=dry_run)
            print(f"[fix_default_tenant] Bootstrap result: {created}")
        return 0
    print(f"[fix_default_tenant] Found default tenant id={tid} slug={slug!r}")

    issues = conflicting_demo_rows(engine, tid)
    if issues:
        print("[fix_default_tenant] Conflicting demo records:")
        for i in issues:
            print(f"  - {i}")
    else:
        print("[fix_default_tenant] No conflicting demo records detected.")

    fixed = patch_default_tenant_metadata(engine, tid, dry_run=dry_run)
    if fixed:
        print(f"[fix_default_tenant] Patched {len(fixed)} NOT NULL metadata column(s):")
        for f in fixed:
            print(f"  + {f}")
    else:
        print("[fix_default_tenant] Default tenant metadata already consistent.")

    if not no_backup:
        fn = regenerate_default_backup(database_url, tid, dry_run=dry_run)
        print(f"[fix_default_tenant] Regenerated scoped backup: {fn}")

    print("[fix_default_tenant] DONE.")
    return 0


def run_default_tenant_maintenance(dry_run: bool = False) -> dict:
    """
    Run default tenant maintenance as a startup hook.
    
    Args:
        dry_run: If True, only report what would be done without making changes
        
    Returns:
        dict: Maintenance result with keys:
            - 'patched': list of columns patched
            - 'backup_regenerated': str or None
            - 'action_needed': bool
    """
    database_url = os.environ.get("DATABASE_URL") or "postgresql+psycopg2://postgres@localhost:5432/azad_uae"
    raw_url = database_url.replace("postgresql+psycopg2", "postgresql")
    
    print(f"[fix_default_tenant] Startup maintenance check (dry_run={dry_run})")
    engine = create_engine(raw_url)

    tid, slug = find_default_tenant(engine)
    if tid is None:
        # No default tenant in live DB - this is expected in production
        # where the default tenant was only in backup archives
        return {
            'patched': [],
            'backup_regenerated': None,
            'action_needed': False,
            'message': 'No live default tenant found (conflict is backup-archive only)'
        }
    
    print(f"[fix_default_tenant] Found default tenant id={tid} slug={slug!r}")

    issues = conflicting_demo_rows(engine, tid)
    if issues:
        print("[fix_default_tenant] Conflicting demo records detected:")
        for i in issues:
            print(f"  - {i}")

    fixed = patch_default_tenant_metadata(engine, tid, dry_run=dry_run)
    if fixed:
        print(f"[fix_default_tenant] Patched {len(fixed)} NOT NULL metadata column(s)")
    else:
        print("[fix_default_tenant] Default tenant metadata already consistent.")

    backup_fn = None
    if not dry_run and not False:  # Always regenerate backup in production
        backup_fn = regenerate_default_backup(database_url, tid, dry_run=dry_run)
        print(f"[fix_default_tenant] Regenerated scoped backup: {backup_fn}")

    return {
        'patched': fixed,
        'backup_regenerated': backup_fn,
        'action_needed': len(fixed) > 0 or backup_fn is not None,
        'conflicts': issues,
    }


if __name__ == "__main__":
    sys.exit(main())
