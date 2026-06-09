import pytest
from sqlalchemy import inspect


# ── Index Integrity Tests ────────────────────────────────────────────


class TestModelIntegrity:

    def test_all_tenant_id_columns_indexed(self, app):
        """Every tenant_id FK must have an index."""
        from extensions import db
        with app.app_context():
            inspector = inspect(db.engine)
            missing = []
            for table in inspector.get_table_names():
                if table.startswith("alembic_"):
                    continue
                cols = [c["name"] for c in inspector.get_columns(table)]
                if "tenant_id" not in cols:
                    continue
                pks = inspector.get_pk_constraint(table)["constrained_columns"]
                indexes = set()
                for idx in inspector.get_indexes(table):
                    indexes.update(idx["column_names"])
                if "tenant_id" not in indexes and "tenant_id" not in pks:
                    missing.append(table)
            assert not missing, f"Tables with tenant_id NOT indexed: {missing}"

    def test_all_created_at_indexed(self, app):
        """Every created_at column used in sorting must have an index."""
        from extensions import db
        with app.app_context():
            inspector = inspect(db.engine)
            missing = []
            for table in inspector.get_table_names():
                if table.startswith("alembic_"):
                    continue
                cols = [c["name"] for c in inspector.get_columns(table)]
                if "created_at" not in cols:
                    continue
                pks = inspector.get_pk_constraint(table)["constrained_columns"]
                indexes = set()
                for idx in inspector.get_indexes(table):
                    indexes.update(idx["column_names"])
                if "created_at" not in indexes and "created_at" not in pks:
                    missing.append(table)
            assert not missing, f"Tables with created_at NOT indexed ({len(missing)}): {missing}"

    def test_all_status_flags_indexed(self, app):
        """Every status/is_active/is_suspended filter column must have an index."""
        from extensions import db
        with app.app_context():
            inspector = inspect(db.engine)
            flag_cols = ("status", "is_active", "is_suspended")
            missing = []
            for table in inspector.get_table_names():
                if table.startswith("alembic_"):
                    continue
                cols = {c["name"] for c in inspector.get_columns(table)}
                pks = set(inspector.get_pk_constraint(table)["constrained_columns"])
                indexes = set()
                for idx in inspector.get_indexes(table):
                    indexes.update(idx["column_names"])
                for flag in flag_cols:
                    if flag in cols and flag not in indexes and flag not in pks:
                        missing.append(f"{table}.{flag}")
            assert not missing, f"Flag columns NOT indexed ({len(missing)}): {missing}"

    def test_all_fks_have_on_delete(self, app):
        """Every foreign key must define ON DELETE behavior."""
        from extensions import db
        with app.app_context():
            inspector = inspect(db.engine)
            missing = []
            for table in inspector.get_table_names():
                if table.startswith("alembic_"):
                    continue
                for fk in inspector.get_foreign_keys(table):
                    options = fk.get("options", {})
                    ondelete = options.get("ondelete")
                    if not ondelete:
                        cols = ", ".join(fk["constrained_columns"])
                        missing.append(f"{table}({cols}) -> {fk['referred_table']}")
            assert not missing, f"FKs without ON DELETE ({len(missing)}):\n" + "\n".join(missing[:20])

    def test_all_fk_columns_indexed(self, app):
        """Every FK column must have an index (excl. PKs)."""
        from extensions import db
        with app.app_context():
            inspector = inspect(db.engine)
            missing = []
            for table in inspector.get_table_names():
                if table.startswith("alembic_"):
                    continue
                pks = set(inspector.get_pk_constraint(table)["constrained_columns"])
                indexes = set()
                for idx in inspector.get_indexes(table):
                    indexes.update(idx["column_names"])
                for fk in inspector.get_foreign_keys(table):
                    for col in fk["constrained_columns"]:
                        if col not in indexes and col not in pks:
                            missing.append(f"{table}.{col} -> {fk['referred_table']}")
            assert not missing, f"FK columns NOT indexed ({len(missing)}):\n" + "\n".join(missing[:20])
