"""Coverage tests for dialects uncovered arcs 171->176 and 176->180."""

from __future__ import annotations

from ai_knowledge.personality.dialects import DialectManager


class TestCovTranslatePartialDicts:
    def test_cov_translate_missing_common_phrases(self):
        """Arc 171->176: dict without common_phrases still applies greetings."""
        dm = DialectManager()
        dm.dialects["cov_no_common"] = {"greetings": {"أهلا": "هلا"}}
        out = dm.translate_response("أهلا وسهلا", dialect="cov_no_common")
        assert "هلا" in out

    def test_cov_translate_missing_greetings(self):
        """Arc 176->180: dict without greetings still applies common_phrases."""
        dm = DialectManager()
        dm.dialects["cov_no_greet"] = {"common_phrases": {"كيف يمكنني": "كيف بقدر"}}
        out = dm.translate_response("كيف يمكنني مساعدتك", dialect="cov_no_greet")
        assert "كيف بقدر" in out

    def test_cov_translate_missing_both(self):
        """Both arcs together: dict with neither key returns text unchanged."""
        dm = DialectManager()
        dm.dialects["cov_bare"] = {}
        text = "نص بدون أي تحويل"
        assert dm.translate_response(text, dialect="cov_bare") == text

    def test_cov_translate_both_present(self):
        """Other side: normal dialect applies both sections."""
        dm = DialectManager()
        dm.dialects["cov_full"] = {
            "common_phrases": {"كيف يمكنني": "كيف بقدر"},
            "greetings": {"أهلا": "هلا"},
        }
        out = dm.translate_response("أهلا كيف يمكنني", dialect="cov_full")
        assert "هلا" in out
        assert "كيف بقدر" in out
