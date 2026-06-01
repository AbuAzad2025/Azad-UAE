"""
Backup/restore QA — does not touch the current DATABASE_URL unless --restore-to-target
with a different TARGET_TEST_DATABASE_URL.

Usage:
  python tools/qa/backup_restore_check.py --verify-tools
  python tools/qa/backup_restore_check.py --create-and-verify
  python tools/qa/backup_restore_check.py --restore-to-target
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))


def verify_tools() -> int:
    from services.backup_service import BackupService

    BackupService.initialize()
    tools = BackupService.pg_tools_status()
    writable = os.access(BackupService.BACKUP_DIR, os.W_OK | os.X_OK)
    print("BACKUP_DIR", BackupService.BACKUP_DIR)
    print("writable", writable)
    print("pg_dump", tools.get("pg_dump") or "MISSING")
    print("pg_restore", tools.get("pg_restore") or "MISSING")
    print("pg_dump_version", tools.get("pg_dump_version"))
    if not writable:
        return 1
    if not tools.get("pg_dump"):
        print("WARN: pg_dump not available")
        return 2
    return 0


def create_and_verify() -> int:
    from services.backup_service import BackupService

    _load_env()
    from app import create_app

    app = create_app()
    with app.app_context():
        BackupService.initialize()
        created = BackupService.create_backup(manual=True, description="backup_restore_check")
        if not created:
            print("FAIL: create_backup returned None")
            return 1
        fn = created["filename"]
        print("CREATED", fn, created.get("size_mb"), "MB")
        result = BackupService.verify_backup(fn)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("valid") else 1


def restore_to_target() -> int:
    from services.backup_service import BackupService

    _load_env()
    target = (os.environ.get("TARGET_TEST_DATABASE_URL") or "").strip()
    if not target:
        print("SKIP: TARGET_TEST_DATABASE_URL not set")
        return 2
    current = (os.environ.get("DATABASE_URL") or "").strip()
    if BackupService._urls_same_database(current, target):
        print("FAIL: TARGET_TEST_DATABASE_URL equals DATABASE_URL")
        return 1

    from app import create_app

    app = create_app()
    with app.app_context():
        backups = BackupService.list_backups()
        modern = [b for b in backups if b.get("format") == "azad_tar_v1" or str(b.get("filename", "")).startswith("azad_backup_")]
        if not modern:
            print("FAIL: no modern backup to restore")
            return 1
        fn = modern[0]["filename"]
        verify = BackupService.verify_backup(fn)
        if not verify.get("valid"):
            print("FAIL: backup invalid", verify)
            return 1
        outcome = BackupService.restore_backup_to_target_db(
            fn,
            target,
            confirmation="RESTORE CONFIRM",
            restore_uploads=False,
        )
        print(json.dumps(outcome, indent=2, default=str))
        if not outcome.get("ok"):
            return 1
        # Optional predeploy against target (set DATABASE_URL temporarily)
        prev = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = target
            from tools.qa import predeploy_check

            report = predeploy_check.Report()
            predeploy_check.check_field_quality(report)
            predeploy_check.check_schema_hardening(report)
            print("PREDEPLOY_SUBSET", report.overall)
            for s in report.sections:
                print(f"  [{s.status}] {s.name}: {s.detail}")
            return 1 if report.failed else 0
        finally:
            if prev:
                os.environ["DATABASE_URL"] = prev


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-tools", action="store_true")
    parser.add_argument("--create-and-verify", action="store_true")
    parser.add_argument("--restore-to-target", action="store_true")
    args = parser.parse_args()
    if args.verify_tools:
        return verify_tools()
    if args.create_and_verify:
        return create_and_verify()
    if args.restore_to_target:
        return restore_to_target()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
