"""Coverage tests for ai_knowledge/agents_core.py uncovered lines/arcs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import ai_knowledge.agents_core as core
from ai_knowledge.agents_core import (
    _build_system_prompt,
    _env_mtime,
    _get_llm_response,
    ask_azad_enhanced,
    load_env_cached,
)


class TestCovLoadEnvCached:
    def test_load_when_mtime_differs_38_39(self):
        saved = core._env_loaded_mtime
        core._env_loaded_mtime = None
        try:
            with (
                patch("dotenv.find_dotenv", return_value="/tmp/.env"),
                patch("os.path.exists", return_value=True),
                patch("os.path.getmtime", return_value=1234.0),
                patch("dotenv.load_dotenv") as mock_load,
            ):
                load_env_cached()
            mock_load.assert_called_once_with(override=True)
            assert core._env_loaded_mtime == 1234.0
        finally:
            core._env_loaded_mtime = saved

    def test_load_exception_path_40_41(self):
        saved = core._env_loaded_mtime
        try:
            with patch("dotenv.find_dotenv", side_effect=RuntimeError("boom")):
                load_env_cached()
        finally:
            core._env_loaded_mtime = saved


class TestCovEnvMtime:
    def test_env_mtime_exception_124_126(self):
        with patch("os.path.exists", side_effect=RuntimeError("boom")):
            assert _env_mtime() is None

    def test_env_mtime_find_dotenv_exception(self):
        with patch("dotenv.find_dotenv", side_effect=RuntimeError("boom")):
            assert _env_mtime() is None


class TestCovGetLlmResponse:
    def test_groq_exception_falls_to_none_184_206(self):
        with (
            patch.dict(
                "os.environ",
                {"GROQ_API_KEY": "g-key", "GEMINI_API_KEY": "", "OPENAI_API_KEY": ""},
                clear=False,
            ),
            patch("requests.post", side_effect=RuntimeError("net down")),
        ):
            assert _get_llm_response("sys", "hello") is None

    def test_gemini_empty_parts_201_206(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"candidates": [{"content": {"parts": []}}]}
        with (
            patch.dict(
                "os.environ",
                {"GROQ_API_KEY": "", "GEMINI_API_KEY": "gem-key", "OPENAI_API_KEY": ""},
                clear=False,
            ),
            patch("requests.post", return_value=mock_resp),
        ):
            assert _get_llm_response("sys", "hello") is None


class TestCovBuildSystemPrompt:
    def test_unknown_result_type_223_218(self):
        with patch(
            "ai_knowledge.system_knowledge.search_knowledge",
            return_value=[{"type": "mystery", "name": "X", "info": {}}],
        ):
            prompt = _build_system_prompt("سؤال عام", "user")
        assert "أزاد" in prompt


class TestCovAskAzadEnhanced:
    def test_unknown_knowledge_type_292_280(self):
        brain = MagicMock()
        brain.ask.return_value = {"answer": "من العقل", "confidence": 0.8}
        with (
            patch("ai_knowledge.system_knowledge.FAQ", {}),
            patch(
                "ai_knowledge.system_knowledge.search_knowledge",
                return_value=[{"type": "weird", "code": "X"}],
            ),
            patch("ai_knowledge.agents_core._check_llm_availability", return_value=False),
            patch("ai_knowledge.agents_core.get_master_brain", return_value=brain),
            patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
        ):
            result = ask_azad_enhanced("سؤال غريب جدا xyz")
        assert result["answer"] == "من العقل"
        assert result["source"] == "master_brain"
