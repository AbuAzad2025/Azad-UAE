"""Top-up coverage for the last remaining ai_knowledge arcs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_knowledge.agents_core import _env_mtime, _get_llm_response, ask_azad_enhanced


class TestCovAgentsCoreRemainder:
    def test_env_mtime_missing_file_123_127(self):
        with (
            patch("dotenv.find_dotenv", return_value="/tmp/does-not-exist.env"),
            patch("os.path.exists", return_value=False),
        ):
            assert _env_mtime() is None

    def test_groq_non200_falls_through_178_183(self):
        resp = MagicMock()
        resp.status_code = 500
        with (
            patch.dict(
                "os.environ",
                {"GROQ_API_KEY": "g-key", "GEMINI_API_KEY": "", "OPENAI_API_KEY": ""},
                clear=False,
            ),
            patch("requests.post", return_value=resp),
        ):
            assert _get_llm_response("sys", "hello") is None

    def test_gemini_non200_falls_through_196_206(self):
        resp = MagicMock()
        resp.status_code = 503
        with (
            patch.dict(
                "os.environ",
                {"GROQ_API_KEY": "", "GEMINI_API_KEY": "gem-key", "OPENAI_API_KEY": ""},
                clear=False,
            ),
            patch("requests.post", return_value=resp),
        ):
            assert _get_llm_response("sys", "hello") is None

    def test_llm_empty_response_falls_to_master_305_314(self):
        brain = MagicMock()
        brain.ask.return_value = {"answer": "من العقل", "confidence": 0.6}
        with (
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=[]),
            patch("ai_knowledge.agents_core._check_llm_availability", return_value=True),
            patch("ai_knowledge.agents_core._get_llm_response", return_value=""),
            patch("ai_knowledge.agents_core.get_master_brain", return_value=brain),
            patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
        ):
            result = ask_azad_enhanced("سؤال بلا إجابة معرفية xyz")
        assert result["answer"] == "من العقل"
        assert result["source"] == "master_brain"


class TestCovKnowledgeExpansionRemainder:
    def test_load_sources_non_dict_40_45(self, tmp_path, monkeypatch):
        import json

        from ai_knowledge.expansion import knowledge_expansion as ke_mod

        src = tmp_path / "knowledge_sources.json"
        src.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        # instantiate without running __init__ file discovery side effects
        inst = ke_mod.KnowledgeExpander.__new__(ke_mod.KnowledgeExpander)
        inst.sources_file = str(src)
        assert inst._load_sources() == {"books": [], "websites": [], "documents": [], "last_updated": None}


class TestCovAutoRetrainingRemainder:
    def test_should_retrain_count_threshold_line_30(self):
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        q = MagicMock()
        q.filter_by.return_value.count.return_value = 250
        with (
            patch("models.Sale.query", q),
            patch.object(
                AutoRetrainingScheduler,
                "get_last_training_info",
                return_value={"sales_count": 100, "timestamp": "2026-09-01T00:00:00"},
            ),
        ):
            assert AutoRetrainingScheduler.should_retrain() is True


class TestCovContinuousLearnerRemainder:
    def test_wiki_200_empty_extract_129_158(self):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner.__new__(ContinuousLearner)
        learner.accumulated_knowledge = {"wikipedia": {}, "total_items": 0}
        learner.learning_history = []
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"extract": ""}
        learner.session = MagicMock()
        learner.session.get.return_value = resp
        out = learner.learn_from_wikipedia("موضوع فارغ", lang="ar")
        assert out["success"] is False
        assert "Status" in out["error"] or "error" in out
