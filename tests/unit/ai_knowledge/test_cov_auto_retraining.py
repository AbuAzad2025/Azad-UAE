"""Coverage tests for ai_knowledge/learning/auto_retraining.py partial arcs.

Target: 63->exit (empty training history list returns None).
"""

from __future__ import annotations

import json
from unittest.mock import patch


class TestCovAutoRetraining:
    def test_cov_last_training_empty_history(self, tmp_path):
        """Arc 63->exit: history file contains [] so nothing is returned."""
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        log = tmp_path / "training_history.json"
        log.write_text(json.dumps([]), encoding="utf-8")
        with patch.object(AutoRetrainingScheduler, "TRAINING_LOG_FILE", str(log)):
            assert AutoRetrainingScheduler.get_last_training_info() is None

    def test_cov_last_training_with_entry(self, tmp_path):
        """Arc 63 true side: history file with an entry returns the last one."""
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        log = tmp_path / "training_history.json"
        entries = [
            {"timestamp": "2024-01-01T00:00:00", "sales_count": 100, "results": {}},
            {"timestamp": "2024-02-01T00:00:00", "sales_count": 250, "results": {"success": True}},
        ]
        log.write_text(json.dumps(entries), encoding="utf-8")
        with patch.object(AutoRetrainingScheduler, "TRAINING_LOG_FILE", str(log)):
            last = AutoRetrainingScheduler.get_last_training_info()
        assert last is not None
        assert last["sales_count"] == 250

    def test_cov_last_training_missing_file(self, tmp_path):
        """File does not exist: returns None without error."""
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        missing = tmp_path / "does_not_exist.json"
        with patch.object(AutoRetrainingScheduler, "TRAINING_LOG_FILE", str(missing)):
            assert AutoRetrainingScheduler.get_last_training_info() is None
