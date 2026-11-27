#!/usr/bin/env python3
"""Inspect the local test database (credentials from the environment)."""

import os

import psycopg2

DSN = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not DSN:
    raise SystemExit("Set TEST_DATABASE_URL (or DATABASE_URL) before running this dev script.")

conn = psycopg2.connect(DSN)
cur = conn.cursor()
cur.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
    "AND table_name IN ('roles','users','tenants','products','customers') ORDER BY table_name"
)
print("Tables:", [r[0] for r in cur.fetchall()])
cur.execute("SELECT id, slug FROM roles LIMIT 5")
print("Roles:", cur.fetchall())
cur.execute("SELECT id, username FROM users LIMIT 5")
print("Users:", cur.fetchall())
conn.close()
