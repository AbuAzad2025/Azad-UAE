"""Coverage tests for ai_knowledge/learning/external_learning.py partial arcs.

Target: 412->411 (non-dict source entry skipped in sources list).
"""

from __future__ import annotations


class TestCovExternalLearning:
    def test_cov_sources_list_skips_non_dict(self):
        """Arc 412->411: non-dict entries are skipped, dicts are listed."""
        from ai_knowledge.learning.external_learning import ExternalLearningSystem

        el = ExternalLearningSystem()
        el.learning_sources["bogus_category"] = {
            "weird_entry": "just-a-string",
            "ok_entry": {"name": "Ok Source", "url": "https://example.com"},
        }
        sources = el.get_knowledge_sources_list()
        names = [s["name"] for s in sources if s["category"] == "bogus_category"]
        assert names == ["ok_entry"]
        assert len(sources) > 1

    def test_cov_sources_list_defaults(self):
        """Sanity: real catalog entries resolve description/url defaults."""
        from ai_knowledge.learning.external_learning import ExternalLearningSystem

        el = ExternalLearningSystem()
        sources = el.get_knowledge_sources_list()
        by_name = {s["name"]: s for s in sources}
        assert by_name["wikipedia"]["auto_learning"] is True
        assert by_name["wikipedia"]["url"] == "https://ar.wikipedia.org"
