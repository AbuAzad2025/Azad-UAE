"""Unit tests for services/ai_training_service.py — tenant-scoped memory ops."""

from __future__ import annotations

import pytest

from services import ai_training_service as svc


def _add(db_session, tenant_id, key, value="v", category="general", active=True):
    from models.ai import AiMemory

    mem = AiMemory(
        key=key,
        value=value,
        category=category,
        tenant_id=tenant_id,
        confidence=1.0,
        source="quick_learner",
        is_active=active,
    )
    db_session.add(mem)
    db_session.flush()
    return mem


class TestListMemories:
    def test_strict_tenant_scope(self, db_session, sample_tenant):
        _add(db_session, sample_tenant.id, "local q", "local a")
        rows = svc.list_memories(sample_tenant.id)
        assert [r["key"] for r in rows] == ["local q"]

    def test_other_tenant_rows_hidden(self, db_session, sample_tenant):
        from tests.factories import TenantFactory

        other = TenantFactory()
        db_session.flush()
        _add(db_session, other.id, "foreign q", "foreign a")
        assert svc.list_memories(sample_tenant.id) == []
        assert len(svc.list_memories(other.id)) == 1

    def test_search_and_category(self, db_session, sample_tenant):
        _add(db_session, sample_tenant.id, "vat rate?", "5%", category="learned")
        _add(db_session, sample_tenant.id, "hello", "hi", category="general")
        assert len(svc.list_memories(sample_tenant.id, search="vat")) == 1
        assert len(svc.list_memories(sample_tenant.id, category="general")) == 1
        assert {r["key"] for r in svc.list_memories(sample_tenant.id, category="bogus")} == {
            "vat rate?",
            "hello",
        }

    def test_inactive_hidden_by_default(self, db_session, sample_tenant):
        _add(db_session, sample_tenant.id, "old q", "old a", active=False)
        assert svc.list_memories(sample_tenant.id) == []
        assert len(svc.list_memories(sample_tenant.id, include_inactive=True)) == 1


class TestAddQa:
    def test_create_and_refresh(self, db_session, sample_tenant):
        first = svc.add_qa("How?", "Because.", "general", sample_tenant.id)
        assert first["value"] == "Because."
        second = svc.add_qa("how?", "Updated.", "learned", sample_tenant.id)
        assert second["id"] == first["id"]
        assert second["value"] == "Updated."

    def test_rejects_empty(self, db_session, sample_tenant):
        with pytest.raises(ValueError):
            svc.add_qa("", "answer", "general", sample_tenant.id)
        with pytest.raises(ValueError):
            svc.add_qa("question", "", "general", sample_tenant.id)

    def test_system_category_normalized(self, db_session, sample_tenant):
        row = svc.add_qa("q", "a", "system", sample_tenant.id)
        assert row["category"] == "general"


class TestToggleMemory:
    def test_toggle_roundtrip(self, db_session, sample_tenant):
        mem = _add(db_session, sample_tenant.id, "q", "a")
        assert svc.toggle_memory(mem.id, sample_tenant.id, False)["is_active"] is False
        assert svc.toggle_memory(mem.id, sample_tenant.id, True)["is_active"] is True

    def test_cross_tenant_toggle_404(self, db_session, sample_tenant):
        from werkzeug.exceptions import NotFound

        mem = _add(db_session, sample_tenant.id, "q", "a")
        with pytest.raises(NotFound):
            svc.toggle_memory(mem.id, sample_tenant.id + 999, False)

    def test_missing_memory_404(self, db_session, sample_tenant):
        from werkzeug.exceptions import NotFound

        with pytest.raises(NotFound):
            svc.toggle_memory(999999999, sample_tenant.id, False)


class TestSubmitCorrection:
    def test_correction_learned(self, db_session, sample_tenant):
        result = svc.submit_correction("What?", "Right.", sample_tenant.id, user_id=1)
        assert result == {"question": "What?", "corrected": True}

    def test_rejects_empty(self, db_session, sample_tenant):
        with pytest.raises(ValueError):
            svc.submit_correction("", "a", sample_tenant.id, user_id=1)
