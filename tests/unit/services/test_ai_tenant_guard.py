"""Fail-closed tenant guard tests for the AI subsystem (S1/S3 hardening).

Verifies that:
- ``_collect_real_data`` never queries cross-tenant data when no valid
  tenant context exists (returns ``{}`` instead).
- ``intelligent_assistant.process`` without a tenant reports zero context
  records (``data_used`` falsy).
- ``learning_system`` persistence is strictly tenant-scoped — no tenant
  means no writes to shared/global JSON logs.
"""

from __future__ import annotations

import os


from ai_knowledge.agents.intelligent_assistant import intelligent_assistant
from ai_knowledge.core.learning_system import learning_system


class TestCollectRealDataFailClosed:
    def test_no_request_context_returns_empty(self, app):
        """Outside any request context there is no tenant -> empty data."""
        with app.app_context():
            data = intelligent_assistant._collect_real_data("sales_analysis", {}, None)
        assert data == {}

    def test_unresolved_tenant_returns_empty(self, app, mocker):
        """Tenant resolution failure must NOT fall back to global queries."""
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        with app.test_request_context("/"):
            data = intelligent_assistant._collect_real_data("sales_analysis", {}, None)
        assert data == {}

    def test_no_db_queries_when_fail_closed(self, app, mocker):
        """The guard must trigger BEFORE any database session use."""
        spy = mocker.patch("extensions.db.session")
        with app.app_context():
            data = intelligent_assistant._collect_real_data("inventory_check", {}, None)
        assert data == {}
        spy.query.assert_not_called()


class TestProcessWithoutTenant:
    def test_process_reports_zero_context_records(self, app):
        with app.app_context():
            result = intelligent_assistant.process("كم عدد العملاء؟", 1, {})
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert not result.get("data_used"), "process() leaked data without a tenant context"


class TestLearningPersistenceTenantScoped:
    def test_no_tenant_no_shared_log_write(self, app, tmp_path):
        """learn_from_interaction without tenant_id must not touch shared files."""
        shared_log = learning_system.interactions_file
        before = os.path.getmtime(shared_log) if os.path.exists(shared_log) else None

        with app.app_context():
            learning_system.learn_from_interaction(
                "سؤال اختباري للعزل",
                "رد اختباري",
                tenant_id=None,
            )

        after = os.path.getmtime(shared_log) if os.path.exists(shared_log) else None
        assert after == before, "shared interactions_log.json was written without tenant context"

    def test_shared_save_data_is_noop(self, app, tmp_path, monkeypatch):
        """_save_data (legacy shared persistence) is a deprecated no-op."""
        writes = []
        real_open = open

        def spy_open(file, *args, **kwargs):
            if kwargs.get("mode") == "w" or (len(args) > 0 and "w" in str(args[0])):
                writes.append(str(file))
            return real_open(file, *args, **kwargs)

        monkeypatch.setattr("builtins.open", spy_open)
        with app.app_context():
            learning_system._save_data()
        assert writes == [], f"_save_data wrote files: {writes}"
