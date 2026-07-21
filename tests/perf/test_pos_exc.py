"""Exception probe — surfaces real tracebacks behind generic 500 pages."""

from __future__ import annotations

import traceback

from tests.perf.test_baseline import _seed_bulk


def test_pos_exceptions(auth_client, db_session, sample_tenant, sample_user, capsys):
    from flask import current_app

    _seed_bulk(db_session, sample_tenant, sample_user)
    current_app.config["DEBUG"] = True
    for path in ("/pos/", "/pos/grid"):
        try:
            resp = auth_client.get(path)
            status = resp.status_code
            tb = "(no exception)"
        except Exception:
            status = "RAISED"
            tb = traceback.format_exc()
        with capsys.disabled():
            print(f"\n=== {path} → {status} ===")
            lines = tb.strip().splitlines()
            print("\n".join(lines[-12:]))
