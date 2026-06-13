import sys
sys.path.insert(0, r'D:\Data\karaj\UAE\Azad-UAE')
from app import create_app
from sqlalchemy import inspect
from extensions import db

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    missing = []
    for table in inspector.get_table_names():
        if table.startswith('alembic_'):
            continue
        pks = set(inspector.get_pk_constraint(table)['constrained_columns'])
        indexes = set()
        for idx in inspector.get_indexes(table):
            indexes.update(idx['column_names'])
        for fk in inspector.get_foreign_keys(table):
            for col in fk['constrained_columns']:
                if col not in indexes and col not in pks:
                    missing.append(table + '.' + col + ' -> ' + fk['referred_table'])
    for m in missing:
        print(m)
