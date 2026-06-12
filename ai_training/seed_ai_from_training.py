"""Seed AI tables from organized training data files.

Reads ai_training/GLOBAL/<type>/*.json and ai_training/<tenant_slug>/<type>/*.json
Safe to run multiple times — uses upsert logic.

Usage:
    python ai_training/seed_ai_from_training.py
"""
import os
import sys
import json
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "DATABASE_URL" not in os.environ:
    print("ERROR: DATABASE_URL environment variable is not set.")
    print("Usage: set DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname")
    sys.exit(1)
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from app import create_app
from extensions import db
from sqlalchemy import text

TRAINING_DIR = os.path.dirname(os.path.abspath(__file__))

# Tenant slug -> tenant_id cache (filled at runtime)
TENANT_CACHE = {}


def _get_tenant_id(conn, slug):
    """Resolve tenant slug to ID, caching results."""
    if slug == "GLOBAL":
        return None
    if slug in TENANT_CACHE:
        return TENANT_CACHE[slug]
    row = conn.execute(
        text("SELECT id FROM tenants WHERE slug = :slug AND is_active = true"),
        {"slug": slug}
    ).fetchone()
    tid = row[0] if row else None
    TENANT_CACHE[slug] = tid
    return tid


def _list_json_files(subpath):
    """List all JSON files under a training subfolder."""
    full = os.path.join(TRAINING_DIR, subpath)
    if not os.path.isdir(full):
        return []
    return sorted(glob.glob(os.path.join(full, "**", "*.json"), recursive=True))


def seed_memories(conn):
    """Seed ai_memories from GLOBAL/memories and <tenant>/memories."""
    files = _list_json_files("GLOBAL/memories") + _list_json_files("*/memories")
    count = 0
    for path in files:
        rel = os.path.relpath(path, TRAINING_DIR)
        parts = rel.split(os.sep)
        tenant_slug = parts[0]
        tenant_id = _get_tenant_id(conn, tenant_slug)

        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"  ⚠️ Skipping invalid JSON: {rel}")
                continue

        # learned_knowledge.json has dict with keys
        if isinstance(data, dict):
            items = []
            for key, value in data.items():
                if isinstance(value, (list, dict)) and len(value) == 0:
                    continue
                value_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
                items.append((key, value_str))
        elif isinstance(data, list):
            items = [(it.get("key", f"item_{i}"), json.dumps(it, ensure_ascii=False)) for i, it in enumerate(data)]
        else:
            continue

        for key, value in items:
            existing = conn.execute(
                text("SELECT id FROM ai_memories WHERE key = :key AND (tenant_id IS NOT DISTINCT FROM :tid)"),
                {"key": key, "tid": tenant_id}
            ).fetchone()
            if existing:
                continue
            conn.execute(
                text("""
                    INSERT INTO ai_memories (tenant_id, category, key, value, confidence, source)
                    VALUES (:tid, :category, :key, :value, :confidence, :source)
                """),
                {
                    "tid": tenant_id,
                    "category": "learned",
                    "key": key,
                    "value": value,
                    "confidence": 0.85,
                    "source": rel,
                }
            )
            count += 1
    return count


def seed_interactions(conn):
    """Seed ai_interactions from GLOBAL/interactions and <tenant>/interactions."""
    files = _list_json_files("GLOBAL/interactions") + _list_json_files("*/interactions")
    count = 0
    for path in files:
        rel = os.path.relpath(path, TRAINING_DIR)
        parts = rel.split(os.sep)
        tenant_slug = parts[0]
        tenant_id = _get_tenant_id(conn, tenant_slug)

        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"  ⚠️ Skipping invalid JSON: {rel}")
                continue

        if not isinstance(data, list):
            print(f"  ⚠️ Expected list in {rel}, got {type(data).__name__}")
            continue

        for item in data[:500]:
            query = item.get("query") or item.get("question") or item.get("user_message")
            if not query:
                continue
            response = item.get("response") or item.get("answer") or ""
            existing = conn.execute(
                text("SELECT id FROM ai_interactions WHERE query = :query AND (tenant_id IS NOT DISTINCT FROM :tid) LIMIT 1"),
                {"query": query[:255], "tid": tenant_id}
            ).fetchone()
            if existing:
                continue
            conn.execute(
                text("""
                    INSERT INTO ai_interactions (tenant_id, query, response, intent, was_successful, is_training_sample)
                    VALUES (:tid, :query, :response, :intent, :success, true)
                """),
                {
                    "tid": tenant_id,
                    "query": query[:2000],
                    "response": str(response)[:4000],
                    "intent": item.get("intent", "general"),
                    "success": item.get("was_successful", True),
                }
            )
            count += 1
    return count


def seed_expertise(conn):
    """Seed ai_expertise from GLOBAL/expertise and <tenant>/expertise JSON files."""
    files = _list_json_files("GLOBAL/expertise") + _list_json_files("*/expertise")
    count = 0
    for path in files:
        rel = os.path.relpath(path, TRAINING_DIR)
        parts = rel.split(os.sep)
        tenant_slug = parts[0]
        tenant_id = _get_tenant_id(conn, tenant_slug)

        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"  ⚠️ Skipping invalid JSON: {rel}")
                continue

        areas = data.get("expertise_areas", []) if isinstance(data, dict) else data
        for area in areas:
            topic = area.get("topic", "")
            if not topic:
                continue
            existing = conn.execute(
                text("SELECT id FROM ai_expertise WHERE topic = :topic AND (tenant_id IS NOT DISTINCT FROM :tid)"),
                {"topic": topic, "tid": tenant_id}
            ).fetchone()
            if existing:
                continue
            conn.execute(
                text("""
                    INSERT INTO ai_expertise (tenant_id, domain, topic, knowledge, priority)
                    VALUES (:tid, :domain, :topic, :knowledge, :priority)
                """),
                {
                    "tid": tenant_id,
                    "domain": area.get("domain", "general"),
                    "topic": topic,
                    "knowledge": area.get("knowledge", ""),
                    "priority": area.get("priority", 5),
                }
            )
            count += 1
    return count


def seed_documents(conn):
    """Seed ai_memories from documents (treated as memories with category=document)."""
    files = _list_json_files("GLOBAL/documents") + _list_json_files("*/documents")
    count = 0
    for path in files:
        rel = os.path.relpath(path, TRAINING_DIR)
        parts = rel.split(os.sep)
        tenant_slug = parts[0]
        tenant_id = _get_tenant_id(conn, tenant_slug)

        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"  ⚠️ Skipping invalid JSON: {rel}")
                continue

        title = data.get("title", os.path.basename(path))
        sections = data.get("sections", [])
        for sec in sections:
            heading = sec.get("heading", "")
            content = sec.get("content", "")
            key = f"doc:{title}:{heading}" if heading else f"doc:{title}"
            existing = conn.execute(
                text("SELECT id FROM ai_memories WHERE key = :key AND (tenant_id IS NOT DISTINCT FROM :tid)"),
                {"key": key, "tid": tenant_id}
            ).fetchone()
            if existing:
                continue
            conn.execute(
                text("""
                    INSERT INTO ai_memories (tenant_id, category, key, value, confidence, source)
                    VALUES (:tid, 'document', :key, :value, 0.90, :source)
                """),
                {
                    "tid": tenant_id,
                    "key": key,
                    "value": content,
                    "source": rel,
                }
            )
            count += 1
    return count


def seed_quick_learner(tenant_id: int = None):
    """Seed trainer's quick_learner from expertise files."""
    try:
        from ai_knowledge.trainer import trainer
        trainer.seed()
        files = _list_json_files("GLOBAL/expertise")
        for path in files:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            areas = data.get("expertise_areas", []) if isinstance(data, dict) else data
            for area in areas:
                topic = area.get("topic", "")
                knowledge = area.get("knowledge", "")
                if topic and knowledge:
                    trainer.learn_from_interaction(topic, knowledge, success=True, tenant_id=tenant_id)
        print(f"  Seeded quick_learner from {len(files)} expertise files")
        return True
    except Exception as e:
        print(f"  ⚠️ Quick learner seed skipped: {e}")
        return False


def main():
    print("=" * 60)
    print("  SEED AI TABLES & QUICK LEARNER")
    print("=" * 60)

    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            print("\n📌 Seeding ai_memories...")
            mem_count = seed_memories(conn)
            doc_count = seed_documents(conn)
            print(f"  Added {mem_count} memories + {doc_count} documents")

            print("\n📌 Seeding ai_interactions...")
            int_count = seed_interactions(conn)
            print(f"  Added {int_count} interactions")

            print("\n📌 Seeding ai_expertise...")
            exp_count = seed_expertise(conn)
            print(f"  Added {exp_count} expertise areas")

            conn.commit()

    print("\n📌 Seeding quick_learner (local AI)...")
    with app.app_context():
        seed_quick_learner()

    print("\n" + "=" * 60)
    print(f"  Done: {mem_count} memories, {doc_count} docs, {int_count} interactions, {exp_count} expertise")
    print("=" * 60)


if __name__ == "__main__":
    main()
