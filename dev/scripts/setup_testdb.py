#!/usr/bin/env python3
"""Recreate the local test database (credentials from the environment)."""

import os

import psycopg2

ADMIN_DSN = os.environ.get("TEST_ADMIN_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not ADMIN_DSN:
    raise SystemExit("Set TEST_ADMIN_DATABASE_URL (or DATABASE_URL) before running this dev script.")

conn = psycopg2.connect(ADMIN_DSN)
conn.autocommit = True
cur = conn.cursor()
cur.execute(
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
    "WHERE datname = 'azad_uae_test' AND pid <> pg_backend_pid()"
)
cur.execute("DROP DATABASE IF EXISTS azad_uae_test")
cur.execute("CREATE DATABASE azad_uae_test")
print("created")
conn.close()
