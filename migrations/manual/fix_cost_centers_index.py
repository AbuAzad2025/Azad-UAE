import os
os.environ['DATABASE_URL'] = 'postgresql+psycopg2://postgres:123@localhost:5432/azad_uae'
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    # Drop old unique index on code
    try:
        conn.execute(text('DROP INDEX IF EXISTS ix_cost_centers_code'))
        print('✅ Dropped old unique index on code')
    except Exception as e:
        print(f'Note: {e}')
    
    # Delete existing cost centers (they have NULL tenant_id)
    conn.execute(text('DELETE FROM cost_centers WHERE tenant_id IS NULL'))
    print('✅ Deleted old cost centers with NULL tenant_id')
    
    conn.commit()
    print('✅ Cleanup completed successfully')
