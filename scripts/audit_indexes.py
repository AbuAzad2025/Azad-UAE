#!/usr/bin/env python3
"""
Read-only index audit for the Azad-UAE database (PostgreSQL only).

Reports three classes of findings:

  1. MISSING FK INDEXES   — foreign-key columns with no index whose leading
                            columns cover the FK (slow parent deletes/joins).
  2. REDUNDANT INDEXES    — exact duplicates, or a non-unique, non-partial
                            index that is a strict left-prefix of another
                            non-partial index on the same table.
  3. HIGH SEQ-SCAN TABLES — tables with seq_scan > idx_scan beyond a row
                            threshold (pg_stat_user_tables). Advisory only:
                            legitimate for small lookup tables, so these do
                            NOT fail --strict.

Usage:
    python scripts/audit_indexes.py [--strict] [--min-rows N]

Exit code is 1 only with --strict AND actionable findings (classes 1-2).
On non-PostgreSQL dialects the audit prints a skip message and exits 0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_FK_SQL = text(
    """
    SELECT cl.relname AS table_name,
           con.conname AS constraint_name,
           (SELECT array_agg(att.attname ORDER BY u.ord)
              FROM unnest(con.conkey) WITH ORDINALITY AS u(attnum, ord)
              JOIN pg_attribute att
                ON att.attrelid = con.conrelid AND att.attnum = u.attnum
           ) AS cols
      FROM pg_constraint con
      JOIN pg_class cl ON cl.oid = con.conrelid
      JOIN pg_namespace ns ON ns.oid = cl.relnamespace
     WHERE con.contype = 'f' AND ns.nspname = 'public'
     ORDER BY cl.relname
    """
)

_INDEX_SQL = text(
    """
    SELECT t.relname AS table_name,
           i.relname AS index_name,
           array_agg(a.attname ORDER BY u.ord) AS cols,
           ix.indisunique AS is_unique,
           (ix.indpred IS NOT NULL) AS is_partial,
           pg_get_indexdef(ix.indexrelid) AS def
      FROM pg_index ix
      JOIN pg_class i ON i.oid = ix.indexrelid
      JOIN pg_class t ON t.oid = ix.indrelid
      JOIN pg_namespace ns ON ns.oid = t.relnamespace
      LEFT JOIN unnest(ix.indkey) WITH ORDINALITY AS u(attnum, ord) ON true
      LEFT JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = u.attnum
     WHERE ns.nspname = 'public'
     GROUP BY t.relname, i.relname, ix.indisunique, ix.indpred, ix.indexrelid
     ORDER BY t.relname, i.relname
    """
)

_SEQSCAN_SQL = text(
    """
    SELECT relname, seq_scan, COALESCE(idx_scan, 0) AS idx_scan, n_live_tup
      FROM pg_stat_user_tables
     WHERE n_live_tup >= :min_rows
       AND seq_scan > COALESCE(idx_scan, 0)
     ORDER BY seq_scan - COALESCE(idx_scan, 0) DESC
     LIMIT 25
    """
)


def _find_missing_fk(fks, indexes):
    """FK columns not covered by any index whose leading columns match."""
    by_table = {}
    for idx in indexes:
        by_table.setdefault(idx["table_name"], []).append(idx)
    missing = []
    for fk in fks:
        fk_cols = [c for c in (fk["cols"] or []) if c]
        if not fk_cols:
            continue
        covered = False
        for idx in by_table.get(fk["table_name"], []):
            idx_cols = [c for c in (idx["cols"] or []) if c]
            if idx_cols[: len(fk_cols)] == fk_cols:
                covered = True
                break
        if not covered:
            missing.append(fk)
    return missing


def _find_redundant(indexes):
    """Exact duplicates and strict left-prefix redundancy (same table)."""
    findings = []
    by_table = {}
    for idx in indexes:
        by_table.setdefault(idx["table_name"], []).append(idx)
    for table, idxs in by_table.items():
        for i, a in enumerate(idxs):
            a_cols = [c for c in (a["cols"] or []) if c]
            if not a_cols:
                continue  # expression (functional) index — skip overlap logic
            for b in idxs[i + 1 :]:
                b_cols = [c for c in (b["cols"] or []) if c]
                if not b_cols:
                    continue
                if a["is_partial"] or b["is_partial"]:
                    continue  # different predicates may differ — not comparable
                if a_cols == b_cols:
                    findings.append((table, a["index_name"], b["index_name"], "exact duplicate"))
                elif not a["is_unique"] and len(a_cols) < len(b_cols) and b_cols[: len(a_cols)] == a_cols:
                    findings.append((table, a["index_name"], b["index_name"], f"left-prefix of {b['index_name']}"))
                elif not b["is_unique"] and len(b_cols) < len(a_cols) and a_cols[: len(b_cols)] == b_cols:
                    findings.append((table, b["index_name"], a["index_name"], f"left-prefix of {a['index_name']}"))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true", help="exit 1 when actionable findings exist")
    parser.add_argument(
        "--min-rows",
        type=int,
        default=1000,
        help="minimum live rows for seq-scan reporting (default 1000)",
    )
    args = parser.parse_args(argv)

    from app.factory import create_app
    from extensions import db

    app = create_app()
    with app.app_context():
        if db.engine.dialect.name != "postgresql":
            print(f"index audit: skipped (dialect is {db.engine.dialect.name!r}, PostgreSQL only)")
            return 0

        fks = [dict(r._mapping) for r in db.session.execute(_FK_SQL)]
        indexes = [dict(r._mapping) for r in db.session.execute(_INDEX_SQL)]
        scans = [dict(r._mapping) for r in db.session.execute(_SEQSCAN_SQL, {"min_rows": args.min_rows})]

    missing_fk = _find_missing_fk(fks, indexes)
    redundant = _find_redundant(indexes)

    print(f"index audit: {len(indexes)} indexes, {len(fks)} foreign keys inspected\n")

    print(f"[1] Missing FK indexes: {len(missing_fk)}")
    for fk in missing_fk:
        print(f"    - {fk['table_name']}: {fk['constraint_name']} ({', '.join(fk['cols'])})")

    print(f"\n[2] Redundant/duplicate indexes: {len(redundant)}")
    for table, a, b, kind in redundant:
        print(f"    - {table}: {a} vs {b} — {kind}")

    print(f"\n[3] High seq-scan tables (advisory, min_rows={args.min_rows}): {len(scans)}")
    for row in scans:
        print(
            f"    - {row['relname']}: seq_scan={row['seq_scan']} "
            f"idx_scan={row['idx_scan']} live_rows={row['n_live_tup']}"
        )

    actionable = len(missing_fk) + len(redundant)
    if args.strict and actionable:
        print(f"\nSTRICT: {actionable} actionable finding(s) — failing.")
        return 1
    print("\nOK" if not actionable else f"\n{actionable} actionable finding(s) (advisory mode).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
