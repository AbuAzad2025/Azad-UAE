"""Seed AI tables from training data files.

Reads ai_training/*.json files and populates ai_memories, ai_interactions, ai_expertise.
Safe to run multiple times — uses upsert logic.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae")
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from app import create_app
from extensions import db
from sqlalchemy import text

TRAINING_DIR = os.path.dirname(os.path.abspath(__file__))


def seed_memories(conn):
    path = os.path.join(TRAINING_DIR, "learned_knowledge_seed.json")
    if not os.path.exists(path):
        print("  No learned_knowledge_seed.json found")
        return 0

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for key, value in data.items():
        if isinstance(value, (list, dict)) and len(value) == 0:
            continue
        value_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
        # Upsert: skip if key already exists
        existing = conn.execute(
            text("SELECT id FROM ai_memories WHERE key = :key"),
            {"key": key}
        ).fetchone()
        if existing:
            continue
        conn.execute(
            text("""
                INSERT INTO ai_memories (category, key, value, confidence, source)
                VALUES (:category, :key, :value, :confidence, :source)
            """),
            {
                "category": "learned",
                "key": key,
                "value": value_str,
                "confidence": 0.85,
                "source": "learned_knowledge_seed.json",
            }
        )
        count += 1
    return count


def seed_interactions(conn):
    path = os.path.join(TRAINING_DIR, "interactions_log_seed.json")
    if not os.path.exists(path):
        print("  No interactions_log_seed.json found")
        return 0

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("  interactions_log_seed.json is not a list")
        return 0

    count = 0
    for item in data[:500]:  # Cap at 500 to avoid bloat
        query = item.get("query") or item.get("question") or item.get("user_message")
        if not query:
            continue
        response = item.get("response") or item.get("answer") or ""
        # Skip duplicates
        existing = conn.execute(
            text("SELECT id FROM ai_interactions WHERE query = :query LIMIT 1"),
            {"query": query[:255]}
        ).fetchone()
        if existing:
            continue
        conn.execute(
            text("""
                INSERT INTO ai_interactions (query, response, intent, was_successful, is_training_sample)
                VALUES (:query, :response, :intent, :success, true)
            """),
            {
                "query": query[:2000],
                "response": str(response)[:4000],
                "intent": item.get("intent", "general"),
                "success": item.get("was_successful", True),
            }
        )
        count += 1
    return count


def seed_expertise(conn):
    """Seed automotive / accounting expertise from existing knowledge base."""
    expertise_areas = [
        {
            "domain": "accounting",
            "topic": "المحاسبة العامة",
            "knowledge": "المحاسبة العامة تشمل: القيود اليومية، دفتر الأستاذ، ميزان المراجعة، القوائم المالية. النظام يدعم العملة المتعددة والفروع."
        },
        {
            "domain": "accounting",
            "topic": "المخزون",
            "knowledge": "إدارة المخزون: إضافة منتجات، تتبع الكميات، تنبيهات نقص المخزون، حركات المستودعات، الجرد الدوري."
        },
        {
            "domain": "sales",
            "topic": "المبيعات",
            "knowledge": "المبيعات: إنشاء فواتير، خصومات، ضريبة القيمة المضافة، الدفع الجزئي، إيصالات القبض، المرتجعات."
        },
        {
            "domain": "purchases",
            "topic": "المشتريات",
            "knowledge": "المشتريات: أوامر الشراء، فواتير الموردين، الدفعات، حسابات الموردين، المرتجعات."
        },
        {
            "domain": "payroll",
            "topic": "الرواتب",
            "knowledge": "الرواتب: الموظفون، الرواتب الشهرية، السلف، الحضور والانصراف، التأمينات الاجتماعية."
        },
        {
            "domain": "reports",
            "topic": "التقارير",
            "knowledge": "التقارير: تقارير المبيعات، تقارير المخزون، التقارير المالية، التقارير الضريبية، التصدير إلى Excel/PDF."
        },
        {
            "domain": "automotive",
            "topic": "السيارات",
            "knowledge": "السيارات: فحص السيارات، تشخيص الأعطال، قطع الغيار، الصيانة الدورية، ضمانات."
        },
        {
            "domain": "system",
            "topic": "استخدام النظام",
            "knowledge": "استخدام النظام: تسجيل الدخول، لوحة التحكم، إدارة المستخدمين، الفروع، التينانتس، النسخ الاحتياطي."
        },
    ]

    count = 0
    for area in expertise_areas:
        existing = conn.execute(
            text("SELECT id FROM ai_expertise WHERE topic = :topic"),
            {"topic": area["topic"]}
        ).fetchone()
        if existing:
            continue
        conn.execute(
            text("""
                INSERT INTO ai_expertise (domain, topic, knowledge, priority)
                VALUES (:domain, :topic, :knowledge, :priority)
            """),
            {
                "domain": area["domain"],
                "topic": area["topic"],
                "knowledge": area["knowledge"],
                "priority": 5,
            }
        )
        count += 1
    return count


def main():
    print("=" * 60)
    print("  SEED AI TABLES FROM TRAINING DATA")
    print("=" * 60)

    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            print("\n📌 Seeding ai_memories...")
            mem_count = seed_memories(conn)
            print(f"  Added {mem_count} memories")

            print("\n📌 Seeding ai_interactions...")
            int_count = seed_interactions(conn)
            print(f"  Added {int_count} interactions")

            print("\n📌 Seeding ai_expertise...")
            exp_count = seed_expertise(conn)
            print(f"  Added {exp_count} expertise areas")

            conn.commit()

    print("\n" + "=" * 60)
    print(f"  Done: {mem_count} memories, {int_count} interactions, {exp_count} expertise")
    print("=" * 60)


if __name__ == "__main__":
    main()
