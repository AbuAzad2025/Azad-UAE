"""The ``users.points`` column the gamification economy writes to.

The column did not exist: the service set ``user.points`` as a plain Python
attribute on the ORM instance and the value was discarded with the session.
These tests describe the column the model now declares and the migration
creates.
"""

from __future__ import annotations

from sqlalchemy import inspect

from extensions import db
from models import User


class TestUserPointsColumn:
    def test_the_column_is_declared(self):
        column = User.__table__.columns["points"]
        assert column.type.python_type is int
        assert column.nullable is False
        assert column.default is not None
        assert column.default.arg == 0

    def test_the_column_has_a_server_default(self):
        column = User.__table__.columns["points"]
        assert column.server_default is not None
        assert "0" in str(column.server_default.arg)

    def test_the_leaderboard_index_is_declared(self):
        indexes = {idx.name: [c.name for c in idx.columns] for idx in User.__table__.indexes}
        assert "idx_users_tenant_points" in indexes
        assert indexes["idx_users_tenant_points"] == ["tenant_id", "points"]

    def test_a_new_user_starts_on_zero(self, db_session, sample_user):
        """A user row that never earned anything still has a balance of zero."""
        assert sample_user.points == 0
        assert sample_user.points is not None

    def test_the_balance_survives_a_flush(self, db_session, sample_user):
        sample_user.points = 42
        db_session.flush()
        db_session.refresh(sample_user)
        assert sample_user.points == 42


class TestSchemaParity:
    def test_the_migrated_schema_carries_the_column(self, app):
        """The column has to exist in the database, not only in the metadata."""
        with app.app_context():
            inspector = inspect(db.engine)
            columns = {c["name"]: c for c in inspector.get_columns("users")}

            assert "points" in columns
            assert columns["points"]["nullable"] is False
            assert columns["points"]["default"] is not None

    def test_the_migrated_schema_carries_the_index(self, app):
        with app.app_context():
            inspector = inspect(db.engine)
            indexes = {idx["name"]: idx for idx in inspector.get_indexes("users")}

            assert "idx_users_tenant_points" in indexes
            assert indexes["idx_users_tenant_points"]["column_names"] == ["tenant_id", "points"]
