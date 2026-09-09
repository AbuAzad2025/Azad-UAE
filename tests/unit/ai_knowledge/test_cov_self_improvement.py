"""Coverage tests for ai_knowledge/improvement/self_improvement.py partial arcs.

Targets: 296->294, 302->308, 305->308, 329->332, 385->384, 453->430.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest


@pytest.fixture
def engine(tmp_path):
    from ai_knowledge.improvement.self_improvement import AzadSelfImprovement

    with patch("ai_knowledge.get_knowledge_path", side_effect=lambda n: str(tmp_path / n)):
        yield AzadSelfImprovement()


class TestCovSelfImprovement:
    def test_cov_auto_improve_first_weakness_fails(self, engine):
        """Arc 296->294: first implement_improvement fails, loop continues."""
        engine.improvement_areas["response_quality"]["current_score"] = 6.0
        engine.improvement_areas["prediction_accuracy"]["current_score"] = 6.0
        calls = []

        def fake(area, improvement_type="automatic"):
            calls.append(area)
            if len(calls) == 1:
                return {"success": False, "error": "boom"}
            return {"success": True, "area": area, "improvement": 0.1}

        with patch.object(engine, "implement_improvement", side_effect=fake):
            result = engine.auto_improve()
        assert calls[0] == "response_quality"
        assert result["improvements_made"] == 2
        assert len(calls) == 3

    def test_cov_auto_improve_no_available_areas(self, engine):
        """Arc 302->308: all areas are weaknesses, available_areas is empty."""
        engine.improvement_areas = {
            "area_a": {"current_score": 5.0, "target_score": 9.0, "improvement_rate": 0.1, "last_improvement": None},
            "area_b": {"current_score": 5.0, "target_score": 9.0, "improvement_rate": 0.1, "last_improvement": None},
        }
        result = engine.auto_improve()
        assert result["improvements_made"] == 2
        assert result["details"] != []

    def test_cov_auto_improve_random_area_fails(self, engine):
        """Arc 305->308: weakness improves but the random-area improve fails."""
        assert engine.improvement_areas["prediction_accuracy"]["current_score"] < 7.0

        def fake(area, improvement_type="automatic"):
            if area == "prediction_accuracy":
                return {"success": True, "area": area, "improvement": 0.1}
            return {"success": False, "error": "random fail"}

        with patch.object(engine, "implement_improvement", side_effect=fake):
            result = engine.auto_improve()
        assert result["improvements_made"] == 1

    def test_cov_set_goal_new_and_existing_list(self, engine):
        """Arc 329->332: first call creates active_goals, second appends to it."""
        first = engine.set_improvement_goal("response_quality", 9.0)
        assert first["success"] is True
        assert "active_goals" in engine.improvement_goals
        second = engine.set_improvement_goal("knowledge_depth", 9.5)
        assert second["success"] is True
        assert len(engine.improvement_goals["active_goals"]) == 2

    def test_cov_track_goals_skips_inactive(self, engine):
        """Arc 385->384: inactive goal is skipped while looping."""
        engine.improvement_goals["active_goals"] = [
            {
                "area": "response_quality",
                "current_score": 7.5,
                "target_score": 9.0,
                "created_at": datetime.now().isoformat(),
                "status": "active",
            },
            {
                "area": "knowledge_depth",
                "current_score": 8.0,
                "target_score": 9.8,
                "created_at": datetime.now().isoformat(),
                "status": "completed",
            },
        ]
        progress = engine._track_goals_progress()
        assert len(progress) == 1
        assert progress[0]["area"] == "response_quality"

    def test_cov_milestones_skip_area_at_target(self, engine):
        """Arc 453->430: area at/above target gets no milestone, loop continues."""
        engine.improvement_areas["response_speed"]["current_score"] = 9.9
        engine.improvement_areas["response_speed"]["target_score"] = 9.9
        milestones = engine._get_next_milestones()
        assert all(m["area"] != "response_speed" for m in milestones)
        assert any(m["area"] == "prediction_accuracy" for m in milestones)
