"""
Remove inactive legacy invoice_settings rows with tenant_id=NULL (id >= 6).

Dev/staging remediation only. Requires invoice_settings_backup_20260601 (created
if missing). Does not delete active rows or tenant-specific ids 1–5.

Run: SKIP_SYSTEM_INTEGRITY=1 python scripts/maintenance/invoice_settings_inactive_null_cleanup.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv()

BACKUP_TABLE = "invoice_settings_backup_20260601"


def main() -> int:
    from sqlalchemy import text
    from extensions import db
    from app import create_app
    from models.invoice_settings import InvoiceSettings

    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    app = create_app()
    report: dict = {"pre": {}, "action": {}, "post": {}}

    with app.app_context():

        def scalar(sql: str) -> int:
            return db.session.execute(text(sql)).scalar()

        report["pre"] = {
            "null_total": scalar("SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL"),
            "active_null": scalar(
                "SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL AND is_active = true"
            ),
            "inactive_null_ids": [
                r[0]
                for r in db.session.execute(
                    text(
                        "SELECT id FROM invoice_settings WHERE tenant_id IS NULL "
                        "AND is_active = false ORDER BY id"
                    )
                ).fetchall()
            ],
            "tenant_active_1_5": [
                dict(row._mapping)
                for row in db.session.execute(
                    text(
                        "SELECT id, tenant_id, is_active FROM invoice_settings "
                        "WHERE id BETWEEN 1 AND 5 ORDER BY id"
                    )
                ).fetchall()
            ],
        }

        get_active_check = {}
        for tid in range(1, 6):
            s = InvoiceSettings.get_active(tenant_id=tid)
            get_active_check[str(tid)] = {"id": s.id, "tenant_id": s.tenant_id} if s else None
        report["pre"]["get_active_by_tenant"] = get_active_check

        db.session.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS
                SELECT * FROM invoice_settings WHERE tenant_id IS NULL
                """
            )
        )
        db.session.execute(
            text(
                f"""
                INSERT INTO {BACKUP_TABLE}
                SELECT inv.* FROM invoice_settings inv
                WHERE inv.tenant_id IS NULL AND inv.is_active = false AND inv.id >= 6
                AND NOT EXISTS (
                    SELECT 1 FROM {BACKUP_TABLE} b WHERE b.id = inv.id
                )
                """
            )
        )
        deleted = db.session.execute(
            text(
                """
                DELETE FROM invoice_settings
                WHERE tenant_id IS NULL AND is_active = false AND id >= 6
                """
            )
        ).rowcount
        db.session.commit()
        report["action"] = {"backup_table": BACKUP_TABLE, "deleted_rows": deleted}

        report["post"] = {
            "null_total": scalar("SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL"),
            "active_null": scalar(
                "SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL AND is_active = true"
            ),
        }
        get_active_post = {}
        for tid in range(1, 6):
            s = InvoiceSettings.get_active(tenant_id=tid)
            get_active_post[str(tid)] = {"id": s.id, "tenant_id": s.tenant_id} if s else None
        report["post"]["get_active_by_tenant"] = get_active_post

    ok = (
        report["post"]["null_total"] == 0
        and report["post"]["active_null"] == 0
        and all(v and v["tenant_id"] == int(k) for k, v in get_active_post.items())
    )
    print(json.dumps(report, indent=2, default=str))
    print("CLEANUP_OK" if ok else "CLEANUP_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
