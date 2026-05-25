"""
Correct existing Alhazem branches in DB (no new branches).
Map ids 1-4 → سعير، بيرزيت، دير سامت، الظاهرية and rebind users/warehouses.

  python tools/fix_alhazem_branches.py
  python tools/fix_alhazem_branches.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

os.environ.setdefault("APP_ENV", "development")

# branch_id → (code, name, is_main)
ALHAZEM_BRANCHES = {
    1: ("SAIR", "سعير", False),
    2: ("BIRZ", "بيرزيت", True),
    3: ("DSMT", "دير سامت", False),
    4: ("DHAH", "الظاهرية", False),
}

# old username token → new (matches branch_key after fix)
USER_SUFFIX_RENAME = {
    "main": "sair",
    "north": "birz",
    "south": "dsmt",
    "east": "dhah",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry_run = not args.apply

    from app import create_app
    from extensions import db
    from models import Branch, User, Warehouse
    from models.tenant import Tenant
    from utils.tenanting import without_tenant_scope

    app = create_app()
    with app.app_context(), without_tenant_scope():
        tenant = Tenant.query.filter(
            db.func.lower(Tenant.slug).in_(["alhazem", "alhazem-batteries"])
        ).first()
        if not tenant:
            print("ERROR: alhazem tenant not found")
            sys.exit(1)

        plan = []
        for bid, (code, name, is_main) in ALHAZEM_BRANCHES.items():
            b = Branch.query.filter_by(id=bid, tenant_id=tenant.id).first()
            if not b:
                plan.append({"error": f"missing branch id={bid} for tenant {tenant.id}"})
                continue
            plan.append({
                "branch_id": bid,
                "from": {"code": b.code, "name": b.name, "is_main": b.is_main},
                "to": {"code": code, "name": name, "is_main": is_main},
            })

        for u in User.query.filter_by(tenant_id=tenant.id, is_active=True).filter(User.is_owner == False).all():
            uname = u.username or ""
            if not uname.upper().startswith("HZM_"):
                continue
            local = uname[4:]
            new_local = None
            for old, new in USER_SUFFIX_RENAME.items():
                if local.startswith(f"{old}_"):
                    new_local = new + local[len(old):]
                    break
                if local == old:
                    new_local = new
                    break
            if new_local and new_local != local:
                plan.append({
                    "user_rename": uname,
                    "to": f"HZM_{new_local}",
                    "branch_id": u.branch_id,
                })

        print(f"=== {'DRY RUN' if dry_run else 'APPLY'} tenant={tenant.slug} id={tenant.id} ===")
        for p in plan:
            print(p)

        if dry_run:
            print("\npython tools/fix_alhazem_branches.py --apply")
            return

        for bid, (code, name, is_main) in ALHAZEM_BRANCHES.items():
            b = Branch.query.filter_by(id=bid, tenant_id=tenant.id).first()
            if not b:
                continue
            b.code = code
            b.name = name
            b.city = name
            b.is_main = is_main
            b.is_active = True
            b.address = b.address or f"فرع {name}"

            for wh in Warehouse.query.filter_by(branch_id=b.id).all():
                wh.name = f"مستودع {name}"
                wh.name_ar = wh.name
                wh.code = f"WH-{code}"
                wh.tenant_id = tenant.id
                wh.is_active = True

        for u in User.query.filter_by(tenant_id=tenant.id, is_active=True).filter(User.is_owner == False).all():
            uname = u.username or ""
            if not uname.upper().startswith("HZM_"):
                continue
            local = uname[4:]
            new_local = None
            for old, new in USER_SUFFIX_RENAME.items():
                if local.startswith(f"{old}_"):
                    new_local = new + local[len(old):]
                    break
                if local == old:
                    new_local = new
                    break
            if not new_local or new_local == local:
                continue
            new_name = f"HZM_{new_local}"
            if User.query.filter(db.func.lower(User.username) == new_name.lower()).first():
                continue
            u.username = new_name
            u.email = f"{new_name.lower()}@tenant.local"

        manager = User.query.filter(
            db.func.lower(User.username) == "hzm_manager"
        ).first()
        birz = Branch.query.filter_by(id=2, tenant_id=tenant.id).first()
        if manager and birz:
            manager.branch_id = birz.id

        db.session.commit()
        print("[OK] Branches corrected and users rebound.")


if __name__ == "__main__":
    main()
