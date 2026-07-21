"""Query-pattern probe — prints normalized SQL patterns per endpoint + 500 details."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import event

from tests.perf.test_baseline import _seed_bulk

PROBE_ENDPOINTS = ["/sales/", "/customers/", "/pos/grid", "/"]


def test_probe(auth_client, db_session, sample_tenant, sample_user, capsys):
    from extensions import db

    _seed_bulk(db_session, sample_tenant, sample_user)

    for path in PROBE_ENDPOINTS:
        auth_client.get(path)
        statements: Counter[str] = Counter()

        def _on_execute(conn, cursor, statement, parameters, context, executemany):
            normalized = statement.strip().split("\n")[0][:110]
            from_clause = statement.upper()
            table = "?"
            for token in ("FROM ", "INTO ", "UPDATE "):
                if token in from_clause:
                    table = from_clause.split(token, 1)[1].strip().split(" ")[0].strip('"').lower()
                    break
            key = f"{normalized[:60]} | {table}"
            statements[key] += 1

        event.listen(db.engine, "before_cursor_execute", _on_execute)
        resp = auth_client.get(path)
        event.remove(db.engine, "before_cursor_execute", _on_execute)

        with capsys.disabled():
            print(f"\n=== {path} → {resp.status_code} ===")
            for stmt, count in statements.most_common(12):
                print(f"  x{count:<3} {stmt}")
            if resp.status_code == 500:
                body = resp.get_data(as_text=True)
                print("  --- 500 body excerpt ---")
                print("  " + body[:600].replace("\n", "\n  "))
