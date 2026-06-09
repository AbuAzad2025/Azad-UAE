"""
Clear all error audit logs.
Safe to run — only truncates error_audit_logs table.

Usage:
    python scripts/maintenance/clear_error_logs.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from extensions import db
from sqlalchemy import text


def main():
    app = create_app()
    with app.app_context():
        result = db.session.execute(text("DELETE FROM error_audit_logs"))
        db.session.commit()
        count = result.rowcount
        print(f"Deleted {count} error audit log(s).")


if __name__ == "__main__":
    main()
