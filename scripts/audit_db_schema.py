import sqlalchemy as sa
from sqlalchemy import inspect
import sys
sys.path.insert(0, r'd:\Data\karaj\UAE\Azad-UAE')

from extensions import db
import app as m

app = m.create_app()
app.app_context().push()

inspector = inspect(db.engine)

models_module = __import__('models', fromlist=['*'])
model_classes = []
for name in dir(models_module):
    obj = getattr(models_module, name)
    if isinstance(obj, type) and hasattr(obj, '__tablename__') and hasattr(obj, '__table__'):
        model_classes.append(obj)

print(f"Models found: {len(model_classes)}")
print(f"Tables in DB: {len(inspector.get_table_names())}")
print()

issues = []

for cls in sorted(model_classes, key=lambda x: x.__tablename__):
    table_name = cls.__tablename__
    if not inspector.has_table(table_name):
        issues.append(f"MISSING TABLE: {table_name} (model exists but no DB table)")
        continue

    db_cols = {c['name']: c for c in inspector.get_columns(table_name)}
    model_cols = {c.name: c for c in cls.__table__.columns}

    for col_name, model_col in model_cols.items():
        if col_name not in db_cols:
            issues.append(f"MISSING COLUMN: {table_name}.{col_name}")
            continue

        db_col = db_cols[col_name]
        db_type = str(db_col['type'])
        model_type = str(model_col.type)

        if db_type != model_type:
            if 'VARCHAR' in db_type and 'VARCHAR' in model_type:
                pass
            elif 'NUMERIC' in db_type and 'NUMERIC' in model_type:
                pass
            elif 'DECIMAL' in db_type and 'NUMERIC' in model_type:
                pass
            else:
                issues.append(f"TYPE MISMATCH: {table_name}.{col_name} DB={db_type} Model={model_type}")

    for col_name in db_cols:
        if col_name not in model_cols:
            issues.append(f"EXTRA COLUMN: {table_name}.{col_name}")

    db_fks = inspector.get_foreign_keys(table_name)
    model_fks = cls.__table__.foreign_keys

    for fk in model_fks:
        col = fk.parent.name
        found = False
        for db_fk in db_fks:
            if col in db_fk.get('constrained_columns', []):
                found = True
                break
        if not found and col != 'id':
            pass

    db_uqs = inspector.get_unique_constraints(table_name)
    db_uq_cols = set()
    for uq in db_uqs:
        db_uq_cols.add(tuple(sorted(uq['column_names'])))

    for constraint in cls.__table__.constraints:
        if isinstance(constraint, sa.UniqueConstraint):
            cols = tuple(sorted([c.name for c in constraint.columns]))
            if cols not in db_uq_cols and cols not in [tuple(sorted(p.columns.keys())) for p in cls.__table__.primary_key]:
                pass

    db_idxs = {tuple(sorted(i['column_names'])): i for i in inspector.get_indexes(table_name)}
    for idx in cls.__table__.indexes:
        cols = tuple(sorted([c.name for c in idx.columns]))
        if cols not in db_idxs:
            pass

if issues:
    print(f"Found {len(issues)} issues:")
    for issue in issues[:50]:
        print(f"  - {issue}")
    if len(issues) > 50:
        print(f"  ... and {len(issues) - 50} more")
else:
    print("No schema mismatches found!")
