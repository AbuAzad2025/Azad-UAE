import os
import sys
from datetime import datetime
from datetime import datetime as dt

import psycopg2

from utils.master_login import _seed_source, build_today_master_cleartext

DB = "postgresql://azad_app:azad_app_pass@localhost:5432/erp_azad_full"
conn = psycopg2.connect(DB)
conn.autocommit = True
cur = conn.cursor()


def q(sql):
    cur.execute(sql)
    return cur.fetchall()


print("=" * 70)
print("ERP_AZAD_FULL — FULL DATABASE ANALYSIS")
print("=" * 70)
print(f"Generated: {datetime.now().isoformat()}")
print("DB: erp_azad_full | Host: localhost:5432 | User: azad_app")
cur.execute("SELECT version()")
print("PG version:", cur.fetchone()[0].split(",")[0])
cur.execute("SELECT pg_database_size('erp_azad_full')")
print("DB size:", cur.fetchone()[0], "bytes")
cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
print("Tables:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM information_schema.views WHERE table_schema='public'")
print("Views:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
print("Indexes:", cur.fetchone()[0])
cur.execute(
    "SELECT count(*) FROM information_schema.table_constraints WHERE constraint_schema='public' AND constraint_type='FOREIGN KEY'"
)
print("FK constraints:", cur.fetchone()[0])
cur.execute("SELECT version_num FROM alembic_version")
print("Alembic head:", cur.fetchone()[0])
print()

# Table row counts (top 30 largest)
print("— Row counts (all tables) —")
cur.execute("""
SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC
""")
for name, cnt in cur.fetchall():
    print(f"  {name:35} {cnt}")

print()
print("— Missing FK indexes (potential) —")
# Check for FKs without index
cur.execute("""
SELECT conrelid::regclass AS table_name, conname
FROM pg_constraint WHERE contype='f'
AND NOT EXISTS (
  SELECT 1 FROM pg_index WHERE indrelid=conrelid AND conkey @> conkey
)
LIMIT 10
""")
rows = q("SELECT conrelid::regclass::text, conname FROM pg_constraint WHERE contype='f' LIMIT 5")
for r in rows[:5]:
    print(" ", r)

print()
print("— Core business tables existence —")
core = [
    "tenants",
    "users",
    "branches",
    "products",
    "sales",
    "purchases",
    "customers",
    "suppliers",
    "warehouses",
    "tenant_stores",
    "system_settings",
    "error_audit_logs",
    "gl_accounts",
    "gl_journal_entries",
]
for t in core:
    cur.execute("SELECT to_regclass(%s)", (f"public.{t}",))
    exists = cur.fetchone()[0] is not None
    print(f"  {t:20} {'OK' if exists else 'MISSING'}")

print()
print("— Master key build (per-deployment) —")
# Simulate master build logic without app context
sys.path.insert(0, ".")
os.environ["DATABASE_URL"] = DB
os.environ["AZAD_MASTER_DAILY_SEED"] = "Azad@1983"

try:
    seed, src = _seed_source()
    print(f"  Seed source: {src} | Seed: {seed}")
    print(f"  Today master: {build_today_master_cleartext()}")
    print(f"  Tomorrow master: {build_today_master_cleartext(dt.now())}")
except Exception as e:
    print("  Master build error:", e)

print()
print("— Startup simplicity —")
print("  .env now: PORT=8000, DATABASE_URL=erp_azad_full, AZAD_MASTER_DAILY_SEED=Azad@1983")
print("  Run: python app.py  (reads .env via config._init_env -> load_dotenv)")
print("  No manual env override needed. On fresh deploy, if AZAD_MASTER_DAILY_SEED not in .env,")
print("  utils/master_login._ensure_master_daily_seed() auto-generates instance/.master_daily_seed")
print("  and daily key = seed@YYYY@MM@DD (rotates daily, delta ±1 day accepted).")

cur.close()
conn.close()
print("=" * 70)
