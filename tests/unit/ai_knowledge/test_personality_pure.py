"""Tests for pure personality modules."""

from __future__ import annotations

from unittest.mock import patch

from ai_knowledge.personality.azad_personality import AzadPersonality, azad_personality
from ai_knowledge.personality.beginners_mode import (
    BEGINNERS_TUTORIALS,
    BeginnersGuide,
    beginners_guide,
)
from ai_knowledge.personality.dialects import (
    DialectManager,
    apply_dialect,
    dialect_manager,
    get_dialectal_greeting,
)


class TestAzadPersonality:
    def test_get_greeting(self):
        with patch("secrets.choice", return_value="مرحبا"):
            assert AzadPersonality.get_greeting()

    def test_inappropriate_detection(self):
        assert AzadPersonality.is_inappropriate_message("you are stupid") == "insult"

    def test_normal_message(self):
        assert AzadPersonality.is_inappropriate_message("كم المبيعات اليوم") == "normal"

    def test_contextual_response_insult(self):
        out = AzadPersonality.get_contextual_response("insult", "ok")
        assert isinstance(out, str)

    def test_add_personality_happy(self):
        out = AzadPersonality.add_personality_to_response("تم", "happy")
        assert "تم" in out

    def test_add_personality_default(self):
        out = AzadPersonality.add_personality_to_response("تم", "unknown")
        assert "تم" in out

    def test_singleton(self):
        assert azad_personality is not None


class TestBeginnersGuide:
    def test_get_tutorial_known(self):
        assert "فاتورة" in BeginnersGuide.get_tutorial("create_invoice")

    def test_get_tutorial_unknown(self):
        assert (
            BeginnersGuide.get_tutorial("missing") == BEGINNERS_TUTORIALS["first_time"]
        )

    def test_suggest_next_step(self):
        nxt = BeginnersGuide.suggest_next_step("first_time")
        assert isinstance(nxt, str)

    def test_suggest_invalid_step(self):
        assert "محترف" in BeginnersGuide.suggest_next_step("invalid")

    def test_beginner_invoice(self):
        assert "فاتورة" in BeginnersGuide.get_beginner_response("كيف أعمل فاتورة")

    def test_beginner_customer(self):
        assert "زبون" in BeginnersGuide.get_beginner_response("إضافة زبون")

    def test_beginner_product(self):
        assert "منتج" in BeginnersGuide.get_beginner_response("إضافة منتج")

    def test_beginner_report(self):
        assert (
            "تقرير" in BeginnersGuide.get_beginner_response("تقرير المبيعات")
            or "report" in BeginnersGuide.get_beginner_response("report").lower()
        )

    def test_beginner_default(self):
        assert (
            BeginnersGuide.get_beginner_response("مرحبا")
            == BEGINNERS_TUTORIALS["first_time"]
        )

    def test_singleton(self):
        assert beginners_guide is not None


class TestDialects:
    def test_set_dialect_valid(self):
        dm = DialectManager()
        assert dm.set_dialect("gulf") is True

    def test_set_dialect_invalid(self):
        dm = DialectManager()
        assert dm.set_dialect("invalid") is False

    def test_translate_palestinian(self):
        dm = DialectManager()
        dm.set_dialect("palestinian")
        out = dm.translate_response("كيف يمكنني مساعدتك")
        assert "كيف بقدر" in out

    def test_translate_unknown_dialect(self):
        dm = DialectManager()
        dm.current_dialect = "unknown"
        text = "hello"
        assert dm.translate_response(text) == text

    def test_get_encouragement(self):
        dm = DialectManager()
        dm.set_dialect("palestinian")
        assert isinstance(dm.get_encouragement(), str)

    def test_get_response_word(self):
        dm = DialectManager()
        dm.set_dialect("gulf")
        assert dm.get_response_word("yes") in ("إي", "أيوا")

    def test_apply_dialect_helper(self):
        assert isinstance(apply_dialect("كيف يمكنني"), str)

    def test_dialectal_greeting(self):
        with patch("secrets.choice", return_value="أهلين"):
            assert get_dialectal_greeting("palestinian") == "أهلين"

    def test_default_dialect(self):
        assert dialect_manager.current_dialect == "palestinian"
