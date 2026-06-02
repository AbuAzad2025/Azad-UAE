"""
Owner panels / RBAC readiness checks.

Run: python tools/qa/owner_panel_check.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

FAIL = "FAIL"
WARN = "WARN"
PASS = "PASS"


def _login(client, app, username: str, tenant_id: int | None = None) -> None:
    from flask import session
    from flask_login import login_user
    from models.user import User
    from utils.tenanting import ACTIVE_TENANT_SESSION_KEY

    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            raise RuntimeError(f"user not found: {username}")
        with app.test_request_context():
            login_user(user)
            saved = dict(session)
        with client.session_transaction() as sess:
            sess.clear()
            sess.update(saved)
            if tenant_id is not None and getattr(user, "is_owner", False):
                sess[ACTIVE_TENANT_SESSION_KEY] = tenant_id


def run_owner_panel_check(profile: str = "local") -> tuple[str, list[str], list[str]]:
    from app import create_app
    from extensions import db
    from models.tenant import Tenant
    from models.user import User
    from utils.owner_panel import build_tenant_management_rows, evaluate_tenant_user_warnings

    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    app = create_app()
    fails: list[str] = []
    warns: list[str] = []

    with app.app_context():
        rows = build_tenant_management_rows()
        t_fails, t_warns = evaluate_tenant_user_warnings(rows)
        if profile == "production-readiness":
            fails.extend(t_fails)
            warns.extend(t_warns)
        else:
            warns.extend(t_fails)
            warns.extend(t_warns)

        nasrallah = Tenant.query.filter(Tenant.slug.ilike("nasrallah")).first()
        if not nasrallah:
            warns.append("nasrallah tenant not in DB (skip)")
        else:
            n_row = next((r for r in rows if (r.get("warn_slug") or "") == "nasrallah"), None)
            if not n_row:
                fails.append("nasrallah not listed in platform tenant table")
            elif n_row.get("user_count", -1) != 0:
                warns.append(f"nasrallah users={n_row.get('user_count')} (expected 0 for WARN)")
            elif not n_row.get("warn_no_users"):
                warns.append("nasrallah should flag warn_no_users")

    client = app.test_client()

    checks = [
        ("platform owner dashboard", "owner", "/owner/dashboard", (200,)),
        ("tenant manager blocked owner dashboard", "AED_manager", "/owner/dashboard", (403, 404)),
        ("tenant manager company dashboard", "AED_manager", "/owner/company-dashboard", (200, 403)),
        ("seller blocked owner dashboard", "AED_a_seller", "/owner/dashboard", (403, 404)),
    ]

    for name, user, url, ok in checks:
        try:
            c = app.test_client()
            _login(c, app, user)
            resp = c.get(url)
            if resp.status_code not in ok:
                fails.append(f"{name}: HTTP {resp.status_code} expected {ok}")
        except Exception as exc:
            fails.append(f"{name}: {exc}")

    # Cross-tenant: manager cannot hit another tenant's product
    with app.app_context():
        from models import Product

        mgr = User.query.filter_by(username="AED_manager").first()
        if mgr and mgr.tenant_id:
            other = Product.query.filter(Product.tenant_id != mgr.tenant_id).first()
            if other:
                c = app.test_client()
                _login(c, app, "AED_manager")
                resp = c.get(f"/products/{other.id}")
                if resp.status_code not in (403, 404):
                    fails.append(f"cross-tenant product leak: {resp.status_code}")

    # Branding preview tenant 7 for platform owner
    try:
        c = app.test_client()
        _login(c, app, "owner")
        resp = c.get("/owner/preview-invoice/modern?tenant_id=7")
        if resp.status_code >= 500:
            fails.append(f"nasrallah preview 500: {resp.status_code}")
        elif resp.status_code not in (200, 302):
            warns.append(f"nasrallah preview HTTP {resp.status_code}")
        elif b"nasrallah" not in resp.data.lower() and b"nasr" not in resp.data.lower():
            warns.append("nasrallah branding not obvious in preview HTML")
    except Exception as exc:
        fails.append(f"branding preview: {exc}")

    # Backup scoping: manager should not create system backup
    try:
        c = app.test_client()
        _login(c, app, "AED_manager")
        resp = c.post(
            "/owner/backups/create",
            data={"scope": "system", "csrf_token": "test"},
            follow_redirects=False,
        )
        if resp.status_code in (403, 400):
            pass
        elif resp.status_code >= 500:
            fails.append(f"manager system backup POST caused {resp.status_code}")
        else:
            warns.append(f"manager system backup POST returned {resp.status_code} (expected 403/400)")
    except Exception as exc:
        warns.append(f"backup scope check skipped: {exc}")

    # No 500 on core owner routes (owner user)
    owner_routes = [
        "/owner/dashboard",
        "/owner/users-list",
        "/owner/backups/list",
        "/owner/system-health",
    ]
    c = app.test_client()
    _login(c, app, "owner")
    for path in owner_routes:
        resp = c.get(path)
        if resp.status_code >= 500:
            fails.append(f"owner route 500: {path}")

    if fails:
        return FAIL, fails, warns
    if warns:
        return WARN, fails, warns
    return PASS, fails, warns


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="local", choices=("local", "production-readiness"))
    args = parser.parse_args()
    status, fails, warns = run_owner_panel_check(args.profile)
    print("=" * 60)
    print(f"OWNER PANEL CHECK — {status}")
    for w in warns:
        print(f"  [WARN] {w}")
    for f in fails:
        print(f"  [FAIL] {f}")
    print("=" * 60)
    return 1 if status == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
