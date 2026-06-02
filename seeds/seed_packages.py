"""Seed system packages for Azad platform."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Package

app = create_app()


def seed():
    with app.app_context():
        # System Packages (not tenant-specific)
        data = [
            {
                "name_ar": "الباقة الأساسية",
                "name_en": "Basic Package",
                "slug": "basic",
                "icon": "📦",
                "price": 29.99,
                "currency": "USD",
                "description_ar": "باقة مثالية للمتاجر الصغيرة",
                "description_en": "Perfect for small businesses",
                "features": ["5 Users", "2 Branches", "Basic Reports", "Email Support"],
                "is_active": True,
                "is_featured": False,
                "sort_order": 1,
                "max_users": 5,
                "max_branches": 2,
                "has_ai": False,
                "has_whatsapp": False,
                "has_pos": True,
                "has_advanced_reports": False,
                "has_customization": False,
                "has_training": False,
                "has_priority_support": False,
            },
            {
                "name_ar": "الباقة المتقدمة",
                "name_en": "Advanced Package",
                "slug": "advanced",
                "icon": "🚀",
                "price": 79.99,
                "currency": "USD",
                "description_ar": "للشركات المتنامية",
                "description_en": "For growing companies",
                "features": ["20 Users", "5 Branches", "Advanced Reports", "Priority Support", "AI Features"],
                "is_active": True,
                "is_featured": True,
                "badge_text": "الأكثر شعبية",
                "badge_color": "success",
                "sort_order": 2,
                "max_users": 20,
                "max_branches": 5,
                "has_ai": True,
                "has_whatsapp": True,
                "has_pos": True,
                "has_advanced_reports": True,
                "has_customization": True,
                "has_training": True,
                "has_priority_support": True,
            },
            {
                "name_ar": "الباقة الاحترافية",
                "name_en": "Professional Package",
                "slug": "professional",
                "icon": "💎",
                "price": 199.99,
                "currency": "USD",
                "description_ar": "للمؤسسات الكبيرة",
                "description_en": "For large enterprises",
                "features": ["Unlimited Users", "Unlimited Branches", "Custom Reports", "24/7 Support", "Full AI Suite", "WhatsApp Integration", "Custom Development"],
                "is_active": True,
                "is_featured": False,
                "sort_order": 3,
                "max_users": None,
                "max_branches": None,
                "has_ai": True,
                "has_whatsapp": True,
                "has_pos": True,
                "has_advanced_reports": True,
                "has_customization": True,
                "has_training": True,
                "has_priority_support": True,
            },
            {
                "name_ar": "الباقة التجريبية",
                "name_en": "Trial Package",
                "slug": "trial",
                "icon": "🎁",
                "price": 0,
                "currency": "USD",
                "description_ar": "جرب النظام مجاناً",
                "description_en": "Try the system for free",
                "features": ["2 Users", "1 Branch", "Limited Reports", "Community Support"],
                "is_active": True,
                "is_featured": False,
                "badge_text": "مجاني",
                "badge_color": "info",
                "sort_order": 0,
                "max_users": 2,
                "max_branches": 1,
                "has_ai": False,
                "has_whatsapp": False,
                "has_pos": True,
                "has_advanced_reports": False,
                "has_customization": False,
                "has_training": False,
                "has_priority_support": False,
            },
        ]
        
        count = 0
        for pkg_data in data:
            if Package.query.filter_by(slug=pkg_data["slug"]).first(): continue
            p = Package(**pkg_data)
            db.session.add(p); count += 1
        db.session.commit()
        print(f"System packages added: {count}")
        print("✅ Packages seeded successfully")


if __name__ == "__main__":
    seed()
