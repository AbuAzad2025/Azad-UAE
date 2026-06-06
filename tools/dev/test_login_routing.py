"""In-process login + branch/tenant routing check."""
import os
import re
import sys

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE)
os.environ.setdefault("APP_ENV", "development")

from app import create_app  # noqa: E402


def login(client, username, password="123"):
    r = client.get("/auth/login")
    csrf = None
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    if m:
        csrf = m.group(1).decode()
    data = {"username": username, "password": password, "access_mode": "users"}
    if csrf:
        data["csrf_token"] = csrf
    r2 = client.post("/auth/login", data=data, follow_redirects=False)
    with client.session_transaction() as sess:
        return {
            "status": r2.status_code,
            "location": r2.headers.get("Location", ""),
            "active_tenant_id": sess.get("active_tenant_id"),
            "active_branch_id": sess.get("active_branch_id"),
            "active_branch_mode": sess.get("active_branch_mode"),
        }


def main():
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    users = [
        ("HZM_birz_seller", 1, 2),
        ("HZM_dhah_seller", 1, 4),
        ("HZM_sair_seller", 1, 1),
        ("owner", 5, None),
    ]
    ok = True
    for username, exp_tenant, exp_branch in users:
        with app.test_client() as client:
            info = login(client, username)
        tenant_ok = info["active_tenant_id"] == exp_tenant
        branch_ok = info["active_branch_id"] == exp_branch
        if username == "owner":
            branch_ok = info["active_branch_mode"] == "all" and info["active_branch_id"] is None
        passed = info["status"] in (302, 303) and tenant_ok and branch_ok
        ok = ok and passed
        print(
            f"[{'OK' if passed else 'FAIL'}] {username}: status={info['status']} "
            f"tenant={info['active_tenant_id']}(exp {exp_tenant}) "
            f"branch={info['active_branch_id']}(exp {exp_branch}) mode={info['active_branch_mode']}"
        )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
