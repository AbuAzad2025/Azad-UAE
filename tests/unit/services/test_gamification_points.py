"""The gamification points economy has to live in the database.

The defect these tests pin down: ``users`` had no ``points`` column, so
``GamificationService.award_points`` wrote a plain Python attribute onto the
ORM instance and the balance died with the session.
``GamificationService.get_leaderboard`` compensated by sorting on ``User.id``
(``hasattr(User, "points")`` is False on the class), so the board was the
oldest users first and every badge stayed "newbie" forever.

The persistence check reads the row back over a *separate* connection, so an
in-memory attribute cannot satisfy it.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from extensions import db
from models import Role, Tenant, User
from services.gamification_service import GamificationService


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_user(tenant_id: int, role_id: int, points: int = 0) -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(
        username=f"pts-{tag}",
        email=f"pts-{tag}@example.com",
        password_hash="not-a-real-hash",
        full_name=f"Points {tag}",
        tenant_id=tenant_id,
        role_id=role_id,
    )
    user.points = points
    return user


@pytest.fixture()
def committed_user(app):
    """A user row that is genuinely committed, so another connection can see it.

    The ``db_session`` fixture keeps everything inside an uncommitted outer
    transaction, which a second connection cannot see. Proving the points are
    *persisted* needs a second connection, so this fixture owns its own
    transaction and cleans its rows up afterwards.
    """
    with app.app_context(), db.engine.begin() as conn, Session(bind=conn) as orm:
        role = Role(name=f"Points Role {uuid.uuid4().hex[:8]}", slug=_unique("points-role"), is_active=True)
        orm.add(role)
        orm.flush()

        tenant = Tenant(
            name=f"Points Co {uuid.uuid4().hex[:8]}",
            name_ar="شركة النقاط",
            slug=_unique("points-co"),
            email=f"{_unique('points')}@example.com",
            country="AE",
            subscription_plan="basic",
        )
        orm.add(tenant)
        orm.flush()

        user = _make_user(tenant.id, role.id)
        orm.add(user)
        orm.flush()

        ids = SimpleNamespace(user_id=user.id, tenant_id=tenant.id, role_id=role.id)

    yield ids

    with app.app_context(), db.engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM users WHERE id = :i"), {"i": ids.user_id})
        conn.execute(sa_text("DELETE FROM tenants WHERE id = :i"), {"i": ids.tenant_id})
        conn.execute(sa_text("DELETE FROM roles WHERE id = :i"), {"i": ids.role_id})


class TestPointsArePersisted:
    def test_award_points_reaches_the_database(self, app, committed_user):
        """The awarded points must be on disk, not on the ORM instance."""
        with app.app_context():
            result = GamificationService.award_points(committed_user.user_id, "sale_created")
            assert result["success"] is True
            assert result["total_points"] == 10
            db.session.commit()

        # A different connection, a different session: only the database can
        # answer this.
        with app.app_context(), db.engine.connect() as conn:
            reader = Session(bind=conn)
            try:
                fresh = reader.get(User, committed_user.user_id)
                assert fresh is not None
                assert fresh.points == 10
            finally:
                reader.close()

    def test_awards_accumulate_across_sessions(self, app, committed_user):
        """A second award adds to the balance the first one left behind."""
        with app.app_context():
            GamificationService.award_points(committed_user.user_id, "sale_created")
            db.session.commit()
            second = GamificationService.award_points(committed_user.user_id, "payment_collected")
            db.session.commit()

        assert second["points_awarded"] == 5
        assert second["total_points"] == 15

        with app.app_context(), db.engine.connect() as conn:
            stored = conn.execute(
                sa_text("SELECT points FROM users WHERE id = :i"), {"i": committed_user.user_id}
            ).scalar()
        assert stored == 15

    def test_the_column_exists_in_the_schema(self, app, committed_user):
        """The balance is a real column, with a server default of zero."""
        with app.app_context(), db.engine.connect() as conn:
            column = conn.execute(
                sa_text(
                    "SELECT is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'users' AND column_name = 'points'"
                )
            ).first()

        assert column is not None
        assert column[0] == "NO"
        assert "0" in (column[1] or "")


class TestLeaderboardOrdering:
    def test_leaderboard_ranks_by_points_not_by_id(self, db_session, sample_tenant, sample_role):
        """The board must follow the points, with the id only as a tie-break."""
        from flask import g

        low = _make_user(sample_tenant.id, sample_role.id, points=50)
        high = _make_user(sample_tenant.id, sample_role.id, points=900)
        middle = _make_user(sample_tenant.id, sample_role.id, points=300)
        db_session.add_all([low, high, middle])
        db_session.flush()

        # Id order is low, high, middle - points order is high, middle, low.
        assert low.id < high.id < middle.id

        g.active_tenant_id = sample_tenant.id
        board = GamificationService.get_leaderboard(limit=10)

        assert [row["user_id"] for row in board[:3]] == [high.id, middle.id, low.id]
        assert [row["points"] for row in board[:3]] == [900, 300, 50]
        assert [row["rank"] for row in board[:3]] == [1, 2, 3]

    def test_leaderboard_breaks_ties_on_the_id(self, db_session, sample_tenant, sample_role):
        """Two users on the same total always come back in the same order."""
        from flask import g

        first = _make_user(sample_tenant.id, sample_role.id, points=250)
        second = _make_user(sample_tenant.id, sample_role.id, points=250)
        db_session.add_all([first, second])
        db_session.flush()
        assert first.id < second.id

        g.active_tenant_id = sample_tenant.id
        board = GamificationService.get_leaderboard(limit=10)

        assert [row["user_id"] for row in board[:2]] == [first.id, second.id]

    def test_leaderboard_reports_the_badge_of_the_points(self, db_session, sample_tenant, sample_role):
        """The badge on the board is the badge of the points, not a separate award."""
        from flask import g

        gold = _make_user(sample_tenant.id, sample_role.id, points=1200)
        db_session.add(gold)
        db_session.flush()

        g.active_tenant_id = sample_tenant.id
        board = GamificationService.get_leaderboard(limit=10)

        top = board[0]
        assert top["user_id"] == gold.id
        assert top["points"] == 1200
        assert top["badge"]["key"] == "gold"


class TestBadgeFollowsPoints:
    @pytest.mark.parametrize(
        "points,expected_key",
        [
            (0, "newbie"),
            (100, "bronze"),
            (500, "silver"),
            (1000, "gold"),
            (5000, "platinum"),
            (10000, "legend"),
        ],
    )
    def test_thresholds_are_unchanged(self, points, expected_key):
        assert GamificationService.get_user_badge(points)["key"] == expected_key

    def test_the_badge_follows_the_balance(self, db_session, sample_user):
        """Crossing a threshold during an award is what moves the badge."""
        sample_user.points = 495
        db_session.flush()

        result = GamificationService.award_points(sample_user.id, "sale_created")
        assert result["total_points"] == 505
        assert result["badge"]["key"] == "silver"
        assert result["level_up"] is True

        stats = GamificationService.get_user_stats(sample_user.id)
        assert stats["points"] == 505
        assert stats["current_badge"]["key"] == "silver"


class TestAwardPointsContract:
    """The public shape of the returned dict must not move."""

    def test_returned_dict_is_unchanged(self, db_session, sample_user):
        sample_user.points = 0
        db_session.flush()

        result = GamificationService.award_points(sample_user.id, "sale_created")

        assert set(result) == {"success", "points_awarded", "total_points", "badge", "level_up"}
        assert result["success"] is True
        assert result["points_awarded"] == 10
        assert result["total_points"] == 10
        assert result["level_up"] is False
        assert set(result["badge"]) == {"key", "name_ar", "icon", "min_points"}

    def test_unknown_user_still_reports_the_error(self):
        assert GamificationService.award_points(999999999, "sale_created") == {
            "success": False,
            "error": "User not found",
        }

    def test_an_unknown_action_is_worth_nothing(self, db_session, sample_user):
        sample_user.points = 7
        db_session.flush()

        result = GamificationService.award_points(sample_user.id, "not-a-real-action")
        assert result["points_awarded"] == 0
        assert result["total_points"] == 7
        assert result["level_up"] is False
