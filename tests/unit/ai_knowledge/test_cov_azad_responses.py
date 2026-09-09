"""Coverage tests for azad_responses uncovered arcs.

Targets:
- 164->173: intelligent assistant returned falsy (no success / no data_used)
- 240->244: beginners_mode on but beginner_response falsy or == first_time
- 1332->1329: _show_knowledge_sources topic matched but sources empty (loop continues)
- 2304->2307: _get_dtc_info unknown code (code_match truthy, not in common_codes)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_knowledge.personality.azad_responses import AzadResponses
from ai_knowledge.personality.beginners_mode import BEGINNERS_TUTORIALS


def _patch_smart_common(mock_understand=None, mock_intelligent=None):
    """Build patchers for the common smart_response preamble."""
    p1 = patch(
        "ai_knowledge.personality.azad_responses.understand_message",
        return_value=mock_understand,
    )
    p2 = patch("ai_knowledge.personality.azad_responses.intelligent_assistant")
    p3 = patch(
        "ai_knowledge.personality.azad_responses.AzadResponses._handle_detected_intent",
        return_value=None,
    )
    p4 = patch("ai_knowledge.personality.azad_responses.azad_personality")
    p5 = patch("ai_knowledge.personality.azad_responses.learning_system")
    p6 = patch("services.ai_service.AIService")
    return p1, p2, p3, p4, p5, p6


class TestCovIntelligentFalsy:
    def test_cov_intelligent_no_success_falls_through(self):
        """Arc 164->173: success False skips intelligent return, falls to generic."""
        understand = {"intent": "sales_analysis", "confidence": 0.9}
        p1, p2, p3, p4, p5, p6 = _patch_smart_common(understand, None)
        with p1, p2 as mock_ia, p3, p4 as mock_p, p5, p6 as mock_ai:
            mock_ia.process.return_value = {
                "success": False,
                "response": "SHOULD-NOT-APPEAR",
                "data_used": False,
            }
            mock_p.is_inappropriate_message.return_value = "normal"
            mock_p.get_help_intro.return_value = "intro"
            mock_ai.is_sensitive_request.return_value = (False, False, None)
            out = AzadResponses.smart_response("zzz neutral query 12345")
        assert isinstance(out, str)
        assert "SHOULD-NOT-APPEAR" not in out
        assert "أزاد" in out

    def test_cov_intelligent_no_data_falls_through(self):
        """Arc 164->173: success True but data_used falsy still falls through."""
        understand = {"intent": "inventory_check", "confidence": 0.95}
        p1, p2, p3, p4, p5, p6 = _patch_smart_common(understand, None)
        with p1, p2 as mock_ia, p3, p4 as mock_p, p5, p6 as mock_ai:
            mock_ia.process.return_value = {
                "success": True,
                "response": "SHOULD-NOT-APPEAR-2",
                "data_used": None,
            }
            mock_p.is_inappropriate_message.return_value = "normal"
            mock_p.get_help_intro.return_value = "intro"
            mock_ai.is_sensitive_request.return_value = (False, False, None)
            out = AzadResponses.smart_response("zzz neutral query 67890")
        assert isinstance(out, str)
        assert "SHOULD-NOT-APPEAR-2" not in out

    def test_cov_intelligent_exception_falls_through(self):
        """Robustness: intelligent_assistant raising still reaches line 173+."""
        understand = {"intent": "sales_analysis", "confidence": 0.9}
        p1, p2, p3, p4, p5, p6 = _patch_smart_common(understand, None)
        with p1, p2 as mock_ia, p3, p4 as mock_p, p5, p6 as mock_ai:
            mock_ia.process.side_effect = RuntimeError("boom")
            mock_p.is_inappropriate_message.return_value = "normal"
            mock_p.get_help_intro.return_value = "intro"
            mock_ai.is_sensitive_request.return_value = (False, False, None)
            out = AzadResponses.smart_response("zzz neutral query boom")
        assert isinstance(out, str)
        assert "أزاد" in out


class TestCovBeginnersFallthrough:
    def test_cov_beginners_none_falls_to_greeting_check(self):
        """Arc 240->244: beginners_mode on, beginner_response None."""
        p1 = patch(
            "ai_knowledge.personality.azad_responses.understand_message",
            return_value={"intent": None, "confidence": 0.0},
        )
        p3 = patch(
            "ai_knowledge.personality.azad_responses.AzadResponses._handle_detected_intent",
            return_value=None,
        )
        p4 = patch("ai_knowledge.personality.azad_responses.azad_personality")
        p5 = patch("ai_knowledge.personality.azad_responses.learning_system")
        p6 = patch("services.ai_service.AIService")
        p7 = patch("ai_knowledge.personality.azad_responses.beginners_guide")
        with p1, p3, p4 as mock_p, p5, p6 as mock_ai, p7 as mock_bg:
            mock_p.is_inappropriate_message.return_value = "normal"
            mock_p.get_help_intro.return_value = "intro"
            mock_ai.is_sensitive_request.return_value = (False, False, None)
            mock_bg.get_beginner_response.return_value = None
            out = AzadResponses.smart_response(
                "zzz neutral query beginners-none",
                {"beginners_mode": True, "dialect": "palestinian"},
            )
            mock_bg.get_beginner_response.assert_called_once()
        assert isinstance(out, str)
        assert "أزاد" in out

    def test_cov_beginners_first_time_falls_through(self):
        """Arc 240->244: beginner_response == first_time is filtered out."""
        p1 = patch(
            "ai_knowledge.personality.azad_responses.understand_message",
            return_value={"intent": None, "confidence": 0.0},
        )
        p3 = patch(
            "ai_knowledge.personality.azad_responses.AzadResponses._handle_detected_intent",
            return_value=None,
        )
        p4 = patch("ai_knowledge.personality.azad_responses.azad_personality")
        p5 = patch("ai_knowledge.personality.azad_responses.learning_system")
        p6 = patch("services.ai_service.AIService")
        p7 = patch("ai_knowledge.personality.azad_responses.beginners_guide")
        with p1, p3, p4 as mock_p, p5, p6 as mock_ai, p7 as mock_bg:
            mock_p.is_inappropriate_message.return_value = "normal"
            mock_p.get_help_intro.return_value = "intro"
            mock_ai.is_sensitive_request.return_value = (False, False, None)
            mock_bg.get_beginner_response.return_value = BEGINNERS_TUTORIALS["first_time"]
            out = AzadResponses.smart_response(
                "zzz neutral query beginners-first",
                {"beginners_mode": True, "dialect": "palestinian"},
            )
        assert isinstance(out, str)
        assert out != BEGINNERS_TUTORIALS["first_time"] or "أزاد" in out


class TestCovKnowledgeSources:
    def test_cov_show_sources_empty_continues_loop(self):
        """Arc 1332->1329: matched keyword but empty sources -> SOURCES_GUIDE."""
        from ai_knowledge.expansion.knowledge_sources import SOURCES_GUIDE

        with patch("ai_knowledge.personality.azad_responses.knowledge_manager") as mock_km:
            mock_km.get_sources_by_topic.return_value = []
            out = AzadResponses._show_knowledge_sources("استفسار عن ضريبة الدخل")
        assert out == SOURCES_GUIDE
        assert mock_km.get_sources_by_topic.call_count >= 1

    def test_cov_show_sources_with_results(self):
        """Other side of 1332: non-empty sources returns formatted response."""
        with patch("ai_knowledge.personality.azad_responses.knowledge_manager") as mock_km:
            mock_km.get_sources_by_topic.return_value = [
                {"name": "N1", "url": "https://example.com", "type": "article"}
            ]
            out = AzadResponses._show_knowledge_sources("استفسار عن ضريبة الدخل")
        assert "N1" in out
        assert isinstance(mock_km.get_sources_by_topic, MagicMock)


class TestCovDtcInfo:
    def test_cov_dtc_unknown_code_generic(self):
        """Arc 2304->2307: code matched but not in common_codes -> generic guide."""
        out = AzadResponses._get_dtc_info("عندي كود P9999 في السيارة")
        assert "أكواد الأعطال" in out
        assert "P0300" in out

    def test_cov_dtc_known_code_specific(self):
        """Other side of 2304: known code returns its specific entry."""
        out = AzadResponses._get_dtc_info("عندي كود P0300 في المحرك")
        assert "P0300" in out
        assert "Misfire" in out or "بواجي" in out
