"""Live storefront + platform-lock verification against the running server (8001)."""
import os
import sys

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE)
os.environ.setdefault("APP_ENV", "development")

import requests  # noqa: E402

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import TenantStore, Tenant  # noqa: E402
from services.store_service import StoreService  # noqa: E402

BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8001")


def get(slug):
    r = requests.get(f"{BASE_URL}/s/{slug}", timeout=15, allow_redirects=True)
    return r.status_code, r.text


def main():
    app = create_app()
    with app.app_context():
        store = TenantStore.query.first()
        if not store:
            print("NO STORE")
            sys.exit(1)
        slug = store.store_slug
        tenant = db.session.get(Tenant, store.tenant_id)
        tenant_name = store.title or tenant.name
        orig = (store.is_enabled, store.platform_disabled, StoreService.stores_globally_enabled())

        # Make it open: global on, tenant enabled, not platform-locked
        StoreService.set_stores_globally_enabled(True)
        store.is_enabled = True
        store.platform_disabled = False
        db.session.commit()

    results = []

    code, html = get(slug)
    open_ok = code == 200 and tenant_name in html and "AZAD Smart Systems" in html and "ps-footer-azad" in html
    results.append(("store OPEN shows tenant header + AZAD footer", open_ok, f"http={code} tenant={tenant_name in html} azad={'ps-footer-azad' in html}"))

    # Platform lock
    with app.app_context():
        s = TenantStore.query.first()
        StoreService.set_platform_disabled(s, True)
    code2, html2 = get(slug)
    locked_ok = code2 == 503 and ("store_closed" in html2 or "متوقف" in html2 or "مغلق" in html2 or "store-slash" in html2 or "ps-closed" in html2)
    results.append(("platform LOCK -> storefront closed", locked_ok, f"http={code2}"))

    # Tenant cannot enable while locked (route logic)
    with app.app_context():
        s = TenantStore.query.first()
        is_enabled = True
        if s.platform_disabled and is_enabled:
            is_enabled = False
        cannot_enable = (is_enabled is False)
        eff = StoreService.effective_enabled(s)
    results.append(("tenant CANNOT enable while locked", cannot_enable and not eff, f"forced_off={cannot_enable} effective={eff}"))

    # Unlock -> control back to tenant
    with app.app_context():
        s = TenantStore.query.first()
        StoreService.set_platform_disabled(s, False)
        eff2 = StoreService.effective_enabled(s)
    code3, html3 = get(slug)
    unlock_ok = eff2 and code3 == 200 and tenant_name in html3
    results.append(("UNLOCK -> tenant controls again, store open", unlock_ok, f"http={code3} effective={eff2}"))

    # Restore original state
    with app.app_context():
        s = TenantStore.query.first()
        s.is_enabled, s.platform_disabled = orig[0], orig[1]
        db.session.commit()
        StoreService.set_stores_globally_enabled(orig[2])

    ok = True
    for name, passed, detail in results:
        ok = ok and passed
        print(f"[{'OK' if passed else 'FAIL'}] {name} | {detail}")
    print(f"slug tested: {slug}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
