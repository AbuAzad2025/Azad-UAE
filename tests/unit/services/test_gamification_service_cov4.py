"""Cov4: gamification_service — award/badge/leaderboard/stats arcs."""

from __future__ import annotations

from services.gamification_service import GamificationService


def test_award_points_user_not_found(db_session):
    out = GamificationService.award_points(999999999, "sale_created")
    assert out == {"success": False, "error": "User not found"}


def test_award_points_basic_and_level_up(db_session, sample_user):
    sample_user.points = 95
    db_session.flush()
    out = GamificationService.award_points(sample_user.id, "sale_created")
    assert out["success"] is True
    assert out["points_awarded"] == 10
    assert out["total_points"] == 105
    assert out["level_up"] is True
    assert out["badge"]["key"] == "bronze"


def test_award_points_unknown_action_zero_points(db_session, sample_user):
    sample_user.points = 0
    db_session.flush()
    out = GamificationService.award_points(sample_user.id, "no_such_action")
    assert out["points_awarded"] == 0
    assert out["level_up"] is False


def test_award_points_large_sale_tiers(db_session, sample_user):
    sample_user.points = 0
    db_session.flush()
    out = GamificationService.award_points(sample_user.id, "large_sale", {"amount": 20000})
    assert out["points_awarded"] == 50
    sample_user.points = 0
    db_session.flush()
    out = GamificationService.award_points(sample_user.id, "large_sale", {"amount": 7000})
    assert out["points_awarded"] == 30
    sample_user.points = 0
    db_session.flush()
    out = GamificationService.award_points(sample_user.id, "large_sale", {"amount": 100})
    assert out["points_awarded"] == 20
    # large_sale without metadata keeps config value
    sample_user.points = 0
    db_session.flush()
    out = GamificationService.award_points(sample_user.id, "large_sale")
    assert out["points_awarded"] == 20


def test_get_user_badge_thresholds():
    assert GamificationService.get_user_badge(0)["key"] == "newbie"
    assert GamificationService.get_user_badge(100)["key"] == "bronze"
    assert GamificationService.get_user_badge(500)["key"] == "silver"
    assert GamificationService.get_user_badge(1000)["key"] == "gold"
    assert GamificationService.get_user_badge(5000)["key"] == "platinum"
    assert GamificationService.get_user_badge(20000)["key"] == "legend"


def test_get_leaderboard_empty_without_active_tenant(db_session, sample_user):
    # Real scoping path: no logged-in user -> tenant_id<0 fallback -> empty board
    sample_user.points = 150
    db_session.flush()
    assert GamificationService.get_leaderboard(limit=5) == []


def test_get_leaderboard_ranking_and_badges(db_session, sample_user, sample_tenant):
    from unittest.mock import MagicMock, patch

    import utils.tenanting as tenanting

    sample_user.points = 150
    db_session.flush()
    real_users = (
        db_session.query(type(sample_user))
        .filter_by(tenant_id=sample_tenant.id)
        .order_by(type(sample_user).id)
        .limit(5)
        .all()
    )
    assert real_users
    chain = MagicMock()
    chain.order_by.return_value.limit.return_value.all.return_value = real_users
    with patch.object(tenanting, "scoped_user_query", return_value=chain):
        board = GamificationService.get_leaderboard(limit=5)
    assert board[0]["rank"] == 1
    assert board[0]["user_id"] == sample_user.id
    assert board[0]["points"] == 150
    assert board[0]["badge"]["key"] == "bronze"


def test_get_user_stats_basic(db_session, sample_user):
    sample_user.points = 150
    db_session.flush()
    stats = GamificationService.get_user_stats(sample_user.id)
    assert stats["success"] is True
    assert stats["points"] == 150
    assert stats["current_badge"]["key"] == "bronze"
    assert stats["next_badge"]["points"] == 500
    assert stats["points_to_next"] == 350


def test_get_user_stats_not_found():
    assert GamificationService.get_user_stats(999999999) == {"success": False}


def test_get_user_stats_max_badge_no_next(db_session, sample_user):
    sample_user.points = 999999
    db_session.flush()
    stats = GamificationService.get_user_stats(sample_user.id)
    assert stats["next_badge"] is None
    assert stats["points_to_next"] == 0
