"""One-off staging smoke pass for the POS overhaul (Phases 1-4).

Runs against the azad_uae_staging PostgreSQL copy — never production.
Covers: register UI boot, fast-cash, parked carts, session lifecycle,
SaaS flag denial on basic tier, then pro-tier features (promotions,
receipt lookup, stock lookup, split tender checkout, idempotency replay).

Usage:
    SKIP_SYSTEM_INTEGRITY=1 DATABASE_URL=postgresql+psycopg2://postgres@localhost:5432/azad_uae_staging \
        python scripts/ops/smoke_pos_staging.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid

os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres@localhost:5432/azad_uae_staging",
)

from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402

SMOKE_PASSWORD = "Smoke#2026!"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def main() -> int:
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        from models.tenant import Tenant
        from models.user import User

        tenant = Tenant.query.filter_by(slug="demo").first()
        admin = User.query.filter_by(username="demo_admin", tenant_id=tenant.id).first()
        admin.password_hash = generate_password_hash(SMOKE_PASSWORD)
        db.session.commit()
        tenant_id = tenant.id
        print(f"staging tenant: {tenant.slug} (id={tenant_id}, plan={tenant.subscription_plan})")

    client = app.test_client()
    resp = client.post(
        "/auth/login",
        data={"username": "demo_admin", "password": SMOKE_PASSWORD},
        follow_redirects=False,
    )
    check("login as demo_admin", resp.status_code in (302, 303), f"status={resp.status_code}")

    resp = client.get("/pos/")
    check("register UI boots", resp.status_code == 200, f"status={resp.status_code}")

    resp = client.get("/pos/api/fast-cash?total=37.5&currency=AED")
    body = resp.get_json(silent=True) or {}
    check(
        "fast-cash options",
        resp.status_code == 200 and body.get("success") and len(body.get("options", [])) >= 2,
        json.dumps(body.get("options", [])[:3]),
    )

    resp = client.get("/pos/api/carts")
    body = resp.get_json(silent=True) or {}
    check(
        "list parked carts (lightweight)",
        resp.status_code == 200 and "payload" not in json.dumps(body),
        f"count={len(body.get('carts', []))}",
    )

    terminal = f"SMOKE-{uuid.uuid4().hex[:8]}"
    resp = client.post("/pos/api/session/open", json={"terminal_id": terminal})
    body = resp.get_json(silent=True) or {}
    session_id = (body.get("session") or {}).get("id")
    session_token = body.get("session_token")
    check(
        "open session with terminal binding",
        resp.status_code in (200, 201) and bool(session_token),
        f"session_id={session_id}",
    )

    resp = client.post(
        "/pos/api/carts/park",
        json={
            "label": "smoke-cart",
            "payload": {"lines": [{"product_id": 1, "quantity": 2}], "currency": "AED"},
            "session_token": session_token,
        },
    )
    body = resp.get_json(silent=True) or {}
    cart_id = (body.get("cart") or {}).get("id")
    check("park cart", resp.status_code in (200, 201) and bool(cart_id), f"cart_id={cart_id}")

    if cart_id:
        resp = client.get(f"/pos/api/carts/{cart_id}")
        body = resp.get_json(silent=True) or {}
        check(
            "resume cart returns payload",
            resp.status_code == 200 and bool((body.get("cart") or {}).get("payload")),
            f"status={((body.get('cart') or {}).get('status'))}",
        )
        resp = client.get(f"/pos/api/carts/{cart_id}")
        check("double resume blocked (409)", resp.status_code == 409, f"status={resp.status_code}")

    with app.app_context():
        tenant = db.session.get(Tenant, tenant_id)
        basic_plan = tenant.subscription_plan

    resp = client.post("/pos/api/promotions/evaluate", json={"lines": []})
    check(
        "basic tier denied promotions",
        resp.status_code == 403,
        f"status={resp.status_code} plan={basic_plan}",
    )
    resp = client.get("/pos/api/receipts/lookup?number=X-1")
    check("basic tier denied receipt lookup", resp.status_code == 403, f"status={resp.status_code}")

    with app.app_context():
        tenant = db.session.get(Tenant, tenant_id)
        tenant.subscription_plan = "pro"
        db.session.commit()
        print("staging tenant upgraded to plan=pro for feature smoke")

    resp = client.get("/pos/api/products?search=")
    body = resp.get_json(silent=True)
    products = body if isinstance(body, list) else (body or {}).get("products") or (body or {}).get("items") or []
    check("product search", resp.status_code == 200 and len(products) > 0, f"found={len(products)}")

    if products:
        pid = products[0].get("id")
        resp = client.post(
            "/pos/api/promotions/evaluate",
            json={"lines": [{"product_id": pid, "quantity": 2}]},
        )
        body = resp.get_json(silent=True) or {}
        check(
            "pro tier promotions evaluate",
            resp.status_code == 200 and body.get("success") is not False,
            f"keys={sorted(body.keys())[:6]}",
        )

        resp = client.get(f"/pos/api/stock/lookup?product_id={pid}")
        body = resp.get_json(silent=True) or {}
        check(
            "cross-branch stock breakdown",
            resp.status_code == 200,
            f"warehouses={len(body.get('warehouses', body.get('breakdown', [])))}",
        )

        idem_key = f"smoke-{uuid.uuid4().hex}"
        checkout_payload = {
            "lines": [{"product_id": pid, "quantity": 1}],
            "warehouse_id": products[0].get("warehouse_id"),
            "currency": "AED",
            "payments": [
                {"amount": "10.000", "payment_method": "cash", "currency": "AED"},
                {"amount": "5.000", "payment_method": "card", "currency": "AED"},
            ],
        }
        checkout_payload = {k: v for k, v in checkout_payload.items() if v is not None}
        resp = client.post(
            "/pos/api/checkout", json=checkout_payload, headers={"Idempotency-Key": idem_key}
        )
        first = resp.get_json(silent=True) or {}
        sale_number = (first.get("sale") or {}).get("sale_number") or first.get("sale_number")
        check(
            "split-tender checkout",
            resp.status_code in (200, 201) and first.get("success", True) is not False,
            f"sale={sale_number} status={resp.status_code} err={first.get('error')}",
        )

        resp = client.post(
            "/pos/api/checkout", json=checkout_payload, headers={"Idempotency-Key": idem_key}
        )
        replay = resp.get_json(silent=True) or {}
        replay_sale = (replay.get("sale") or {}).get("sale_number") or replay.get("sale_number")
        check(
            "idempotent replay returns same sale",
            resp.status_code in (200, 201) and replay_sale == sale_number,
            f"replay={replay_sale} flag={replay.get('idempotent_replay')}",
        )

        if sale_number:
            resp = client.get(f"/pos/api/receipts/lookup?number={sale_number}")
            body = resp.get_json(silent=True) or {}
            check(
                "receipt lookup finds smoke sale",
                resp.status_code == 200,
                f"lines={len(body.get('lines', body.get('sale', {}).get('lines', [])))}",
            )

    if session_id:
        resp = client.post(
            f"/pos/api/session/{session_id}/close",
            json={"counted_cash": "0.000"},
            headers={"X-Pos-Session-Token": session_token} if session_token else {},
        )
        check(
            "blind session close with counted cash",
            resp.status_code in (200, 201),
            f"status={resp.status_code} body={str(resp.get_json(silent=True))[:120]}",
        )

    failed = [r for r in results if not r[1]]
    print(f"\n=== SMOKE RESULT: {len(results) - len(failed)}/{len(results)} passed ===")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
