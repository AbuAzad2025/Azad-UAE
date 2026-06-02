import os
os.environ['DATABASE_URL'] = 'postgresql+psycopg2://postgres:123@localhost:5432/azad_uae'
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    r = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"))
    print('=== ALL TABLES ===')
    tables = [row[0] for row in r]
    for t in tables:
        try:
            c = conn.execute(text(f'SELECT COUNT(*) FROM {t}'))
            print(f'{t:40s}: {c.scalar()}')
        except Exception as e:
            print(f'{t:40s}: ERROR - {e}')
