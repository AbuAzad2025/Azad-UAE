"""Coverage for remaining memory_system lines/arcs.

Targets (do not modify sources):
- line 275: _build_index skips non-string episodic message
- line 284: _build_index skips non-string semantic fact
- arc 175->182: remember_user_preference for an existing user
- arc 246->240: recall_fact loop-back on non-matching fact
- arc 277->276: _build_index loop-back on short (<=3) words
- arc 337->341: forget_old_memories with zero deletions
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ai_knowledge.core.memory_system import LongTermMemory


@pytest.fixture
def mem(tmp_path, monkeypatch):
    import ai_knowledge

    monkeypatch.setattr(ai_knowledge, "get_knowledge_path", lambda *args, **kwargs: str(tmp_path))
    instance = LongTermMemory()
    instance._save_memory = MagicMock(return_value=True)
    return instance


class TestCovBuildIndexEpisodic:
    def test_non_string_message_skipped_line275_short_word_loops_arc277_276(self, mem):
        mem.episodic_memory = {
            "memories": [
                {"user_message": None},
                {"user_message": "hi ok abcdefgh"},
            ]
        }
        mem.semantic_memory = {"memories": []}
        mem.memory_index = defaultdict(list)
        mem._build_index()
        assert ("episodic", 1) in mem.memory_index["abcdefgh"]
        assert "hi" not in mem.memory_index
        assert "ok" not in mem.memory_index


class TestCovBuildIndexSemantic:
    def test_non_string_fact_skipped_line284(self, mem):
        mem.episodic_memory = {"memories": []}
        mem.semantic_memory = {
            "memories": [
                {"fact": 12345},
                {"fact": "quarterly tax report filed"},
            ]
        }
        mem.memory_index = defaultdict(list)
        mem._build_index()
        assert ("semantic", 1) in mem.memory_index["quarterly"]
        assert ("semantic", 1) in mem.memory_index["report"]


class TestCovRememberPreference:
    def test_existing_user_skips_creation_arc175_182(self, mem):
        mem.user_preferences = {
            "u1": {"user_id": "u1", "preferences": {}, "created": "2024-01-01T00:00:00"},
        }
        mem.remember_user_preference("u1", "lang", "ar")
        assert mem.user_preferences["u1"]["preferences"]["lang"] == "ar"
        assert "updated" in mem.user_preferences["u1"]
        mem._save_memory.assert_called_once_with("preferences", mem.user_preferences)


class TestCovRecallFact:
    def test_non_matching_fact_continues_loop_arc246_240(self, mem):
        mem.semantic_memory = {
            "memories": [
                {"fact": "VAT in UAE is five percent", "category": "tax"},
                {"fact": "unrelated zebra quantum", "category": "misc"},
            ]
        }
        results = mem.recall_fact("VAT")
        assert len(results) == 1
        assert results[0]["category"] == "tax"


class TestCovForgetOldMemories:
    def test_no_deletions_skips_save_arc337_341(self, mem):
        mem.episodic_memory = {
            "memories": [{"timestamp": datetime.now().isoformat(), "user_id": "u1"}],
        }
        mem._save_memory.reset_mock()
        result = mem.forget_old_memories(days=365)
        assert result == {"deleted": 0, "remaining": 1}
        mem._save_memory.assert_not_called()
