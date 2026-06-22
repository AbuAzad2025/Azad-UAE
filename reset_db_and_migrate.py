#!/usr/bin/env python3
"""Reset database and apply migrations cleanly.

Strategy:
1. Drop ALL tables (including alembic_version)
2. Use db.create_all() to create tables from models (cleanest approach)
3. Run system_init to seed core data
4. Stamp Alembic heads to mark all migrations as applied
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

os.environ['SKIP_SYSTEM_INTEGRITY'] = '1'  # Prevent auto-init during app creation

def main():
    from app import create_app
    from extensions import db
    from sqlalchemy import inspect as sa_inspect, text
    
    app = create_app()
    
    with app.app_context():
        engine = db.engine
        inspector = sa_inspect(engine)
        
        # Step 1: Drop all tables
        tables = inspector.get_table_names()
        print(f"Found {len(tables)} tables. Dropping all...")
        
        with engine.begin() as conn:
            for table in tables:
                try:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
                    print(f"  Dropped: {table}")
                except Exception as e:
                    print(f"  Warning: {e}")
        
        # Step 2: Create all tables from SQLAlchemy models
        print("\nCreating tables from SQLAlchemy models...")
        db.create_all()
        print("Tables created successfully.")
        
        # Step 3: Run system_init for core data
        print("\nRunning system initialization for core data...")
        from utils.system_init import ensure_system_integrity
        ensure_system_integrity(app)
        print("System initialization completed.")
        
        # Step 4: Stamp Alembic heads using Flask-Migrate
        print("\nStamping Alembic revisions...")
        from flask_migrate import stamp
        stamp()
        print("Alembic revisions stamped successfully.")
        
        # Step 5: Verify critical columns
        print("\nVerifying critical columns...")
        inspector = sa_inspect(engine)
        checks = {
            'tenants': ['base_currency'],
            'warehouses': ['allow_negative_inventory'],
        }
        
        all_ok = True
        for table, expected_cols in checks.items():
            cols = [c['name'] for c in inspector.get_columns(table)]
            for col in expected_cols:
                if col in cols:
                    print(f"  OK: {table}.{col}")
                else:
                    print(f"  ERROR: {table}.{col} NOT found!")
                    all_ok = False
        
        if all_ok:
            print("\n=== ALL CHECKS PASSED ===")
            print("Database is clean, migrated, and initialized.")
        else:
            print("\n=== SOME CHECKS FAILED ===")
            sys.exit(1)

if __name__ == '__main__':
    main()
