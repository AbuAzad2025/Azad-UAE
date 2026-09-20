import psycopg2

conn = psycopg2.connect("postgresql://postgres:123@localhost:5432/postgres")
cur = conn.cursor()
cur.execute("SELECT datname FROM pg_database WHERE datname LIKE '%azad%' ORDER BY datname")
for r in cur.fetchall():
    print("DB:", r[0])
cur.close()
conn.close()
