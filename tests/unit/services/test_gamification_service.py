from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from extensions import db
from services.gamification_service import GamificationService


class TestGetUserBadge:
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
    def test_badge_tiers(self, points, expected_key):
        badge = GamificationService.get_user_badge(points)
        assert badge["key"] == expected_key


class TestAwardPoints:
    def test_user_not_found(self, mocker):
        mocker.patch.object(db.session, "get", return_value=None)
        result = GamificationService.award_points(999999, "sale_created")
        assert result["success"] is False

    def test_user_without_points_attr_initializes_zero(self, mocker):
        user = SimpleNamespace(id=1)
        mocker.patch.object(db.session, "get", return_value=user)
        mocker.patch.object(db.session, "commit")
        result = GamificationService.award_points(1, "sale_created")
        assert result["success"] is True
        assert user.points == 10

    def test_sale_created_awards_points(self, db_session, sample_user):
        sample_user.points = 0
        db_session.flush()
        result = GamificationService.award_points(sample_user.id, "sale_created")
        assert result["success"] is True
        assert result["points_awarded"] == 10
        assert result["total_points"] == 10

    def test_unknown_action_zero_points(self, db_session, sample_user):
        sample_user.points = 5
        db_session.flush()
        result = GamificationService.award_points(sample_user.id, "unknown_action")
        assert result["points_awarded"] == 0
        assert result["total_points"] == 5

    def test_large_sale_tier_bonus(self, db_session, sample_user):
        sample_user.points = 0
        db_session.flush()
        result = GamificationService.award_points(
            sample_user.id,
            "large_sale",
            {"amount": 12000},
        )
        assert result["points_awarded"] == 50

    def test_large_sale_mid_tier(self, db_session, sample_user):
        sample_user.points = 0
        db_session.flush()
        result = GamificationService.award_points(
            sample_user.id,
            "large_sale",
            {"amount": 6000},
        )
        assert result["points_awarded"] == 30

    def test_level_up_flag(self, db_session, sample_user):
        sample_user.points = 95
        db_session.flush()
        result = GamificationService.award_points(sample_user.id, "sale_created")
        assert result["level_up"] is True
        assert result["badge"]["key"] == "bronze"

    def test_commit_failure_rolls_back(self, db_session, sample_user, mocker):
        sample_user.points = 0
        db_session.flush()
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("db"))
        with pytest.raises(RuntimeError):
            GamificationService.award_points(sample_user.id, "sale_created")


class TestLeaderboard:
    def test_leaderboard_ranking(self, mocker):
        u1 = MagicMock(id=1, username="a", full_name_ar="أ", full_name="A", points=200)
        u2 = MagicMock(id=2, username="b", full_name_ar="ب", full_name="B", points=50)
        q = MagicMock()
        q.order_by.return_value.limit.return_value.all.return_value = [u1, u2]
        mocker.patch("utils.tenanting.scoped_user_query", return_value=q)
        rows = GamificationService.get_leaderboard(limit=5)
        assert rows[0]["rank"] == 1
        assert rows[0]["points"] == 200
        assert rows[1]["badge"]["key"] == "newbie"


class TestUserStats:
    def test_user_not_found(self, mocker):
        mocker.patch.object(db.session, "get", return_value=None)
        assert GamificationService.get_user_stats(999999)["success"] is False

    def test_stats_with_sales(
        self, db_session, sample_user, sample_tenant, sample_customer
    ):
        from models import Sale

        sample_user.points = 40
        db_session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"ST-{sample_user.id}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            status="confirmed",
            subtotal=Decimal("100"),
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("150"),
        )
        db_session.add(sale)
        db_session.flush()

        stats = GamificationService.get_user_stats(sample_user.id)
        assert stats["success"] is True
        assert stats["total_sales"] == 1
        assert stats["total_amount"] == pytest.approx(150.0)
        assert stats["next_badge"]["points"] == 100
        assert stats["points_to_next"] == 60
