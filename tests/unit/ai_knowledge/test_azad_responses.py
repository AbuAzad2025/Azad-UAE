"""Tests for azad_responses smart routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_knowledge.personality.azad_responses import AzadResponses, azad_responses


class TestAzadResponses:
    @pytest.fixture
    def responses(self):
        return AzadResponses()

    def test_who_are_you(self, responses):
        assert "أزاد" in responses.smart_response("من أنت")

    def test_inappropriate_blocked(self, responses):
        with patch("ai_knowledge.personality.azad_responses.azad_personality") as mock_p:
            mock_p.is_inappropriate_message.return_value = "insult"
            mock_p.get_contextual_response.return_value = "رد محترم"
            assert responses.smart_response("stupid") == "رد محترم"

    def test_ai_status_no_key(self, responses):
        with patch("services.ai_service.AIService") as MockAI:
            MockAI.get_api_key.return_value = None
            MockAI.get_provider.return_value = "groq"
            assert isinstance(responses.smart_response("حالة الذكاء الاصطناعي"), str)

    def test_vat_keyword(self, responses):
        assert isinstance(responses.smart_response("ما هي ضريبة VAT"), str)

    def test_error_response(self, responses):
        assert isinstance(responses.get_error_response(), str)

    def test_singleton(self):
        assert azad_responses is not None
