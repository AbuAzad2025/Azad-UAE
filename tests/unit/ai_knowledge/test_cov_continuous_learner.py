"""Coverage tests for ai_knowledge/learning/continuous_learner.py partial arcs.

Targets: 27-28 (urllib3 Retry fallback import), 129->158 (wikipedia
non-200), 185->203 (arxiv zero papers), 187->190 (arxiv existing query),
253->250 (daily routine arxiv failure), 343->299 (ask raises, no memory).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def learner(tmp_path):
    import importlib

    cl_mod = importlib.import_module("ai_knowledge.learning.continuous_learner")

    with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path / "learned_knowledge")):
        yield cl_mod.ContinuousLearner()


def _resp(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


class TestCovContinuousLearner:
    def test_cov_retry_fallback_import(self):
        """Lines 27-28: force the urllib3 fallback Retry import via reload."""
        import importlib
        import sys

        cl_mod = importlib.import_module("ai_knowledge.learning.continuous_learner")

        with patch.dict(sys.modules, {"urllib3.util.retry": None}):
            importlib.reload(cl_mod)
        try:
            from requests.packages.urllib3.util.retry import Retry as FallbackRetry

            assert cl_mod.Retry is FallbackRetry
        finally:
            importlib.reload(cl_mod)

    def test_cov_wikipedia_non_200(self, learner):
        """Arc 129->158: non-200 wikipedia response returns failure."""
        learner.session.get = MagicMock(return_value=_resp(status_code=404))
        result = learner.learn_from_wikipedia("محاسبة", "ar")
        assert result["success"] is False
        assert "404" in result["error"]

    def test_cov_wikipedia_success(self, learner):
        """Arc 129 true side: 200 with extract stores knowledge."""
        payload = {"extract": "content here", "content_urls": {"desktop": {"page": "https://x"}}}
        learner.session.get = MagicMock(return_value=_resp(status_code=200, json_data=payload))
        result = learner.learn_from_wikipedia("محاسبة", "ar")
        assert result["success"] is True
        assert result["content"] == "content here"

    def test_cov_arxiv_zero_papers(self, learner):
        """Arc 185->203: 200 response with no entries returns failure."""
        learner.session.get = MagicMock(return_value=_resp(status_code=200, text="<feed>no entries</feed>"))
        result = learner.learn_arxiv_papers("quantum", max_results=3)
        assert result["success"] is False

    def test_cov_arxiv_new_then_existing_query(self, learner):
        """Arc 187 both sides: new query creates list, repeat appends."""
        one = _resp(status_code=200, text="<entry>one</entry>")
        two = _resp(status_code=200, text="<entry>one</entry><entry>two</entry>")
        learner.session.get = MagicMock(side_effect=[one, two])
        first = learner.learn_arxiv_papers("ml", max_results=3)
        assert first == {"success": True, "papers": 1}
        second = learner.learn_arxiv_papers("ml", max_results=3)
        assert second == {"success": True, "papers": 2}
        assert len(learner.accumulated_knowledge["arxiv"]["ml"]) == 2

    def test_cov_daily_routine_arxiv_failure(self, learner):
        """Arc 253->250: arxiv failures loop back without counting items."""
        with (
            patch.object(learner, "learn_from_wikipedia", return_value={"success": True}),
            patch.object(learner, "learn_arxiv_papers", return_value={"success": False, "error": "down"}),
        ):
            result = learner.daily_learning_routine()
        assert result["sources_accessed"] == 5
        assert result["items_learned"] == 3
        assert result["errors"] == []

    def test_cov_evaluate_ask_raises_without_memory(self):
        """Arc 343->299: ask_genius raises while memory is None, loop continues."""
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        mock_svc = MagicMock()
        mock_svc.get_learning_system.side_effect = Exception("no learning system")
        mock_svc.ask_genius.side_effect = Exception("boom")
        tests = [
            {"question": "q1?", "expected_keywords": ["kw1"]},
            {"question": "q2?", "expected_keywords": ["kw2"]},
        ]
        results = evaluate_and_learn(tests, ai_service=mock_svc)
        assert len(results) == 2
        assert all(r["success"] is False for r in results)
        assert all(r["answer"].startswith("ERROR:") for r in results)
