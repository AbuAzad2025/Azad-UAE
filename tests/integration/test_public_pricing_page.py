"""Public Arabic pricing page must stay database-driven and RTL.

`templates/public/pricing.html` was once truncated to a 7-line banner stub that
still satisfied the store-banner test while silently dropping the whole pricing
catalogue. These tests pin the behaviour the route contract promises: the page
renders `Package` rows from the database, falls back to the static tiers when the
catalogue is empty, and always carries the store banner + brand stylesheet.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch


def _package(**overrides):
    data = {
        "name_ar": "الباقة الاحترافية",
        "name_en": "Professional Plan",
        "icon": "🚀",
        "price": Decimal("79.000"),
        "currency": "AED",
        "description_ar": "للشركات النامية",
        "description_en": "For growing businesses",
        "features": ["وحدة مخصصة"],
        "max_users": 10,
        "max_branches": -1,
        "has_pos": True,
        "has_ai": True,
        "has_whatsapp": False,
        "has_advanced_reports": True,
        "has_customization": False,
        "has_training": True,
        "has_priority_support": False,
        "is_featured": True,
        "badge_text": "الأكثر طلباً",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_pricing_arabic_renders_db_package(client):
    pkg = _package()
    with patch("routes.public._public_packages", return_value=[pkg]):
        resp = client.get("/pricing")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")

    assert 'dir="rtl"' in html
    assert "الباقة الاحترافية" in html
    assert "AED" in html and "79" in html
    assert "نقاط بيع (POS)" in html
    assert "ميزات مدعومة بالذكاء الاصطناعي" in html
    assert "تقارير متقدمة" in html
    assert "تدريب ذكي" in html
    assert "وحدة مخصصة" in html
    assert "غير محدود" in html  # max_branches = -1
    assert "تكامل واتساب" not in html  # has_whatsapp = False
    assert "brand.css" in html
    assert "azad-stores-banner" in html


def test_pricing_arabic_falls_back_to_static_tiers(client):
    with patch("routes.public._public_packages", return_value=[]):
        resp = client.get("/pricing")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")

    assert "البداية" in html
    assert "الاحترافية" in html
    assert "المؤسسات" in html
    assert "اشترك الآن" in html


def test_pricing_arabic_hides_disabled_features(client):
    pkg = _package(has_pos=False, has_ai=False, has_advanced_reports=False, has_training=False)
    with patch("routes.public._public_packages", return_value=[pkg]):
        resp = client.get("/pricing")
    html = resp.data.decode("utf-8")
    assert resp.status_code == 200
    assert "نقاط بيع (POS)" not in html
    assert "تقارير متقدمة" not in html
    assert "تدريب ذكي" not in html


def test_pricing_whatsapp_link_uses_plan_name(client):
    pkg = _package()
    with patch("routes.public._public_packages", return_value=[pkg]):
        resp = client.get("/pricing")
    html = resp.data.decode("utf-8")
    assert "%D8%A7%D9%84%D8%A8%D8%A7%D9%82%D8%A9" in html  # urlencoded Arabic plan name
    assert "api.whatsapp.com/send?phone=" in html
