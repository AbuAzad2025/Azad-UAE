import os
import sys
from datetime import datetime
from decimal import Decimal

from PIL import Image, ImageOps


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _center_crop_to_aspect(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    target_ratio = target_w / target_h
    w, h = img.size
    src_ratio = w / h
    if src_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)
    return img.crop(box)


def _save_png(img: Image.Image, path: str) -> None:
    _ensure_dir(os.path.dirname(path))
    img.save(path, format="PNG", optimize=True)


def generate_assets(src_dir: str, project_root: str) -> dict:
    src_dir = os.path.abspath(src_dir)
    project_root = os.path.abspath(project_root)

    src_banner = os.path.join(src_dir, "1.png")
    src_brand_sheet = os.path.join(src_dir, "6.png")
    src_icon = os.path.join(src_dir, "3.png")
    src_logo = os.path.join(src_dir, "4.png")

    out_tenant_dir = os.path.join(project_root, "static", "img", "tenants", "alhazem")
    _ensure_dir(out_tenant_dir)

    logo = Image.open(src_logo).convert("RGBA")
    icon = Image.open(src_icon).convert("RGBA")
    banner = Image.open(src_banner).convert("RGBA")

    logo_path = os.path.join(out_tenant_dir, "logo.png")
    logo_dark_path = os.path.join(out_tenant_dir, "logo_dark.png")
    favicon_path = os.path.join(out_tenant_dir, "favicon.png")
    og_path = os.path.join(out_tenant_dir, "og-1200x630.png")
    icon_192_path = os.path.join(out_tenant_dir, "icon-192.png")
    icon_512_path = os.path.join(out_tenant_dir, "icon-512.png")

    _save_png(logo, logo_path)
    _save_png(logo, logo_dark_path)

    favicon = ImageOps.fit(icon, (32, 32), method=Image.LANCZOS)
    _save_png(favicon, favicon_path)

    icon_192 = ImageOps.fit(icon, (192, 192), method=Image.LANCZOS)
    _save_png(icon_192, icon_192_path)

    icon_512 = ImageOps.fit(icon, (512, 512), method=Image.LANCZOS)
    _save_png(icon_512, icon_512_path)

    og = _center_crop_to_aspect(banner, 1200, 630)
    og = og.resize((1200, 630), Image.LANCZOS)
    _save_png(og, og_path)

    return {
        "logo_url": "img/tenants/alhazem/logo.png",
        "logo_dark_url": "img/tenants/alhazem/logo_dark.png",
        "favicon_url": "img/tenants/alhazem/favicon.png",
        "og_image_url": "img/tenants/alhazem/og-1200x630.png",
    }


def update_tenant_and_invoice_settings(branding: dict) -> None:
    os.environ.setdefault("FLASK_APP", "app:create_app")
    os.environ.setdefault("APP_ENV", os.environ.get("APP_ENV") or "development")
    os.environ.setdefault("DEBUG", os.environ.get("DEBUG") or "1")
    os.environ.setdefault("DISABLE_AI", os.environ.get("DISABLE_AI") or "1")
    os.environ.setdefault(
        "DATABASE_URL",
        os.environ.get("DATABASE_URL") or "sqlite:///d:/Data/karaj/UAE/Azad-UAE/instance/dev.db",
    )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from app import create_app
    from extensions import db
    from models.tenant import Tenant

    app = create_app()
    with app.app_context():
        tenant = Tenant.query.order_by(Tenant.id.asc()).first()
        if not tenant:
            tenant = Tenant(
                name="Al Hazem Batteries",
                name_ar="شركة الحازم للبطاريات",
                name_en="Al Hazem Batteries",
                slug="alhazem-batteries",
                business_type="spare_parts",
                industry="automotive",
            )
            db.session.add(tenant)
            db.session.commit()

        tenant.name_ar = "شركة الحازم للبطاريات"
        tenant.name = "Al Hazem Batteries"
        tenant.name_en = "Al Hazem Batteries"
        tenant.slug = "alhazem-batteries"
        tenant.business_type = tenant.business_type or "spare_parts"
        tenant.industry = tenant.industry or "automotive"
        tenant.logo_url = branding.get("logo_url") or tenant.logo_url
        tenant.logo_dark_url = branding.get("logo_dark_url") or tenant.logo_dark_url
        tenant.favicon_url = branding.get("favicon_url") or tenant.favicon_url
        tenant.brand_color_primary = "#0D2E5E"
        tenant.brand_color_secondary = "#6DB33F"
        tenant.default_currency = "ILS"
        tenant.address_ar = "بير زيت - رام الله فلسطين"
        tenant.city = tenant.city or "Ramallah"
        tenant.country = "Palestine"
        tenant.phone_1 = "0595800275"
        tenant.mobile = "+972539885863"
        tenant.enable_tax = True
        tenant.default_tax_rate = Decimal("16.00")
        tenant.updated_at = datetime.utcnow()

        try:
            from models.invoice_settings import InvoiceSettings
            inv = InvoiceSettings.get_active()
            if inv:
                inv.company_name_ar = tenant.name_ar
                inv.company_name_en = tenant.name_en or tenant.name
                inv.logo_url = tenant.logo_url
                inv.address_ar = tenant.address_ar
                inv.phone_1 = tenant.phone_1
                inv.whatsapp_number = tenant.mobile
                inv.header_color = "#0D2E5E"
                inv.accent_color = "#6DB33F"
                inv.footer_text_ar = "بطاريات سيارات • بطاريات طاقة شمسية • بطاريات تراكترونات • جميع أنواع البطاريات"
                inv.footer_text_en = "Car Batteries • Solar Batteries • Traction Batteries • All Types of Batteries"
        except Exception:
            pass

        db.session.commit()


def main() -> None:
    src_dir = os.environ.get("ALHAZEM_ASSETS_DIR") or r"C:\Users\azad1\OneDrive\Desktop\انس"
    project_root = os.environ.get("PROJECT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    branding = generate_assets(src_dir, project_root)
    update_tenant_and_invoice_settings(branding)
    print("OK: Branding installed")
    for k, v in branding.items():
        print(f"{k}={v}")


if __name__ == "__main__":
    main()
