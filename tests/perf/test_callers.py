"""Caller probe — captures WHERE repeated system_settings/tenants queries originate."""

from __future__ import annotations

import traceback

from sqlalchemy import event

from tests.perf.test_baseline import _seed_bulk


def test_callers(auth_client, db_session, sample_tenant, sample_user, capsys):
    from extensions import db

    _seed_bulk(db_session, sample_tenant, sample_user)
    auth_client.get("/sales/")

    seen_stacks: dict[str, int] = {}

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        upper = statement.upper()
        if "SYSTEM_SETTINGS" not in upper and "FROM TENANTS" not in upper:
            return
        frames = traceback.extract_stack()
        app_frames = [
            f"{f.name} ({f.filename.split(chr(92))[-1]}:{f.lineno})"
            for f in frames
            if any(p in f.filename for p in ("routes", "services", "utils", "models", "app\\", "context"))
            and "test_" not in f.filename
            and "sqlalchemy" not in f.filename
        ]
        key = " <- ".join(app_frames[-4:])
        seen_stacks[key] = seen_stacks.get(key, 0) + 1

    event.listen(db.engine, "before_cursor_execute", _on_execute)
    auth_client.get("/sales/")
    event.remove(db.engine, "before_cursor_execute", _on_execute)

    with capsys.disabled():
        print("\n=== system_settings/tenants callers on /sales/ ===")
        for stack, count in sorted(seen_stacks.items(), key=lambda x: -x[1]):
            print(f"x{count}  {stack}")
