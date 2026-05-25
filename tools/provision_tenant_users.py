"""
Provision company users: {TENANT_CODE}_{local_part}
Platform reserved: owner, azad

  python tools/provision_tenant_users.py --dry-run
  python tools/provision_tenant_users.py --apply
"""

from __future__ import annotations

import argparse
import os
import re
import sys

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

os.environ.setdefault("APP_ENV", "development")

from utils.username_policy import (  # noqa: E402
    branch_key,
    build_company_username,
    is_platform_reserved,
    parse_company_username,
    tenant_username_prefix,
)


def _branch_users(tenant, branches):
    prefix = tenant_username_prefix(tenant)
    main_branch = next((b for b in branches if b.is_main), branches[0] if branches else None)

    yield (
        build_company_username(tenant, "manager"),
        f"{prefix.lower()}.manager@tenant.local",
        "manager",
        main_branch.id if main_branch else None,
        f"مدير {tenant.name_ar}",
    )

    for branch in branches:
        bk = branch_key(branch.code)
        for role_slug, local_suffix in (
            ("seller", f"{bk}_seller"),
            ("accountant", f"{bk}_accountant"),
            ("branch_manager", f"{bk}_branch"),
        ):
            yield (
                build_company_username(tenant, local_suffix),
                f"{prefix.lower()}.{local_suffix}@tenant.local",
                role_slug,
                branch.id,
                f"{tenant.name_ar} - {branch.name}",
            )


def _legacy_rename_default(tenant):
    """Old username -> local_part for tenant id 1."""
    return {
        "manager_main": "manager",
        "seller_main": "main_seller",
        "accountant_main": "main_accountant",
        "branch_manager_main": "main_branch",
        "seller_north": "north_seller",
        "manager_north": "north_manager",
        "accountant_north": "north_accountant",
        "branch_manager_north": "north_branch",
        "seller_south": "south_seller",
        "manager_south": "south_manager",
        "accountant_south": "south_accountant",
        "branch_manager_south": "south_branch",
        "seller_east": "east_seller",
        "manager_east": "east_manager",
        "accountant_east": "east_accountant",
        "branch_manager_east": "east_branch",
    }


def _try_legacy_local_part(username: str, tenant) -> str | None:
    """Map simulation-style names to local_part."""
    prefix = tenant_username_prefix(tenant)
    tid = tenant.id
    low = (username or "").lower()

    m = re.match(rf"^(seller|manager|accountant|branch_manager)_{tid}_(a|b)$", low)
    if m:
        role, letter = m.group(1), m.group(2)
        if role == "branch_manager":
            return f"{letter}_branch"
        if role == "manager":
            return f"{letter}_manager"
        if role == "seller":
            return f"{letter}_seller"
        if role == "accountant":
            return f"{letter}_accountant"

    m2 = re.match(rf"^(manager|seller|accountant)_{tid}$", low)
    if m2:
        return "manager" if m2.group(1) == "manager" else f"main_{m2.group(1)}"

    m3 = re.match(rf"^(manager|seller|accountant)_{tid}_(a|b)$", low)
    if m3:
        role, letter = m3.group(1), m3.group(2)
        if role == "manager":
            return f"{letter}_manager"
        return f"{letter}_{role}"

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--password", default="123")
    args = parser.parse_args()
    dry_run = not args.apply

    from app import create_app
    from extensions import db
    from models import User, Role, Branch
    from models.tenant import Tenant
    from utils.tenanting import without_tenant_scope

    app = create_app()
    with app.app_context(), without_tenant_scope():
        roles = {r.slug: r for r in Role.query.filter_by(is_active=True).all()}
        plan = []

        # Platform
        owner = User.query.filter(db.func.lower(User.username) == "owner").first()
        if owner:
            plan.append({"action": "ensure_owner", "username": "owner"})
        else:
            plan.append({"action": "create_platform", "username": "owner", "role": "owner", "is_owner": True})

        azad = User.query.filter(db.func.lower(User.username) == "azad").first()
        if azad:
            plan.append({"action": "ensure_azad", "username": "azad"})
        else:
            plan.append({"action": "create_platform", "username": "azad", "role": "developer", "is_owner": False})

        for old in ("seed_super_admin", "seed_developer"):
            u = User.query.filter_by(username=old).first()
            if u and u.is_active:
                plan.append({"action": "deactivate", "username": old})

        tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.id).all()
        for tenant in tenants:
            prefix = tenant_username_prefix(tenant)
            branches = Branch.query.filter_by(tenant_id=tenant.id, is_active=True).order_by(
                Branch.is_main.desc(), Branch.code
            ).all()
            if not branches:
                continue

            rename_from: set[str] = set()
            rename_to: set[str] = set()

            def _queue_rename(old_name: str, new_name: str) -> None:
                if not User.query.filter_by(username=old_name).first():
                    return
                if User.query.filter(db.func.lower(User.username) == new_name.lower()).first():
                    return
                if old_name in rename_from or new_name in rename_to:
                    return
                rename_from.add(old_name)
                rename_to.add(new_name)
                plan.append({"action": "rename", "from": old_name, "to": new_name})

            if tenant.id == 1:
                for old_name, local in _legacy_rename_default(tenant).items():
                    _queue_rename(old_name, build_company_username(tenant, local))

            for u in User.query.filter_by(tenant_id=tenant.id, is_active=True).filter(User.is_owner == False).all():
                uname = u.username or ""
                if is_platform_reserved(uname):
                    continue
                parsed = parse_company_username(uname)
                if parsed and parsed[0] == prefix:
                    continue
                local = _try_legacy_local_part(uname, tenant)
                if local:
                    _queue_rename(uname, build_company_username(tenant, local))

            for username, email, role_slug, branch_id, full_ar in _branch_users(tenant, branches):
                if username in rename_to:
                    continue
                if User.query.filter(db.func.lower(User.username) == username.lower()).first():
                    plan.append({"action": "exists", "username": username})
                    continue
                if roles.get(role_slug):
                    plan.append({
                        "action": "create",
                        "username": username,
                        "email": email,
                        "role": role_slug,
                        "tenant_id": tenant.id,
                        "branch_id": branch_id,
                        "full_name_ar": full_ar,
                    })

            for u in User.query.filter_by(tenant_id=tenant.id, is_active=True).filter(User.is_owner == False).all():
                uname = u.username or ""
                if is_platform_reserved(uname) or uname in rename_from:
                    continue
                parsed = parse_company_username(uname)
                if parsed and parsed[0] == prefix:
                    continue
                if _try_legacy_local_part(uname, tenant):
                    continue
                plan.append({"action": "deactivate", "username": uname})

        print(f"=== {'DRY RUN' if dry_run else 'APPLY'} ({len(plan)} actions) ===")
        for p in plan:
            print(p)

        if dry_run:
            print("\nUse: python tools/provision_tenant_users.py --apply")
            return

        owner = User.query.filter(db.func.lower(User.username) == "owner").first()
        azad = User.query.filter(db.func.lower(User.username) == "azad").first()

        action_order = {
            "ensure_owner": 0,
            "ensure_azad": 0,
            "create_platform": 1,
            "rename": 2,
            "create": 3,
            "deactivate": 4,
            "exists": 5,
        }
        plan.sort(key=lambda p: action_order.get(p["action"], 9))

        for item in plan:
            act = item["action"]
            if act == "exists":
                continue
            if act == "create_platform":
                role = roles[item["role"]]
                user = User(
                    username=item["username"],
                    email=f"{item['username']}@azad.platform",
                    role_id=role.id,
                    tenant_id=None,
                    branch_id=None,
                    is_owner=bool(item.get("is_owner")),
                    is_active=True,
                    email_verified=True,
                    full_name=item["username"],
                    full_name_ar="منصة ازاد",
                )
                user.set_password(args.password)
                db.session.add(user)
            elif act == "ensure_owner" and owner:
                owner.is_owner = True
                owner.tenant_id = owner.tenant_id or 1
                owner.is_active = True
            elif act == "ensure_azad":
                azad = User.query.filter(db.func.lower(User.username) == "azad").first()
                if azad:
                    azad.is_owner = False
                    azad.tenant_id = None
                    azad.role_id = roles["developer"].id
                    azad.is_active = True
            elif act == "create":
                role = roles[item["role"]]
                user = User(
                    username=item["username"],
                    email=item["email"],
                    role_id=role.id,
                    tenant_id=item["tenant_id"],
                    branch_id=item["branch_id"],
                    is_owner=False,
                    is_active=True,
                    email_verified=True,
                    full_name=item["username"],
                    full_name_ar=item.get("full_name_ar") or item["username"],
                )
                user.set_password(args.password)
                db.session.add(user)
            elif act == "rename":
                user = User.query.filter_by(username=item["from"]).first()
                if user and not User.query.filter(db.func.lower(User.username) == item["to"].lower()).first():
                    user.username = item["to"]
                    local_email = item["to"].lower() + "@tenant.local"
                    user.email = local_email
            elif act == "deactivate":
                user = User.query.filter_by(username=item["username"]).first()
                if user:
                    user.is_active = False

        db.session.commit()
        print("[OK] Done.")


if __name__ == "__main__":
    main()
