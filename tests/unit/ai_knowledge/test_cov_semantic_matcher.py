"""Coverage tests for semantic_matcher lazy-singleton race arc 855->857."""

from __future__ import annotations

import importlib
from unittest.mock import patch

sm_mod = importlib.import_module("ai_knowledge.neural.semantic_matcher")


class TestCovSemanticMatcherRace:
    def test_inner_check_false_skips_construction_855_857(self, monkeypatch):
        # 855->857: outer `is None` passes, but by the time the inner
        # double-checked lock runs the instance already exists, so the
        # constructor must NOT run again.
        monkeypatch.setattr(sm_mod, "_matcher_instance", None)
        sentinel = object()

        class _SeedingLock:
            def __enter__(self):
                sm_mod._matcher_instance = sentinel
                return self

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(sm_mod, "_matcher_lock", _SeedingLock())
        with patch.object(sm_mod, "SemanticMatcher") as mock_cls:
            result = sm_mod._get_matcher()
        mock_cls.assert_not_called()
        assert result is sentinel
