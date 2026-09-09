"""Coverage tests for ai_knowledge/improvement/self_reflection.py partial arcs.

Targets: 65->78 (no accuracy scores), 88->96 (empty error-type map).
"""

from __future__ import annotations

import pytest


class TestCovSelfReflection:
    def test_cov_reflect_entries_without_accuracy(self):
        """Arc 65->78: performance entries lacking 'accuracy' skip scoring."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        sr = SelfReflectionEngine()
        sr.performance_log = [{"task": "no-accuracy-here"}, {"task": "also-missing"}]
        result = sr.reflect_on_performance()
        assert result["overall_score"] == 0
        assert result["strengths"] == []
        assert result["weaknesses"] == []

    def test_cov_reflect_high_accuracy_strength(self):
        """Arc 65 true side: accuracy present and very high."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        sr = SelfReflectionEngine()
        sr.performance_log = [{"accuracy": 0.95} for _ in range(3)]
        result = sr.reflect_on_performance()
        assert result["overall_score"] == pytest.approx(0.95)
        assert any("عالية" in s for s in result["strengths"])

    def test_cov_reflect_errors_slice_empty(self):
        """Arc 88->96: truthy errors_log whose [-50:] slice is empty."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        class SliceEmptyList(list):
            def __getitem__(self, item):
                if isinstance(item, slice):
                    return []
                return super().__getitem__(item)

        sr = SelfReflectionEngine()
        sr.errors_log = SliceEmptyList([{"type": "phantom", "message": "m"}])
        assert sr.errors_log
        result = sr.reflect_on_performance()
        assert result["weaknesses"] == []
        assert result["improvements_needed"] == []

    def test_cov_reflect_repeated_error(self):
        """Arc 88 true side: repeated error type is reported."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        sr = SelfReflectionEngine()
        sr.errors_log = [
            {"type": "db_timeout", "message": "timeout 1"},
            {"type": "db_timeout", "message": "timeout 2"},
            {"type": "other", "message": "other"},
        ]
        result = sr.reflect_on_performance()
        assert any("db_timeout" in w for w in result["weaknesses"])
        assert any("db_timeout" in i for i in result["improvements_needed"])

    def test_cov_reflect_empty_logs(self):
        """Both logs empty: skips accuracy and error branches entirely."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        sr = SelfReflectionEngine()
        result = sr.reflect_on_performance()
        assert result["overall_score"] == 0
        assert "recent_improvements" not in result
