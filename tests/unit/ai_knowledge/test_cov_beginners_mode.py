"""Coverage tests for beginners_mode uncovered arc 224->228."""

from __future__ import annotations

from ai_knowledge.personality.beginners_mode import (
    BEGINNERS_TUTORIALS,
    BeginnersGuide,
)


class TestCovSuggestNextStep:
    def test_cov_suggest_last_step_returns_pro(self):
        """Arc 224->228: last step has no next -> professional message."""
        out = BeginnersGuide.suggest_next_step("create_report")
        assert out == "🎉 أحسنت! أصبحت محترفاً! الآن جرب باقي المميزات!"

    def test_cov_suggest_middle_step_returns_next(self):
        """Other side of 224: middle step returns the next tutorial."""
        out = BeginnersGuide.suggest_next_step("create_invoice")
        assert out == BEGINNERS_TUTORIALS["add_customer"]

    def test_cov_suggest_first_step_returns_next(self):
        """First step also takes the 224-true branch deterministically."""
        out = BeginnersGuide.suggest_next_step("first_time")
        assert out == BEGINNERS_TUTORIALS["create_invoice"]
