"""
Provision شركة الحازم (tenant slug: alhazem) from static/img/tenants/alhazem/.
Converts the primary company tenant (id=1, was 'default') and keeps simulation tenants.

  python tools/provision_alhazem_tenant.py
  python tools/provision_alhazem_tenant.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

os.environ.setdefault("APP_ENV", "development")

ALHAZEM_SLUG = "alhazem"
SOURCE_SLUG = "default"  # tenant that holds real branches today


def _rename_def_to_hzm(db, User, tenant_id: int, dry_run: bool) -> list[dict]:
    actions = []
    for u in User.query.filter_by(tenant_id=tenant_id, is_active=True).filter(User.is_owner == False).all():
        uname = (u.username or "").strip()
        if uname.upper().startswith("DEF_"):
            new_name = "HZM_" + uname[4:]
            conflict = User.query.filter(db.func.lower(User.username) == new_name.lower()).first()
            if conflict and conflict.id != u.id:
                actions.append({"action": "skip_rename", "from": uname, "reason": "target exists"})
                continue
            actions.append({"action": "rename", "from": uname, "to": new_name})
            if not dry_run:
                u.username = new_name
                u.email = f"{new_name.lower()}@tenant.local"
    return actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry_run = not args.apply

    from decimal import Decimal

    from app import create_app
    from extensions import db
    from models import User
    from models.tenant import Tenant
    from utils.tenant_assets import branding_paths_for_folder, slug_from_folder
    from utils.tenanting import without_tenant_scope

    branding = branding_paths_for_folder("alhazem")
    if not branding.get("logo_url"):
        print("ERROR: missing static/img/tenants/alhazem/logo.png")
        sys.exit(1)

    app = create_app()
    plan: list[dict] = []

    with app.app_context(), without_tenant_scope():
        existing = Tenant.query.filter(
            db.func.lower(Tenant.slug).in_([ALHAZEM_SLUG, "alhazem-batteries"])
        ).first()
        source = Tenant.query.filter_by(slug=SOURCE_SLUG).first()

        if existing and source and existing.id != source.id:
            plan.append({
                "action": "migrate_branches",
                "from_tenant_id": source.id,
                "to_tenant_id": existing.id,
            })
            target = existing
        elif existing:
            target = existing
        elif source:
            plan.append({"action": "convert_tenant", "tenant_id": source.id, "slug": ALHAZEM_SLUG})
            target = source
        else:
            plan.append({"action": "create_tenant", "slug": ALHAZEM_SLUG})
            target = None

        if target:
            plan.append({"action": "apply_branding", "tenant_id": target.id, **branding})
            plan.append({"action": "rename_users", "tenant_id": target.id})

        if source and (not target or (target and target.id == source.id)):
            if not Tenant.query.filter_by(slug=SOURCE_SLUG).filter(Tenant.id != (target.id if target else -1)).first():
                plan.append({"action": "ensure_platform_default_tenant"})

        print(f"=== {'DRY RUN' if dry_run else 'APPLY'} ===")
        for p in plan:
            print(p)
        tid = target.id if target else (source.id if source else None)
        if tid:
            for r in _rename_def_to_hzm(db, User, tid, True):
                print(r)

        if dry_run:
            print("\nUse: python tools/provision_alhazem_tenant.py --apply")
            return

        # --- apply ---
        if not target:
            target = Tenant(
                name="Al Hazem Batteries",
                name_ar="شركة الحازم للبطاريات",
                name_en="Al Hazem Batteries",
                slug=ALHAZEM_SLUG,
                business_type="spare_parts",
                industry="automotive",
            )
            db.session.add(target)
            db.session.flush()

        if source and target and source.id != target.id:
            from models import Branch

            Branch.query.filter_by(tenant_id=source.id).update({"tenant_id": target.id})
            for table in (
                "users",
                "warehouses",
                "customers",
                "suppliers",
                "products",
                "sales",
                "purchases",
            ):
                try:
                    db.session.execute(
                        db.text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id = :sid"),
                        {"tid": target.id, "sid": source.id},
                    )
                except Exception:
                    pass

        target.name = "Al Hazem Batteries"
        target.name_ar = "شركة الحازم للبطاريات"
        target.name_en = "Al Hazem Batteries"
        target.slug = ALHAZEM_SLUG
        target.business_type = target.business_type or "spare_parts"
        target.industry = target.industry or "automotive"
        target.logo_url = branding.get("logo_url")
        target.logo_dark_url = branding.get("logo_dark_url") or branding.get("logo_url")
        target.favicon_url = branding.get("favicon_url")
        target.brand_color_primary = "#0D2E5E"
        target.brand_color_secondary = "#6DB33F"
        target.default_currency = "ILS"
        target.country = "Palestine"
        target.city = target.city or "Ramallah"
        target.address_ar = "بير زيت - رام الله فلسطين"
        target.phone_1 = target.phone_1 or "0595800275"
        target.mobile = target.mobile or "+972539885863"
        target.enable_tax = True
        target.default_tax_rate = Decimal("16.00")
        target.is_active = True

        renames = _rename_def_to_hzm(db, User, target.id, False)
        for r in renames:
            print(r)

        if not Tenant.query.filter_by(slug=SOURCE_SLUG).first():
            demo = Tenant(
                name="Default System",
                name_ar="النظام الافتراضي",
                slug=SOURCE_SLUG,
                business_type="general",
                default_currency="AED",
                country="UAE",
                is_active=True,
            )
            db.session.add(demo)
            db.session.flush()
            print({"action": "created_default_demo", "id": demo.id})

        demo_default = Tenant.query.filter_by(slug=SOURCE_SLUG).first()
        owner = User.query.filter(db.func.lower(User.username) == "owner").first()
        if owner and demo_default:
            owner.tenant_id = demo_default.id
        elif owner:
            owner.tenant_id = None

        try:
            from models.invoice_settings import InvoiceSettings

            inv = InvoiceSettings.query.filter_by(tenant_id=target.id).first()
            if not inv:
                inv = InvoiceSettings.get_active()
            if inv:
                inv.tenant_id = target.id
                inv.company_name_ar = target.name_ar
                inv.company_name_en = target.name_en or target.name
                inv.logo_url = target.logo_url
                inv.address_ar = target.address_ar
                inv.phone_1 = target.phone_1
                inv.whatsapp_number = target.mobile
                inv.header_color = "#0D2E5E"
                inv.accent_color = "#6DB33F"
                inv.footer_text_ar = (
                    "بطاريات سيارات • بطاريات طاقة شمسية • بطاريات تراكترونات • جميع أنواع البطاريات"
                )
        except Exception:
            pass

        db.session.commit()
        print("[OK] Alhazem tenant ready:", target.id, target.slug)

        import subprocess
        subprocess.run(
            [sys.executable, os.path.join(BASE, "tools", "provision_tenant_users.py"), "--apply"],
            check=False,
        )


if __name__ == "__main__":
    main()
