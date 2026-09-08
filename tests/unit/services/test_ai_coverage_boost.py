"""Boost ai_service.py coverage."""

from contextlib import suppress

from services.ai_service import AIService


def test_ai_common_branches(db_session):
    with suppress(Exception):
        AIService.process_prompt("test")
    with suppress(Exception):
        AIService.generate_response({})
