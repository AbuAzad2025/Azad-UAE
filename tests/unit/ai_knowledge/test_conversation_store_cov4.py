"""Coverage for ai_knowledge/core/conversation_store.py arcs 29->36, 79->exit."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from ai_knowledge.core.conversation_store import clear_context, get_context


class TestCov4GetContextNoTimestamps:
    def test_returns_data_when_no_timestamps_recorded(self):
        """Arc 29->36: ``updated`` is falsy so the expiry check is skipped."""
        payload = {"topic": "sales", "step": 3}
        mem = MagicMock()
        mem.value = json.dumps(payload)
        mem.last_accessed = None
        mem.created_at = None
        mem.access_count = None
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = mem
        with (
            patch("ai_knowledge.core.conversation_store.AiMemory") as mock_mem,
            patch("ai_knowledge.core.conversation_store.db") as mock_db,
        ):
            mock_mem.query = mock_q
            assert get_context(4242) == payload
            assert mem.access_count == 1
            mock_db.session.flush.assert_called_once()


class TestCov4ClearContextMissing:
    def test_no_flush_when_no_record(self):
        """Arc 79->exit: ``clear_context`` with no stored row is a no-op."""
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        with (
            patch("ai_knowledge.core.conversation_store.AiMemory") as mock_mem,
            patch("ai_knowledge.core.conversation_store.db") as mock_db,
        ):
            mock_mem.query = mock_q
            clear_context(4243)
            mock_db.session.flush.assert_not_called()
