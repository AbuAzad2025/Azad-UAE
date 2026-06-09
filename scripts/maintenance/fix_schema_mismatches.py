"""
Repair missing DB columns that models define but tables lack.
Safe to run multiple times — skips columns that already exist.

Usage:
    python scripts/maintenance/fix_schema_mismatches.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from extensions import db
from sqlalchemy import text, inspect


def _column_exists(table_name, column_name):
    engine = db.engine
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns(table_name)}
    return column_name in cols


def _index_exists(table_name, index_name):
    engine = db.engine
    inspector = inspect(engine)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def _fk_exists(table_name, fk_name):
    engine = db.engine
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys(table_name)
    return any(fk["name"] == fk_name for fk in fks)


def main():
    app = create_app()
    with app.app_context():
        fixes = []

        # card_vault.tenant_id
        if not _column_exists("card_vault", "tenant_id"):
            db.session.execute(text(
                "ALTER TABLE card_vault ADD COLUMN tenant_id INTEGER"
            ))
            db.session.execute(text(
                "UPDATE card_vault SET tenant_id = 1 WHERE tenant_id IS NULL"
            ))
            db.session.execute(text(
                "ALTER TABLE card_vault ALTER COLUMN tenant_id SET NOT NULL"
            ))
            if not _index_exists("card_vault", "ix_card_vault_tenant_id"):
                db.session.execute(text(
                    "CREATE INDEX ix_card_vault_tenant_id ON card_vault (tenant_id)"
                ))
            fixes.append("card_vault.tenant_id")

        # audit_logs.tenant_id (nullable in model)
        if not _column_exists("audit_logs", "tenant_id"):
            db.session.execute(text(
                "ALTER TABLE audit_logs ADD COLUMN tenant_id INTEGER"
            ))
            if not _index_exists("audit_logs", "ix_audit_logs_tenant_id"):
                db.session.execute(text(
                    "CREATE INDEX ix_audit_logs_tenant_id ON audit_logs (tenant_id)"
                ))
            fixes.append("audit_logs.tenant_id")

        # purchases landed cost columns
        for col in ("freight", "insurance", "customs_duty", "other_landed_cost"):
            if not _column_exists("purchases", col):
                db.session.execute(text(
                    f"ALTER TABLE purchases ADD COLUMN {col} NUMERIC(15, 3) DEFAULT 0 NOT NULL"
                ))
                fixes.append(f"purchases.{col}")

        # gl_journal_lines dimension columns
        for col in ("branch_id", "warehouse_id", "cost_center_id", "profit_center_id", "partner_id"):
            if not _column_exists("gl_journal_lines", col):
                db.session.execute(text(
                    f"ALTER TABLE gl_journal_lines ADD COLUMN {col} INTEGER"
                ))
                fixes.append(f"gl_journal_lines.{col}")

        # gl_journal_lines indexes for dimension columns
        for col in ("branch_id", "warehouse_id", "cost_center_id", "profit_center_id", "partner_id"):
            idx_name = f"ix_gl_journal_lines_{col}"
            if _column_exists("gl_journal_lines", col) and not _index_exists("gl_journal_lines", idx_name):
                db.session.execute(text(
                    f"CREATE INDEX {idx_name} ON gl_journal_lines ({col})"
                ))

        db.session.commit()

        if fixes:
            print(f"Applied {len(fixes)} fixes:")
            for f in fixes:
                print(f"  + {f}")
        else:
            print("All schema columns already present. No fixes needed.")


if __name__ == "__main__":
    main()
