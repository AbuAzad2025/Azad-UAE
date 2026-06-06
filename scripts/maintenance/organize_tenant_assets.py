"""
One-off: rename static assets + align tenant-1 product names/images.
Run: python tools/organize_tenant_assets.py
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC = os.path.join(ROOT, "static")
PLACEHOLDER = "assets/shared/placeholders/no-product.png"

# --- branding file renames (relative to static/) ---
BRAND_RENAMES = [
    ("assets/brand/azad/logos/certificate-logo.png", "assets/brand/azad/logos/logo-certificate.png"),
    ("assets/brand/azad/logos/logo-icon.png", "assets/brand/azad/logos/logo-mark.png"),
    ("assets/tenants/alhazem/logos/primary.png", "assets/tenants/alhazem/logos/logo-full.png"),
    ("assets/tenants/alhazem/logos/secondary.png", "assets/tenants/alhazem/logos/logo-alt.png"),
    ("assets/tenants/alhazem/logos/emblem.png", "assets/tenants/alhazem/logos/logo-emblem.png"),
    ("assets/tenants/alhazem/headers/banner.png", "assets/tenants/alhazem/headers/store-banner.png"),
    ("assets/tenants/alhazem/headers/letterhead.png", "assets/tenants/alhazem/headers/invoice-letterhead.png"),
    ("assets/tenants/alhazem/og/og-1200x630.png", "assets/tenants/alhazem/og/social-share.png"),
    ("assets/tenants/nasrallah/logos/primary.png", "assets/tenants/nasrallah/logos/logo-primary.png"),
    ("assets/tenants/nasrallah/logos/emblem.png", "assets/tenants/nasrallah/logos/logo-emblem.png"),
    ("assets/tenants/nasrallah/headers/banner.png", "assets/tenants/nasrallah/headers/store-banner.png"),
    ("assets/tenants/nasrallah/headers/letterhead.png", "assets/tenants/nasrallah/headers/invoice-letterhead.png"),
]

DEMO_RENAMES = [
    ("assets/tenants/alhazem/demo-products/DEUTZ_BF4M_1013_64H_P&R_STD.png", "assets/tenants/alhazem/demo-products/deutz-bf4m-1013-64h.png"),
    ("assets/tenants/alhazem/demo-products/DEUTZ_BF4M_1013_P&R_71_cell_STD.png", "assets/tenants/alhazem/demo-products/deutz-bf4m-1013-71cell.png"),
    ("assets/tenants/alhazem/demo-products/DEUTZ_BF4M_1013_P&R_DH_STD.png", "assets/tenants/alhazem/demo-products/deutz-bf4m-1013-dh.png"),
    ("assets/tenants/alhazem/demo-products/DEUTZ_TCD_2.9_P&R_STD.png", "assets/tenants/alhazem/demo-products/deutz-tcd-29-standard.png"),
    ("assets/tenants/alhazem/demo-products/DEUTZ_TCD_2012_P&R_40mm_0.50.png", "assets/tenants/alhazem/demo-products/deutz-tcd-2012-40mm.png"),
    ("assets/tenants/alhazem/demo-products/DEUTZ_TCD_3.6_P&R_0.50.png", "assets/tenants/alhazem/demo-products/deutz-tcd-36-050.png"),
    ("assets/tenants/alhazem/demo-products/DEUTZ_TCD_3.6_P&R_STD.png", "assets/tenants/alhazem/demo-products/deutz-tcd-36-standard.png"),
]

# Generic demo samples → shared (not Al Hazem battery catalog)
GENERIC_DEMO_MOVES = [
    ("assets/tenants/alhazem/demo-products/bag-01.webp", "assets/shared/demo/bag.webp"),
    ("assets/tenants/alhazem/demo-products/camera-01.jpg", "assets/shared/demo/camera.jpg"),
    ("assets/tenants/alhazem/demo-products/headphones-01.jpg", "assets/shared/demo/headphones.jpg"),
    ("assets/tenants/alhazem/demo-products/keyboard-01.webp", "assets/shared/demo/keyboard.webp"),
    ("assets/tenants/alhazem/demo-products/laptop-01.webp", "assets/shared/demo/laptop.webp"),
    ("assets/tenants/alhazem/demo-products/mouse-01.png", "assets/shared/demo/mouse.png"),
    ("assets/tenants/alhazem/demo-products/phone-01.webp", "assets/shared/demo/phone.webp"),
    ("assets/tenants/alhazem/demo-products/sneakers-01.png", "assets/shared/demo/sneakers.png"),
    ("assets/tenants/alhazem/demo-products/tv-01.jpg", "assets/shared/demo/tv.jpg"),
    ("assets/tenants/alhazem/demo-products/watch-01.png", "assets/shared/demo/watch.png"),
]

DEUTZ_PRODUCTS = [
    (6, "DEUTZ BF4M 1013 64H", "بطارية DEUTZ BF4M 1013 64H", "DEUTZ-BF4M-1013-64H", "assets/tenants/alhazem/demo-products/deutz-bf4m-1013-64h.png"),
    (7, "DEUTZ BF4M 1013 71 Cell", "بطارية DEUTZ BF4M 1013 71 خلية", "DEUTZ-BF4M-1013-71C", "assets/tenants/alhazem/demo-products/deutz-bf4m-1013-71cell.png"),
    (8, "DEUTZ BF4M 1013 DH", "بطارية DEUTZ BF4M 1013 DH", "DEUTZ-BF4M-1013-DH", "assets/tenants/alhazem/demo-products/deutz-bf4m-1013-dh.png"),
    (9, "DEUTZ TCD 2.9 Standard", "بطارية DEUTZ TCD 2.9", "DEUTZ-TCD-29-STD", "assets/tenants/alhazem/demo-products/deutz-tcd-29-standard.png"),
    (10, "DEUTZ TCD 2012 40mm", "بطارية DEUTZ TCD 2012 40mm", "DEUTZ-TCD-2012-40", "assets/tenants/alhazem/demo-products/deutz-tcd-2012-40mm.png"),
    (11, "DEUTZ TCD 3.6 0.50", "بطارية DEUTZ TCD 3.6 0.50", "DEUTZ-TCD-36-050", "assets/tenants/alhazem/demo-products/deutz-tcd-36-050.png"),
    (12, "DEUTZ TCD 3.6 Standard", "بطارية DEUTZ TCD 3.6", "DEUTZ-TCD-36-STD", "assets/tenants/alhazem/demo-products/deutz-tcd-36-standard.png"),
]

ACCESSORY_IMAGES = {
    1: "assets/shared/demo/keyboard.webp",
    2: "assets/shared/demo/mouse.png",
    3: "assets/shared/demo/phone.webp",
    4: "assets/tenants/alhazem/demo-products/deutz-bf4m-1013-64h.png",
    5: "assets/shared/demo/laptop.webp",
}


def _git_mv(src_rel: str, dst_rel: str) -> None:
    src = os.path.join(STATIC, src_rel.replace("/", os.sep))
    dst = os.path.join(STATIC, dst_rel.replace("/", os.sep))
    if not os.path.isfile(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isfile(dst):
        os.remove(dst)
    try:
        subprocess.run(["git", "mv", src, dst], cwd=ROOT, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        shutil.move(src, dst)


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s[:60] or "product"


def rename_files() -> None:
    os.makedirs(os.path.join(STATIC, "assets/shared/demo"), exist_ok=True)
    for old, new in BRAND_RENAMES + DEMO_RENAMES + GENERIC_DEMO_MOVES:
        _git_mv(old, new)
    # Restore small Azad favicon from git if bloated
    fav = os.path.join(STATIC, "assets/brand/azad/favicons/favicon.png")
    if os.path.isfile(fav) and os.path.getsize(fav) > 50_000:
        tmp = os.path.join(ROOT, "_tmp_azad_fav.png")
        subprocess.run(
            ["git", "show", "HEAD:static/img/azad_favicon.png"],
            cwd=ROOT,
            stdout=open(tmp, "wb"),
            check=False,
        )
        if os.path.isfile(tmp) and os.path.getsize(tmp) < 50_000:
            shutil.copy2(tmp, fav)
        if os.path.isfile(tmp):
            os.remove(tmp)
    # logo-dark duplicate for alhazem: same bytes as logo — keep one file
    logo = os.path.join(STATIC, "assets/tenants/alhazem/logos/logo.png")
    dark = os.path.join(STATIC, "assets/tenants/alhazem/logos/logo-dark.png")
    if os.path.isfile(logo) and os.path.isfile(dark) and _sha(logo) == _sha(dark):
        shutil.copy2(logo, dark)


def organize_uploads_and_db() -> None:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
    sys.path.insert(0, ROOT)
    from app import create_app
    from extensions import db
    from models import Product, Tenant
    from sqlalchemy import text

    upload_dir = os.path.join(STATIC, "uploads/tenants/1/products")
    files = sorted(f for f in os.listdir(upload_dir) if f.endswith(".webp")) if os.path.isdir(upload_dir) else []

    # Unique by content hash, keep first filename
    seen_hash: dict[str, str] = {}
    unique_files: list[str] = []
    for fn in files:
        path = os.path.join(upload_dir, fn)
        digest = _sha(path)
        if digest not in seen_hash:
            seen_hash[digest] = fn
            unique_files.append(fn)

    app = create_app()
    with app.app_context():
        tenant = db.session.get(Tenant, 1)
        if tenant and not (tenant.logo_url or "").strip():
            tenant.logo_url = "assets/tenants/alhazem/logos/logo.png"
            tenant.logo_dark_url = "assets/tenants/alhazem/logos/logo-dark.png"
            tenant.favicon_url = "assets/tenants/alhazem/favicons/favicon.png"

        for pid, name_en, name_ar, pn, img in DEUTZ_PRODUCTS:
            p = db.session.get(Product, pid)
            if not p:
                continue
            p.name = name_en
            p.name_ar = name_ar
            p.part_number = pn
            p.image_url = img

        for pid, img in ACCESSORY_IMAGES.items():
            p = db.session.get(Product, pid)
            if p:
                p.image_url = img

        # Remaining products 13-35: assign unique uploads with readable filenames
        next_id = 13
        upload_idx = 0
        extra_names = [
            ("Varta Blue Dynamic 60Ah", "فارتا بلو دينamic 60Ah"),
            ("Varta Silver Dynamic 74Ah", "فارتا سيلفر 74Ah"),
            ("Exide Premium 100Ah", "إكسايد بريميوم 100Ah"),
            ("ACDelco Professional 70Ah", "ACDelco احترافية 70Ah"),
            ("Bosch S4 74Ah", "بوش S4 74Ah"),
            ("Yuasa YBX5000 45Ah", "يوasa YBX5000 45Ah"),
            ("Panasonic 55Ah", "باناسونيك 55Ah"),
            ("Tokyo Power 80Ah", "طوkyo Power 80Ah"),
            ("Al Hazem Maintenance Free 65Ah", "الحازم MF 65Ah"),
            ("Al Hazem Heavy Duty 120Ah", "الحازم HD 120Ah"),
            ("Truck Battery 180Ah", "بطارية شاحنات 180Ah"),
            ("Solar Deep Cycle 100Ah", "بطارية solar deep cycle 100Ah"),
            ("Motorcycle Battery 7Ah", "بطارية دراجة 7Ah"),
            ("UPS Battery 12V 9Ah", "بطارية UPS 9Ah"),
            ("Marine Battery 105Ah", "بطارية بحرية 105Ah"),
            ("Start-Stop AGM 70Ah", "بطارية start-stop AGM 70Ah"),
            ("Calcium Battery 62Ah", "بطارية كالسيوم 62Ah"),
            ("Premium Gold 90Ah", "بطارية ذهبية 90Ah"),
            ("Economy Line 50Ah", "بطارية اقتصادية 50Ah"),
            ("Industrial Traction 200Ah", "بطارية traction 200Ah"),
            ("Dual Purpose 95Ah", "بطارية dual purpose 95Ah"),
            ("High CCA 110Ah", "بطارية CCA عالي 110Ah"),
            ("Compact 45Ah", "بطارية compact 45Ah"),
        ]
        for name_en, name_ar in extra_names:
            if next_id > 35:
                break
            p = db.session.get(Product, next_id)
            if not p:
                next_id += 1
                continue
            p.name = name_en
            p.name_ar = name_ar
            p.part_number = f"AHZ-{next_id:04d}"
            if upload_idx < len(unique_files):
                old_fn = unique_files[upload_idx]
                old_path = os.path.join(upload_dir, old_fn)
                ext = os.path.splitext(old_fn)[1]
                new_fn = f"{_slug(name_en)}{ext}"
                new_path = os.path.join(upload_dir, new_fn)
                if old_path != new_path:
                    if os.path.isfile(new_path):
                        os.remove(new_path)
                    os.rename(old_path, new_path)
                p.image_url = f"uploads/tenants/1/products/{new_fn}"
                upload_idx += 1
            else:
                p.image_url = PLACEHOLDER
            next_id += 1

        # Fix placeholder URLs on products 1-5 if still example.com
        db.session.execute(
            text(
                "UPDATE products SET image_url = :ph "
                "WHERE tenant_id = 1 AND image_url LIKE 'https://example.com%'"
            ),
            {"ph": PLACEHOLDER},
        )
        db.session.commit()
        print(f"Updated products; assigned {upload_idx} upload images")


def main() -> None:
    rename_files()
    organize_uploads_and_db()
    print("Done.")


if __name__ == "__main__":
    main()
