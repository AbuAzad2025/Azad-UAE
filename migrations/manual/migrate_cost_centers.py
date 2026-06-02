"""Manual migration: Add tenant_id to cost_centers table."""
import os
os.environ['DATABASE_URL'] = 'postgresql+psycopg2://postgres:123@localhost:5432/azad_uae'
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    # Check if tenant_id column exists
    r = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'cost_centers' AND column_name = 'tenant_id'"))
    if r.scalar():
        print('tenant_id column already exists')
    else:
        # Add tenant_id column
        conn.execute(text('ALTER TABLE cost_centers ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)'))
        conn.execute(text('CREATE INDEX ix_cost_centers_tenant_id ON cost_centers(tenant_id)'))
        print('✅ Added tenant_id column and index')
    
    # Check existing unique constraint
    r = conn.execute(text("SELECT constraint_name FROM information_schema.table_constraints WHERE table_name = 'cost_centers' AND constraint_type = 'UNIQUE'"))
    constraints = [row[0] for row in r]
    print(f'Existing unique constraints: {constraints}')
    
    # Drop old unique constraint on code if exists
    if 'cost_centers_code_key' in constraints:
        conn.execute(text('ALTER TABLE cost_centers DROP CONSTRAINT cost_centers_code_key'))
        print('✅ Dropped old unique constraint on code')
    
    # Add new unique constraint on (tenant_id, code)
    try:
        conn.execute(text('ALTER TABLE cost_centers ADD CONSTRAINT uq_cost_centers_tenant_code UNIQUE (tenant_id, code)'))
        print('✅ Added new unique constraint on (tenant_id, code)')
    except Exception as e:
        print(f'Note: {e}')
    
    conn.commit()
    print('✅ Migration completed successfully')
