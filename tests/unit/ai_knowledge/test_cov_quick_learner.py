"""Coverage tests for ai_knowledge/learning/quick_learner.py partial arcs.

Targets: 76->81 (no fuzzy match), 77->81 (close match not among rows),
78->77 (candidate mismatch loops back).
"""

from __future__ import annotations

from unittest.mock import patch


class TestCovQuickLearner:
    @staticmethod
    def _add_memory(db_session, tenant_id, key, value="v"):
        from models.ai import AiMemory

        mem = AiMemory(key=key, value=value, category="general", tenant_id=tenant_id, is_active=True)
        db_session.add(mem)
        db_session.flush()
        return mem

    def test_cov_get_answer_no_fuzzy_match(self, db_session, sample_tenant):
        """Arc 76->81: candidates exist but nothing is close enough."""
        from ai_knowledge.learning.quick_learner import QuickLearner

        self._add_memory(db_session, sample_tenant.id, "zzzqqq unrelated anchor", "anchored")
        result = QuickLearner().get_answer("qwerty asdfgh zxcvbn", tenant_id=sample_tenant.id)
        assert result is None

    def test_cov_get_answer_close_match_unknown_key(self, db_session, sample_tenant):
        """Arcs 78->77 and 77->81: close match names a key no row has."""
        from ai_knowledge.learning.quick_learner import QuickLearner

        self._add_memory(db_session, sample_tenant.id, "alpha bravo", "ab-value")
        self._add_memory(db_session, sample_tenant.id, "charlie delta", "cd-value")
        with patch("difflib.get_close_matches", return_value=["phantom-key"]):
            result = QuickLearner().get_answer("totally different query text", tenant_id=sample_tenant.id)
        assert result is None

    def test_cov_get_answer_fuzzy_hit(self, db_session, sample_tenant):
        """Arcs 76/77/78 true side: fuzzy match returns the stored value."""
        from ai_knowledge.learning.quick_learner import QuickLearner

        self._add_memory(db_session, sample_tenant.id, "hello world", "hi-value")
        result = QuickLearner().get_answer("helo world", tenant_id=sample_tenant.id)
        assert result == "hi-value"

    def test_cov_get_answer_no_rows(self, db_session, sample_tenant):
        """No rows at all: returns None without touching fuzzy logic."""
        from ai_knowledge.learning.quick_learner import QuickLearner

        result = QuickLearner().get_answer("anything at all", tenant_id=sample_tenant.id)
        assert result is None

    def test_global_rows_hidden_from_tenant_caller(self, db_session, sample_tenant):
        """P0: tenant-scoped callers must never see global (NULL-tenant) rows."""
        from ai_knowledge.learning.quick_learner import QuickLearner

        self._add_memory(db_session, None, "shared secret", "leaked")
        assert QuickLearner().get_answer("shared secret", tenant_id=sample_tenant.id) is None
        assert QuickLearner().get_answer("shared secret", tenant_id=None) == "leaked"

    def test_other_tenant_rows_hidden(self, db_session, sample_tenant):
        """P0: tenant A's rows are invisible to tenant B."""
        from ai_knowledge.learning.quick_learner import QuickLearner

        self._add_memory(db_session, sample_tenant.id, "tenant secret", "hidden")
        assert QuickLearner().get_answer("tenant secret", tenant_id=sample_tenant.id + 999) is None
        assert QuickLearner().get_answer("tenant secret", tenant_id=sample_tenant.id) == "hidden"

    def test_exact_match_beats_substring_order(self, db_session, sample_tenant):
        """Deterministic: exact key wins even when a longer key also contains it."""
        from ai_knowledge.learning.quick_learner import QuickLearner

        self._add_memory(db_session, sample_tenant.id, "رصيد العميل أحمد", "exact-hit")
        self._add_memory(db_session, sample_tenant.id, "رصيد العميل أحمد اليوم", "longer-hit")
        assert QuickLearner().get_answer("رصيد العميل أحمد", tenant_id=sample_tenant.id) == "exact-hit"
