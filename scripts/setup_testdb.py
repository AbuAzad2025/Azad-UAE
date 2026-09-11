import psycopg2

conn = psycopg2.connect('postgresql://postgres:123@localhost:5432/postgres')
conn.autocommit = True
cur = conn.cursor()
cur.execute(
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
    "WHERE datname = 'azad_uae_test' AND pid <> pg_backend_pid()"
)
cur.execute("DROP DATABASE IF EXISTS azad_uae_test")
cur.execute("CREATE DATABASE azad_uae_test")
print('created')
conn.close()
