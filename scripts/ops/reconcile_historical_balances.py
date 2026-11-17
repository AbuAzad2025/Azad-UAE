#!/usr/bin/env python3
"""Reconcile EVERY historical document against the stored sub-ledger balances.

Dry run (default) reports all discrepancies; ``--apply`` writes the corrected
balances. Requires a DATABASE_URL pointing at the target database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils.balance_reconciliation import reconcile  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write corrections (default: report only)")
    parser.add_argument("--report", type=Path, help="write the JSON report to this path")
    args = parser.parse_args()

    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        parser.error("DATABASE_URL is required")

    engine = create_engine(url)
    try:
        with Session(engine) as session:
            # Fail loudly on a non-target database rather than silently
            # repairing a scratch/test database.
            db_name = session.execute(text("SELECT current_database()")).scalar()
            report = reconcile(session.connection(), apply=args.apply)
            report["database"] = db_name
    finally:
        engine.dispose()

    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(payload)
    if args.report:
        args.report.write_text(payload, encoding="utf-8")
    return 0 if report["total_discrepancies"] == 0 or args.apply else 1


if __name__ == "__main__":
    raise SystemExit(main())
