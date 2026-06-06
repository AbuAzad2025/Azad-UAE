import os
os.environ['FLASK_APP'] = 'app.py'
from app import create_app
from extensions import db

app = create_app()

with app.app_context():
    print("\n" + "="*70)
    print("1. SCHEMA DRIFT CHECK (flask db check)")
    print("="*70)

    try:
        from alembic.config import Config
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import inspect, text

        # Get alembic config
        alembic_cfg = Config('migrations/alembic.ini')
        alembic_cfg.set_main_option('sqlalchemy.url', db.engine.url)

        # Create migration context
        with db.engine.begin() as connection:
            ctx = MigrationContext.configure(connection, opts={'compare_type': True, 'compare_server_default': True})
            op = Operations(ctx)

            # Check for differences
            diffs = ctx.get_context().run_migrations()

    except Exception as e:
        print(f"ERROR checking schema: {str(e)}")

    # Alternative: Check with SQLAlchemy inspector
    print("\nChecking with SQLAlchemy Inspector:")
    inspector = inspect(db.engine)

    # Check profit_centers specifically
    print("\nprofit_centers columns:")
    if 'profit_centers' in inspector.get_table_names():
        cols = inspector.get_columns('profit_centers')
        for col in cols:
            col_type = str(col['type'])
            print(f"  - {col['name']:<20} {col_type}")

    # Check gl_journal_lines columns
    print("\ngl_journal_lines columns (new dimension fields):")
    if 'gl_journal_lines' in inspector.get_table_names():
        cols = inspector.get_columns('gl_journal_lines')
        dimension_cols = ['branch_id', 'warehouse_id', 'profit_center_id', 'partner_id', 'cost_center_id']
        for col in cols:
            if col['name'] in dimension_cols:
                nullable_str = "NULLABLE" if col['nullable'] else "NOT NULL"
                col_type = str(col['type'])
                print(f"  - {col['name']:<20} {col_type:<15} {nullable_str}")

    # Check foreign keys
    print("\nChecking Foreign Keys in gl_journal_lines:")
    try:
        fks = inspector.get_foreign_keys('gl_journal_lines')
        dimension_fks = [fk for fk in fks if fk['constrained_columns'][0] in ['branch_id', 'warehouse_id', 'profit_center_id', 'partner_id']]

        if dimension_fks:
            for fk in dimension_fks:
                col = fk['constrained_columns'][0]
                ref_table = fk['referred_table']
                print(f"  ✓ {col} -> {ref_table}")
        else:
            print("  ⚠ NO FOREIGN KEYS FOUND for dimension columns!")
            print("    (This might be OK if using NOT VALID constraints)")
    except Exception as e:
        print(f"  ERROR: {str(e)}")

    # Check constraints
    print("\nChecking Constraints:")
    try:
        constraints = inspector.get_check_constraints('gl_journal_lines')
        print(f"  Check constraints: {len(constraints)}")
        for c in constraints[:3]:
            print(f"    - {c.get('name', 'unnamed')}")
    except:
        pass

    print("\n" + "="*70)
    print("2. ORPHANED REFERENCES CHECK")
    print("="*70)

    # Check for orphaned references
    checks = [
        ("gl_journal_lines.branch_id", "branches.id"),
        ("gl_journal_lines.warehouse_id", "warehouses.id"),
        ("gl_journal_lines.profit_center_id", "profit_centers.id"),
        ("gl_journal_lines.partner_id", "partners.id"),
    ]

    for col_ref, table_id in checks:
        table, col = col_ref.split('.')
        ref_table, ref_col = table_id.split('.')

        try:
            query = f"""
            SELECT COUNT(*) FROM {table}
            WHERE {col} IS NOT NULL
            AND {col} NOT IN (SELECT id FROM {ref_table})
            """
            result = db.session.execute(text(query))
            orphaned = result.fetchone()[0]

            if orphaned > 0:
                print(f"  ⚠ {col_ref}: {orphaned} orphaned references!")
            else:
                print(f"  ✓ {col_ref}: OK (no orphaned references)")
        except Exception as e:
            print(f"  ERROR checking {col_ref}: {str(e)}")

    print("\n" + "="*70)
    print("3. DATA COMPLETENESS CHECK")
    print("="*70)

    # Check data in key tables
    tables_to_check = {
        'profit_centers': 'Profit Centers',
        'branches': 'Branches',
        'warehouses': 'Warehouses',
        'partners': 'Partners',
        'cost_centers': 'Cost Centers',
    }

    for table, label in tables_to_check.items():
        try:
            result = db.session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.fetchone()[0]
            status = "✓" if count > 0 else "⚠"
            print(f"  {status} {label:<20} {count} rows")
        except Exception as e:
            print(f"  ✗ {label:<20} ERROR: {str(e)}")

