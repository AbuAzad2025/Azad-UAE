"""AI access policy integration check.

Covers:
- global off + tenant off behaviors
- owner/developer bypass
- tenant user isolation policy
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

load_dotenv(".env")

from app import create_app
from extensions import db
from models.system_settings import SystemSettings
from models.tenant import Tenant
from models.user import User, Role
from utils.ai_access import get_ai_access_state, get_tenant_ai_level, set_tenant_ai_level


def _pick_users():
    owner = User.query.filter_by(is_owner=True, is_active=True).first()
    developer = (
        User.query.join(Role, Role.id == User.role_id)
        .filter(Role.slug == "developer", User.is_active == True)
        .first()
    )
    tenant_user = (
        User.query.join(Role, Role.id == User.role_id)
        .filter(
            User.is_owner == False,
            User.tenant_id.isnot(None),
            User.is_active == True,
            Role.slug.in_(("super_admin", "manager", "seller")),
        )
        .first()
    )
    if not owner or not developer or not tenant_user:
        raise RuntimeError("required users not found (owner/developer/tenant user)")
    return owner, developer, tenant_user


def _as_login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def run():
    app = create_app()
    report = {"checks": []}

    with app.app_context():
        try:
            db.session.rollback()
        except Exception:
            pass
        owner, developer, tenant_user = _pick_users()
        settings = SystemSettings.get_current()
        tenant = db.session.get(Tenant, int(tenant_user.tenant_id))
        if not tenant:
            raise RuntimeError("tenant user has invalid tenant")

        original = {
            "global_enabled": bool(settings.enable_ai_assistant),
            "tenant_enabled": bool(getattr(tenant, "enable_ai", True)),
            "tenant_level": get_tenant_ai_level(int(tenant.id), default="execute"),
        }

        try:
            # Baseline on
            settings.enable_ai_assistant = True
            tenant.enable_ai = True
            set_tenant_ai_level(int(tenant.id), "advanced")
            db.session.commit()

            state_owner = get_ai_access_state(owner)
            state_dev = get_ai_access_state(developer)
            state_tenant = get_ai_access_state(tenant_user)
            report["checks"].append({
                "name": "baseline_access",
                "owner_allowed": state_owner["allowed"],
                "developer_allowed": state_dev["allowed"],
                "tenant_allowed": state_tenant["allowed"],
                "tenant_level": state_tenant.get("ai_level"),
                "ok": state_owner["allowed"] and state_dev["allowed"] and state_tenant["allowed"],
            })

            # Global OFF: tenant user denied, developer/owner still allowed
            settings.enable_ai_assistant = False
            db.session.commit()
            state_owner = get_ai_access_state(owner)
            state_dev = get_ai_access_state(developer)
            state_tenant = get_ai_access_state(tenant_user)
            report["checks"].append({
                "name": "global_off_policy",
                "owner_allowed": state_owner["allowed"],
                "developer_allowed": state_dev["allowed"],
                "tenant_allowed": state_tenant["allowed"],
                "tenant_reason": state_tenant.get("reason"),
                "ok": state_owner["allowed"] and state_dev["allowed"] and (not state_tenant["allowed"]) and state_tenant.get("reason") == "global_disabled",
            })

            # Tenant OFF: tenant user denied
            settings.enable_ai_assistant = True
            tenant.enable_ai = False
            db.session.commit()
            state_tenant = get_ai_access_state(tenant_user)
            report["checks"].append({
                "name": "tenant_off_policy",
                "tenant_allowed": state_tenant["allowed"],
                "tenant_reason": state_tenant.get("reason"),
                "ok": (not state_tenant["allowed"]) and state_tenant.get("reason") == "tenant_disabled",
            })

            # Endpoint integration check
            tenant.enable_ai = True
            settings.enable_ai_assistant = True
            db.session.commit()

            with app.test_client() as client:
                _as_login(client, tenant_user)
                r_ok = client.get("/ai/exchange-rate/USD", headers={"Accept": "application/json"})
                settings.enable_ai_assistant = False
                db.session.commit()
                r_block = client.get("/ai/exchange-rate/USD", headers={"Accept": "application/json"})

            report["checks"].append({
                "name": "chat_endpoint_policy",
                "status_when_enabled": r_ok.status_code,
                "status_when_global_off": r_block.status_code,
                "ok": r_ok.status_code < 500 and r_block.status_code == 403,
            })

        finally:
            settings.enable_ai_assistant = original["global_enabled"]
            tenant.enable_ai = original["tenant_enabled"]
            set_tenant_ai_level(int(tenant.id), original["tenant_level"])
            db.session.commit()

    total = len(report["checks"])
    passed = sum(1 for c in report["checks"] if c.get("ok"))
    report["summary"] = {"total": total, "passed": passed, "failed": total - passed}
    return report


if __name__ == "__main__":
    import json

    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["summary"]["failed"] > 0:
        raise SystemExit(1)
