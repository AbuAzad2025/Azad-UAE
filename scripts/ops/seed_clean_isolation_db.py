#!/usr/bin/env python3
"""Build a CLEAN 20-tenant database with realistic, varied seeds.

Every tenant has a different industry (and therefore a different GL extension),
a different country/currency/VAT jurisdiction, a different package (module
flags), a different catalogue of hundreds of real products, and a different
number and size of documents. All balances are derived from the documents and
posted through balanced GL entries, so the reconciliation gate must report zero
discrepancies.

    $env:DATABASE_URL = "postgresql+psycopg2://postgres@localhost:5433/postgres"
    python scripts/ops/seed_clean_isolation_db.py
    $env:DATABASE_URL = "postgresql+psycopg2://postgres@localhost:5433/azad_isolation_test"
    python scripts/ops/reconcile_historical_balances.py
    python scripts/ops/verify_isolation_db.py
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DB_NAME = os.environ.get("ISOLATION_DB_NAME", "azad_isolation_test")

# Realistic catalogue per industry. The names are used verbatim as products,
# with size/model variants appended to reach each tenant's target count.
CATALOG: dict[str, tuple[list[str], list[str]]] = {
    "supermarket": (
        ["Fresh Food", "Beverages", "Household", "Bakery", "Frozen"],
        [
            "Full Cream Milk",
            "Basmati Rice",
            "Orange Juice",
            "Laundry Detergent",
            "Whole Wheat Bread",
            "Cheddar Cheese",
            "Green Tea",
            "Olive Oil",
            "Pasta",
            "Greek Yoghurt",
            "Chicken Breast",
            "Potatoes",
            "Tomatoes",
            "Mineral Water",
            "Coffee Beans",
            "Butter",
            "Eggs",
            "Onions",
        ],
    ),
    "trading": (
        ["General Goods", "Electronics", "Textiles", "Hardware", "Office Supplies"],
        [
            "USB Cable",
            "LED Lamp",
            "Cotton Fabric",
            "Brass Valve",
            "Notebook",
            "Wall Charger",
            "Distribution Panel",
            "Steel Container",
            "Toolkit",
            "Copy Paper",
            "Packing Tape",
            "Safety Gloves",
            "Extension Cord",
            "Plastic Crate",
            "Cleaning Brush",
            "Label Printer",
        ],
    ),
    "construction": (
        ["Building Materials", "Steel", "Cement", "Tools", "Site Equipment"],
        [
            "Portland Cement",
            "Reinforcement Bar",
            "Hammer Drill Bit",
            "Aluminium Scaffold",
            "River Gravel",
            "Mortar Mix",
            "Tower Crane Hook",
            "Ceramic Tile",
            "PVC Pipe",
            "Safety Helmet",
            "Concrete Mixer",
            "Measuring Tape",
            "Steel Shuttering",
            "Waterproof Sealant",
            "Wheelbarrow",
            "Crowbar",
        ],
    ),
    "pharmacy": (
        ["Prescription", "Over The Counter", "Vitamins", "Medical Devices", "Personal Care"],
        [
            "Amoxicillin Tablet",
            "Paracetamol Syrup",
            "Vitamin D Capsule",
            "Hydrocortisone Ointment",
            "Insulin Injection",
            "Sterile Bandage",
            "Digital Thermometer",
            "Multivitamin",
            "Eye Drops",
            "Saline Solution",
            "Ibuprofen Tablet",
            "Cetirizine Syrup",
            "Omega 3 Capsule",
            "Blood Glucose Strip",
            "Surgical Mask",
            "Hand Sanitiser",
        ],
    ),
    "restaurant": (
        ["Beverages", "Main Dishes", "Appetizers", "Desserts", "Ingredients"],
        [
            "Arabica Coffee",
            "Mint Tea",
            "Grilled Chicken",
            "Beef Shawarma",
            "Hummus Plate",
            "Falafel Plate",
            "Baklava",
            "Cheesecake",
            "Olive Oil",
            "Basmati Rice",
            "Chicken Stock",
            "Tomato Paste",
            "Flat Bread",
            "Feta Cheese",
            "Orange Juice",
            "Mixed Spices",
        ],
    ),
    "electronics": (
        ["Computing", "Mobile", "Audio", "Components", "Accessories"],
        [
            "Laptop 14 inch",
            "Wireless Mouse",
            "Bluetooth Speaker",
            "SSD 512GB",
            "HDMI Cable",
            "USB Hub",
            "Monitor 24 inch",
            "Keyboard",
            "Power Bank",
            "Earphones",
            "Router",
            "Graphics Card",
            "RAM Module",
            "Webcam",
            "Laptop Stand",
            "Cooling Fan",
        ],
    ),
    "automotive": (
        ["Engine", "Brakes", "Electrical", "Tyres", "Maintenance"],
        [
            "Engine Oil 5W30",
            "Brake Pads",
            "Spark Plug",
            "Car Battery",
            "Tyre 205/55",
            "Air Filter",
            "Fuel Filter",
            "Wiper Blade",
            "Alternator",
            "Radiator",
            "Brake Fluid",
            "Timing Belt",
            "Headlight Bulb",
            "Wheel Bearing",
            "Coolant",
            "Car Jack",
        ],
    ),
    "engineering": (
        ["Building Works", "Steel & Structure", "MEP", "Site Equipment", "Subcontracts"],
        [
            "Ready Mix Concrete",
            "Steel Reinforcement",
            "Structural Beam",
            "HVAC Unit",
            "Electrical Panel",
            "Scaffolding Rental",
            "Excavator Hours",
            "Waterproof Membrane",
            "Concrete Pump",
            "Rebar Mesh",
            "Cable Tray",
            "Fire Alarm Panel",
            "Site Office",
            "Crane Rental Day",
            " Grout Mortar",
            "Safety Net",
        ],
    ),
    "consultancy": (
        ["Design Services", "Supervision", "Advisory", "Reports", "Approvals"],
        [
            "Architectural Design",
            "Structural Calculation",
            "MEP Design Review",
            "Site Supervision Day",
            "Feasibility Study",
            "Drawing Set",
            "Permit Processing",
            "Tender Documents",
            "Quantity Survey",
            "Geotechnical Report",
            "Energy Modelling",
            "Safety Audit",
            "Design Review Session",
            "As Built Drawings",
            "Valuation Report",
            "Expert Witness Report",
        ],
    ),
    "clothing": (
        ["Men", "Women", "Children", "Footwear", "Accessories"],
        [
            "Cotton T-Shirt",
            "Oxford Shirt",
            "Denim Jeans",
            "Winter Jacket",
            "Polo Shirt",
            "Linen Dress",
            "Skinny Jeans",
            "Blouse",
            "Kids Hoodie",
            "School Uniform",
            "Leather Shoes",
            "Sports Sneakers",
            "Wool Scarf",
            "Leather Belt",
            "Cap",
            "Socks Pack",
        ],
    ),
    "jewelry": (
        ["Gold", "Silver", "Precious Stones", "Watches", "Accessories"],
        [
            "Gold Ring 18K",
            "Silver Bracelet",
            "Diamond Pendant",
            "Gold Necklace",
            "Pearl Earrings",
            "Silver Chain",
            "Sapphire Ring",
            "Wrist Watch",
            "Gold Bangle",
            "Emerald Pendant",
            "Cufflinks",
            "Anklet",
            "Brooch",
            "Jewellery Box",
            "Silver Ring",
            "Gold Coin",
        ],
    ),
    "batteries": (
        ["Industrial", "Automotive", "Household", "Solar", "Accessories"],
        [
            "Lead Acid Battery",
            "Li-Ion Cell",
            "Car Battery 12V",
            "AA Alkaline",
            "AAA Alkaline",
            "UPS Battery",
            "Solar Panel Battery",
            "Battery Charger",
            "Terminal Cable",
            "Battery Box",
            "Gel Battery",
            "Deep Cycle Battery",
            "Button Cell",
            "Power Pack",
            "Inverter Battery",
            "Fuse Set",
        ],
    ),
    "mobile_new": (
        ["Smartphones", "Tablets", "Wearables", "Accessories", "Networking"],
        [
            "Smartphone 128GB",
            "Smartphone 256GB",
            "Tablet 10 inch",
            "Smart Watch",
            "Wireless Earbuds",
            "Phone Case",
            "Screen Protector",
            "Fast Charger",
            "USB C Cable",
            "Power Bank 20000",
            "Selfie Stick",
            "Bluetooth Headset",
            "SIM Card",
            "Mobile Router",
            "Stylus",
            "Car Mount",
        ],
    ),
    "mobile_parts": (
        ["Screens", "Batteries", "Charging", "Cameras", "Tools"],
        [
            "LCD Screen",
            "OLED Display",
            "Replacement Battery",
            "Charging Port",
            "Back Cover",
            "Front Camera",
            "Rear Camera",
            "Speaker Module",
            "Vibration Motor",
            "Flex Cable",
            "Screwdriver Set",
            "Suction Cup",
            "Heat Gun",
            "Adhesive Tape",
            "Antenna Cable",
            "SIM Tray",
        ],
    ),
    "mobile_used": (
        ["Refurbished Phones", "Refurbished Tablets", "Parts", "Accessories", "Grading"],
        [
            "Refurbished Phone A",
            "Refurbished Phone B",
            "Refurbished Tablet",
            "Used Smartphone",
            "Renewed Handset",
            "Grade A Device",
            "Grade B Device",
            "Second-hand Phone",
            "Pre-owned Tablet",
            "Replacement Screen",
            "Used Battery",
            "Refurbished Charger",
            "Case",
            "Protector",
            "Stylus",
            "Cable",
        ],
    ),
}

VARIANTS = ["Standard", "Premium", "Economy", "Pro", "Lite", "Max", "Plus", "Mini"]

# Arabic display names for the seeded catalogue. `name` stays English for
# deterministic tests while `name_ar` carries a real Arabic label — copying the
# English name into name_ar left Arabic ERP screens with no Arabic text at all.
ARABIC_NAMES: dict[str, str] = {
    "Full Cream Milk": "حليب كامل الدسم",
    "Basmati Rice": "أرز بسمتي",
    "Orange Juice": "عصير برتقال",
    "Laundry Detergent": "مسحوق غسيل",
    "Whole Wheat Bread": "خبز القمح الكامل",
    "Cheddar Cheese": "جبنة شيدر",
    "Green Tea": "شاي أخضر",
    "Olive Oil": "زيت الزيتون",
    "Pasta": "معكرونة",
    "Greek Yoghurt": "زبادي يوناني",
    "Chicken Breast": "صدور دجاج",
    "Potatoes": "بطاطس",
    "Tomatoes": "طماطم",
    "Mineral Water": "مياه معدنية",
    "Coffee Beans": "حبوب قهوة",
    "Butter": "زبدة",
    "Eggs": "بيض",
    "Onions": "بصل",
    "USB Cable": "كابل يو إس بي",
    "LED Lamp": "مصباح ليد",
    "Cotton Fabric": "قماش قطني",
    "Brass Valve": "صمام نحاسي",
    "Notebook": "دفتر ملاحظات",
    "Wall Charger": "شاحن حائط",
    "Distribution Panel": "لوحة توزيع",
    "Steel Container": "حاوية فولاذية",
    "Toolkit": "مجموعة أدوات",
    "Copy Paper": "ورق تصوير",
    "Packing Tape": "شريط تعبئة",
    "Safety Gloves": "قفازات أمان",
    "Extension Cord": "سلك تمديد",
    "Plastic Crate": "صندوق بلاستيكي",
    "Cleaning Brush": "فرشاة تنظيف",
    "Label Printer": "طابعة ملصقات",
    "Portland Cement": "أسمنت بورتلاند",
    "Reinforcement Bar": "حديد تسليح",
    "Hammer Drill Bit": "ريشة مطرقة ثاقبة",
    "Aluminium Scaffold": "سقالة ألومنيوم",
    "River Gravel": "حصى نهر",
    "Mortar Mix": "خلطة مونة",
    "Tower Crane Hook": "خطاف رافعة برجية",
    "Ceramic Tile": "بلاط سيراميك",
    "PVC Pipe": "أنبوب بي في سي",
    "Safety Helmet": "خوذة أمان",
    "Concrete Mixer": "خلاط خراسانة",
    "Measuring Tape": "شريط قياس",
    "Steel Shuttering": "قوالب فولاذية",
    "Waterproof Sealant": "مانع تسرب مائي",
    "Wheelbarrow": "عربة يدوية",
    "Crowbar": "قضبة حديدية",
    "Amoxicillin Tablet": "قرص أموكسيسيلين",
    "Paracetamol Syrup": "شراب باراسيتامول",
    "Vitamin D Capsule": "كبسولة فيتامين د",
    "Hydrocortisone Ointment": "مرهم هيدروكورتيزون",
    "Insulin Injection": "حقنة إنسولين",
    "Sterile Bandage": "ضماد معقم",
    "Digital Thermometer": "ميزان حرارة رقمي",
    "Multivitamin": "فيتامين متعدد",
    "Eye Drops": "قطرات عين",
    "Saline Solution": "محلول ملحي",
    "Ibuprofen Tablet": "قرص إيبوبروفين",
    "Cetirizine Syrup": "شراب سيتيريزين",
    "Omega 3 Capsule": "كبسولة أوميغا 3",
    "Blood Glucose Strip": "شريط قياس السكر",
    "Surgical Mask": "كمامة جراحية",
    "Hand Sanitiser": "معقم يدين",
    "Arabica Coffee": "قهوة عربية",
    "Mint Tea": "شاي بالنعناع",
    "Grilled Chicken": "دجاج مشوي",
    "Beef Shawarma": "شاورما لحم",
    "Hummus Plate": "طبق حمص",
    "Falafel Plate": "طبق فلافل",
    "Baklava": "بقلاوة",
    "Cheesecake": "كيك الجبن",
    "Chicken Stock": "مرق دجاج",
    "Tomato Paste": "معجون طماطم",
    "Flat Bread": "خبز مسطح",
    "Feta Cheese": "جبنة فيتا",
    "Mixed Spices": "بهارات مشكلة",
    "Laptop 14 inch": "لابتوب 14 بوصة",
    "Wireless Mouse": "فأرة لاسلكية",
    "Bluetooth Speaker": "مكبر صوت بلوتوث",
    "SSD 512GB": "قرص صلب 512 جيجا",
    "HDMI Cable": "كابل إتش دي إم آي",
    "USB Hub": "مركز يو إس بي",
    "Monitor 24 inch": "شاشة 24 بوصة",
    "Keyboard": "لوحة مفاتيح",
    "Power Bank": "شاحن متنقل",
    "Earphones": "سماعات أذن",
    "Router": "راوتر",
    "Graphics Card": "بطاقة رسوميات",
    "RAM Module": "وحدة ذاكرة",
    "Webcam": "كاميرا ويب",
    "Laptop Stand": "حامل لابتوب",
    "Cooling Fan": "مروحة تبريد",
    "Engine Oil 5W30": "زيت محرك 5W30",
    "Brake Pads": "فحمات فرامل",
    "Spark Plug": "شمعاة إشعال",
    "Car Battery": "بطارية سيارة",
    "Tyre 205/55": "إطار 205/55",
    "Air Filter": "فلتر هواء",
    "Fuel Filter": "فلتر وقود",
    "Wiper Blade": "ريشة مساحات",
    "Alternator": "مولد شحن",
    "Radiator": "رادياتير",
    "Brake Fluid": "سائل فرامل",
    "Timing Belt": "حزام توقيت",
    "Headlight Bulb": "لمبة مصابيح أمامية",
    "Wheel Bearing": "محمل عجلة",
    "Coolant": "سائل تبريد",
    "Car Jack": "رافعة سيارة",
    "Ready Mix Concrete": "خراسانة جاهزة",
    "Steel Reinforcement": "حديد تسليح",
    "Structural Beam": "عارضة إنشائية",
    "HVAC Unit": "وحدة تكييف مركزية",
    "Electrical Panel": "لوحة كهربائية",
    "Scaffolding Rental": "إيجار سقالات",
    "Excavator Hours": "ساعات حفر",
    "Waterproof Membrane": "غشاء عازل للماء",
    "Concrete Pump": "مضخة خراسانة",
    "Rebar Mesh": "شبكة حديد",
    "Cable Tray": "صينية كابلات",
    "Fire Alarm Panel": "لوحة إنذار حريق",
    "Site Office": "مكتب موقع",
    "Crane Rental Day": "إيجار رافعة يومي",
    " Grout Mortar": "مونة ملاط",
    "Safety Net": "شبكة أمان",
    "Architectural Design": "تصميم معماري",
    "Structural Calculation": "حساب إنشائي",
    "MEP Design Review": "مراجعة تصميم ميكانيكا وكهرباء",
    "Site Supervision Day": "يوم إشراف موقع",
    "Feasibility Study": "دراسة جدوى",
    "Drawing Set": "مجموعة مخططات",
    "Permit Processing": "إتمام التصاريح",
    "Tender Documents": "وثائق مناقصة",
    "Quantity Survey": "مساحة كميات",
    "Geotechnical Report": "تقرير جيوتقني",
    "Energy Modelling": "نمذجة طاقة",
    "Safety Audit": "تدقيق سلامة",
    "Design Review Session": "جلسة مراجعة تصميم",
    "As Built Drawings": "مخططات كما بُنيت",
    "Valuation Report": "تقرير تقييم",
    "Expert Witness Report": "تقرير خبير",
    "Cotton T-Shirt": "تيشيرت قطني",
    "Oxford Shirt": "قميص أوكسفورد",
    "Denim Jeans": "بنطال جينز",
    "Winter Jacket": "جاكت شتوي",
    "Polo Shirt": "قميص بولو",
    "Linen Dress": "فستان كتان",
    "Skinny Jeans": "جينز ضيق",
    "Blouse": "بلوزة",
    "Kids Hoodie": "هودي أطفال",
    "School Uniform": "زي مدرسي",
    "Leather Shoes": "حذاء جلد",
    "Sports Sneakers": "حذاء رياضي",
    "Wool Scarf": "وشاح صوف",
    "Leather Belt": "حزام جلد",
    "Cap": "قبعة",
    "Socks Pack": "علبة جوارب",
    "Gold Ring 18K": "خاتم ذهب 18 قيراط",
    "Silver Bracelet": "سوار فضة",
    "Diamond Pendant": "قلادة ألماس",
    "Gold Necklace": "قلادة ذهب",
    "Pearl Earrings": "أقراط لؤلؤ",
    "Silver Chain": "سلسلة فضة",
    "Sapphire Ring": "خاتم ياقوت أزرق",
    "Wrist Watch": "ساعة يد",
    "Gold Bangle": "سوار ذهب",
    "Emerald Pendant": "قلادة زمرد",
    "Cufflinks": "أزرار أكمام",
    "Anklet": "خلخال",
    "Brooch": "دبوس صدر",
    "Jewellery Box": "علبة مجوهرات",
    "Silver Ring": "خاتم فضة",
    "Gold Coin": "عملة ذهب",
    "Lead Acid Battery": "بطارية حمض الرصاص",
    "Li-Ion Cell": "خلية ليثيوم أيون",
    "Car Battery 12V": "بطارية سيارة 12 فولت",
    "AA Alkaline": "بطارية AA قلوية",
    "AAA Alkaline": "بطارية AAA قلوية",
    "UPS Battery": "بطارية يو بي إس",
    "Solar Panel Battery": "بطارية لوحة شمسية",
    "Battery Charger": "شاحن بطاريات",
    "Terminal Cable": "كابل أطراف",
    "Battery Box": "صندوق بطارية",
    "Gel Battery": "بطارية جل",
    "Deep Cycle Battery": "بطارية دورة عميقة",
    "Button Cell": "بطارية زر",
    "Power Pack": "حزمة طاقة",
    "Inverter Battery": "بطارية إنفرتر",
    "Fuse Set": "مجموعة فيوزات",
    "Smartphone 128GB": "هاتف ذكي 128 جيجا",
    "Smartphone 256GB": "هاتف ذكي 256 جيجا",
    "Tablet 10 inch": "جهاز لوحي 10 بوصات",
    "Smart Watch": "ساعة ذكية",
    "Wireless Earbuds": "سماعات لاسلكية",
    "Phone Case": "غطاء هاتف",
    "Screen Protector": "واقي شاشة",
    "Fast Charger": "شاحن سريع",
    "USB C Cable": "كابل يو إس بي سي",
    "Power Bank 20000": "شاحن متنقل 20000",
    "Selfie Stick": "عصا سيلفي",
    "Bluetooth Headset": "سماعة بلوتوث",
    "SIM Card": "بطاقة سيم",
    "Mobile Router": "راوتر جوال",
    "Stylus": "قلم لمس",
    "Car Mount": "حامل سيارة",
    "LCD Screen": "شاشة إل سي دي",
    "OLED Display": "شاشة أوليد",
    "Replacement Battery": "بطارية بديلة",
    "Charging Port": "منفذ شحن",
    "Back Cover": "غطاء خلفي",
    "Front Camera": "كاميرا أمامية",
    "Rear Camera": "كاميرا خلفية",
    "Speaker Module": "وحدة سماعة",
    "Vibration Motor": "محرك اهتزاز",
    "Flex Cable": "كابل مرن",
    "Screwdriver Set": "مجموعة مفكات",
    "Suction Cup": "كوب شفط",
    "Heat Gun": "مسدس حراري",
    "Adhesive Tape": "شريط لاصق",
    "Antenna Cable": "كابل هوائي",
    "SIM Tray": "درج سيم",
    "Refurbished Phone A": "هاتف مجدد أ",
    "Refurbished Phone B": "هاتف مجدد ب",
    "Refurbished Tablet": "جهاز لوحي مجدد",
    "Used Smartphone": "هاتف ذكي مستعمل",
    "Renewed Handset": "هاتف مجدد",
    "Grade A Device": "جهاز درجة أ",
    "Grade B Device": "جهاز درجة ب",
    "Second-hand Phone": "هاتف مستعمل",
    "Pre-owned Tablet": "جهاز لوحي مستعمل",
    "Replacement Screen": "شاشة بديلة",
    "Used Battery": "بطارية مستعملة",
    "Refurbished Charger": "شاحن مجدد",
    "Case": "غطاء",
    "Protector": "واقي",
    "Cable": "كابل",
}

ARABIC_VARIANTS = {
    "Standard": "القياسي",
    "Premium": "المميز",
    "Economy": "الاقتصادي",
    "Pro": "الاحترافي",
    "Lite": "الخفيف",
    "Max": "ماكس",
    "Plus": "بلس",
    "Mini": "ميني",
}

# These two catalogues are service/contracting businesses; their GL chart uses
# the construction industry extension (materials, contract revenue, site cost).
CATALOG_GL_INDUSTRY = {"engineering": "construction", "consultancy": "construction"}

# slug, entity name, country, vat country, currency, vat %, industry, package,
# product count, sales, purchases, price base, store, partners, maintenance
TENANTS = [
    (
        "iso-supermarket",
        "Gulf Retail Co",
        "AE",
        "AE",
        "AED",
        5,
        "supermarket",
        "retail",
        240,
        48,
        20,
        25,
        True,
        False,
        False,
    ),
    (
        "iso-trading",
        "Levant Trading House",
        "PS",
        "PS",
        "ILS",
        16,
        "trading",
        "wholesale",
        190,
        36,
        24,
        40,
        False,
        True,
        False,
    ),
    (
        "iso-construction",
        "Najd Contracting",
        "SA",
        "SA",
        "SAR",
        15,
        "construction",
        "projects",
        165,
        30,
        28,
        150,
        False,
        False,
        True,
    ),
    (
        "iso-pharmacy",
        "Coastal Pharmacy",
        "IL",
        "IL",
        "ILS",
        18,
        "pharmacy",
        "healthcare",
        220,
        42,
        18,
        35,
        True,
        False,
        False,
    ),
    (
        "iso-restaurant",
        "Damascus Kitchen",
        "AE",
        "AE",
        "AED",
        5,
        "restaurant",
        "food_service",
        140,
        55,
        16,
        30,
        True,
        False,
        False,
    ),
    (
        "iso-electronics",
        "Nile Electronics",
        "SA",
        "SA",
        "SAR",
        15,
        "electronics",
        "electronics_retail",
        205,
        40,
        22,
        200,
        True,
        False,
        False,
    ),
    (
        "iso-automotive",
        "Gulf Auto Parts",
        "AE",
        "AE",
        "AED",
        5,
        "automotive",
        "auto_parts",
        180,
        34,
        26,
        120,
        False,
        False,
        True,
    ),
    (
        "iso-clothing",
        "Amman Fashion",
        "PS",
        "PS",
        "ILS",
        16,
        "clothing",
        "fashion",
        175,
        38,
        20,
        60,
        True,
        False,
        False,
    ),
    (
        "iso-jewelry",
        "Riyadh Jewellers",
        "SA",
        "SA",
        "SAR",
        15,
        "jewelry",
        "luxury",
        130,
        22,
        12,
        500,
        False,
        True,
        False,
    ),
    (
        "iso-batteries",
        "Power Cell Trading",
        "IL",
        "IL",
        "ILS",
        18,
        "batteries",
        "battery_distribution",
        155,
        28,
        25,
        45,
        False,
        True,
        False,
    ),
    (
        "iso-mobile-new",
        "Modern Mobile",
        "AE",
        "AE",
        "AED",
        5,
        "mobile_new",
        "telecom_retail",
        210,
        50,
        15,
        350,
        True,
        False,
        False,
    ),
    (
        "iso-mobile-parts",
        "Mobile Parts Center",
        "SA",
        "SA",
        "SAR",
        15,
        "mobile_parts",
        "telecom_repair",
        170,
        32,
        21,
        55,
        False,
        False,
        True,
    ),
    (
        "iso-mobile-used",
        "Second Life Devices",
        "IL",
        "IL",
        "ILS",
        18,
        "mobile_used",
        "refurbished",
        145,
        26,
        19,
        120,
        True,
        False,
        False,
    ),
    (
        "iso-supermarket-2",
        "Red Sea Hypermarket",
        "SA",
        "SA",
        "SAR",
        15,
        "supermarket",
        "retail_plus",
        260,
        60,
        30,
        28,
        True,
        True,
        False,
    ),
    (
        "iso-restaurant-2",
        "Catering House",
        "PS",
        "PS",
        "ILS",
        16,
        "restaurant",
        "catering",
        120,
        44,
        22,
        45,
        False,
        True,
        True,
    ),
    (
        "iso-pharmacy-2",
        "Pharmacy Plus",
        "AE",
        "AE",
        "AED",
        5,
        "pharmacy",
        "pharma_retail",
        230,
        46,
        20,
        38,
        True,
        False,
        False,
    ),
    (
        "iso-electronics-2",
        "Tech Zone",
        "IL",
        "IL",
        "ILS",
        18,
        "electronics",
        "electronics_wholesale",
        195,
        35,
        27,
        180,
        False,
        True,
        False,
    ),
    (
        "iso-trading-2",
        "Import Export Group",
        "SA",
        "SA",
        "SAR",
        15,
        "trading",
        "import_export",
        185,
        33,
        32,
        65,
        False,
        True,
        False,
    ),
    (
        "iso-construction-2",
        "Al Haram Projects",
        "AE",
        "AE",
        "AED",
        5,
        "construction",
        "contracting",
        150,
        27,
        30,
        175,
        False,
        False,
        True,
    ),
    (
        "iso-clothing-2",
        "Textile Partners",
        "PS",
        "PS",
        "ILS",
        16,
        "clothing",
        "apparel_wholesale",
        160,
        31,
        24,
        70,
        False,
        True,
        False,
    ),
    # Heavy contracting / engineering firm: works, a maintenance workshop and
    # partner joint ventures; no consumer store.
    (
        "iso-engineering",
        "Al Binaa Contracting & Engineering",
        "SA",
        "SA",
        "SAR",
        15,
        "engineering",
        "contracting_engineering",
        175,
        30,
        28,
        220,
        False,
        True,
        True,
    ),
    # Advisory consultancy: design supervision and partner fee sharing; no
    # retail store and no maintenance workshop.
    (
        "iso-consultancy",
        "Al Masharia Engineering Consultancy",
        "AE",
        "AE",
        "AED",
        5,
        "consultancy",
        "advisory_consultancy",
        140,
        26,
        12,
        320,
        False,
        True,
        False,
    ),
]


def _ins(conn, table: str, **values):
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    return conn.execute(sa.text(f"INSERT INTO {table} ({cols}) VALUES ({params}) RETURNING id"), values).scalar_one()


def _post(conn, tid: int, number: str, ref_type: str, ref_id: int, accounts: dict, lines):
    lines = [(code, Decimal(str(d)), Decimal(str(c))) for code, d, c in lines]
    dr = sum((d for _, d, _ in lines), Decimal("0"))
    cr = sum((c for _, _, c in lines), Decimal("0"))
    assert dr == cr, f"unbalanced seed entry {number}"
    eid = _ins(
        conn,
        "gl_journal_entries",
        tenant_id=tid,
        entry_number=number,
        entry_date="2026-01-15 10:00:00+00",
        description=f"Isolation seed {number}",
        reference_type=ref_type,
        reference_id=ref_id,
        currency="AED",
        exchange_rate=1,
        total_debit=dr,
        total_credit=cr,
        is_posted=True,
        is_reversed=False,
        status="posted",
        created_at="2026-01-15 10:00:00+00",
        updated_at="2026-01-15 10:00:00+00",
    )
    for code, debit, credit in lines:
        _ins(
            conn,
            "gl_journal_lines",
            tenant_id=tid,
            entry_id=eid,
            account_id=accounts[code],
            description=f"{number} {code}",
            debit=debit,
            credit=credit,
            amount=debit or credit,
            amount_aed=debit or credit,
        )


def _create_database(base_url: str) -> str:
    url = sa.engine.make_url(base_url).set(database="postgres")
    admin = sa.create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{DB_NAME}'"))
            conn.execute(sa.text(f"DROP DATABASE IF EXISTS {DB_NAME}"))
            conn.execute(sa.text(f"CREATE DATABASE {DB_NAME}"))
    finally:
        admin.dispose()
    return sa.engine.make_url(base_url).set(database=DB_NAME).render_as_string(hide_password=False)


def _upgrade(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")


def _seed_users(conn, tid: int, idx: int, branch_id: int, store: bool, maintenance: bool) -> list[str]:
    """One independent user set per tenant, limited to what its package grants."""
    from werkzeug.security import generate_password_hash

    roles = dict(conn.execute(sa.text("SELECT slug, id FROM roles")).all())
    assigned = [("manager", "Manager"), ("accountant", "Accountant"), ("seller", "Sales")]
    if store:
        assigned += [("cashier", "Cashier"), ("inventory", "Inventory")]
    if maintenance:
        assigned += [
            ("maintenance_reception", "Reception"),
            ("maintenance_engineer", "Engineer"),
            ("maintenance_cashier", "Workshop Cashier"),
        ]
    for slug, label in assigned:
        _ins(
            conn,
            "users",
            tenant_id=tid,
            username=f"iso{idx:02d}_{slug}",
            email=f"iso{idx:02d}.{slug}@example.test",
            password_hash=generate_password_hash("IsolationSeed1!"),
            full_name=f"{label} - Tenant {idx}",
            role_id=roles[slug],
            branch_id=branch_id,
            is_owner=False,
            is_active=True,
            created_at="2026-01-01 00:00:00+00",
        )
    return [slug for slug, _ in assigned]


def _seed_tenant(conn, tid: int, spec, idx: int) -> dict:
    (
        slug,
        name,
        country,
        vat_country,
        currency,
        vat,
        industry,
        package,
        product_count,
        sales_count,
        purchase_count,
        price_base,
        store,
        partners,
        maintenance,
    ) = spec

    accounts = dict(conn.execute(sa.text("SELECT code, id FROM gl_accounts WHERE tenant_id=:t"), {"t": tid}).all())
    # Branch-scoped documents and balances need an active branch. Give each
    # tenant a main branch and attach its warehouse and users to it, otherwise
    # a branchless cashier cannot open a POS session or post a sale.
    branch_id = _ins(
        conn,
        "branches",
        tenant_id=tid,
        name="Main Branch",
        code=f"BR{idx:02d}",
        is_active=True,
    )
    categories, nouns = CATALOG[industry]
    cat_ids = [
        _ins(
            conn,
            "product_categories",
            tenant_id=tid,
            name=f"{category} - {industry.title()}",
            name_ar=category,
            is_active=True,
        )
        for category in categories
    ]
    warehouse_id = _ins(
        conn,
        "warehouses",
        tenant_id=tid,
        name=f"{name} Main Warehouse",
        name_ar="المستودع الرئيسي",
        code=f"WH{idx}",
        warehouse_type="main",
        branch_id=branch_id,
        is_active=True,
        is_main=True,
    )

    product_ids: list[int] = []
    for i in range(product_count):
        base_name = nouns[i % len(nouns)]
        variant = VARIANTS[(i // len(nouns)) % len(VARIANTS)]
        cost = (Decimal(price_base) + Decimal((i * 7) % 90)).quantize(Decimal("0.001"))
        stock_qty = 20 + (i * 3) % 180
        ar_name = f"{ARABIC_NAMES.get(base_name, base_name)} {ARABIC_VARIANTS.get(variant, variant)}"
        pid = _ins(
            conn,
            "products",
            tenant_id=tid,
            name=f"{base_name} {variant}",
            name_ar=ar_name,
            sku=f"SKU-{idx:02d}-{i + 1:05d}",
            barcode=f"BAR{idx:02d}{i + 1:08d}",
            category_id=cat_ids[i % len(cat_ids)],
            cost_price=cost,
            regular_price=(cost * Decimal("1.8")).quantize(Decimal("0.001")),
            current_stock=stock_qty,
            has_serial_number=False,
            is_active=True,
            industry=industry,
            created_at="2026-01-01 00:00:00+00",
        )
        product_ids.append(pid)
        # POS/sales consume warehouse-level stock (ProductWarehouseStock), not
        # the product's aggregate current_stock. Seed the per-warehouse rows so
        # a real checkout has stock to deduct from.
        _ins(
            conn,
            "product_warehouse_stock",
            tenant_id=tid,
            product_id=pid,
            warehouse_id=warehouse_id,
            quantity=stock_qty,
        )
        # On-hand quantities are derived from StockMovement rows, not from the
        # product's aggregate field, so seed the matching opening movement.
        _ins(
            conn,
            "stock_movements",
            tenant_id=tid,
            product_id=pid,
            warehouse_id=warehouse_id,
            movement_type="adjustment",
            quantity=stock_qty,
            reference_type="seed_opening",
            reference_id=pid,
            notes="Opening stock (seed)",
            created_at="2026-01-01 00:00:00+00",
        )
    if store:
        for pid in product_ids[:50]:
            _ins(
                conn,
                "store_product_prices",
                tenant_id=tid,
                product_id=pid,
                currency_code=currency,
                price=Decimal("99.000"),
            )

    # Two customers and two suppliers per tenant, with distinct names.
    customers = [
        _ins(
            conn,
            "customers",
            tenant_id=tid,
            name=f"{name} - Client {k + 1}",
            name_ar=f"عميل {k + 1}",
            customer_type="regular",
            balance=0,
            total_purchases=0,
            is_active=True,
            created_at="2026-01-01 00:00:00+00",
            updated_at="2026-01-01 00:00:00+00",
        )
        for k in range(2)
    ]
    suppliers = [
        _ins(
            conn,
            "suppliers",
            tenant_id=tid,
            name=f"{name} - Vendor {k + 1}",
            name_ar=f"مورد {k + 1}",
            total_purchases_aed=0,
            total_paid_aed=0,
            is_active=True,
            created_at="2026-01-01 00:00:00+00",
            updated_at="2026-01-01 00:00:00+00",
        )
        for k in range(2)
    ]

    cust_totals = {c: {"sales": Decimal("0"), "in": Decimal("0")} for c in customers}
    sup_totals = {s: {"purchases": Decimal("0"), "paid": Decimal("0")} for s in suppliers}

    for s in range(sales_count):
        cust = customers[s % 2]
        amount = (Decimal(price_base) + Decimal((s * 13) % 200)).quantize(Decimal("0.001"))
        cust_totals[cust]["sales"] += amount
        sale = _ins(
            conn,
            "sales",
            tenant_id=tid,
            sale_number=f"ISO{idx:02d}-SALE-{s + 1:03d}",
            customer_id=cust,
            seller_id=1,
            sale_date="2026-01-10 10:00:00+00",
            subtotal=amount,
            discount_amount=0,
            tax_amount=0,
            total_amount=amount,
            amount=amount,
            paid_amount=amount,
            balance_due=0,
            amount_aed=amount,
            currency=currency,
            base_currency=currency,
            exchange_rate=1,
            prices_include_vat=False,
            source="manual",
            status="confirmed",
            is_active=True,
            payment_status="paid",
            created_at="2026-01-10 10:00:00+00",
        )
        for line_no in range(1 + (s % 3)):
            pid = product_ids[(s * 3 + line_no) % len(product_ids)]
            _ins(
                conn,
                "sale_lines",
                tenant_id=tid,
                sale_id=sale,
                product_id=pid,
                quantity=1,
                unit_price=amount / (1 + (s % 3)),
                discount_percent=0,
                line_total=amount / (1 + (s % 3)),
                cost_price=5,
            )
        _post(
            conn,
            tid,
            f"ISO{idx:02d}-SGL-{s + 1:03d}",
            "Sale",
            sale,
            accounts,
            [("1130", amount, 0), ("4100", 0, amount)],
        )

        # Different collection patterns per tenant/sale: cash payment, or a
        # payment plus a receipt with a different reference (no dedup clash).
        if s % 3 == 0:
            paid, receipt = (
                (amount * Decimal("0.6")).quantize(Decimal("0.001")),
                (amount * Decimal("0.4")).quantize(Decimal("0.001")),
            )
        elif s % 3 == 1:
            paid, receipt = amount, Decimal("0")
        else:
            paid, receipt = (
                (amount * Decimal("0.7")).quantize(Decimal("0.001")),
                (amount * Decimal("0.3")).quantize(Decimal("0.001")),
            )
        if paid:
            pay = _ins(
                conn,
                "payments",
                tenant_id=tid,
                payment_number=f"ISO{idx:02d}-SPAY-{s + 1:03d}",
                payment_type="sale_payment",
                direction="incoming",
                customer_id=cust,
                sale_id=sale,
                amount=paid,
                amount_aed=paid,
                currency=currency,
                base_currency=currency,
                exchange_rate=1,
                payment_method="cash",
                payment_confirmed=True,
                payment_date="2026-01-11 10:00:00+00",
                created_at="2026-01-11 10:00:00+00",
            )
            cust_totals[cust]["in"] += paid
            _post(
                conn,
                tid,
                f"ISO{idx:02d}-PGL-{s + 1:03d}",
                "Payment",
                pay,
                accounts,
                [("1111", paid, 0), ("1130", 0, paid)],
            )
        if receipt:
            rcpt = _ins(
                conn,
                "receipts",
                tenant_id=tid,
                receipt_number=f"ISO{idx:02d}-RCPT-{s + 1:03d}",
                customer_id=cust,
                sale_id=sale,
                source_type="sale",
                direction="incoming",
                amount=receipt,
                amount_aed=receipt,
                currency=currency,
                base_currency=currency,
                exchange_rate=1,
                payment_method="cash",
                payment_confirmed=True,
                receipt_date="2026-01-12 10:00:00+00",
                created_at="2026-01-12 10:00:00+00",
            )
            cust_totals[cust]["in"] += receipt
            _post(
                conn,
                tid,
                f"ISO{idx:02d}-RGL-{s + 1:03d}",
                "Receipt",
                rcpt,
                accounts,
                [("1111", receipt, 0), ("1130", 0, receipt)],
            )

    for p in range(purchase_count):
        sup = suppliers[p % 2]
        amount = (Decimal(price_base) * 2 + Decimal((p * 17) % 250)).quantize(Decimal("0.001"))
        sup_totals[sup]["purchases"] += amount
        purchase = _ins(
            conn,
            "purchases",
            tenant_id=tid,
            purchase_number=f"ISO{idx:02d}-PUR-{p + 1:03d}",
            supplier_id=sup,
            supplier_name=f"{name} - Vendor",
            purchase_date="2026-01-10 10:00:00+00",
            subtotal=amount,
            discount_amount=0,
            tax_amount=0,
            total_amount=amount,
            amount=amount,
            amount_aed=amount,
            currency=currency,
            base_currency=currency,
            exchange_rate=1,
            prices_include_vat=False,
            freight=0,
            insurance=0,
            customs_duty=0,
            other_landed_cost=0,
            user_id=1,
            status="confirmed",
            created_at="2026-01-10 10:00:00+00",
        )
        _post(
            conn,
            tid,
            f"ISO{idx:02d}-PUGL-{p + 1:03d}",
            "Purchase",
            purchase,
            accounts,
            [("5100", amount, 0), ("2110", 0, amount)],
        )
        pay = _ins(
            conn,
            "payments",
            tenant_id=tid,
            payment_number=f"ISO{idx:02d}-PAY-{p + 1:03d}",
            payment_type="supplier_payment",
            direction="outgoing",
            supplier_id=sup,
            purchase_id=purchase,
            amount=amount,
            amount_aed=amount,
            currency=currency,
            base_currency=currency,
            exchange_rate=1,
            payment_method="cash",
            payment_confirmed=True,
            payment_date="2026-01-12 10:00:00+00",
            created_at="2026-01-12 10:00:00+00",
        )
        sup_totals[sup]["paid"] += amount
        _post(
            conn,
            tid,
            f"ISO{idx:02d}-SPGL-{p + 1:03d}",
            "Payment",
            pay,
            accounts,
            [("2110", amount, 0), ("1111", 0, amount)],
        )

    maint_count = 0
    if maintenance:
        maint_count = 3 + idx % 4
        maint_cust = customers[0]
        for m in range(maint_count):
            amount = (Decimal(price_base) * 3 + Decimal(m * 25)).quantize(Decimal("0.001"))
            order = _ins(
                conn,
                "maintenance_orders",
                tenant_id=tid,
                order_number=f"ISO{idx:02d}-MORD-{m + 1:03d}",
                order_date="2026-01-13 10:00:00+00",
                customer_id=maint_cust,
                subtotal=amount,
                discount_line_total=0,
                discount_total_percent=0,
                discount_total_value=0,
                tax_rate=0,
                tax_amount=0,
                taxable_amount=amount,
                total_amount=amount,
                amount=amount,
                paid_amount=amount,
                balance_due=0,
                deposit_amount=0,
                refunded_amount=0,
                amount_aed=amount,
                paid_amount_aed=amount,
                balance_due_aed=0,
                currency=currency,
                exchange_rate=1,
                base_currency=currency,
                prices_include_vat=False,
                received_by=1,
                status="closed",
                priority="normal",
                warranty_status="unknown",
                warranty_checked=False,
                color_tag="#10b981",
                customer_signature=False,
                is_archived=False,
                created_at="2026-01-13 10:00:00+00",
                updated_at="2026-01-13 10:00:00+00",
            )
            invoice = _ins(
                conn,
                "maintenance_invoices",
                tenant_id=tid,
                order_id=order,
                invoice_number=f"ISO{idx:02d}-MINV-{m + 1:03d}",
                invoice_date="2026-01-13 10:00:00+00",
                subtotal=amount,
                discount_total_percent=0,
                discount_total_value=0,
                tax_rate=0,
                tax_amount=0,
                taxable_amount=amount,
                total_amount=amount,
                amount=amount,
                paid_amount=amount,
                balance_due=0,
                amount_aed=amount,
                paid_amount_aed=amount,
                balance_due_aed=0,
                currency=currency,
                exchange_rate=1,
                base_currency=currency,
                prices_include_vat=False,
                posted=True,
                gl_posted=True,
                is_archived=False,
                created_at="2026-01-13 10:00:00+00",
            )
            receipt = _ins(
                conn,
                "maintenance_receipts",
                tenant_id=tid,
                order_id=order,
                receipt_number=f"ISO{idx:02d}-MRCPT-{m + 1:03d}",
                receipt_date="2026-01-14 10:00:00+00",
                amount=amount,
                payment_mode="cash",
                cashier_id=1,
                is_deposit=False,
                is_refund=False,
                gl_posted=True,
                is_archived=False,
                created_at="2026-01-14 10:00:00+00",
            )
            _post(
                conn,
                tid,
                f"ISO{idx:02d}-MINVGL-{m + 1:03d}",
                "MaintenanceInvoice",
                invoice,
                accounts,
                [("1134", amount, 0), ("4119", 0, amount)],
            )
            _post(
                conn,
                tid,
                f"ISO{idx:02d}-MRGL-{m + 1:03d}",
                "MaintenanceReceipt",
                receipt,
                accounts,
                [("1111", amount, 0), ("1134", 0, amount)],
            )

    partner_count = 0
    if partners:
        partner_count = 2 + idx % 3
        partner = _ins(
            conn,
            "partners",
            tenant_id=tid,
            name=f"{name} Partner",
            code=f"ISO{idx:02d}-PARTNER",
            partner_type="investor",
            scope_type="company",
            current_balance=0,
            is_active=True,
            created_at="2026-01-01 00:00:00+00",
        )
        partner_balance = Decimal("0")
        for k in range(partner_count):
            amount = (Decimal(price_base) + Decimal(k * 30)).quantize(Decimal("0.001"))
            partner_balance += amount
            txn = _ins(
                conn,
                "partner_transactions",
                tenant_id=tid,
                partner_id=partner,
                transaction_type="additional_investment",
                amount=amount,
                amount_base=amount,
                balance_after=partner_balance,
                currency=currency,
                exchange_rate=1,
                transaction_date="2026-01-15",
            )
            _post(
                conn,
                tid,
                f"ISO{idx:02d}-PTGL-{k + 1:03d}",
                "PartnerTransaction",
                txn,
                accounts,
                [("1111", amount, 0), ("2150", 0, amount)],
            )
        conn.execute(
            sa.text("UPDATE partners SET current_balance=:b WHERE id=:i"), {"b": partner_balance, "i": partner}
        )

    for cid, totals in cust_totals.items():
        conn.execute(
            sa.text("UPDATE customers SET balance=:b, total_purchases=:p WHERE id=:i"),
            {"b": -(totals["sales"] - totals["in"]), "p": totals["sales"], "i": cid},
        )
    for sid, totals in sup_totals.items():
        conn.execute(
            sa.text("UPDATE suppliers SET total_purchases_aed=:p, total_paid_aed=:d WHERE id=:i"),
            {"p": totals["purchases"], "d": totals["paid"], "i": sid},
        )

    user_roles = _seed_users(conn, tid, idx, branch_id, store, maintenance)

    # The POS order-type settings page is otherwise empty and boot reports
    # "UNDER-SEEDED pos_order_types". Use the model's canonical defaults so the
    # seed cannot drift from what a freshly provisioned tenant gets.
    from models.pos_order_type import DEFAULT_POS_ORDER_TYPES

    for code, name_ar, name_en, is_default, sort_order, kds_enabled in DEFAULT_POS_ORDER_TYPES:
        _ins(
            conn,
            "pos_order_types",
            tenant_id=tid,
            code=code,
            name_ar=name_ar,
            name_en=name_en,
            is_active=True,
            is_default=is_default,
            sort_order=sort_order,
            kds_enabled=kds_enabled,
        )

    return {
        "tenant": tid,
        "slug": slug,
        "industry": industry,
        "package": package,
        "accounts": len(accounts),
        "products": len(product_ids),
        "sales": sales_count,
        "purchases": purchase_count,
        "maintenance": maint_count,
        "partner_txns": partner_count,
        "users": len(user_roles),
        "user_roles": user_roles,
    }


def main() -> int:
    base_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not base_url:
        raise SystemExit("DATABASE_URL (server connection) is required")
    db_url = _create_database(base_url)
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"
    os.environ.setdefault("OWNER_PASSWORD", "IsolationSeedOwner1!")

    from app import create_app

    app = create_app()
    with app.app_context():
        _upgrade(db_url)
        from utils.system_init import ensure_system_integrity

        ensure_system_integrity(app)

        from models import Tenant
        from services.gl_service import GLService

        engine = sa.create_engine(db_url)
        summaries = []
        with Session(engine) as session:
            for idx, spec in enumerate(TENANTS, 1):
                (
                    slug,
                    name,
                    country,
                    vat_country,
                    currency,
                    vat,
                    industry,
                    package,
                    product_count,
                    sales_count,
                    purchase_count,
                    price_base,
                    store,
                    partners,
                    maintenance,
                ) = spec
                tenant = Tenant(
                    name=name,
                    name_ar=name,
                    slug=slug,
                    country=country,
                    vat_country=vat_country,
                    base_currency=currency,
                    default_currency=currency,
                    default_tax_rate=vat,
                    prices_include_vat=False,
                    business_type=CATALOG_GL_INDUSTRY.get(industry, industry),
                    enable_tax=True,
                    enable_store=store,
                    enable_partners=partners,
                    enable_maintenance=maintenance,
                    is_active=True,
                )
                from extensions import db as flask_db

                flask_db.session.add(tenant)
                flask_db.session.flush()
                GLService.ensure_core_accounts(tenant_id=tenant.id)
                flask_db.session.flush()
                summaries.append(_seed_tenant(session.connection(), tenant.id, spec, idx))
                session.commit()
        engine.dispose()

    print(f"Clean 20-tenant database built: {db_url}")
    for s in summaries:
        print(
            f"  {s['tenant']:>2} {s['slug']:<20} {s['industry']:<14} {s['package']:<20} "
            f"acct={s['accounts']:>3} prod={s['products']:>3} sale={s['sales']:>2} "
            f"pur={s['purchases']:>2} maint={s['maintenance']} partner={s['partner_txns']} "
            f"users={s['users']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
